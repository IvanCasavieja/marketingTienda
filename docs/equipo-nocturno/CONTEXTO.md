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
- Una copia de prueba / staging.
- Purgas de imágenes de entregas.
- Tratar a «Diseñadores» como gente de Tienda.
- Mejoras inventadas que no le sirven a nadie. Cada propuesta responde a una
  necesidad concreta de alguien que usa la plataforma.

## De dónde sacar necesidades

- Las reuniones a las que mandaron a Claude (conector Meetings), si hay.
- Los issues abiertos del repo.
- `PENDIENTES.md` (ojo: es del 01/09/2026 y una parte ya se hizo).
- El código: cosas a medio hacer, textos confusos, pantallas que traban,
  errores que no se avisan, pruebas que faltan en algo importante.
- La visión de arriba: qué le falta a la plataforma para ser el hilo conductor
  de promo y marca.
