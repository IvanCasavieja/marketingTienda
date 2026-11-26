# Lo que el equipo nocturno tiene que saber de Core Tienda

## Qué es

Core Tienda (antes "MKTG Platform"; el repo se llama `marketingTienda`) es la
plataforma del área de **promo y marca** de Tienda Inglesa (supermercados,
Uruguay). La construyó Ivan, de marketing digital, trabajando con Claude.

- Backend: FastAPI en `backend/` (migraciones Alembic en `backend/migrations`).
- Frontend: Next.js en `frontend/` (páginas en `frontend/app/(dashboard)/`).
- Producción: API en Render (plan gratis), front en Vercel, base Postgres en
  Supabase (plan gratis: 500 MB para todo).
- Don Tino: el asistente con IA dentro de la plataforma (usa la API de Claude).

## Hacia dónde va (Ivan, 15/11/2026)

- **El core de las acciones.** El calendario y las tareas son el hilo conductor
  de todo lo que hace promo y marca. Diseño propio y a medida, no "un calendario
  más".
- **Referencia funcional: COR** (projectcor.com, gestión de proyectos para
  agencias). Se toma cómo funciona, no su diseño: a Ivan le parece espantoso y
  la gente se traba.
- **Entregas por fases con rondas de corrección** con las agencias, como
  tarjetas de Trello (tablero en `/entregas`): se entrega, se aprueba o vuelve
  con correcciones, hasta que se aprueba.
- **Agencias externas con vista limitada.**
- **Más adelante:** Azure con los usuarios Microsoft de la empresa
  (`docs/AZURE.md`) y las imágenes aprobadas en SharePoint.
- Le importan: seguridad, diseño, que ande rápido y funcionalidades que la
  gente use de verdad.

## Qué queremos que surja (la vara)

Core Tienda tiene que sentirse como **un producto profesional**, no como una
herramienta interna armada de a pedazos. Concretamente:

- **Una persona nueva la entiende sola.** Alguien de una agencia entra por
  primera vez y en un minuto sabe qué le pidieron, para cuándo y cómo
  entregarlo, sin que nadie le explique. Lo mismo un encargado de local con
  su pedido del mes.
- **El equipo sabe en 10 segundos qué le toca hoy** y qué está atrasado, y
  hace lo de todos los días (cargar una acción, pedir una pieza, revisar una
  entrega) en pocos pasos y sin ir y volver entre pantallas.
- **Nada queda en el aire.** Cada acción avisa qué pasó; cada error dice qué
  hacer; cada pantalla vacía explica qué va ahí; lo que hace uno le llega al
  otro (equipo ↔ agencia ↔ local).
- **Pareja en todas partes.** El mismo botón, el mismo encabezado, el mismo
  cartel para lo mismo en todas las pantallas; las pantallas viejas se van
  pareciendo a las nuevas (las del calendario).
- **Se lee bien:** contraste alto, letra que no obliga a acercarse, textos
  completos, en notebook de oficina y en el celular, claro y oscuro.
- **Rápida y confiable:** nada se pierde (lo escrito, las imágenes), nada
  tarda sin avisar.

El Equipo nocturno trabaja para acercar la plataforma a esto cada noche, con
pruebas de que lo que cambia se nota para una persona. Las personas para
quienes se mira (analista de promo y marca, agencia, local, jefatura) están
en `.claude/skills/recorrido-humano/criterios.md`.

## Quién la usa

- **El equipo de Tienda (promo y marca):** calendario por mundos, mis tareas,
  entregas, cenefas, precios, colocación (fotos de locales), Don Tino.
- **Agencias EXTERNAS:** Publicis, Another Monday y «Diseñadores».
  **«Diseñadores» es el nombre de una agencia externa, NO son diseñadores de
  Tienda.** Las tres se tratan igual: cuentas externas que ven solo su tablero.
  Nunca proponer casos especiales para «Diseñadores».
- **Sucursales (Redexpres):** logins por local.

## Reglas que no se discuten

- **Logo:** la margarita COMPLETA, con 7 pétalos azules (`#0047BA`) alrededor
  de la "i" roja (`#F6323E`). La de 5 pétalos está mal y no se usa nunca. Está
  en `frontend/app/icon.svg` y la cuida `backend/tests/test_logo_margarita.py`.
- **Las imágenes de las entregas NO se borran nunca.** Son el histórico (irán a
  SharePoint por año). Nada de purgas automáticas de imágenes de entregas. El
  único freno es `BASE_TOPE_MB` en `backend/app/services/espacio.py`: deja de
  guardar y avisa, no borra.
- **Espacio:** la base tiene 500 MB para todo. Lo que guarde datos tiene que
  ser liviano (las imágenes se comprimen en el navegador).
- **Nada de planes pagos.** No proponer pasar Render o Supabase a pago ni
  cambiar de proveedor. Solo mejoras que se hagan en el código.
- **Vocabulario:** camelCase en todo (hay una prueba que lo controla). Nombres
  textuales de variables (`tipoOferta`, `unidadMoneda`). Nada de jerga en la
  pantalla.
- **Contraste alto:** se usa con luz de oficina y ojos cansados. Todo bien
  visible en modo claro y oscuro.
- **Notebook y celular:** todo tiene que andar en las dos, iPhone/Safari
  incluido.
- **Cenefas:** las reglas de las descripciones están en `_STYLE_RULES`
  (`backend/app/services/cenefas/convertidor_ai.py`) con la historia de cada
  decisión. La marca nunca se deduce. No tocarlas sin un pedido de Ivan.

## Ya decidido: NO proponer

- Que el repo sea público, las contraseñas de los logins de los locales, rotar
  claves, que Supabase esté en una cuenta personal. Ivan lo decidió: no se hace.
- Planes pagos o cambio de proveedor (Render, Supabase, Vercel).
- Plantillas con opciones para tildar («la agencia ya recibe el pedido como
  debe recibirlo»).
- Purgas de imágenes de entregas.
- Tratar a «Diseñadores» como gente de Tienda.
- Volver a anidar tareas: subtareas, piezas adentro de una tarea o una tarea
  "de afuera". Desde el 24/11/2026 una tarea = un pedido, todas en un solo
  nivel (Ivan: "tener así dividido en tarea, pedido de piezas y luego
  subtareas me parece al pedo y confuso"; migración 0090).
- Sacar Medios (`/dashboard`, `/analytics`, `/campaigns`, `/canales`) o
  Finanzas (`/facturacion`) del menú: siguen por decisión de Ivan (20/11/2026).
  Sí se puede mejorar cómo se ven.
- Volver a guardar historial de las validaciones de RRSS. Desde el 26/11/2026
  cada validación dura 24 horas («Las de hoy», para terminar de revisarla ese
  día) y después se borra entera, con sus imágenes (Ivan, con 73 MB de
  validaciones en la base: «no tiene sentido que mantengamos historial de
  validaciones»).
- Volver a poner tipos o plantillas de cenefa en Tienda Inglesa. Ivan los
  borró el 26/11/2026 («el resto elimina todos los submundos esos de cenefas
  porque no se van a usar»; migración 0094): las cenefas que se usan son las de
  Redexpres. Que Tienda Inglesa no tenga tipos de cenefa es lo esperado.
- Mejoras inventadas que no le sirven a nadie. Cada propuesta responde a una
  necesidad concreta de alguien que usa la plataforma.

## Cambios recientes que hay que conocer (24/11/2026)

- **Una tarea = un pedido** (migración 0090): todo en un solo nivel, con su
  responsable de Tienda.
- **Adjuntos en el pedido** de una tarea (migración 0089), por ejemplo el
  Excel con lo que hay que hacer.
- Los **cambios pedidos** a la agencia se ven **en rojo**, y el análisis de
  las entregas (lo que ve la IA) es **solo para Tienda**.
- La contraseña se cambia cada **60 días**; el botón Herramientas cierra
  siempre.
- **Redexpres guarda lo último** que escribe el local (antes podía perder la
  última tecla).
- Existe el **entorno de pruebas** con tres cuentas (README, *La plataforma
  andando*) y el **cuaderno de hallazgos** (rama `equipo-nocturno/cuaderno`).

## De dónde sacar necesidades

- **Usar la plataforma** como cada persona (skill `recorrido-humano`): es la
  fuente principal.
- **El cuaderno de hallazgos** (lo que ya se vio otras noches, ordenado por
  prioridad).
- Las reuniones a las que mandaron a Claude (conector Meetings), si hay.
- Los issues abiertos del repo.
- El mapa de la plataforma (`plataforma/`): sus «puntos a mirar» son
  sospechas leyendo el código, para confirmar en la pantalla.
- La vara de arriba: qué le falta a la plataforma para sentirse profesional.
- `PENDIENTES.md` es del 01/09/2026 y está viejo: no lo uses.
