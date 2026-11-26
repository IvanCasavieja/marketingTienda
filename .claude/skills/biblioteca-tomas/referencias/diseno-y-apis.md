# Diseño de software y de APIs

## La complejidad: qué buscar (Ousterhout)

*A Philosophy of Software Design* (John Ousterhout) define la complejidad como
todo lo que hace difícil entender y cambiar un sistema. Tres síntomas: la
**amplificación del cambio** (algo chico toca muchos lugares), la **carga
cognitiva** (hay que saber demasiado) y **lo que no sabés que no sabés** (no es
obvio qué tocar: el peor). Dos causas: dependencias y oscuridad.

- **Módulos profundos**: interfaz chica, mucho resuelto adentro.
  `exigir_lugar(db, bytes)` (`app/services/espacio.py`) es una línea para quien
  llama y adentro mide la base, compara con el tope, loguea y corta con 507;
  `_barra_o_404` (`routes/calendario.py`) junta existencia, mundo, alcance y
  cuenta externa. Lo contrario, el **módulo playo**: una función que solo le
  pasa los mismos argumentos a otra.
- **Filtración de información**: la misma decisión en dos lugares. Acá pasa
  cuando hay dos lenguajes: los mundos en `app/core/mundos.py` y
  `frontend/lib/mundos.ts`; los permisos de externos en `externos.py` y en la
  regla de la 0069. Si un plan suma otro caso, pedí el aviso en los dos lados y
  una prueba que los ate (como el chequeo contra `ORDEN_EXPORT` en
  `cenefas_convertidor.py`).
- **Bajar la complejidad**: que sufra el módulo y no cada uno que lo usa.
- **Definir los errores para que no existan**: el alta con id del front hace
  que un reintento no duplique (devuelve `yaExistia`).
- **Diseñalo dos veces**: el plan nombra la alternativa descartada y por qué.
- **Estratégico, no táctico**: Ousterhout propone invertir en diseño de forma
  chica y constante (habla de un 10–20 % del tiempo). En una noche: el arreglo
  y la limpieza mínima que deja el lugar mejor, no un refactor aparte.

Señales de alarma del libro, para el diff: módulo playo, filtración,
descomposición temporal (partir por «primero esto, después aquello» y no por
lo que sabe cada parte), sobreexposición, método que solo pasa argumentos,
repetición, mezcla de lo general con lo particular, comentario que repite el
código, nombre vago o difícil de elegir, código no obvio.

## Acoplamiento, cohesión y límites

- **Cohesión**: lo que cambia junto vive junto. **Acoplamiento**: cuánto tiene
  que saber un módulo de otro. Vienen de *Structured Design* (Stevens, Myers y
  Constantine, IBM Systems Journal, 1974).
- **Parnas** (1972): partí por las decisiones que pueden cambiar y escondé cada
  una en un módulo. Prueba: «si mañana cambia X (el alcance pasa a semanas, un
  mundo nuevo, la entrada con Microsoft), ¿cuántos archivos se tocan?».
- **Integridad conceptual** (Fred Brooks, *The Mythical Man-Month*, desde el
  OS/360 de IBM): el mismo problema se resuelve igual en todo el sistema. Es la
  cara técnica de «pareja en todas partes»: un helper de permisos, un formato
  de error, un patrón de revisión.
- **Núcleo puro, cáscara con efectos** (Gary Bernhardt): la regla en funciones
  puras con pruebas; base y red en una capa fina. La casa ya lo hace.

| Capa | Dónde | Qué va | Qué no va |
|---|---|---|---|
| HTTP | `backend/app/api/routes/` | validación (pydantic), permisos, códigos, armar la respuesta | reglas de negocio largas |
| Negocio | `backend/app/services/` | reglas, trabajos, avisos, espacio | detalles de HTTP |
| Transversal | `backend/app/core/` | sesión, permisos, mundos, alcance, externos, base, límites | lógica de una pantalla |
| Datos | `backend/app/models/`, `backend/migrations/versions/` | tablas e historia del esquema | lógica |
| Pantallas | `frontend/app/(dashboard)/` | componer | reglas que deciden |
| Lógica del front | `frontend/lib/` | reglas puras con su `.test.ts` | llamadas sueltas a la API |
| Estado | `frontend/store/`, `frontend/lib/calendario/store.ts` | estado y sincronización | permisos (solo esconden) |

## El chequeo de cada endpoint

De las guías públicas de Google (AIP) y Microsoft (REST API Guidelines),
filtrado a lo que sirve con un solo cliente, nuestro front:

1. **Recurso y método**: obtener, listar, crear, actualizar, borrar (AIP-131 a
   135); lo que no encaja, un método propio explícito (AIP-136), como `POST
   /calendario/barras/{id}/copiar`. Nunca se escribe con GET: saltea el freno de
   CSRF y una precarga del navegador lo dispara.
2. **Actualizar es parcial**: PATCH con solo los campos que vienen (AIP-134;
   Microsoft usa JSON Merge Patch, RFC 7396). Hasta el 28/09/2026 un PUT subía
   el mes entero del calendario y dos personas se pisaban.
3. **Listas acotadas**: tope del servidor y orden estable (AIP-158, `page_size`
   y `page_token`; Microsoft, `nextLink`). En la casa, `Query(50, ge=1, le=200)`.
4. **Errores para la persona**: el formato de FastAPI, `{"detail": ...}`, que el
   front traduce (`textoDeErroresDeValidacion` en `frontend/lib/api.ts`); si
   algún día se unifica, RFC 9457 y AIP-193. Códigos: 400/422 dato mal; 401 sin
   sesión; 403 sin permiso; 404 no existe **o no lo podés ver**; 409 choca con
   el estado; 412 copia vieja; 429 límite; 507 sin lugar; 503 degradado.
5. **Reintentos sin duplicar**: GET, PUT y DELETE son idempotentes (RFC 9110);
   POST no. Si el front reintenta, el alta lleva id del cliente: la idea del
   `request_id` de AIP-155 y de la `Idempotency-Key` de Stripe.
6. **Dos personas a la vez**, de lo simple a lo pesado: cambios por campo;
   bloquear la fila (`with_for_update`, ya usado); versión o ETag con
   `If-Match` y 412 si cambió (AIP-154, Microsoft). Lo mínimo que evite el
   pisotón que de verdad pasa.
7. **Lo que no se ve no viaja**: el filtro va en la consulta
   (`externos.condicion_tarea_propia`), no después en Python (OWASP API3).
8. **Nombres**: camelCase en el JSON (regla del repo, con prueba; Microsoft
   pide lo mismo) y textuales: `tipoOferta`, no `tOf`.
9. **Permiso en la firma**: `Depends(require_permission("..."))`, más mundo,
   alcance y cuenta externa para el objeto (`seguridad.md`).

## Versionado y compatibilidad

Los hechos:

- Al mergear, Vercel publica el front y Render el back, cada uno a su ritmo.
- Las pestañas quedan abiertas horas con el JavaScript viejo, y el navegador
  guarda datos con la forma vieja (el store del calendario).
- **Ley de Hyrum** (Hyrum Wright, *Software Engineering at Google*): con
  suficientes usuarios, alguien depende de todo comportamiento observable: un
  orden, un campo nulo, el texto de un error.
- **Pydantic descarta en silencio** los campos que no conoce (`extra="ignore"`,
  lo por defecto). Ya costó: `tipoOferta` se perdía y el Excel salía sin esa
  columna (`cenefas_convertidor.py`). Un front nuevo que le manda un campo a un
  back viejo pierde el dato sin error.

Las reglas:

- **En un paso, solo cambios que agregan**: campo opcional, endpoint, un valor
  más. Nunca en un paso: renombrar o quitar un campo, cambiarle tipo o
  significado, volver obligatorio algo que el front viejo no manda, cambiar un
  código de estado del que el front depende (AIP-180 define qué rompe).
- **Lo que rompe va en dos PR** (*Parallel Change*, Danilo Sato en el sitio de
  Martin Fowler): el back entiende lo viejo y lo nuevo y el front pasa a lo
  nuevo; publicado eso, y con al menos un día hábil por las pestañas viejas, se
  quita lo viejo.
- **Primero el back**: si un PR toca los dos lados, el front anda aunque el back
  nuevo no esté (si falta el campo, no muestra lo nuevo), o se parte en dos.
- **Lector tolerante** (Fowler): el front ignora lo que no conoce y le pone un
  valor por defecto a lo que falta.
- **Nada de `/api/v2`**: el versionado explícito (AIP-185, el `api-version` de
  Microsoft) es para APIs con muchos clientes; acá hay uno solo.
- **Lo guardado en el navegador tiene versión**: si cambia la forma, se sube
  `version` con su `migrate`, o se cambia la clave (como `calendario-mktg-v3`).
- **Lo viejo se marca para irse**: comentario con fecha y «quitar cuando…».

## Fuentes

- John Ousterhout, *A Philosophy of Software Design* (2018; 2.ª ed., 2021).
- W. Stevens, G. Myers y L. Constantine, «Structured Design», *IBM Systems Journal* (1974).
- David L. Parnas, «On the Criteria To Be Used in Decomposing Systems into Modules», *CACM* (1972).
- Fred Brooks, *The Mythical Man-Month* (1975); Gary Bernhardt, *Functional Core, Imperative Shell*.
- Google, API Improvement Proposals: AIP-131 a 136, 154, 155, 158, 180, 185 y 193.
- Microsoft, REST API Guidelines (incluye las de Azure).
- IETF: RFC 9110 (HTTP Semantics), RFC 9457 (Problem Details), RFC 7396 (JSON Merge Patch).
- Martin Fowler: «ParallelChange» (Danilo Sato) y «TolerantReader».
- T. Winters, T. Manshreck y H. Wright, *Software Engineering at Google* (2020).
