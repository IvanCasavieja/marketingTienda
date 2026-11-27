"""La guía de uso de Core Tienda: UNA sola fuente para la pantalla y para Don Tino.

Pedido de Ivan (25/11/2026): "hay que actualizar la guía de uso y fijarse que
Don Tino pueda manejar toda la app". La guía de /ayuda estaba en los archivos
de idioma y se había quedado en septiembre (cenefas, medios, la planilla), sin
el calendario, las tareas ni el tablero; y Don Tino tenía su propio texto,
aparte, que también se iba quedando viejo. Ahora las dos cosas salen de acá:

- la pantalla pide GET /guia y muestra las secciones que la persona puede usar
  (ver `secciones_para`);
- Don Tino lleva la guía entera en su prompt (`como_texto`) y, en el bloque de
  cada conversación, qué secciones puede usar quien le pregunta.

Si cambia cómo se usa algo, se cambia ACÁ y queda al día en los dos lados.

Quién ve cada sección (`quienes`):
- "equipo": la gente de Tienda (cualquier cuenta que no sea externa y tenga
  algún permiso además del chat);
- "agencia": una cuenta externa (Publicis, Another Monday, Diseñadores...);
- "local": un login de sucursal de Redexpres (tiene un local asignado).
Además, `permisos` (alcanza con uno; vacío = cualquiera), `mundos` (alcanza
con uno; vacío = todos) y `ve_calendario` (que su alcance no sea "No lo ve").
Cada parte de una sección puede recortarse igual.

Escrita en castellano rioplatense, para leer en el celular. Texto con
**negrita** y nada más: la pantalla lo pinta y Don Tino lo lee tal cual.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import select

EQUIPO, AGENCIA, LOCAL = "equipo", "agencia", "local"
TODOS = frozenset({EQUIPO, AGENCIA, LOCAL})


@dataclass(frozen=True)
class Parte:
    titulo: str
    puntos: tuple[str, ...]
    # Pasos que van en orden (la pantalla los numera).
    numerada: bool = False
    quienes: frozenset[str] = TODOS
    permisos: tuple[str, ...] = ()
    mundos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Seccion:
    clave: str
    titulo: str
    # Un nombre de ícono de lucide-react; la pantalla lo traduce (ver ICONOS en ayuda/page.tsx).
    icono: str
    resumen: str
    partes: tuple[Parte, ...]
    ruta: str | None = None
    quienes: frozenset[str] = frozenset({EQUIPO})
    permisos: tuple[str, ...] = ()
    mundos: tuple[str, ...] = ()
    ve_calendario: bool = False


SECCIONES: tuple[Seccion, ...] = (
    Seccion(
        clave="primeros-pasos", titulo="Cómo moverte por la plataforma", icono="Compass",
        quienes=TODOS,
        resumen="Lo básico: entrar, elegir dónde trabajar y enterarte de lo que te piden.",
        partes=(
            Parte("Entrar", (
                "Entrás con tu mail y tu contraseña. Cada 60 días la plataforma te pide cambiarla.",
                "¿Te la olvidaste? En la entrada tocá **¿Olvidaste tu contraseña?** y te llega un link por mail "
                "(dura una hora).",
            )),
            Parte("El mundo", (
                "Cada negocio es un **mundo**: Tienda Inglesa, Tienda Express, Redexpres, Tienda Viajes y Tienda "
                "Farma. Si tenés más de uno, elegís en cuál trabajar al entrar y lo cambiás con **Cambiar mundo**.",
                "El calendario, las tareas y el tablero que ves son los del mundo elegido.",
            ), quienes=frozenset({EQUIPO})),
            Parte("El menú", (
                "Arriba, lo de todos los días: **Calendario**, **Mis tareas** y **Tablero** (y, según el mundo, "
                "**Colocación** o la **Planilla de pedidos**).",
                "Abajo, **Herramientas**, que se abre y se cierra: cenefas, medios, finanzas, precios y lo que "
                "tengas habilitado.",
                "En el celular, lo principal está en la barra de abajo y el resto en **Más**.",
            ), quienes=frozenset({EQUIPO})),
            # Fija abajo del menú desde H-126 (antes, al final de Herramientas,
            # donde nadie la encontraba).
            Parte("Administración", (
                "Si administrás la plataforma, **Administración** (usuarios y permisos) está fija abajo del menú, "
                "arriba de tu nombre.",
            ), quienes=frozenset({EQUIPO}), permisos=("platform.admin",)),
            Parte("El menú", (
                "Tu menú es corto: **Mi tablero** (y el **Calendario**, si te lo habilitaron) y esta guía.",
                "En el celular, todo está en la barra de abajo.",
            ), quienes=frozenset({AGENCIA})),
            Parte("El menú", (
                "Arriba tenés **Fotos para subir** (con cuántas te faltan) y en **Herramientas**, **Mi pedido**.",
                "En el celular, las dos están en la barra de abajo.",
            ), quienes=frozenset({LOCAL})),
            Parte("Los avisos", (
                "La **campanita** (arriba a la derecha; en el celular, **Avisos** abajo) te avisa cuando te asignan "
                "algo, te piden una pieza, te devuelven cambios o te aprueban. Tocás el aviso y te lleva directo.",
                "Los avisos de tareas y del calendario también llegan por mail; lo del tablero (entregas, cambios, "
                "aprobaciones) llega solo a la campanita.",
            )),
            Parte("Tu perfil", (
                "Tocando tu nombre, abajo del menú: cambiar la contraseña y prender o apagar los avisos por mail.",
                "Al lado están el modo oscuro y el idioma.",
            )),
        ),
    ),
    Seccion(
        clave="calendario", titulo="El calendario", icono="CalendarDays", ruta="/calendario",
        quienes=frozenset({EQUIPO, AGENCIA}), permisos=("calendario.view",), ve_calendario=True,
        resumen="Las acciones del mes de tu mundo, como en el Excel: qué sale, cuándo y cómo viene cada una.",
        partes=(
            Parte("Las vistas", (
                "**Calendario**: el mes entero, una fila por categoría y una barra por acción.",
                "**Lista**: las mismas acciones en tarjetas (en curso, lo que viene, las que terminaron); cómoda "
                "en el celular.",
                "**Equipo**: cuántas tareas abiertas tiene cada persona por semana (amarillo desde 3, rojo desde 5). "
                "Una tarea que hace una agencia le cuenta a quien la lleva por Tienda.",
            )),
            Parte("Moverte", (
                "Flechas o el selector para cambiar de mes; **Hoy** vuelve al mes actual.",
                "Los chips **Todo · Comercial · Envíos · Retail Media · Headers** filtran qué parte ves.",
                "Tocar el número de un día lo marca; tocar una categoría marca su fila.",
                "El puntito de color de cada acción (el semáforo) avisa si viene bien o si algo se atrasa: "
                "tocá la acción para ver qué.",
            )),
            Parte("Crear y cambiar acciones", (
                "**Nueva acción** (o el **+** de una categoría, o tocar un día vacío): nombre, fechas y color.",
                "En la ficha de la acción: **Editar nombre, fechas y color** y **Copiar a otra fecha** (para repetir "
                "una acción del año pasado; con permiso de tareas, se copian también sus tareas).",
                "Si cambiás las fechas de una acción, las tareas que salieron de una plantilla se corren solas.",
            ), quienes=frozenset({EQUIPO}), permisos=("calendario.edit",)),
            Parte("Envíos, Retail Media y headers", (
                "Abajo del calendario comercial: el cronograma de envíos (mail, WhatsApp, push), Retail Media y "
                "cuántos banners hay en el header de la home cada día (en rojo si pasan de 8).",
            ), quienes=frozenset({EQUIPO}), mundos=("tienda_inglesa",)),
            Parte("Mi agenda", (
                "Arriba podés conectar tu calendario de Outlook o Google para ver tus reuniones al lado de las "
                "acciones. Lo ves solo vos.",
            )),
            Parte("De dónde salen las fechas", (
                "El calendario comercial de Tienda Inglesa se carga del Excel **CALENDARIO 2025 Y 2026 TI**. Si en "
                "el Excel cambian fechas o aparecen acciones nuevas, pedile a quien administra la plataforma que lo "
                "vuelva a cargar: se corrige lo distinto sin pisar lo que se cambió a mano en la pantalla.",
            ), quienes=frozenset({EQUIPO}), mundos=("tienda_inglesa",)),
        ),
    ),
    Seccion(
        clave="ficha", titulo="La ficha de una acción", icono="PanelRight",
        permisos=("calendario.view",), ve_calendario=True,
        resumen="Tocás una acción y se abre su ficha: sus datos y, abajo, sus tareas.",
        partes=(
            Parte("Qué tiene", (
                "Arriba: nombre, fechas y categoría. Después, **Tareas** con cuántas están hechas "
                "(«1 de 3 hechas»).",
                "**Avisos (N)**: los recordatorios de la acción (cuántos días antes y a quién le llegan). No hay "
                "ninguno por defecto: los configura quien carga la acción.",
                "**Fotos** (en Redexpres): el pedido de fotos de colocación a los locales.",
                "Si la acción trae piezas del cronograma (por ejemplo, el header de la home o los envíos), van en "
                "una lista corta abajo.",
            )),
            Parte("Cada tarea", (
                "Se ve en dos o tres líneas: nombre y vencimiento; quién la hace y cuántos archivos lleva; y, si es "
                "de una agencia, en qué está («Le toca a Publicis: entregar») con **Abrir la tarjeta**.",
                "Las de Tienda llevan su casilla para darlas por hechas y su estado (Pendiente, En proceso, Hecha). "
                "Las de una agencia no: se cierran solas cuando se aprueban.",
            )),
            Parte("Editar con «⋯»", (
                "Cada tarea tiene su **⋯**: ver y cambiar el detalle (escrito o dictado), adjuntar o sacar archivos, "
                "quién la hace y el responsable de Tienda, la fecha y el nombre, o borrarla.",
                "En las de una agencia, también **Darla por hecha** o **Volver a abrir**.",
            )),
        ),
    ),
    Seccion(
        clave="crear-tarea", titulo="Pedir algo: crear una tarea", icono="ListPlus",
        permisos=("calendario.tareas", "calendario.pedidos"),
        resumen="Una tarea es un pedido: qué se pide, quién lo hace y para cuándo. Todo en un solo formulario y en "
                "un solo nivel.",
        partes=(
            Parte("Paso a paso", (
                "En la ficha de la acción, **Crear tarea**.",
                "**¿Qué se pide?**: Banners, Mailing, Redes, Cenefas… u **Otra cosa**. Cada tipo abre sus opciones "
                "(por ejemplo, Header o Slider y el CTA).",
                "**¿Quién la hace?**: una agencia (Publicis, Another Monday, Diseñadores) o alguien de Tienda.",
                "El nombre se arma solo («TiendaChecks Emisión - Banners») y lo podés cambiar. Con **Otra cosa** lo "
                "escribís vos.",
                "**Detalle**: lo que hay que hacer, escrito o con **Dictar el pedido** (la IA lo ordena).",
                "**Archivos**: Excel, CSV, PDF, Word, imágenes o ZIP; hasta 5, de 10 MB cada uno. La agencia los ve "
                "y los baja desde su tarjeta.",
                "**Responsable de Tienda** (si la hace una agencia): quien la sigue por Tienda. Le llegan los avisos "
                "y la ve en Mis tareas.",
                "**Vence** (opcional) y **Crear tarea**.",
            ), numerada=True),
            Parte("Bueno saber", (
                "Si marcás dos tipos (Banners y Mailing), se crean dos tareas, cada una con su tarjeta, con el mismo "
                "detalle y los mismos archivos.",
                "Si la hace una agencia, nace su tarjeta en el tablero de esa agencia y le llega el aviso.",
                "Ya no hay subtareas ni «pedir una pieza»: cada pedido es su propia tarea.",
                "**Usar plantilla** crea de una las tareas que lleva siempre un tipo de acción, con fechas relativas "
                "al inicio o al fin de la acción; si la acción se mueve, se mueven con ella.",
            )),
        ),
    ),
    Seccion(
        clave="tablero", titulo="Tableros: las piezas con las agencias", icono="Layers", ruta="/entregas",
        permisos=("calendario.view",),
        resumen="Cada pieza pedida es una tarjeta, como en Trello, y va pasando de columna hasta aprobarse.",
        partes=(
            Parte("Las columnas", (
                "**Ingresado**: nueva, todavía no se arrancó.",
                "**En proceso**: la están trabajando (o volvió con cambios).",
                "**Esperando feedback**: entregada; le toca a Tienda revisarla.",
                "**Finalizado**: aprobada.",
                "**Archivado**: las finalizadas pasan solas a los 10 días.",
            )),
            Parte("Qué podés hacer", (
                "Pestañas por tablero: Publicis, Another Monday, Diseñadores y Otras.",
                "Arrastrar una tarjeta (con el dedo, mantenela apretada) o usar **Mover a…**. Moverla a mano no "
                "entrega ni aprueba nada: solo la acomoda.",
                "Buscar por nombre arriba (busca también en lo archivado).",
                "Archivar algo que no se terminó es cancelarlo; se puede sacar del archivo.",
                "Tocar una tarjeta abre su ficha.",
            )),
            Parte("Nueva tarjeta (sin acción)", (
                "Para pedir algo que no es de ninguna acción del calendario: **Nueva tarjeta**. Es el mismo "
                "formulario de una tarea, con un nombre que escribís vos. La tarjeta dice **Sin acción** y no aparece "
                "en el calendario.",
            ), permisos=("calendario.tareas", "calendario.pedidos")),
            Parte("Análisis de entregas", (
                "Abajo del tablero: cuánto tarda cada agencia, cuántas piezas se pasan de fecha y cuántas versiones "
                "lleva aprobar. Lo ve solo Tienda; las agencias no.",
            )),
        ),
    ),
    Seccion(
        clave="tarjeta", titulo="La tarjeta de una pieza", icono="SquareStack",
        quienes=frozenset({EQUIPO, AGENCIA}), permisos=("calendario.view",),
        resumen="Todo de una pieza en un lugar: a quién le toca, la última versión, lo que se pidió y lo que se dijo.",
        partes=(
            Parte("Qué tiene", (
                "Arriba: el tipo, la acción (o **Sin acción**), quién la hace y cuándo vence. Después, a quién le "
                "toca ahora y la última versión en grande.",
                "Si la versión trae varias imágenes, la tira de miniaturas las cambia sin que la pantalla salte.",
                "**Comparar** pone la versión que elijas al lado de la actual, cada una con sus miniaturas.",
                "**Lo que se pidió**: el detalle y los archivos del pedido para bajar.",
                "Más abajo: las versiones anteriores con sus marcas, y los comentarios.",
                "Se pone al día sola cada pocos segundos: no hace falta recargar.",
            )),
            Parte("Los cambios pedidos", (
                "Van como números rojos sobre la imagen, y abajo la lista con cada número y qué hay que cambiar.",
            )),
        ),
    ),
    Seccion(
        clave="revisar", titulo="Revisar una entrega", icono="ClipboardCheck",
        permisos=("calendario.view",),
        resumen="Cuando la agencia entrega y te toca a vos, decidís: pedir cambios, avanzar o aprobar y terminar.",
        partes=(
            Parte("Cómo se revisa", (
                "En la tarjeta aparece **Revisar ahora**.",
                "A la izquierda, la imagen: queda quieta aunque escribas mucho. A la derecha, lo que hay que mirar: "
                "las piezas del pedido que faltan, lo que se pidió con lo que vio la IA en cada punto (lo que falta "
                "en rojo, lo dudoso en ámbar, lo hecho en verde) y lo que encontró la IA en la pieza.",
                "Para pedir un cambio, tocá la imagen donde está: queda una marca numerada en rojo y escribís qué "
                "cambiar. Lo que vio la IA lo pasás a marca con **Hacer marca**, o lo sacás con **Descartar**.",
                "Si la IA vio lo mismo en varias imágenes, va una sola vez («Está en las imágenes 1 y 2»): **Hacer "
                "una marca en cada una** las marca todas y **Descartar** las descarta juntas.",
                "La IA es una ayuda y se puede equivocar: decidís vos.",
            )),
            Parte("Decidir", (
                "**Pedir cambios**: la tarjeta vuelve a la agencia con tus marcas y tu comentario.",
                "**Avanzar**: esa parte está bien y la agencia sigue con lo que falta (por ejemplo, aprobaste el KV "
                "y ahora hacen el resto). La tarea sigue abierta.",
                "**Aprobar y terminar**: está todo. Cierra la fase (y la tarea, si era la última). Cuando ya vinieron "
                "todas las piezas pedidas, es el botón grande.",
                "**Comentario para la agencia**: lo general, que no va en un punto de la imagen. **Nota interna**: la "
                "ve solo Tienda.",
            )),
        ),
    ),
    Seccion(
        clave="mis-tareas", titulo="Mis tareas", icono="ListChecks", ruta="/mis-tareas",
        permisos=("calendario.view",),
        resumen="Lo tuyo, de todas las acciones, ordenado por vencimiento.",
        partes=(
            Parte("Qué ves", (
                "Lo que tenés asignado y lo que llevás como responsable de Tienda (aunque lo haga una agencia).",
                "Arriba, lo que espera tu decisión (para revisar) y lo que te devolvieron con cambios.",
                "Tildás para darla por hecha, con **Deshacer** por si te equivocaste.",
                "Si tenés pendientes en otro mundo, te avisa y te lleva.",
                "Aunque no veas el calendario, tus tareas te llegan igual.",
            )),
        ),
    ),
    Seccion(
        clave="agencia", titulo="Tu tablero (agencias)", icono="Layers", ruta="/entregas",
        quienes=frozenset({AGENCIA}), permisos=("calendario.view",),
        resumen="Lo que te pidió Tienda Inglesa, en tarjetas: lo trabajás, lo entregás y ves qué te contestan.",
        partes=(
            Parte("Qué ves", (
                "Las tarjetas que te pidieron, en columnas: Ingresado, En proceso, Esperando feedback, Finalizado y "
                "Archivado.",
                "Cuando arrancás una, pasala a **En proceso** (arrastrándola o con **Mover a…**).",
                "Tocala para ver el pedido: el detalle, la fecha y los archivos para bajar (por ejemplo, el Excel).",
            )),
            Parte("Entregar", (
                "En la tarjeta, **Entregar** (o arrastrala a **Esperando feedback**).",
                "Subí las imágenes (y el ZIP o el link al original, si corresponde).",
                "Antes de mandar, la IA revisa la pieza y te muestra lo mismo que va a ver Tienda: lo que falta del "
                "pedido, lo que te pidieron cambiar y lo que encontró (ortografía, precios, fechas, legales). Elegís "
                "**Corregir** o **Mandar igual**.",
                "Si no va todo (por ejemplo, mandás primero el KV para que lo aprueben), escribí por qué en "
                "**¿Por qué no va todo?**.",
                "Si querés contarle algo a quien revisa, va en **Nota de este envío**.",
            ), numerada=True),
            Parte("Cuando te contestan", (
                "**Cambios pedidos**: la tarjeta vuelve a En proceso con números rojos sobre la imagen y el "
                "comentario. Corregís y mandás una versión nueva.",
                "Si a la versión que está esperando solo le faltó algo, **Sumar archivos** lo agrega a esa misma "
                "versión, sin mandar otra, con una nota corta. A quien revisa le llega el aviso.",
                "**Te dieron el OK: entregá lo que falta**: esa parte está bien; seguí con el resto y entregalo.",
                "**Aprobada**: pasa a Finalizado. Si después hace falta otro cambio, Tienda la puede **Reabrir para "
                "otro cambio** y te llega el aviso con lo que hay que cambiar.",
                "Te enterás por la campanita. Abajo de la tarjeta podés escribirle a Tienda.",
            )),
        ),
    ),
    Seccion(
        clave="mi-pedido", titulo="Mi pedido (locales de Redexpres)", icono="ClipboardList",
        ruta="/redexpres/mi-pedido", quienes=frozenset({LOCAL}),
        resumen="Lo que tu local necesita de material este mes.",
        partes=(
            Parte("Cargar", (
                "Elegí el mes y completá las cantidades. Se guarda solo al dejar de escribir.",
                "Cada material tiene un máximo por local: si te pasás, se baja al máximo y te avisa.",
                "Si marketing todavía no abrió el mes, te lo dice: cuando lo abra, lo vas a poder cargar.",
            )),
            Parte("Confirmar", (
                "Cuando terminaste, **Confirmar pedido** (te pregunta antes).",
                "Ya confirmado, sale un cartel verde y no se puede cambiar.",
                "Si tenés que cambiar algo después de confirmar, pedíselo a marketing: lo desconfirman desde la "
                "Planilla de pedidos.",
            )),
        ),
    ),
    Seccion(
        clave="fotos", titulo="Fotos para subir (locales)", icono="Camera", ruta="/fotos",
        quienes=frozenset({LOCAL}),
        resumen="Las fotos de cómo quedó colocado el material en tu local.",
        partes=(
            Parte("Qué hacer", (
                "En **Fotos para subir** ves qué acción, qué foto te piden y hasta cuándo.",
                "Sacás la foto con el celular y la subís (se achica sola).",
                "Si te la devuelven, ves por qué y la volvés a subir.",
            )),
        ),
    ),
    Seccion(
        clave="planilla", titulo="Planilla de pedidos (Redexpres)", icono="ClipboardList", ruta="/redexpres/planilla",
        permisos=("redexpres.view", "redexpres.manage"), mundos=("redexpres",),
        resumen="Todos los locales en una planilla: qué pidió cada uno y si confirmó.",
        partes=(
            Parte("Qué podés hacer", (
                "En el mundo Redexpres está arriba en el menú.",
                "Elegir el mes; los punteados todavía no están abiertos.",
                "Abrir un mes nuevo: te pregunta antes y copia las columnas del mes anterior. Un mes abierto no se "
                "borra.",
                "Completar o corregir filas, y confirmar o desconfirmar pedidos (quien gestiona la planilla).",
                "Bajar todo a Excel.",
                "Un pedido confirmado no se puede cambiar por ningún lado: primero hay que desconfirmarlo acá.",
            )),
        ),
    ),
    Seccion(
        clave="colocacion", titulo="Colocación (fotos de los locales)", icono="Camera", ruta="/colocacion",
        permisos=("calendario.edit",), ve_calendario=True, mundos=("redexpres",),
        resumen="Cómo vienen las fotos de colocación que mandan los locales.",
        partes=(
            Parte("Qué ves", (
                "Las acciones con pedido de fotos abierto, cuánto se cumplió y qué locales están atrasados.",
                "Tocás una y vas a sus fotos, en la ficha de la acción. El pedido de fotos se arma ahí, con el botón "
                "**Fotos**.",
            )),
        ),
    ),
    Seccion(
        clave="cenefas", titulo="Cenefas", icono="Presentation", ruta="/materiales/cenefas",
        permisos=("cenefas.view",), mundos=("tienda_inglesa", "redexpres"),
        resumen="Los carteles de precios en PPTX, a partir de un Excel de productos.",
        partes=(
            Parte("Generar", (
                "En **Herramientas → Cenefas**, elegí el tipo de cenefa.",
                "Cargá uno o varios Excel y a cada uno elegile hasta 5 plantillas: cada Excel × plantilla es una "
                "cenefa.",
                "Revisá el lote: avisa lo que falta o no cierra antes de generar.",
                "Descargá el PPTX. En **Historial** quedan las generaciones anteriores.",
            ), numerada=True),
            Parte("Bueno saber", (
                "Si tu Excel es el listado de gestión, pasalo primero por el **Convertidor de Excel**: si lo subís "
                "directo, Cenefas te frena y te dice qué hacer.",
                "Las plantillas se cargan desde un PPTX con los lugares marcados (por ejemplo <<precioOferta>> o "
                "<<descripcion>>). Ninguna variable es obligatoria.",
            )),
        ),
    ),
    Seccion(
        clave="convertidor", titulo="Convertidor de Excel y Diccionario", icono="FileSpreadsheet",
        ruta="/materiales/convertidor", permisos=("cenefas.view",), mundos=("tienda_inglesa", "redexpres"),
        resumen="Del listado de gestión a un Excel limpio, listo para las cenefas.",
        partes=(
            Parte("Convertir", (
                "Subí el Excel de gestión: las descripciones salen del Diccionario, por código.",
                "Revisá la grilla: lo marcado es para mirar (precios por 100 g, moneda en dólares, alcohol, "
                "descripciones que faltan). La IA (Tinín) propone descripciones.",
                "Bajalo, o **Convertir a cenefa** para seguir directo en Cenefas.",
            ), numerada=True),
            Parte("El Diccionario", (
                "En **Herramientas → Diccionario**: las descripciones guardadas por código y los grupos de varios "
                "códigos con un mismo cartel. Lo que corregís ahí lo usa el Convertidor.",
            ), permisos=("cenefas.diccionario",)),
        ),
    ),
    Seccion(
        clave="rrss", titulo="Validación de redes sociales", icono="ScanSearch", ruta="/redes-sociales/validacion",
        permisos=("rrss.view",), mundos=("tienda_inglesa",),
        resumen="CatTi compara las placas de redes con el mailing o la planilla de la campaña.",
        partes=(
            Parte("Cómo", (
                "Subí la fuente (el mailing en PDF o imagen, o la planilla Excel) y después las placas.",
                "CatTi marca las diferencias de precio, descripción, legales y fechas.",
                "Al final bajás el Excel con lo encontrado. En **Las de hoy** retomás una si cerraste la "
                "pestaña: cada validación se borra sola a las 24 horas, así que bajá el Excel antes.",
            ), numerada=True),
        ),
    ),
    Seccion(
        clave="medios", titulo="Medios", icono="BarChart2", ruta="/dashboard",
        permisos=("analytics.view", "ai.triada", "connections.view"),
        resumen="Las campañas pagas: números, análisis y conexiones.",
        partes=(
            Parte("Dashboard y campañas", (
                "**Dashboard**: inversión, impresiones, clics, CTR, CPC, conversiones y ROAS, comparados con el "
                "período anterior, con alertas si algo cae mucho.",
                "**Campañas**: la tabla con filtros y exportación a CSV. **Analytics GA4**: por canal.",
                "Meta Ads está pausado: lo que se ve de Meta es de ejemplo (dice DEMO).",
            ), permisos=("analytics.view",)),
            Parte("Análisis IA (La Triada)", (
                "Tres IAs debaten sobre los datos y cierran con una síntesis.",
            ), permisos=("ai.triada",)),
            Parte("Conexiones", (
                "Las cuentas de Google Ads, GA4, TikTok y DV360, cada una con su guía en la pantalla.",
            ), permisos=("connections.view",)),
        ),
    ),
    Seccion(
        clave="precios", titulo="Buscar precios y listas de monitoreo", icono="Tag", ruta="/precios",
        permisos=("precios.search",),
        resumen="Los precios de la competencia, en vivo.",
        partes=(
            Parte("Buscar", (
                "Escribís el producto o pegás el código de barras: busca en vivo en 17 cadenas (supermercados, "
                "farmacias y electrodomésticos).",
                "Filtrás por cadena, ordenás por precio y **Ver gráfico** compara con tu precio.",
            )),
            Parte("Listas de monitoreo", (
                "Seguís productos de la competencia: se chequean solos una vez por día y avisan si cambia el precio. "
                "Se pueden compartir.",
            ), mundos=("tienda_inglesa",)),
        ),
    ),
    Seccion(
        clave="finanzas", titulo="Finanzas", icono="Receipt", ruta="/facturacion",
        permisos=("facturacion.view", "facturacion.manage"),
        resumen="Presupuesto, canjes y facturas.",
        partes=(
            Parte("Qué hay", (
                "El presupuesto (entradas y salidas) y los canjes con marcas y proveedores.",
                "Subís las facturas en PDF, DogTi las lee y las revisás antes de confirmar.",
                "En **Cuentas** (con permiso de gestión) se crean y ordenan las cuentas.",
            )),
        ),
    ),
    Seccion(
        clave="clientes-vip", titulo="Clientes VIP", icono="Crown", ruta="/clientes-vip",
        permisos=("clientes_vip.view",), mundos=("tienda_inglesa",),
        resumen="Las compras de los clientes VIP mes a mes: quién crece, quién se está yendo y qué se espera.",
        partes=(
            Parte("Qué hay", (
                "La venta, el margen, cuántos compraron, el ticket promedio y las compras por cliente del último "
                "mes, contra el anterior y contra el mismo mes del año pasado.",
                "**El informe del mes** y **Lo que viene** los hace Valentina, la economista y estadística del "
                "Escuadrón Lechuza: después de cada carga analiza los datos, investiga el contexto (campañas, "
                "calendario, Uruguay), proyecta el mes que viene con su margen de error y manda el informe por mail a "
                "quienes tienen acceso. Hasta que lo hace, «Lo que viene» muestra un cálculo rápido de la plataforma.",
                "Respondiendo su mail le podés enseñar, preguntar o discutirle: si algo no le cierra con los datos, te lo "
                "dice. Lo que aprende queda en **Lo que aprendió Valentina**.",
                "Los **segmentos** (Creciendo, Estable, Nuevo, Bajando, En riesgo, Perdido): tocás uno y la lista "
                "muestra esos clientes; cada uno tiene su riesgo de dejar de comprar, de 0 a 100, y su ficha mes a mes.",
                "Es confidencial: lo ve solo quien tiene el permiso, y no se reenvía fuera de Tienda Inglesa.",
            )),
            Parte("Cargar el archivo del mes", (
                "**Cargar archivo** y elegís el CSV de compras (o el .zip que lo trae).",
                "Se lee en tu computadora (un año tarda alrededor de un minuto) y te muestra qué trae: meses, "
                "clientes y venta.",
                "**Cargar**: sube solo el resumen por cliente y por mes. Si un mes ya estaba, se reemplaza.",
            ), numerada=True, permisos=("clientes_vip.cargar",)),
        ),
    ),
    Seccion(
        clave="don-tino", titulo="Don Tino, el asistente", icono="MessageCircle",
        quienes=frozenset({EQUIPO, LOCAL}), permisos=("ai.don_tino",),
        resumen="Preguntale lo que quieras de la plataforma: te guía y consulta por vos.",
        partes=(
            Parte("Dónde está", (
                "Siempre a mano: la burbuja de abajo a la derecha, en cualquier pantalla. Se abre sin salir de lo "
                "que estás haciendo (en el celular, casi a pantalla entera) y se cierra con la X.",
                "En **Inicio** lo tenés grande. La conversación es la misma en los dos lados: no se pierde al "
                "cambiar de pantalla.",
            )),
            Parte("Qué hace", (
                "Te explica paso a paso cómo se hace algo en la plataforma.",
                "Consulta por vos, con tus permisos: el calendario, tus tareas, cómo vienen las piezas en el tablero, "
                "qué te toca revisar, los pedidos de Redexpres, precios de la competencia o una cenefa.",
                "No cambia nada por vos: crear, aprobar o mover se hace en la pantalla, y él te dice dónde.",
            )),
        ),
    ),
    Seccion(
        clave="admin", titulo="Usuarios y permisos", icono="Users", ruta="/admin",
        permisos=("platform.admin",),
        resumen="Quién entra y qué puede hacer cada uno.",
        partes=(
            Parte("En Administración", (
                "Alta, edición, desactivar y eliminar cuentas (de a una o varias), con filtros por rol y en orden "
                "alfabético.",
                "Cada persona tiene su rol de arranque, sus permisos, sus mundos y hasta dónde ve el calendario "
                "(No lo ve, 1 mes, 2 meses, 12 meses o Todo).",
                "Las cuentas de agencia se crean eligiendo su agencia: ven solo su tablero.",
                "Nadie puede dar un permiso, un mundo o más calendario que los que tiene. Un Admin no toca a otro "
                "Admin ni al superadmin.",
            )),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Quién ve qué
# ---------------------------------------------------------------------------

def audiencias_de(usuario, tiene_local: bool) -> frozenset[str]:
    """Qué tipo de cuenta es: la agencia, un local, el equipo (o local y
    equipo a la vez, como quien carga la planilla y tiene un local). Pura."""
    from app.core import externos

    if externos.es_externo(usuario):
        return frozenset({AGENCIA})
    permisos = set(getattr(usuario, "permissions", None) or [])
    del_equipo = bool(getattr(usuario, "is_superuser", False)) or bool(permisos - {"ai.don_tino"})
    out = set()
    if del_equipo:
        out.add(EQUIPO)
    if tiene_local:
        out.add(LOCAL)
    return frozenset(out or {EQUIPO})


def _tiene(usuario, permisos: tuple[str, ...]) -> bool:
    if not permisos:
        return True
    from app.core import externos

    return any(externos.puede_tener(usuario, p) for p in permisos)


def _en_mundo(usuario, mundos: tuple[str, ...]) -> bool:
    if not mundos or getattr(usuario, "is_superuser", False):
        return True
    return bool(set(mundos) & set(getattr(usuario, "mundos", None) or []))


def _puede(usuario, audiencias: frozenset[str], quienes, permisos, mundos) -> bool:
    return bool(audiencias & quienes) and _tiene(usuario, permisos) and _en_mundo(usuario, mundos)


def secciones_para(usuario, tiene_local: bool) -> list[Seccion]:
    """Las secciones (con solo sus partes) que esta persona puede usar. Pura."""
    from app.core import alcance

    audiencias = audiencias_de(usuario, tiene_local)
    out = []
    for s in SECCIONES:
        if not _puede(usuario, audiencias, s.quienes, s.permisos, s.mundos):
            continue
        if s.ve_calendario and not alcance.ve_el_calendario(usuario):
            continue
        partes = tuple(p for p in s.partes if _puede(usuario, audiencias, p.quienes, p.permisos, p.mundos))
        if partes:
            out.append(replace(s, partes=partes))
    return out


async def tiene_local(db, usuario) -> bool:
    """Si tiene un local de Redexpres asignado (un login de sucursal)."""
    from app.models.local_asignacion import LocalAsignacion

    uid = getattr(usuario, "id", None)
    if uid is None or db is None:
        return False
    fila = (await db.execute(select(LocalAsignacion.id).where(LocalAsignacion.user_id == uid).limit(1))).first()
    return fila is not None


# ---------------------------------------------------------------------------
# Para la pantalla y para Don Tino
# ---------------------------------------------------------------------------

def como_json(secciones: list[Seccion]) -> list[dict]:
    return [
        {
            "clave": s.clave, "titulo": s.titulo, "icono": s.icono, "ruta": s.ruta, "resumen": s.resumen,
            "partes": [{"titulo": p.titulo, "puntos": list(p.puntos), "numerada": p.numerada} for p in s.partes],
        }
        for s in secciones
    ]


_NOMBRE_DE_QUIENES = {AGENCIA: "las agencias", LOCAL: "los locales de Redexpres", EQUIPO: "el equipo de Tienda"}


def como_texto(secciones: tuple[Seccion, ...] = SECCIONES, base_url: str = "") -> str:
    """La guía entera para Don Tino, en markdown simple. Dice para quién es
    cada sección y cada parte, y qué permiso pide, para que no le explique a
    nadie algo que no tiene."""
    lineas: list[str] = []
    for s in secciones:
        para = ", ".join(_NOMBRE_DE_QUIENES[q] for q in (EQUIPO, AGENCIA, LOCAL) if q in s.quienes)
        cabeza = f"## {s.titulo}"
        if s.ruta:
            cabeza += f" — [{s.titulo}]({base_url}{s.ruta})"
        lineas.append(cabeza)
        datos = [f"Para {para}."]
        if s.permisos:
            datos.append("Pide " + " o ".join(f"`{p}`" for p in s.permisos) + ".")
        if s.mundos:
            datos.append("Solo en " + ", ".join(s.mundos) + ".")
        lineas.append(" ".join(datos) + " " + s.resumen)
        for p in s.partes:
            extra = []
            if p.quienes != TODOS and p.quienes != s.quienes:
                extra.append("para " + ", ".join(_NOMBRE_DE_QUIENES[q] for q in (EQUIPO, AGENCIA, LOCAL)
                                                 if q in p.quienes))
            if p.permisos:
                extra.append("pide " + " o ".join(f"`{x}`" for x in p.permisos))
            if p.mundos:
                extra.append("solo en " + ", ".join(p.mundos))
            lineas.append(f"**{p.titulo}**" + (f" ({'; '.join(extra)})" if extra else "") + ":")
            for i, punto in enumerate(p.puntos, 1):
                lineas.append(f"{i}. {punto}" if p.numerada else f"- {punto}")
        lineas.append("")
    return "\n".join(lineas).strip()
