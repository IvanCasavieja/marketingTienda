"""Los tipos de tarea, con las opciones que se tildan al pedirlas (0070).

Pedido de Ivan (16/11/2026): al crear la tarea en la acción se elige el tipo y
se despliegan opciones para tildar, cada una con su medida al lado ("Header ·
web 1920×416 · mobile 640×260"), así la agencia la ve sin buscarla; la
descripción a mano es opcional. La tarjeta se llama sola "<Nombre de la
acción> - <Tipo>" ("Ciberlunes - Banners"), así se encuentra escribiendo el
nombre de la acción.

ESTE ES EL ÚNICO LUGAR DONDE SE EDITA EL CATÁLOGO. La pantalla lo pide al
servidor (GET /calendario/tipos-de-tarea) y no tiene una copia: agregar una
medida es agregar UNA línea acá y desplegar el backend. Las medidas son las
que mandó Ivan el 16/11/2026 (su planilla "Medidas banners", "Medidas EMM",
"Envío WhatsApp" y las de cenefas en hoja A4).

Cada tipo:
- `clave`: lo que se guarda en `calendario_tareas.tipo`. No se cambia nunca
  (las tareas viejas lo tienen guardado); el nombre sí se puede cambiar.
- `nombre`: lo que va en el nombre de la tarjeta ("Ciberlunes - Banners").
- `opciones`: lo que se tilda, cada una con su `medida` (o None).
- `otras`: si se pueden agregar opciones escritas a mano ("Otro…").
- `medida`: la medida del tipo entero, cuando no hay opciones (WhatsApp).
- `campos`: datos de más para elegir (el CTA de un banner, cuántos bloques
  lleva un mailing). Cada uno con `clave`, `nombre` y `opciones` (se elige
  una) o `minimo`/`maximo` (un número).
- `bajada`: una ayuda corta debajo del tipo.
- `pieza`: el tipo de pieza de las entregas (TIPOS_DE_PIEZA en
  app/services/entregas.py) con el que nace: decide qué campos trae
  "Más opciones".
"""
from __future__ import annotations

import unicodedata


def _px(ancho: int, alto: int) -> str:
    return f"{ancho}×{alto}"


def banner(nombre: str, web: tuple[int, int], mobile: tuple[int, int] | None = None) -> dict:
    """Una medida de banner: web ancho×alto y, si hay, mobile ancho×alto."""
    medida = f"web {_px(*web)}" + (f" · mobile {_px(*mobile)}" if mobile else "")
    return {"nombre": nombre, "medida": medida}


def opcion(nombre: str, medida: str | None = None) -> dict:
    return {"nombre": nombre, "medida": medida}


TIPOS_DE_TAREA: list[dict] = [
    {
        "clave": "banners", "nombre": "Banners", "pieza": "banner", "otras": True,
        "bajada": "Medidas en px.",
        "opciones": [
            banner("Header", (1920, 416), (640, 260)),
            banner("Slider fila (normal)", (1200, 179), (640, 260)),
            banner("Slider fila fino", (1200, 62), (640, 202)),
            banner("Carrito", (368, 140)),
            banner("Checkout", (412, 157)),
            banner("Menú principal", (625, 450)),
            banner("Menú secundario", (313, 450)),
            banner("Búsqueda/Categoría", (1390, 207)),
            banner("Cocardas", (112, 70)),
            banner("Bases y condiciones", (1200, 100), (640, 260)),
            banner("Foto receta", (1200, 900)),
            banner("Foto producto", (1200, 900)),
            banner("Dobles", (590, 240), (315, 405)),
            banner("Triples", (390, 240), (206, 265)),
            banner("Cuádruples", (290, 240), (155, 200)),
            banner("Quíntuples", (230, 230)),
            banner("Séxtuples", (190, 182)),
            banner("Séptuples", (162, 158)),
            banner("Óctuples", (140, 140)),
            banner("Cuenta regresiva", (1200, 400)),
        ],
        # A veces piden cambiar el CTA: estos son los permitidos.
        "campos": [
            {"clave": "cta", "nombre": "CTA", "opciones": ["Ver ofertas", "Ver más", "Ver mailing", "Ver mis cupones", "Participar"]},
        ],
    },
    {
        # La hoja "Medidas EMM" de Ivan: el email marketing (lo que llega por mail).
        "clave": "emm", "nombre": "Email marketing (EMM)", "pieza": "mailing", "otras": False,
        "opciones": [
            opcion("Una sola imagen", "600 px de ancho fijo · alto máx. 1600 px"),
            opcion("En bloques",
                   "bloques de 600 × 227–283 px · banner interno 570 px · entran 5 bloques altos o 7 bajos"),
        ],
        "campos": [
            {"clave": "bloques", "nombre": "Cantidad de bloques", "minimo": 1, "maximo": 7, "para": "En bloques"},
        ],
    },
    {
        # Redes sociales (Ivan, 17/11/2026): se pide por proporción, "1:1,
        # 4:5, 9:16, 16:9". Sin medida en px: lo que se pide es la proporción.
        "clave": "redes", "nombre": "Redes sociales", "pieza": "redes", "otras": False,
        "opciones": [opcion("1:1"), opcion("4:5"), opcion("9:16"), opcion("16:9")],
    },
    {
        # El folleto o catálogo de ofertas ("DECO NAVIDAD 16 PAG", "CATÁLOGO
        # CANASTAS 44 pag"). El formato es la hoja "Medidas Mailings" de Ivan
        # (impresos): depende del medio que lo reparte.
        "clave": "mailing", "nombre": "Mailing", "pieza": "otro", "otras": False,
        "opciones": [opcion("Digital"), opcion("Físico (impreso)")],
        "bajada": "Antes de armar la pieza, confirmar medio y formato con quien la pide: "
                  "el tamaño depende de cada pedido.",
        "campos": [
            {"clave": "formato", "nombre": "Formato", "opciones": [
                "El País grande · 28 × 34 cm",
                "El País chico · 22,5 × 29,5 cm",
                "CM grande · 27,5 × 34 cm",
                "CM chico · 21 × 29,7 cm (A4)",
                "A4 · 21 × 29,7 cm (mailing, volantes, dípticos)",
                "A5 · 14,8 × 21 cm (volantes y similares)",
            ]},
            {"clave": "paginas", "nombre": "Cantidad de páginas", "minimo": 1, "maximo": 200},
        ],
    },
    {
        "clave": "whatsapp", "nombre": "Envío WhatsApp", "pieza": "otro", "otras": False,
        "opciones": [], "medida": "imagen de 1080×1350 px · 4:5 vertical",
    },
    {
        # Push (17/11/2026): faltaba entre las piezas que pide el equipo. Sin
        # opciones: el texto y a dónde lleva van en la descripción.
        "clave": "push", "nombre": "Push", "pieza": "otro", "otras": False,
        "opciones": [],
        "bajada": "Escribí el texto y a dónde lleva en la descripción.",
    },
    {
        "clave": "cenefas", "nombre": "Cenefas", "pieza": "cenefa", "otras": True,
        "bajada": "En hoja A4.",
        "opciones": [
            opcion("A4", "1 por hoja · 210×297 mm"),
            opcion("A5", "2 por hoja · 210×148,5 mm"),
            opcion("3xA4", "3 por hoja · 210×99 mm"),
            opcion("A6", "6 por hoja A4 horizontal · 115×70 mm"),
        ],
    },
    {
        "clave": "pantallas", "nombre": "Pantallas", "pieza": "otro", "otras": False,
        "opciones": [opcion("Horizontal"), opcion("Vertical")],
    },
    {
        # "Cartelería" desde el 17/11/2026: así la llama el equipo ("banners,
        # rrss, cartelería, mailing..."). La clave sigue siendo "material".
        "clave": "material", "nombre": "Cartelería", "pieza": "otro", "otras": True,
        "opciones": [opcion("Stopper"), opcion("Clip strip"), opcion("Afiche")],
    },
    {
        "clave": "totem", "nombre": "Tótem", "pieza": "otro", "otras": False,
        "opciones": [],
        "bajada": "Adaptar el key visual. Normalmente no hace falta descripción.",
    },
    {
        "clave": "otro", "nombre": "Otro", "pieza": "otro", "otras": False,
        "opciones": [],
        "bajada": "Contá qué hace falta en la descripción.",
    },
]

_POR_CLAVE = {t["clave"]: t for t in TIPOS_DE_TAREA}
MAX_OPCIONES = 30
LARGO_OPCION = 80


def tipo_de(clave: str | None) -> dict | None:
    return _POR_CLAVE.get(clave or "")


def para_la_pantalla() -> list[dict]:
    """El catálogo como lo pide la pantalla. Lleva `pieza` (a qué tipo de
    pieza de las entregas corresponde) para que "Más opciones" arranque con
    el mismo que pondría el servidor."""
    return [
        {
            "clave": t["clave"], "nombre": t["nombre"], "opciones": t["opciones"], "otras": t["otras"],
            "medida": t.get("medida"), "campos": t.get("campos", []), "bajada": t.get("bajada"),
            "pieza": t.get("pieza"),
        }
        for t in TIPOS_DE_TAREA
    ]


def nombre_de_tarjeta(accion: str, tipo: str) -> str:
    """"Ciberlunes - Banners". Sin el nombre de la acción, solo el tipo."""
    t = tipo_de(tipo)
    nombre = t["nombre"] if t else (tipo or "").strip()
    accion = " ".join((accion or "").split())
    return f"{accion} - {nombre}" if accion else nombre


def opciones_validas(clave: str, opciones) -> list[str]:
    """Lo tildado, limpio: sin repetidos (sin mirar mayúsculas), en el orden
    del catálogo y después las escritas a mano. Una opción que no es del
    catálogo solo vale si el tipo deja agregar otras. ValueError con el
    mensaje para la persona."""
    t = tipo_de(clave)
    if t is None:
        raise ValueError("Ese tipo de tarea no existe")
    if opciones is None:
        return []
    if not isinstance(opciones, list):
        raise ValueError("Las opciones no tienen la forma esperada")
    del_catalogo = {o["nombre"].casefold(): o["nombre"] for o in t["opciones"]}
    elegidas: list[str] = []
    vistas: set[str] = set()
    extra: list[str] = []
    for o in opciones:
        if not isinstance(o, str):
            raise ValueError("Las opciones no tienen la forma esperada")
        o = " ".join(o.split())
        if not o or o.casefold() in vistas:
            continue
        if len(o) > LARGO_OPCION:
            raise ValueError(f"«{o[:30]}…» es demasiado largo para una opción")
        vistas.add(o.casefold())
        if o.casefold() in del_catalogo:
            elegidas.append(del_catalogo[o.casefold()])
        elif t["otras"]:
            extra.append(o)
        else:
            raise ValueError(f"«{o}» no es una opción de {t['nombre']}")
    if len(elegidas) + len(extra) > MAX_OPCIONES:
        raise ValueError(f"Son demasiadas opciones (máximo {MAX_OPCIONES})")
    orden = {o["nombre"]: i for i, o in enumerate(t["opciones"])}
    return sorted(elegidas, key=lambda o: orden[o]) + extra


def detalles_validos(clave: str, detalles, opciones: list[str]) -> dict:
    """Los datos de más (el CTA, la cantidad de bloques), limpios. Uno que no
    corresponde a lo tildado (bloques sin "en bloques") no se guarda."""
    t = tipo_de(clave)
    if t is None:
        raise ValueError("Ese tipo de tarea no existe")
    if not detalles:
        return {}
    if not isinstance(detalles, dict):
        raise ValueError("Los datos del pedido no tienen la forma esperada")
    campos = {c["clave"]: c for c in t.get("campos", [])}
    out: dict = {}
    for clave_campo, valor in detalles.items():
        campo = campos.get(clave_campo)
        if campo is None or valor in (None, ""):
            continue
        if campo.get("para") and campo["para"] not in opciones:
            continue
        if "opciones" in campo:
            if valor not in campo["opciones"]:
                raise ValueError(f"«{valor}» no es un {campo['nombre']} permitido")
            out[clave_campo] = valor
        else:
            try:
                n = int(valor)
            except (TypeError, ValueError, OverflowError):
                # OverflowError: un 1e400 en el JSON llega como infinito, e
                # int(infinito) no es un ValueError: contestaba 500 (16/11/2026).
                raise ValueError(f"«{campo['nombre']}» tiene que ser un número")
            if not (campo.get("minimo", 0) <= n <= campo.get("maximo", 1000)):
                raise ValueError(f"«{campo['nombre']}» va de {campo.get('minimo', 0)} a {campo.get('maximo', 1000)}")
            out[clave_campo] = n
    return out


def descripcion_del_pedido(clave: str | None, opciones: list[str] | None, detalles: dict | None) -> str | None:
    """Lo que se pidió, con las medidas, para la descripción de la tarjeta y
    el pedido a la agencia (así la ve sin buscarla):

        Banners: Header (web 1920×416 · mobile 640×260), Checkout (web 412×157)
        CTA: Ver ofertas
    """
    t = tipo_de(clave)
    if t is None:
        return None
    medidas = {o["nombre"]: o.get("medida") for o in t["opciones"]}
    lineas = []
    if opciones:
        partes = [f"{o} ({medidas[o]})" if medidas.get(o) else o for o in opciones]
        lineas.append(f"{t['nombre']}: {', '.join(partes)}")
    elif t.get("medida"):
        lineas.append(f"{t['nombre']}: {t['medida']}")
    for campo in t.get("campos", []):
        valor = (detalles or {}).get(campo["clave"])
        if valor not in (None, ""):
            lineas.append(f"{campo['nombre']}: {valor}")
    return "\n".join(lineas) or None


def sin_tildes(texto: str | None) -> str:
    """Para buscar: "Ciberlunes - Banners" y "ciberlunes banners" son lo
    mismo. En minúscula, sin tildes ni diéresis."""
    base = unicodedata.normalize("NFKD", (texto or "").casefold())
    return "".join(c for c in base if not unicodedata.combining(c))


def palabras_de_busqueda(texto: str | None) -> list[str]:
    """Lo que escribió la persona, partido en palabras (el guión, la coma y
    los espacios separan). Sin repetidas y hasta 8, para que una búsqueda
    rara no arme una consulta gigante."""
    limpio = "".join(c if c.isalnum() else " " for c in sin_tildes(texto))
    out: list[str] = []
    for p in limpio.split():
        if p not in out:
            out.append(p)
    return out[:8]
