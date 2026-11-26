# Confiabilidad: SLO, despliegues, flags, observabilidad e incidentes

## SLO a la medida de Core Tienda (Google SRE)

- **SLI**: una medida desde la persona (¿cargó?, ¿cuánto tardó?); **SLO**: la
  meta; **SLA**: un contrato con multas (acá no hay). El libro de SRE de Google
  (cap. *Embracing Risk*): el 100 % es la meta equivocada; cada nueve de más
  cuesta y, pasado cierto punto, nadie lo nota.
- **Presupuesto de error**: lo que va del SLO al 100 % se puede «gastar» en
  cambios. Sin incidentes recientes hay lugar para arriesgar; con incidentes,
  primero la confiabilidad (*The Site Reliability Workbook* trae un ejemplo de
  política).

| SLI | Cómo se mide hoy, sin herramientas pagas |
|---|---|
| Disponibilidad | Chequeos del monitor que dan 200 (`.github/workflows/monitor.yml`: cada 30 min, hasta 3 intentos por el sueño de Render) |
| Errores | Respuestas 5xx sobre el total, en los logs JSON de Render |
| Latencia del camino crítico | `/calendario/datos?rev=`, el alta de una tarea y abrir una entrega, medidos en el entorno de pruebas |
| «Nada se pierde» | Cero escrituras perdidas: cola con reintento y altas idempotentes; Ramiro prueba con la red cortada y doble clic |

- **Cómo lo usa Tomás**: para juzgar, no para armar tableros de noche. Si la
  propuesta toca el login, el calendario o las entregas, lleva medida de antes
  y después y plan de vuelta atrás. **Si en la semana hubo un incidente que
  llegó a la gente, lo próximo que toque ese camino trae primero su prueba de
  regresión.**
- **Las cuatro señales doradas** (cap. *Monitoring Distributed Systems*):
  latencia, tráfico, errores y saturación. La saturación acá: la base contra el
  tope de 400 MB, el pool de conexiones, la décima de CPU y los 200 pedidos por
  minuto por persona.

## DORA, a escala de una noche

DORA (hoy en Google Cloud) y *Accelerate* (Forsgren, Humble y Kim, 2018) miden
frecuencia de despliegue, tiempo del cambio a producción, tasa de cambios que
fallan y tiempo de recuperación (en los informes recientes, «tiempo de
recuperación de un despliegue fallido»). Acá: noches con PR mergeado, días del
cuaderno a producción, PR nocturnos que hubo que arreglar o revertir, y cuánto
tardó en volver a andar. La lección: velocidad y estabilidad van juntas con
cambios chicos, probados y reversibles. Y la ley de Goodhart: si la métrica se
vuelve la meta, deja de medir (nada de partir un cambio en tres PR).

## Despliegues reversibles

- **Se revierte el código**: revertir el PR (vuelven front y back). Render no da
  por bueno un deploy cuyo `/health` da 503 (`app/main.py`). De noche no se toca
  producción: lo hace quien mergea.
- **No se revierten** el esquema, los datos, los mails y avisos enviados ni lo
  guardado en el navegador.
- **Cinco preguntas antes de decir SIGUE**:
  1. Si se revierte el PR, ¿la versión anterior anda con la base como quedó?
  2. ¿Se escriben datos con una forma que el código viejo no entiende?
  3. ¿El front viejo (pestañas abiertas) anda con el back nuevo, y al revés?
  4. ¿Lo guardado en el navegador con la forma nueva rompe al front viejo?
  5. ¿Hay efectos que no se deshacen (mails, avisos, IA)? ¿Se duplican con un
     reintento?
- **El canario de esta casa** es el entorno de pruebas con tres cuentas y el OK
  de Ivan; no hay reparto de tráfico ni hace falta proponerlo.

## Feature flags

Pete Hodgson (*Feature Toggles*, en el sitio de Martin Fowler) distingue flags
de lanzamiento, de operación (apagar en caliente), de experimento y de permiso.
Meta describió su Gatekeeper, que habilita funciones por grupo de personas, en
*Holistic Configuration Management at Facebook* (SOSP 2015).

- **Lo que ya hay**: variables de entorno como `IA_REVISION_ACTIVA` (apaga la
  revisión con IA sin tocar código), `MODELO_IA` y `MODELO_IA_REVISION`,
  `IA_REVISION_POR_DIA` (tope diario), los `*_INTERVAL_HOURS=0` que apagan un
  loop y `BASE_TOPE_MB`. Los permisos por persona son flags de permiso:
  `clientes_vip.view` no lo trae ningún rol.
- **Cuándo pedir uno**: camino crítico o costo de afuera (IA, mails), algo que
  a las 9 haya que apagar sin desplegar. La variable la carga Ivan en Render y
  vale al reiniciar: el plan dice el valor por defecto seguro.
- **Cuándo no**: un cambio trivial, o dos caminos vivos por meses. Cada flag es
  deuda: nombre, para qué y cuándo se borra.
- **Esconder una pantalla no protege datos**: el endpoint igual chequea.

## Observabilidad

Logs, métricas y trazas son las señales de OpenTelemetry; hoy hay logs, y
tienen que ser buenos:

- **Estructurados**: structlog en JSON con el `request_id` de cada pedido
  (`app/core/logging_config.py` y el middleware de `app/main.py`, que lo
  devuelve en `X-Request-ID`). Un incidente se sigue filtrando por ese id.
- **Con datos, no prosa**: quién, qué, qué id, cuánto, resultado. El modelo es
  el error de `espacio.py`: cuánto ocupa la base, el tope y lo rechazado.
- **Niveles con sentido**: ERROR, alguien tiene que actuar; WARNING, degradado
  pero anda; INFO, cambios de estado. Lo esperable no es ERROR: el ruido tapa
  los incendios.
- **Nunca** contraseñas, tokens, claves, links de recuperación ni datos de
  clientes (OWASP Logging Cheat Sheet). Todo `except Exception` que se traga el
  error lo loguea con `exc_info`, como `_avisar_sin_romper`.
- **Métricas y trazas sin pagar**: de los logs o del entorno de pruebas; el
  `request_id` es la traza de los pobres. En Azure: OpenTelemetry con W3C Trace
  Context (la idea viene de Dapper, Google, 2010).
- **`/health` barato y honesto**: base, migraciones y commit, nada lento: Render
  mata la instancia si no contesta en 5 s (`app/main.py`).
- **Alertas por síntoma, no por causa** (SRE): «la API no contesta» sí; una
  alerta que nadie lee, no.

## Incidentes y postmortems sin culpa

El postmortem sin culpa (libro de SRE, *Postmortem Culture*; John Allspaw,
Etsy, 2012) pregunta qué hizo que esa acción tuviera sentido en ese momento, no
quién se equivocó, y termina en cambios al sistema:

```
INCIDENTE <fecha> — <título en criollo>
Impacto: <quién no pudo hacer qué y durante cuánto tiempo>
Cómo nos enteramos: <monitor, Ivan, el recorrido de la noche>
Línea de tiempo: <hora de Montevideo — hecho>
Causa: <la técnica y la condición que la dejó pasar>
Qué anduvo bien: <...>
Acciones: <cambio — prueba o monitor que lo cuida — quién>
```

Cada acción trae la prueba que lo hubiera atrapado: la «regla Beyoncé» de
*Software Engineering at Google* (si te gustaba, le hubieras puesto una prueba).

### Los casos de la casa

| Qué pasó (según el repo) | La lección |
|---|---|
| 15/11/2026: Supabase pausó la base tras 7 días sin uso; producción cayó y las migraciones fallaron | `/health` da 503 si fallan las migraciones; monitor cada 30 min; `despierto.py` |
| Hasta el 10/09/2026 una migración rota no dejaba ni una línea en el log (el `fileConfig` de Alembic pisaba el logging) | Lo que falla tiene que verse: `configure_logger=False` en `migrations/env.py` |
| Auditoría del 15/11/2026: el límite de pedidos era uno para todos (la IP del proxy); `X-Forwarded-For` se falseaba (12 logins, ningún 429); FastAPI 0.139 apagó en silencio el límite (210 pedidos, ningún 429) | Una actualización puede apagar un control sin error: cada control tiene su prueba (`test_limite_de_pedidos.py`, `test_limite_por_persona.py`) |
| Un 500 de `/auth/forgot-password` salía sin headers de CORS y el navegador mostraba un error de CORS | El error tiene que llegar legible a donde se mira |
| Un redeploy a mitad de un render dejó un job «running» para siempre (uno desde el 14/08) | Todo trabajo en segundo plano sobrevive a un reinicio: `recuperar_jobs_huerfanos` |
| Un backend en una PC con el `.env` de producción corrió el mantenimiento contra producción y vació archivos de una corrida en curso | Lo que escribe en producción lo declara: `corre_mantenimiento` |
| El Dockerfile del front estuvo roto del 12/05 al 10/09/2026 sin que nadie lo notara | Lo que no se ejecuta no falla: job de CI «despliegue desde cero» |
| bcrypt con 12 rondas tardaba ~2,5 s en la décima de CPU y trababa a todos al entrar | Trabajo pesado en el loop de eventos es una caída para todos: 10 rondas (OWASP pide 10 o más) y en un hilo |

## Fuentes

- B. Beyer, C. Jones, J. Petoff y N. R. Murphy (eds.), *Site Reliability Engineering* (2016) y *The Site Reliability Workbook* (2018).
- N. Forsgren, J. Humble y G. Kim, *Accelerate* (2018); informes de DORA; J. Humble y D. Farley, *Continuous Delivery* (2010).
- Pete Hodgson, «Feature Toggles (aka Feature Flags)», martinfowler.com (2017).
- C. Tang y otros, «Holistic Configuration Management at Facebook», SOSP 2015.
- B. Sigelman y otros, «Dapper, a Large-Scale Distributed Systems Tracing Infrastructure», Google (2010); OpenTelemetry; W3C Trace Context.
- John Allspaw, «Blameless PostMortems and a Just Culture», Etsy (2012).
- OWASP Logging Cheat Sheet y Password Storage Cheat Sheet.
