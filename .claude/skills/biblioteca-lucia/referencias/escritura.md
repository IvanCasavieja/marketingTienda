# Escritura en la interfaz (UX writing)

El texto es interfaz: buena parte de lo que encontró la auditoría son
palabras (jerga, inglés, errores que no dicen qué hacer, dos nombres para lo
mismo). Referencias públicas: Microsoft Writing Style Guide, la sección de
escritura de Material, el contenido de GOV.UK (lenguaje claro), Mailchimp
Content Style Guide; libros: Torrey Podmajersky, *Strategic Writing for UX*, y
Kinneret Yifrah, *Microcopy: The Complete Guide*.

## La voz de Core Tienda

- Castellano rioplatense con «vos»: «Ingresá», «Probá de nuevo»,
  «Pedíselo a quien administra Core Tienda».
- Las palabras de la gente (glosario abajo). Sin jerga técnica ni inglés
  suelto («Sync datos», «Account ID», «Viewer», «done», «pending»).
- Corta y en orden: primero lo importante, después el detalle.
- Amable sin chistes, sin signos de exclamación ni emojis. Los errores no
  culpan: «No pudimos guardar», no «Ingresaste mal».
- Sin género cuando se puede: «Te damos la bienvenida» o «Hola, Ana» en vez
  de «Bienvenido» (hoy en el login).
- Sin marketing adentro de la herramienta: quien la usa ya la eligió.
- Todo texto va en los tres idiomas (`frontend/lib/locales/es.json`,
  `en.json`, `pt.json`), nunca fijo en el componente. Las traducciones no
  miden lo mismo que el castellano: probá los tres y dejá lugar para el más
  largo.

## Glosario: lo mismo se llama igual en todas partes

| Decí | No digas | Nota |
|---|---|---|
| acción | evento, campaña (fuera de Medios) | lo que va en el calendario |
| tarea | ticket, job, subtarea | una tarea = un pedido, todas en un nivel (24/11/2026) |
| pieza | asset, creatividad | banner, placa, cenefa |
| entrega, versión | upload, ronda | la pantalla dice «versión» desde el PR #86 |
| tablero, tarjeta | board, card | |
| local | «sucursal» para lo mismo | en los textos de Redexpres hoy conviven las dos para el mismo lugar; `criterios.md` toma «local». En Precios, «sucursal» es la de una cadena y ahí sí va |
| mundo | workspace | Tienda Inglesa, Express, Redexpres, Viajes, Farma |
| avisos | notis, notificaciones y avisos mezclados | la auditoría propone «Avisos»; hoy conviven los dos nombres |
| plantilla, historial, informe, clics | template, jobs, report, clicks | |

## Botones, etiquetas y links

- **Botón = verbo + objeto:** «Crear tarea», «Entregar versión 2», «Pedir
  cambios»; el verbo solo, si el objeto es obvio en esa pantalla («Aprobar»).
  Nunca «Aceptar», «OK», «Sí» o «Enviar» a secas.
- El botón repite el verbo de la pregunta: si el título dice «¿Borrar la
  acción?», el botón dice «Borrar acción».
- Etiquetas de campo: sustantivo corto («Fecha de entrega»), sin dos puntos,
  con mayúscula solo al principio.
- Opciones que no se pisen: «Otro» y «Otra cosa» juntos (H-047) es una de más.
- Links que dicen adónde llevan: «Ver la tarea», no «Hacé clic acá».
- Íconos acompañados de texto, salvo los universales (cerrar, buscar).
- Títulos de 1 a 3 palabras; si hace falta un subtítulo, una línea.

## Mensajes de error que dicen qué hacer

Estructura: **qué pasó** + (si ayuda) **por qué** + **qué hacer**, en el lugar
del problema.

| Hoy | Mejor |
|---|---|
| «Error desconocido» al generar cenefas (H-008) | «No pudimos generar las cenefas. Probá de nuevo; si vuelve a pasar, avisale a quien administra Core Tienda con el nombre de la plantilla.» |
| «Contraseña incorrecta» cuando falta un permiso (H-013) | «Tu cuenta puede ver las conexiones pero no cambiarlas. Pedíselo a quien administra Core Tienda.» |
| «404 This page could not be found» (H-058) | «Esta página no existe. Puede ser un link viejo o mal copiado.» + «Ir al inicio» |
| «Token inválido o expirado» | «El link para cambiar la contraseña venció. Pedí uno nuevo.» + el botón |
| Un borde rojo sin texto | «Falta la fecha de entrega», debajo del campo |
| Un error técnico en inglés al buscar precios (H-045) | «No encontramos ese producto. Probá con otra palabra o con el código.» |

- Sin códigos (403, 422) ni textos técnicos a la vista; si sirven para
  soporte, en un «Ver detalle» plegado.
- Si falló el sistema, decilo («No pudimos…»). Si es un dato, decí cuál y
  cómo tiene que ser: «La fecha de fin tiene que ser posterior al 1/12».
- Nada de «inválido», «error fatal» u «operación fallida»: no dicen qué hacer.

## Estados vacíos

Estructura: **qué va acá** + **cómo se llena** (el botón). Opcional: una
línea de por qué está vacío.

- Primera vez: «Todavía no hay acciones en diciembre.» + «Nueva acción».
- Sin resultados por un filtro: «No hay tareas con estos filtros.» +
  «Limpiar filtros».
- Todo al día: «No tenés tareas pendientes.» (sin confeti).
- Sin permiso: «No tenés acceso a Precios. Si lo necesitás, pedíselo a quien
  administra Core Tienda.» + «Volver al inicio».

Errores típicos: «Nada por acá.» (no dice qué ni cómo); ilustraciones
grandes; párrafos; el mismo cartel para «no hay nada» y «no hay resultados».

## Avisos, confirmaciones y esperas

- **Éxito:** lo que pasó + lo que sigue. «Entrega enviada. Tienda ya tiene el
  aviso.»
- **Confirmación:** la pregunta con el objeto y la consecuencia. «¿Borrar
  “Black Friday 2026”? Se borran también sus 3 tareas.»
- **Espera:** gerundio con el objeto («Generando 48 cenefas…»); si puede
  tardar, cuánto: «El servidor se está despertando; puede tardar hasta un
  minuto.»
- **Deshabilitado:** decí qué falta. «Completá la vigencia para generar.»

## Formatos

- Fechas: «25/11/2026» o «25 de noviembre»; lo reciente, «hace 5 minutos».
  Días y meses en minúscula: «miércoles 25 de noviembre», no «Miércoles 25 De
  Noviembre» (Dashboard).
- Números a la uruguaya: punto de miles y coma decimal (1.234,50).
- Plurales bien hechos: «1 acción», «2 acciones» (hoy aparecen «1 acciones» y
  «1 días»). Con i18n, usá las formas de plural, no el número pegado a una
  palabra fija.
- Mayúscula solo al principio en títulos, botones y menú.
