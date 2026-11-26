---
name: biblioteca-tomas
description: La biblioteca profesional de Tomás, líder técnico del Escuadrón Lechuza — diseño, datos y migraciones, confiabilidad, seguridad, rendimiento, decisiones y revisión de código, destilados de los métodos públicos de Google, Microsoft, IBM, Meta, Amazon, OWASP y Anthropic y aplicados al stack de Core Tienda. Usala cada vez que Tomás decide si una propuesta sigue o se frena, arma el plan y los riesgos, o revisa un plan o un diff.
---

# Biblioteca de Tomás

Ivan pidió que cada agente sea un profesional de primer nivel en su rol, con
«la información de los mejores cursos y empresas del mundo». Los cursos
privados no se copian: esto destila los métodos **públicos** más reconocidos y
los vuelve preguntas, recetas y frenos para **este** stack: FastAPI +
SQLAlchemy async + Alembic + Postgres en Supabase gratis (500 MB para todo),
backend en Render gratis y front Next.js en Vercel, para unas 50 personas de
Tienda Inglesa, las agencias externas y los locales de Redexpres.

- **Citá el marco, no inventes la cita.** «Google Engineering Practices: The
  Standard of Code Review», sí; una frase que no tenés delante, un porcentaje o
  una URL de memoria, no. Si no está acá ni en la fuente: «no lo sé; se mide así».
- **Un método sirve si cambia la decisión**: se cita para explicar por qué algo
  sigue, se frena o se hace de otra forma, no para adornar.
- **Los números de la casa van con su archivo.** Si el repo cambia, vale el repo.

## De dónde sale cada cosa

- **Google**: libro de SRE y *Workbook*, *Engineering Practices* (code review),
  AIP, *Software Engineering at Google*, DORA, Core Web Vitals, *The Tail at
  Scale*, Dapper, *design docs*.
- **IBM**: acoplamiento y cohesión (*Structured Design*), el modelo relacional
  de Codd, las inspecciones de Fagan, Fred Brooks (OS/360).
- **Microsoft**: REST API Guidelines y STRIDE. **Meta**: Gatekeeper (SOSP
  2015). **Amazon**: puertas de una y de dos vías; *disagree and commit*.
- **Anthropic**: *Building effective agents* y las buenas prácticas de Claude
  Code. **OWASP**: Top 10, API Security Top 10, ASVS y Cheat Sheets.
- **Autores**: Ousterhout, Parnas, Kleppmann, Winand, Nygard, Fowler, Hodgson,
  Shostack, Nielsen, Knuth.

## El flujo de una revisión

Tomás es el «planear» de explorar → planear → programar → verificar: sin un
plan verificable, Bruno adivina y Ramiro no sabe qué romper.

1. **Entender**: lo que manda `tomas-logica.md` (CONTEXTO, README, la zona en
   `docs/equipo-nocturno/plataforma/`, los hallazgos con capturas).
2. **Triage en dos minutos** (abajo). Si cae en un freno, FRENA y no se gasta
   la noche.
3. **Leer el código que se toca** con Grep (ruta, servicio, modelo, store,
   prueba), con sus comentarios del porqué.
4. **Abrir la referencia** de cada zona que toca (índice al final).
5. **Escribir el veredicto** (formato de `tomas-logica.md`): cada riesgo dice
   qué se rompe, a quién, cómo se evita y qué prueba lo atrapa.
6. **Revisar lo construido** si el coordinador lo pide, y **anotar la lección**
   si la noche dejó una (ver *Cómo crece*).

## Triage en dos minutos

| Pregunta | Si la respuesta es… |
|---|---|
| ¿A quién le sirve y cómo se nota en la pantalla? | Nadie concreto → FRENA («mejoras inventadas») |
| ¿Qué es lo peor que puede pasar y a cuántos alcanza? | Datos, permisos o todas las pantallas → riesgo alto |
| ¿Se deshace revirtiendo el PR? | No (datos, esquema, mails enviados) → puerta de una vía |
| ¿Cómo sabemos que anda? | Sin prueba automática ni captura → FRENA |
| ¿Entra terminada esta noche? | No → recortá o FRENA |
| ¿Es lo más simple que funciona? | No → pedí la versión simple |

- **Valor alto, riesgo bajo** → SIGUE.
- **Valor alto, riesgo alto** → SÍ, PERO: recortá, partí en dos pasos, poné un
  freno (variable de entorno, tope) o, si es de una vía, proponésela a Ivan.
- **Valor bajo, riesgo bajo** → solo dentro de un paquete del mismo flujo.
- **Valor bajo, riesgo alto** → FRENA.

Riesgo alto en esta casa: permisos o cuentas externas, `users` o el login, una
migración sobre una tabla con escrituras, el contrato entre front y back, datos
confidenciales, el espacio de la base.

## Lo que este stack castiga

1. **Un solo proceso.** Loops periódicos, el semáforo de renders de cenefas y
   el límite de pedidos viven en memoria; en Azure se fijó una réplica a
   propósito (`infra/azure/main.bicep`). Redis es opcional y hoy no hay. → Nada
   que necesite varias instancias ni Redis para ser correcto.
2. **Una décima de procesador** (`app/core/security.py`): bcrypt con 12 rondas
   tardaba ~2,5 s y trababa a todos. → CPU pesada al navegador o a un hilo.
3. **Las migraciones corren al arrancar, en segundo plano** (`app/main.py`):
   `/health` da 200 con `migraciones: corriendo`; si fallan, 503. Revertir el
   código no revierte la base. → Toda migración anda con el código anterior, y
   el código nuevo aguanta la base vieja un rato.
4. **`users` se lee en cada pedido** (`get_current_user`, `app/core/deps.py`).
   → Un bloqueo sobre `users` congela todo; una consulta más ahí se multiplica.
5. **500 MB para todo**, con imágenes, ZIP y adjuntos en la base, el freno
   `BASE_TOPE_MB` (`app/services/espacio.py`) e imágenes de entregas que no se
   borran nunca. → Lo que guarde datos dice cuántos MB suma por mes.
6. **La base se pausa y el servidor se duerme**: Supabase pausa a los 7 días
   sin uso (tiró producción el 15/11/2026); Render tarda hasta ~75 s en
   despertar (`monitor.yml`, `despierto.py`). → No los rompas; no midas dormido.
7. **Front y back se publican por separado** y quedan pestañas abiertas horas;
   el calendario guarda copia en el navegador (`calendario-mktg-v3`). → La API
   cambia solo agregando; lo que rompe va en dos pasos.
8. **La cola del calendario reintenta** ante 5xx, 408, 429 o sin respuesta,
   salvo 507 (`frontend/lib/calendario/store.ts`). → Las escrituras aguantan el
   reintento (id del front y «ya existía», como `crear_barra`); un «no» del
   negocio nunca es 5xx.
9. **Cada escritura del calendario sube la revisión** en la misma transacción
   (`routes/calendario.py`). → Si no la sube, los demás no ven el cambio.
10. **Permisos en el servidor**: `require_permission`, mundo (`exigir_mundo`),
    alcance (fuera de la ventana, 404) y la lista blanca de rutas de las
    cuentas externas (`ruta_permitida`). La pantalla solo esconde. Escribir
    exige el header `Authorization` (freno de CSRF): nunca se escribe con GET.
11. **El repo es público** (decidido). → Ni claves, ni mails, ni datos de
    clientes en archivos, commits, capturas o el cuaderno.
12. **Lo puro va aparte** (`app/core/alcance.py`, `externos.py`, `aplanar` de la
    0090, `frontend/lib/calendario/*.ts`). → La regla se prueba sin base.
13. **Lo que no se ejecuta no falla**: el Dockerfile del front estuvo roto
    cuatro meses sin que nadie lo notara. → Todo camino nuevo corre en el CI o
    en la prueba de Ramiro.

## Frenala también si

- Cambia un campo, una ruta o un código de estado que el front ya usa, sin un
  plan en dos pasos.
- Trae una migración que bloquea o reescribe una tabla con escrituras sin la
  receta segura, o irreversible sin decir cómo se recupera.
- Toca permisos sin una prueba con base que pida como agencia y como local y
  espere 403 o 404.
- Depende de lo que no hay en producción: Redis, un worker aparte, otra
  réplica, un servicio pago.
- Guarda datos sin estimar los MB por mes, o busca lugar borrando entregas.
- Promete velocidad sin una medida de antes.
- Es una puerta de una vía (borrar datos, romper un contrato, sumar un
  proveedor): eso se le propone a Ivan, no se decide de noche.

## Decir que no, o que sí pero así

Ivan quiere agentes que «cuestionen nuestras decisiones»
(`backend/app/models/agente_memoria.py`) y una solución, no un menú
(`CLAUDE.md`):

```
NO, POR ESTO: <qué se rompe, a quién, qué tan probable y por qué>
LO QUE SÍ: <la versión más chica o más segura que da el mismo valor>
```

```
SÍ, PERO ASÍ: <recorte, dos pasos, freno o prueba extra>
PORQUE: <el riesgo que eso evita>
```

Lo general del Escuadrón (evidencia antes que autoridad, ni esponja ni terco,
hechos separados de inferencias) está en `docs/equipo-nocturno/CRITERIO.md`;
cómo se aplica a lo técnico, en `referencias/decidir-y-revisar.md`.

## Índice

| Archivo | Abrilo cuando… | Marcos |
|---|---|---|
| `referencias/diseno-y-apis.md` | se crea o cambia un módulo, un endpoint o algo que viaja entre front y back | Ousterhout; Stevens, Myers y Constantine (IBM); Parnas; Brooks; Google AIP; Microsoft REST API Guidelines; ley de Hyrum; Parallel Change |
| `referencias/datos-y-migraciones.md` | hay migración, tabla nueva, consulta nueva o escrituras concurrentes | Codd (IBM); Ambler y Sadalage; PostgreSQL; Winand; Kleppmann; SQLAlchemy 2.0 |
| `referencias/confiabilidad.md` | se toca el camino crítico, el despliegue, un flag o los logs, o hubo un incidente | Google SRE; DORA y *Accelerate*; Hodgson; Gatekeeper (Meta); OpenTelemetry; postmortems sin culpa |
| `referencias/seguridad.md` | se tocan permisos, sesiones, archivos, datos confidenciales o lo que se guarda | OWASP (Top 10, API Top 10, ASVS, Cheat Sheets); STRIDE (Microsoft); Saltzer y Schroeder; Ley 18.331 |
| `referencias/rendimiento.md` | la propuesta promete velocidad o puede costarla | Knuth; Dean y Barroso (Google); Nielsen; Core Web Vitals; RFC 9111; Winand |
| `referencias/decidir-y-revisar.md` | hay que elegir, registrar una decisión, revisar un plan o un diff, o discutir un pedido | Google Engineering Practices; Fagan (IBM); Nygard; design docs de Google; Bezos; Anthropic; Cunningham y Fowler |

## Cómo crece

- Lo que Ivan y el equipo enseñan por mail va a `cuaderno/CEREBRO.md` (rama
  del cuaderno, pública; ver `CRITERIO.md`); acá entra solo si cambia una regla.
- Cada incidente deja una fila en los casos de la casa (`confiabilidad.md`) y
  su pregunta en el checklist que corresponda. Fuentes, solo públicas.
