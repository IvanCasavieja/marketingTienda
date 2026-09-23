# Calendario

Las tres partes del calendario, una debajo de la otra, en `/calendario`.

Se desarrolló aparte (carpeta `Calendario banners` del escritorio) para no
frenar lo que ya estaba andando acá, y se armó desde el principio con el mismo
stack que la plataforma — Next 16, React 18, Tailwind, zustand, lucide — así
que al entrar no hubo que agregar ni una dependencia.

## Las tres secciones

**1. Calendario comercial.** Las acciones de marketing por tipo (Mega evento,
Mailing GRAL, Especiales, Sin mailing, Actividades tácticas, Seasonal…), igual
que el Excel. Tocar una acción abre su ficha lateral.

**2. Calendario Retail Media.** Los espacios vendidos a marcas, agrupados en
eComm y Express, con un carril por slot de cada formato. `HOME SLIDER (Retail
Media)` está marcado aparte porque es el que alimenta al header.

**3. Headers de la home.** Las 10 posiciones, y abajo el conteo día por día:
verde hasta 7, ámbar en 8, rojo arriba de 8.

## La regla que no se toca

**El sistema cuenta y avisa, nunca decide qué banner bajar.** Qué se baja se
resuelve por venta, dato que la app no tiene.

Si una acción pide header y no hay posición libre, no se le saca el lugar a
nadie: la acción cae en `mes.sinLugar` y aparece un aviso rojo arriba de la
sección con qué quedó afuera y qué días estaba lleno.

## Cómo se llena el header

Casi nada se carga a mano. El header se **deriva**, desde dos lados:

- **Retail Media** → las 3 filas de `HOME SLIDER (Retail Media)` caen en las
  posiciones que RM tenga reservadas, por defecto 4, 5 y 6.
- **Marketing** → las otras 7. Cada acción que en su ficha tenga la pieza
  **Web · Home → Header** baja sola a la primera posición de marketing libre en
  todo su rango.

Una barra derivada se reconoce por el borde negro a la izquierda: no se edita
en el header, se hace clic y te lleva a donde sí se edita (el calendario de
retail o la ficha de la acción). Ese contrato vive en `OrigenHeader`, que es
`retail`, `accion` o `manual`.

## La ficha de la acción

Clic en una acción abre un panel lateral que entra desde la derecha. Adentro:
nombre, tipo, fechas y duración; el progreso de piezas publicadas; y la
estructura por áreas — **Web · Home**, **Web · Landing de la acción**,
**Físico**, **Email**, **WhatsApp**, **Push** — donde se agregan y se sacan
piezas y se les mueve el estado (pendiente → en proceso → aprobado →
publicado). Si la acción lleva header, dice en qué posición quedó, o avisa que
no entró.

Se cierra con Escape, con la X o tocando afuera.

## Permisos

Salen del usuario logueado, no de un selector de prueba. Los tres están en
`backend/app/models/role.py` y se tildan por usuario desde el panel de
administración:

| Permiso | Qué habilita |
|---|---|
| `calendario.view` | Entrar. Es el que decide si aparece el link en el menú. |
| `calendario.edit` | Crear, editar y borrar barras, y mover el estado de las piezas. |
| `calendario.retail_media` | Mover las posiciones que Retail Media tiene reservadas en el header. |

Mover las posiciones de Retail Media genera una notificación para quien lleva
Retail Media, con la misma forma que el modelo `Notificacion` del backend
(`tipo`, `mensaje`, `origen_tipo`, `origen_ref`). Hoy vive en memoria y se ve
en la campanita de la barra del calendario; cuando se persista es un POST.

## Zoom

Las tres secciones se alejan y se acercan juntas, con los botones `−` y `+`.
El porcentaje vuelve al tamaño normal si lo tocás, y el botón de las flechas
ajusta el ancho para que **el mes entero entre en la pantalla sin scroll** —
mide la caja real de una sección, por eso la página necesita el `id="calendario"`.
Al alejar, primero desaparece la inicial del día de la semana y después los
números quedan solo cada 5 días. El zoom se guarda.

Cuando no entra, cada sección tiene scroll horizontal propio y las tres se
mueven juntas; la columna de etiquetas y la fila de días quedan fijas.

## Guardado

**Todavía es `localStorage`** (clave `calendario-mktg`), o sea del navegador de
cada uno y no se comparte. Es el paso intermedio para poder usarlo ya:
`store.ts` está armado para que cambiar `localStorage` por la API sea tocar un
solo lugar.

Mientras los datos salgan de `seed.ts`, los meses que **nadie tocó** se rehacen
solos cuando se reimportan los Excel, y los que tienen ediciones a mano quedan
como están. Lo resuelve la firma `SEED_VERSION` más el flag `tocado` de cada
mes. Con datos del servidor ese mecanismo deja de tener sentido.

## Los colores

Vienen del Excel y **no cambian entre temas**: son pastel, y el texto encima se
calcula por contraste (`textoSobre` en `colores.ts`), así que se leen igual en
claro y en oscuro. Es a propósito.

## Los datos

`seed.ts` es un **muestreo** —setiembre y octubre 2026— sacado de los dos Excel
reales, para que el calendario arranque con algo que se parezca al laburo. No
es la fuente de verdad: eso va a ser el backend.

Para regenerarlo, con los dos Excel en Descargas:

```
python backend/scripts/importar_calendario_excel.py
```

Ese script es referencia de cómo se parsean esos Excel, no parte del producto.

## Estructura

```
lib/calendario/derivar.ts     LA LÓGICA: construir el mes, derivar el header, contar
lib/calendario/tipos.ts       el modelo, el catálogo de piezas y las reglas (7/8/10)
lib/calendario/rejilla.ts     medidas y zoom
lib/calendario/store.ts       estado, notificaciones, guardado
lib/calendario/permisos.ts    quién puede qué, contra el usuario de la plataforma
lib/calendario/seed.ts        datos de ejemplo generados desde los Excel + su firma
lib/calendario/colores.ts     paleta y contraste
lib/calendario/fechas.ts      meses, días de la semana, findes
components/calendario/        las 9 pantallas
app/(dashboard)/calendario/   la página
```

`derivar.ts` y `rejilla.ts` no dependen de React ni de zustand a propósito: son
lo único que hay que portar con cuidado, y así se pueden probar sin levantar
nada.

## Pruebas

```
cd frontend && npm run test:calendario
```

52 comprobaciones, sin framework: se compilan con `tsc` y corren con node.
Fijan las reglas del header y el zoom. No borrarlas al reescribirlas con otro
runner.

## Lo que falta

- **Persistencia real** contra el backend, en vez de `localStorage`. Es lo
  primero, y está aislado en `store.ts`.
- **Subtareas por pieza** (arte desktop, arte mobile, aprobación comercial) y
  responsable con vencimiento. Hoy el modelo llega hasta acción → pieza.
- **`Pieza.enSharePoint`** existe en el modelo pero no se usa en ninguna
  pantalla y no sube nada. Está puesto a futuro.
- **Los textos están solo en español.** El link del menú sí está en los tres
  idiomas; el cuerpo del calendario no.
- El **apartado Retail Media** con el resto de las hojas del Excel (campañas,
  SKUs, reportes, benchmarks).
- Vista de semana y arrastrar barras para mover fechas.
