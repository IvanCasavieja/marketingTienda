# Rendimiento

## Medir antes y después

Donald Knuth (1974): la optimización prematura es la raíz de todos los males,
pero no hay que dejar pasar el 3 % crítico. Ese 3 % se encuentra midiendo.

El protocolo para toda propuesta que prometa velocidad:

1. **La tarea y la condición**: «abrir el calendario del mes», «guardar una
   tarea», «abrir una entrega con 4 imágenes»; notebook o celular; servidor
   despierto (el dormido se mide aparte: tarda hasta ~75 s en despertar).
2. **Antes, al menos 5 veces**: mediana y peor caso (o p95 si hay muestras).
   Nunca solo el promedio: lo que se recuerda es la cola (Jeffrey Dean y Luiz
   André Barroso, *The Tail at Scale*, Google, 2013).
3. **Qué medir**: tiempo hasta que se ve y se puede usar (panel Performance,
   `performance.now()`), bytes comprimidos y sin comprimir, cantidad de
   pedidos, viajes a la base por pedido (el `echo` de SQLAlchemy en
   desarrollo), CPU del servidor.
4. **Una cosa por vez**, y después se mide igual.
5. **En el PR**: antes → después, con el método. Si no cruza un umbral que la
   persona note (abajo), la complejidad no se justifica y se vuelve atrás.

La casa escribe la medida al lado de la decisión: `/calendario/datos` pasó de
458 KB a 23 KB comprimido (`app/main.py`); la pregunta del calendario hacía 13
viajes a la base con `pool_pre_ping` (`app/core/database.py`); bcrypt bajó a 10
rondas porque cada hash tardaba ~2,5 s (`app/core/security.py`).

## Latencia percibida

Los tres límites de Jakob Nielsen (*Usability Engineering*, 1993):

- **~0,1 s** se siente instantáneo: filtrar, abrir una tarjeta, cambiar de
  pestaña. Se resuelve en el navegador con los datos que ya están.
- **~1 s** no corta el hilo del pensamiento, pero se nota: sin indicador, pero
  sin pantalla congelada.
- **~10 s** es el límite de la atención: progreso visible y poder hacer otra
  cosa. Lo que tarda eso o más (análisis con IA, render de cenefas, subir un
  ZIP) es un trabajo con estado que sobrevive a navegar y a un reinicio.

Además:

- **Que se vea que está trabajando** pasado ~1 s. La queja de Ivan que llevó a
  bajar bcrypt fue esa: «no me muestra que esté cargando y demora».
- **UI optimista** (mostrar el cambio antes de que el servidor confirme, con
  vuelta atrás y aviso si falla): solo para lo que falla poco y se deshace,
  como la cola del calendario. Nunca para aprobar una entrega o mandar un mail.
- **Core Web Vitals** de Google, en el percentil 75: LCP ≤ 2,5 s, INP ≤ 200 ms,
  CLS ≤ 0,1. En una herramienta de trabajo el que más importa es INP: cuánto
  tarda en responder a un clic. Reservar ancho y alto de imágenes evita saltos
  (CLS).

## Navegador o servidor

- El servidor es una décima de procesador para todos; cada navegador tiene un
  procesador entero para una persona. **La CPU que depende solo de los datos
  de esa persona va al navegador**, como la compresión de imágenes, los ZIP
  (`frontend/lib/calendario/zip.ts`) y el lector de Clientes VIP en un Web
  Worker (`frontend/lib/clientes-vip/lector.worker.ts`).
- **Se queda en el servidor**: permisos, la validación que protege datos (el
  servidor vuelve a controlar tamaños), lo que usa claves (la IA) y lo que tiene
  que ser igual para todos.
- **CPU pesada en el servidor, nunca en el loop de eventos**: a un hilo, como
  `hash_password_async`. Con 0,1 CPU el hilo no suma procesador, solo evita
  frenar a los demás. Lo largo, como job con estado en la base.
- **Hilo principal del navegador**: las tareas de más de 50 ms empeoran INP;
  leer un Excel o un CSV grande va en un Worker.
- **Paquete de JavaScript**: `xlsx`, `konva` o `recharts` se cargan con
  `import()` o `next/dynamic` en la pantalla que los usa, no en el layout común.

## Caché

- Primera pregunta: **qué puede estar viejo, cuánto tiempo y quién lo ve.** Un
  caché mal pensado es una filtración (alguien ve lo de otro) o un dato viejo.
- **HTTP (RFC 9111)**: lo que nunca cambia y se pide por id, `private,
  max-age=31536000, immutable` (ya se usa en las imágenes de entregas); lo
  confidencial, `no-store` (Clientes VIP, adjuntos); nada con login, `public`.
- **Pedidos condicionales**: la `rev` del calendario es un GET condicional
  propio (contesta `sinCambios`), el equivalente a un ETag con `If-None-Match`
  y 304. Extendé ese patrón antes de inventar otro.
- **En memoria del servidor**: vale porque hay un solo proceso, pero se pierde
  en cada reinicio y cada vez que Render se duerme. Solo para lo caro que se lee
  mucho y cambia poco, con vencimiento e invalidación al escribir. Sin Redis.
- **En el navegador**: localStorage para pintar al instante y después manda el
  servidor (el calendario guarda solo los meses cerca del que se mira: el mundo
  entero llenaba el almacenamiento). Nunca es la única copia de lo que la
  persona escribió, salvo que una cola lo suba.

## Paginación y tamaño de las respuestas

- **Toda lista que crece** (tareas, historial, auditoría, avisos, entregas)
  tiene tope en el servidor y orden estable con desempate único
  (`created_at, id`).
- **Offset o keyset**: el offset sirve cerca del principio (listas de admin);
  para listas largas o que cambian mientras se recorren, keyset (Markus Winand):
  `WHERE (created_at, id) < (:ultimoCreado, :ultimoId) ORDER BY created_at DESC, id DESC LIMIT :n`.
  El `page_token` opaco de AIP-158 deja cambiar de uno a otro sin romper al front.
- **No mandar lo que no se muestra**: miniaturas de 320 px en las listas, la
  imagen grande a pedido, los bytes `deferred`.
- **Compresión**: GZip desde 1 KB (`app/main.py`); el streaming de eventos
  queda sin comprimir para que llegue en vivo.
- **Preguntar cada tanto**: el calendario pregunta cada 15 s y no pregunta con
  la pestaña oculta (`visibilityState`, igual que `MiAgenda.tsx` y
  `VistaEntregas.tsx`). Un poll nuevo reusa la revisión o se justifica.

## El checklist

- ¿Hay medida de antes, y se va a medir después de la misma forma?
- ¿Suma consultas a `get_current_user` o a la revisión del calendario?
- ¿Consultas en un bucle, listas sin tope, columnas pesadas sin `deferred`?
- ¿CPU pesada en el servidor que podría ir al navegador?
- ¿Se ve que algo está pasando si tarda más de 1 s?
- ¿El caché puede mostrar datos de otra persona, o viejos?
- ¿Suma una dependencia pesada al paquete común?

## Fuentes

- Donald Knuth, «Structured Programming with go to Statements», *Computing Surveys* (1974).
- Jeffrey Dean y Luiz André Barroso, «The Tail at Scale», *CACM* (2013).
- Jakob Nielsen, *Usability Engineering* (1993).
- Google, Core Web Vitals (LCP, INP, CLS); AIP-158 (paginación).
- IETF, RFC 9111 (HTTP Caching); Markus Winand, Use The Index, Luke.
