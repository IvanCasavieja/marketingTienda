# Sistemas de referencia y el sistema propio

## Qué tomar de cada sistema (y qué no)

Ningún sistema se copia entero: se toma de cada uno lo que mejor resuelve un
problema de Core Tienda. Todos son públicos; las versiones cambian, así que el
detalle fino (valores exactos, componentes nuevos) verificalo en la web.

| Sistema | Qué tomar | Qué no tomar |
|---|---|---|
| **Material Design 3** (Google) | Colores con **rol** y nombre (*primary*, *on-primary*, *surface*, *outline*, *error*): cada color dice para qué es. Escala tipográfica por función (*display*, *headline*, *title*, *body*, *label*). **Capas de estado**: hover, foco y presionado como una capa encima del mismo color, no un color nuevo por estado. Grilla de 8 dp, objetivos de 48 dp. | El color dinámico (Material You), los radios grandes y lo expresivo: Material 3 Expressive (2025) suma color, forma y movimiento pensando en apps de consumo (verificá en la web su estado). |
| **Human Interface Guidelines** (Apple) | La **deferencia**, uno de los temas clásicos de la HIG: la interfaz se corre para que se luzca el contenido (acá, las piezas de las agencias). Colores semánticos (*label*, *secondaryLabel*, *systemBackground*) que cambian solos en oscuro. 44 pt para tocar. Hojas que suben en el celular. Estilo destructivo para borrar. Respetar los ajustes de la persona: tamaño de letra, reducir movimiento, más contraste. | Liquid Glass (2025: translucidez y desenfoque): en la web baja el contraste y pesa en celulares modestos (verificá en la web). |
| **Fluent 2** (Microsoft) | Es el idioma de Outlook, Teams y SharePoint, lo que la gente de Tienda usa todo el día, y Core Tienda va hacia Azure y SharePoint (`docs/AZURE.md`): parecerse en **patrones** (no en marca) baja lo que hay que aprender. Tokens en capas: globales y *alias* con significado (`colorNeutralForeground1`, `colorBrandBackground`). Rampa de marca de 16 tonos. Pocas sombras, atadas a la altura. Microsoft Writing Style Guide. Inclusive Design: discapacidad permanente, temporal y **situacional** (ojos cansados, una mano ocupada en el local). | Las transparencias (acrílico, mica) y el aspecto de Windows. |
| **Carbon** (IBM) | Lo mejor para pantallas densas: **tablas de datos** (alturas de fila, barra de herramientas, búsqueda, acciones en lote, orden), patrones de **vacío, carga y notificaciones**, indicadores de estado con forma + color + texto. Estilos **productivos** contra **expresivos**. Temas oscuros grises, no negros, con capas para la jerarquía. El checklist de IBM Equal Access. | IBM Plex y la estética de IBM. |
| **Atlassian Design System** | Atlassian hace Jira y Trello, y el Tablero de Core Tienda se pidió con tarjetas como las de Trello (Ivan): es la referencia directa para tableros, tarjetas y estados. *Lozenges* (estado sobrio, en texto). Tokens de espacio (`space.100` = 8 px) y de elevación (*surface*, *sunken*, *raised*, *overlay*). Guías de contenido para vacíos, errores y botones. Arrastrar con alternativa sin arrastre. | Las ilustraciones y personajes de marketing. |

Para herramientas sobrias, mirá también **GOV.UK Design System** (formularios,
errores y lenguaje claro: el mejor modelo de «tranqui y legible»), **Primer**
(GitHub) y **Polaris** (el admin de comercios de Shopify).

**Cómo leer un sistema ajeno:** andá a los fundamentos (color, letra,
espacio) y a los patrones (formularios, vacíos, errores), no a la galería de
componentes. Buscá el porqué de cada regla: si el porqué no aplica a Core
Tienda, la regla tampoco. Si dos sistemas discrepan (48 dp contra 44 pt),
manda la regla de Core Tienda (44 px), con el piso de WCAG (24 px).

## El sistema de Core Tienda

### Tokens en tres capas

El término *design tokens* nació en Salesforce (Lightning Design System) y hoy
hay un formato común en el W3C Design Tokens Community Group (verificá en la
web en qué estado está).

1. **Primitivos** (valores): `azul-700 = #0047BA`, `gris-900 = #18181B`.
   Ninguna pantalla los usa directo.
2. **Semánticos** (para qué): `marca`, `marca-suave`, `texto`, `texto-2`,
   `fondo`, `superficie`, `borde`, `borde-control`, `peligro`, `exito`,
   `atencion` (la paleta del `SKILL.md`). Cada uno tiene su valor claro y
   oscuro. Las pantallas usan estos.
3. **De componente**, solo si hace falta: `boton-principal-fondo = marca`.

**En el repo:** los valores viven en `frontend/tailwind.config.ts` (hoy
`brand` es el índigo, con 1.252 usos) y en `frontend/app/globals.css`.
**Cambiá el valor del token, no las 1.252 clases:** así el cambio llega a
todas las pantallas de una vez (la Tanda 2 del informe). Para el oscuro,
variables CSS bajo `html.dark` en lugar de repetir `dark:` en cada clase. Las
clases propias siguen el estilo de las que ya hay, en castellano (`.campo`,
`.etiqueta-campo`, `.boton-icono`, `.segmentado`, `ease-suave`).

### Componentes

- Uno por función. Antes de crear, buscá en `frontend/components/` y en
  `globals.css`; si hay dos versiones, unificá hacia la del núcleo
  (calendario, Mis tareas, tablero) y anotá cuál se va.
- De lo chico a lo grande (Brad Frost, *Atomic Design*): primero botón, campo
  y etiqueta; después la fila de una tarea, el encabezado de pantalla, el
  cartel de vacío; recién al final la pantalla entera.
- Cada componente define **todos** sus estados: normal, al pasar el mouse,
  foco, presionado, deshabilitado, cargando, error. Si falta uno, cada
  pantalla lo inventa: así nacieron los tres botones principales, los dos
  campos y las dos ventanas (`entrada-admin-diseno.md`, §4.9). Y se documenta
  con cuatro cosas: para qué sirve, cuándo no usarlo, sus estados y un
  ejemplo en una pantalla real.
- Deshabilitado en gris (no violeta lavado) y diciendo qué falta, o mejor:
  habilitado y que al tocarlo marque lo que falta (`usabilidad.md`).
- Radios en Tailwind: `rounded-md` = 6 px, `rounded-lg` = 8 px. El
  `rounded-2xl` (16 px) de hoy es parte de la «cara de IA».
- Sombras: hoy hay tres escalones (`shadow-card`, `shadow-pop`,
  `shadow-panel`) más dos que sobran (`glow`, `brand`) y `shadow-xl` suelto.
  Con la dirección nueva, `.card` pierde la sombra (solo borde) y quedan las de
  lo que flota.

### Los estados de toda pantalla

| Estado | Cómo va en Core Tienda | Error típico de hoy |
|---|---|---|
| Cargando | Esqueleto con la forma de lo que viene (núcleo). Circulito solo para acciones. Botón «Guardando…» y bloqueado contra el doble clic | Conexiones muestra el vacío mientras carga y parece que no hay nada |
| Vacío | Ícono gris de línea + una frase de qué va acá + la primera acción (el modelo es Colocación) | «Nada por acá.» en caja punteada; texto gris de 1,5:1 (H-031) |
| Vacío por filtro | «No hay tareas con estos filtros» + «Limpiar filtros» | El mismo cartel que «no hay nada» |
| Error | Qué pasó y qué hacer, en criollo, al lado de lo que falló; el aviso rojo flotante solo si no hay otro lugar | El mensaje técnico («Algo salió mal» con el error crudo; el 404 en inglés, H-058) |
| Sin permiso / otro mundo | Un solo cartel: ícono gris, una frase, «Volver al inicio» (`SinAcceso.tsx`, `FueraDeMundo.tsx`) | Tres carteles distintos y alguno sin salida (H-003) |
| Mucho contenido | Buscar, paginar, cortar con criterio, nombres largos en dos renglones | Diseñar con tres datos de ejemplo (60 locales sin buscador, H-044) |
| Servidor dormido | Decir que se está despertando y que puede tardar hasta un minuto (Render gratis) | El logo girando un minuto sin explicación (solo el login lo avisa) |

### Mantenerlo vivo

- Una sola fuente: si cambia un valor, cambia en el token, con un comentario
  que diga el porqué y la fecha (como ya se hace en el repo).
- Lo nuevo se hace con el sistema nuevo; lo viejo se va pareciendo de a una
  pantalla por mejora.
- Al terminar, buscá restos: `bg-gradient`, `shadow-xl`, `shadow-glow`,
  `backdrop-blur`, `text-[9px]`, `text-[10px]`, `text-[11px]`,
  `uppercase tracking`, `rounded-2xl`, `text-slate-400` en texto que importa.
- Medí y contalo en el informe: «`text-[9px]`: de 26 usos a 0».
