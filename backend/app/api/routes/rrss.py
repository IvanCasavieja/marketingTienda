"""Rutas /rrss — Validación de redes sociales con CatTi.

El flujo es de a pasos, no una sola request: se sube el mailing (se lee una
vez), después las placas de a una y al final se cierra el lote. Una sola
request con 30 placas de 2250 px pesaría decenas de MB y tardaría minutos;
de a una el usuario ve avanzar cada placa a medida que se valida, y un
archivo roto no tira abajo al resto. Ver app/services/rrss/.
"""
import io
import json
import logging
import re
import time

import anthropic
from PIL import Image
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.rate_limit import limiter
from app.core.uploads import read_limited
from app.models.rrss_validacion import RrssValidacion, RrssValidacionImagen, RrssValidacionPagina
from app.models.user import User
from app.services.ai_usage_service import log_ai_usage
from app.services.rrss import archivos, catti, comparador, correccion, excel, imagenes, planilla, validador
from app.services.rrss.hilos import en_hilo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rrss", tags=["rrss"])

_MAX_IMAGENES_POR_VALIDACION = 150
# Ni los tipos de archivo ni los tamaños máximos se escriben acá: viven en
# app/data/rrss_archivos.json y los lee tanto este módulo como la pantalla
# (GET /rrss/config). Ver archivos.py.


async def _get_validacion_or_404(db: AsyncSession, validacion_id: int) -> RrssValidacion:
    v = await db.get(RrssValidacion, validacion_id)
    if v is None:
        raise HTTPException(status_code=404, detail="No se encontró esa validación")
    return v


def _exigir_dueno(v: RrssValidacion, user: User) -> None:
    """Cualquiera con rrss.view puede MIRAR una validación (el historial es del
    equipo), pero solo quien la creó -o un superusuario- puede modificarla o
    borrarla."""
    if not user.is_superuser and v.creado_por_id != user.id:
        raise HTTPException(status_code=403, detail="Solo quien creó la validación puede modificarla")


def _imagen_a_dict(i: RrssValidacionImagen) -> dict:
    return {
        "id": i.id, "orden": i.orden, "nombre_archivo": i.nombre_archivo,
        "ancho": i.ancho, "alto": i.alto, "formato": i.formato, "estado": i.estado,
        **i.resultado,
        "vista": imagenes.data_uri(i.vista) if i.vista else None,
    }


async def _paginas(db: AsyncSession, validacion_id: int) -> list[RrssValidacionPagina]:
    res = await db.execute(
        select(RrssValidacionPagina).where(RrssValidacionPagina.validacion_id == validacion_id)
        .order_by(RrssValidacionPagina.numero)
    )
    return list(res.scalars())


async def _detalle(db: AsyncSession, v: RrssValidacion) -> dict:
    res = await db.execute(
        select(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
        .order_by(RrssValidacionImagen.orden, RrssValidacionImagen.id)
    )
    autor = await db.get(User, v.creado_por_id) if v.creado_por_id else None
    return {
        "id": v.id, "nombre_mailing": v.nombre_mailing, "estado": v.estado,
        "config": v.config, "mailing": v.mailing, "resumen": v.resumen,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "usuario": autor.full_name if autor else None,
        "paginas": [
            {"numero": p.numero, "ancho": p.ancho, "alto": p.alto, "imagen": imagenes.data_uri(p.imagen)}
            for p in await _paginas(db, v.id)
        ],
        "imagenes": [_imagen_a_dict(i) for i in res.scalars()],
    }


@router.get("/config")
async def get_config(_: User = Depends(require_permission("rrss.view"))):
    """Lo que se exige por defecto en cada placa, y qué archivos se aceptan.

    Los tipos van en la misma respuesta que ya se pedía al abrir la pantalla:
    así el `accept` de los inputs y los textos de ayuda salen del MISMO archivo
    que usa el backend para aceptar o rechazar, y no de una lista escrita a mano
    en el navegador (ver app/data/rrss_archivos.json)."""
    tipos = json.loads(json.dumps(archivos.TIPOS))  # copia: no se toca el dict compartido
    # Qué datos busca CatTi en la planilla. Ya no son nombres de columna que
    # haya que respetar: desde el 22/09/2026 la planilla puede venir de
    # cualquier forma y qué columna es cada dato lo decide CatTi (ver
    # planilla.CAMPOS_DE_LA_PLANILLA). La pantalla dice QUÉ busca, no cómo
    # tiene que llamarse.
    tipos["fuentes"]["planilla"]["columnas"] = planilla.DATOS_QUE_BUSCA
    return {**validador.CONFIG_DEFECTO, "tipos": tipos}


@router.post("/validaciones")
@limiter.limit("10/minute")
async def crear_validacion(
    request: Request,
    mailing: UploadFile = File(...),
    legal_bases: str | None = Form(None),
    legal_alcohol: str = Form(""),
    fecha: str = Form(""),
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    """Sube la fuente contra la que se validan las placas y abre la validación.

    Son dos caminos, y el archivo decide cuál (ver services/rrss/archivos.py):
    - un MAILING (PDF o imagen): se renderiza, CatTi lo lee y ubica cada
      producto. Tarda medio minuto y gasta tokens.
    - una PLANILLA (.xlsx/.csv): CatTi mira la planilla UNA vez para decidir
      qué es cada columna (puede venir de cualquier forma), y los valores se
      leen de las celdas tal cual. Unos segundos y unos pocos miles de tokens.
      Es lo que pidió Ivan para las campañas que no tienen mailing físico.
    Los dos dejan el MISMO dict en `mailing`, que es contra lo que se comparan
    las placas después."""
    nombre_archivo = mailing.filename or ""
    origen = archivos.origen_de(nombre_archivo, mailing.content_type or "")
    # El tope global de subida (50 MB) se nombra como lo que se subió: "El
    # mailing supera el límite" para alguien que subió una planilla lo manda a
    # buscar un archivo que no existe. El nombre sale del mismo lugar que usan
    # la pantalla y el Excel para nombrar la fuente (correccion), y no de un
    # texto escrito acá.
    datos = await read_limited(mailing, correccion.nombre_de_la_fuente(origen).capitalize())
    # Lo que no es ni mailing ni planilla se rechaza NOMBRANDO los dos, en vez
    # de mandarlo al camino del mailing para que reviente con "No pude abrir el
    # archivo como imagen" -- un mensaje sobre imágenes, para un Word. El
    # `%PDF-` es el olfateo por bytes que ya estaba: un PDF con un content_type
    # raro y sin extensión sigue entrando, como entraba antes.
    if not archivos.acepta_fuente(nombre_archivo, mailing.content_type or "") \
            and not datos.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{nombre_archivo}' no se puede usar como fuente: tiene que ser el mailing "
                f"({archivos.etiqueta_fuente('mailing')}) o la planilla de la campaña "
                f"({archivos.etiqueta_fuente('planilla')})"
            ),
        )
    # El tope es distinto según el camino, y el de la planilla es chico a
    # propósito: un catálogo de 17 MB congelaba el único hilo de CPU del
    # servicio dos minutos y medio antes de rechazarlo. Acá se rechaza sin
    # abrir el archivo. Ver app/data/rrss_archivos.json.
    if len(datos) > archivos.max_bytes(origen):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El archivo pesa {len(datos) // (1024 * 1024)} MB y el máximo para una "
                f"{'planilla' if origen == 'planilla' else 'fuente de este tipo'} es "
                f"{archivos.max_mb(origen)} MB."
                + (" Subí el listado de esta campaña, no el catálogo entero." if origen == "planilla" else "")
            ),
        )
    config = {
        "legal_bases": (validador.CONFIG_DEFECTO["legal_bases"] if legal_bases is None else legal_bases).strip()[:300],
        "legal_alcohol": legal_alcohol.strip()[:300],
        "fecha": fecha.strip()[:300],
    }

    try:
        if origen == "planilla":
            # Sin elegir hoja: la primera, que es lo que hace el Convertidor
            # desde siempre. Cuál se leyó queda guardado y se muestra en
            # pantalla, así que si fuera la equivocada se ve, no se descubre
            # después. Elegirla hace falta el día que una planilla de RRSS venga
            # con varias hojas de verdad; hoy no pasó.
            preparado = await validador.preparar_planilla(datos, mailing.filename or "")
        else:
            preparado = await validador.preparar_mailing(datos, mailing.content_type or "", mailing.filename or "")
    except planilla.PlanillaInvalida as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except imagenes.ArchivoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except catti.LecturaFallida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except anthropic.APIError as exc:
        logger.error("rrss: error de la API leyendo el mailing — %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail="No pude leer el mailing en este momento")
    except Exception as exc:
        # Cualquier otra cosa que salga de leer el archivo es un bug nuestro, no
        # una culpa de quien subió: un ValueError pelado de PIL por un salto de
        # línea adentro de una celda salía como un HTTP 500 sin ninguna pista
        # (ver planilla.py). Queda el stack en el log y la persona ve un motivo.
        logger.error("rrss: error leyendo la fuente %s — %s", nombre_archivo, exc, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=(
                "No pude leer este archivo. Si es una planilla, fijate que tenga una fila "
                "de encabezados con una columna DESCRIPCION y una de precio."
            ),
        )

    v = RrssValidacion(
        nombre_mailing=(mailing.filename or "mailing")[:255], estado="en_proceso",
        config=config, mailing=preparado.mailing, creado_por_id=current_user.id,
    )
    db.add(v)
    await db.flush()
    # Las carillas ya viven en JPEG (imagenes.Carillas): se guardan tal cual, sin
    # abrirlas de nuevo ni volver a comprimirlas.
    for numero, (jpg, (ancho, alto)) in enumerate(
            zip(preparado.paginas.jpegs, preparado.paginas.tamanos)):
        db.add(RrssValidacionPagina(
            validacion_id=v.id, numero=numero, ancho=ancho, alto=alto, imagen=jpg,
        ))
    # Con una planilla no se llamó a la IA: loguear cero consumo ensuciaría el
    # informe con llamadas que no existieron.
    if preparado.tokens_in or preparado.tokens_out:
        await log_ai_usage(
            db, current_user.id, catti.FEATURE, catti.PROVEEDOR, catti._MODEL,
            preparado.tokens_in, preparado.tokens_out,
        )
    await db.commit()
    await db.refresh(v)
    return await _detalle(db, v)


@router.post("/validaciones/{validacion_id}/imagenes")
@limiter.limit("240/minute")
async def validar_imagen(
    request: Request,
    validacion_id: int,
    archivo: UploadFile = File(...),
    orden: int = Form(0),
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    """Valida UNA placa contra el mailing de esta validación."""
    inicio = time.perf_counter()
    v = await _get_validacion_or_404(db, validacion_id)
    _exigir_dueno(v, current_user)
    if v.estado != "en_proceso":
        raise HTTPException(status_code=400, detail="Esta validación ya está cerrada")

    total = await db.scalar(
        select(func.count()).select_from(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
    )
    if (total or 0) >= _MAX_IMAGENES_POR_VALIDACION:
        raise HTTPException(status_code=400, detail=f"Máximo {_MAX_IMAGENES_POR_VALIDACION} placas por validación")
    if not archivos.acepta_placa(archivo.filename or "", archivo.content_type or ""):
        raise HTTPException(
            status_code=400,
            detail=f"'{archivo.filename}' no es una imagen {archivos.etiqueta_placas()}",
        )
    datos = await read_limited(archivo, "La placa")
    if len(datos) > archivos.max_bytes("placas"):
        raise HTTPException(
            status_code=400,
            detail=f"'{archivo.filename}' supera los {archivos.max_mb('placas')} MB",
        )

    async def cargar_paginas():
        # Las páginas del mailing (ya renderizadas) sirven para recortar el lado del
        # mailing de cada diferencia: solo se traen si la placa tiene alguna.
        # Se entregan en JPEG y se abre solo la que se recorta: decodificar las
        # cuatro enteras por placa, con tres placas a la vez, tiraba el servidor
        # (ver imagenes.Carillas.desde_jpegs).
        paginas_db = await _paginas(db, v.id)
        return imagenes.Carillas.desde_jpegs(
            [p.imagen for p in paginas_db], [(p.ancho, p.alto) for p in paginas_db])

    r = await validador.validar_placa(datos, archivo.filename or "placa", v.mailing, cargar_paginas, v.config)
    r.resultado["tiempos_ms"]["hasta_guardar"] = round((time.perf_counter() - inicio) * 1000)

    # Idempotente por `orden`: si el navegador reintenta una placa (la request se
    # cortó pero el servidor sí la había guardado) o la persona reintenta las que
    # fallaron, la nueva REEMPLAZA a la anterior en vez de duplicarla.
    await db.execute(delete(RrssValidacionImagen).where(
        RrssValidacionImagen.validacion_id == v.id, RrssValidacionImagen.orden == orden,
    ))
    fila = RrssValidacionImagen(
        validacion_id=v.id, orden=orden, nombre_archivo=(archivo.filename or "placa")[:255],
        ancho=r.ancho, alto=r.alto, formato=r.formato, estado=r.estado,
        resultado=r.resultado, vista=r.vista,
    )
    db.add(fila)
    if r.tokens_in or r.tokens_out:
        await log_ai_usage(db, current_user.id, catti.FEATURE, catti.PROVEEDOR, catti._MODEL, r.tokens_in, r.tokens_out)
    await db.flush()  # asigna el id; no hace falta releer la fila (incluye la vista y todo el resultado)
    respuesta = _imagen_a_dict(fila)
    await db.commit()
    return respuesta


@router.post("/validaciones/{validacion_id}/cerrar")
async def cerrar_validacion(
    validacion_id: int,
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    """Termina el lote: agrupa las adaptaciones de cada producto y revisa lo
    que solo se ve mirando el conjunto (formatos que faltan, CTA mezclados)."""
    v = await _get_validacion_or_404(db, validacion_id)
    _exigir_dueno(v, current_user)
    res = await db.execute(
        select(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
        .order_by(RrssValidacionImagen.orden, RrssValidacionImagen.id)
    )
    filas = list(res.scalars())
    leidas = [
        {
            "id": i.id, "nombre_archivo": i.nombre_archivo, "formato": i.formato,
            "match_indice": (i.resultado.get("match") or {}).get("indice"),
            "lectura": i.resultado["lectura"],
        }
        for i in filas if i.estado != "error" and i.resultado.get("lectura")
    ]
    chequeos = comparador.chequeos_del_lote(leidas, v.mailing["productos"])
    v.resumen = validador.resumir_lote([i.estado for i in filas], chequeos)
    v.estado = "completada"
    await db.commit()
    return {"resumen": v.resumen}


@router.get("/validaciones")
async def listar_validaciones(
    _: User = Depends(require_permission("rrss.view")),
    db: AsyncSession = Depends(get_db),
):
    """El historial: una fila por validación, con sus contadores."""
    I = RrssValidacionImagen
    res = await db.execute(
        select(
            RrssValidacion.id, RrssValidacion.nombre_mailing, RrssValidacion.estado, RrssValidacion.created_at,
            User.full_name,
            func.count(I.id),
            func.count(I.id).filter(I.estado == "ok"),
            func.count(I.id).filter(I.estado.in_(("diferencias", "avisos"))),
            func.count(I.id).filter(I.estado == "sin_match"),
            func.count(I.id).filter(I.estado == "error"),
        )
        .outerjoin(I, I.validacion_id == RrssValidacion.id)
        .outerjoin(User, User.id == RrssValidacion.creado_por_id)
        .group_by(RrssValidacion.id, User.full_name)
        .order_by(RrssValidacion.created_at.desc())
        .limit(200)
    )
    return [
        {
            "id": r[0], "nombre_mailing": r[1], "estado": r[2],
            "created_at": r[3].isoformat() if r[3] else None, "usuario": r[4],
            "total": r[5], "ok": r[6], "con_diferencias": r[7], "sin_match": r[8], "error": r[9],
        }
        for r in res.all()
    ]


@router.get("/validaciones/{validacion_id}")
async def get_validacion(
    validacion_id: int,
    _: User = Depends(require_permission("rrss.view")),
    db: AsyncSession = Depends(get_db),
):
    return await _detalle(db, await _get_validacion_or_404(db, validacion_id))


def _nombre_para_descarga(texto: str) -> str:
    """Un nombre usable dentro del header Content-Disposition: sin comillas ni
    caracteres de control (cerrarían el filename="..." o inyectarían un header)
    y solo latin-1, que es como Starlette codifica los headers -- un carácter
    fuera de ese rango revienta con UnicodeEncodeError DESPUÉS de armar el Excel.
    Mismo criterio que cenefas_convertidor._nombre_para_descarga."""
    limpio = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', "", texto or "")
    limpio = limpio.encode("latin-1", "ignore").decode("latin-1")
    return re.sub(r"\s+", " ", limpio).strip().rstrip(". ")[:120] or "placas"


@router.get("/validaciones/{validacion_id}/excel")
@limiter.limit("6/minute")
async def descargar_excel(
    request: Request,
    validacion_id: int,
    _: User = Depends(require_permission("rrss.view")),
    db: AsyncSession = Depends(get_db),
):
    """El Excel de correcciones para el diseñador: solo las placas con algo para
    corregir, con la placa, el mailing y qué hacer (ver rrss/excel.py)."""
    v = await _get_validacion_or_404(db, validacion_id)
    res = await db.execute(
        select(RrssValidacionImagen).where(RrssValidacionImagen.validacion_id == v.id)
        .order_by(RrssValidacionImagen.orden, RrssValidacionImagen.id)
    )
    datos = {
        "mailing": v.mailing,
        "imagenes": [
            {
                "nombre_archivo": i.nombre_archivo, "formato": i.formato, "estado": i.estado, "orden": i.orden,
                **i.resultado, "vista": i.vista,
            }
            for i in res.scalars()
        ],
    }
    try:
        # decodifica y arma imágenes: CPU puro, va a un hilo (ver hilos.py)
        xlsx = await en_hilo(excel.construir, datos)
    except excel.NadaParaCorregir as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    base = re.sub(r"\.[A-Za-z0-9]+$", "", v.nombre_mailing or "")
    nombre = _nombre_para_descarga(f"Correcciones RRSS - {base}")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'},
    )


@router.delete("/validaciones/{validacion_id}")
async def borrar_validacion(
    validacion_id: int,
    current_user: User = Depends(require_permission("rrss.validate")),
    db: AsyncSession = Depends(get_db),
):
    v = await _get_validacion_or_404(db, validacion_id)
    _exigir_dueno(v, current_user)
    await db.delete(v)  # las páginas y las placas se van en cascada
    await db.commit()
    return {"ok": True}
