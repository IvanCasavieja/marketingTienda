# Core Tienda: lo que tiene que saber cualquier sesión de Claude

> Si sos el **Equipo nocturno**, seguí `docs/equipo-nocturno/README.md` y
> listo: lo de abajo es para las sesiones en las que Ivan habla con Claude
> (por ejemplo, desde la app del celular con la PC apagada).

## Con quién trabajás

Ivan, de marketing digital de Tienda Inglesa (Uruguay). Construyó Core Tienda
con Claude. Escribe en castellano rioplatense, muchas veces dictando por voz
desde el celular: lo concreto que pide suele estar al final del mensaje.

## Cómo quiere que se trabaje

- **Una solución, no un menú.** Investigá, resolvé, comprobá que anda y
  recién ahí presentala en palabras simples, con un ejemplo si ayuda. Pedí el
  OK y, con el OK, hacelo todo sin volver a preguntar.
- **Respuestas cortas en el chat:** lista por tema, una línea por punto, y al
  final qué necesitás de él (normalmente un OK). Nada de documentos largos si
  no los pide.
- **Si algo no anda, arreglalo.** No se lo presentes como pregunta.
- **No inventes mejoras** que nadie pidió.
- Las advertencias (seguridad, etc.) se dicen una vez y listo.
- Pedile solo lo que de verdad no podés hacer vos (entrar a cuentas suyas),
  todo junto y una sola vez.

## Reglas del repo

- **Nada entra a `main` sin el OK de Ivan.** `main` tiene candado: todo va por
  PR. Mergear sin su OK explícito, nunca.
- **Producción no se toca sin OK:** API en Render
  (`https://marketingtienda.onrender.com/health` dice qué commit corre y si la
  base y las migraciones están bien), front en Vercel, base Postgres en
  Supabase (plan gratis, 500 MB).
- **El repo es público:** nunca escribas claves ni datos privados en archivos.
- La visión de la plataforma, quién la usa, las reglas que no se discuten y lo
  que Ivan ya descartó están en `docs/equipo-nocturno/CONTEXTO.md`. Leelo
  antes de proponer algo.
- Migraciones: el número siguiente al más alto en `backend/migrations/versions`
  de `main`, que no use ninguna rama abierta.

## El Equipo nocturno

Siete agentes (Sofía, Martina, Lucía, Tomás, Bruno, Ramiro y Clara) que de
lunes a viernes a las 2 AM recorren la plataforma entera como las personas
que la usan (en un entorno de pruebas con cuentas propias), anotan lo que
encuentran en un cuaderno, construyen y prueban la mejora que más vale la
pena y abren un PR `[Nocturno] ...`. El informe le llega a Ivan por mail (un
issue que lo menciona), con el antes y después en imágenes. Él responde
**ok** o **no** al mail y `ok-por-mail.yml` mergea o cierra. Todo está
explicado en `docs/equipo-nocturno/README.md`; el mapa de la plataforma en
`docs/equipo-nocturno/plataforma/`; cómo recorren y anotan en
`.claude/skills/`.

Si Ivan pregunta "¿en qué andan los agentes?" o "¿qué hicieron anoche?":
mirá los PR e issues abiertos que empiezan con `[Nocturno]`, las ramas
`origin/nocturno/*` y el cuaderno (`origin/equipo-nocturno/cuaderno`,
`cuaderno/CUADERNO.md`), y contestale corto: qué propusieron, si las pruebas
están en verde, qué encontró el recorrido y qué tiene que decidir.
