# El oficio: leer, cambiar de a poco, commitear y revisar

## Leer antes de cambiar

La cerca de Chesterton (G. K. Chesterton, *The Thing*, 1929): no saques una
cerca hasta saber por qué la pusieron. En este repo casi todo tiene su porqué
escrito (un pedido de Ivan con fecha, un caso real, un número medido):
leelo antes de «simplificar». Para una zona que no conocés:

1. **El mapa y la cabecera:** `docs/equipo-nocturno/plataforma/<zona>.md` y
   el docstring de arriba del archivo (el de `adjuntos.py` trae las rutas y
   las reglas de permiso en quince líneas).
2. **Las pruebas de la zona:** dicen qué se considera correcto y traen las
   ayudas para la tuya (`grep -rln "adjuntos" backend/tests frontend/lib`).
3. **De afuera hacia adentro,** con un caso concreto: la ruta → el servicio →
   el modelo; la pantalla → el store → `lib/api.ts`.
4. **La historia:** `git log --oneline -- <archivo>`; `git log -S "texto"
   --oneline` (cuándo apareció o se fue algo); `git log -L
   :_tarea_visible:backend/app/api/routes/adjuntos.py` (la vida de una
   función); `git blame -w`. El mensaje del commit suele traer el porqué.
5. **Quién más lo usa,** antes de cambiar una firma o un campo del JSON
   (`grep -rn "puedoAdjuntar" frontend backend`). Ley de Hyrum (*Software
   Engineering at Google*): todo comportamiento observable, alguien lo usa.
6. **El código y las pruebas mandan sobre los comentarios:** si no coinciden,
   corregí el comentario (ejemplos en [codigo-limpio.md](codigo-limpio.md)).

Si el código no tiene pruebas y lo tenés que cambiar, primero una **prueba de
caracterización** (Michael Feathers, *Working Effectively with Legacy Code*):
fija lo que el código hace hoy, aunque te parezca raro, y recién después cambiás.

## Refactor seguro (Fowler)

Refactorizar es cambiar la estructura sin cambiar el comportamiento que se ve
de afuera (Martin Fowler, *Refactoring*).

- **Dos sombreros** (Kent Beck, en ese libro): o agregás funcionalidad o
  refactorizás; nunca las dos en el mismo paso ni en el mismo commit. Google
  pide lo mismo (*separate out refactorings*) y Beck le dedicó *Tidy First?*.
- **Pasos chicos, en verde después de cada uno.** Si se pone rojo y en un
  minuto no ves por qué, volvé atrás (`git restore <archivo>` o `git stash`)
  y probá con un paso más chico.
- **El refactor que entra en una noche es el que prepara la mejora.** Beck:
  primero hacé que el cambio sea fácil (ojo: eso puede ser difícil), después
  hacé el cambio fácil. Cualquier otro es una mejora que nadie pidió.
- **Los movimientos que más se usan acá:** *Extract Function* (sacar lo puro
  de una ruta para probarlo), *Rename* (con grep de todos los usos, front y
  pruebas incluidos), *Replace Nested Conditional with Guard Clauses*,
  *Split Phase* (calcular primero, escribir después).
- **Cambiar un contrato** (un campo del JSON, una columna) va en dos tiempos:
  agregar lo nuevo, pasar los usos, sacar lo viejo después («Parallel Change»).
  Y **no es refactor** cambiar un mensaje, un código de estado o un orden:
  eso es comportamiento, y va con su prueba.

## Commits chicos y descriptivos

Las *Engineering Practices* de Google (la guía de quien escribe el cambio):
los cambios chicos se revisan más rápido y más a fondo, meten menos errores,
se diseñan mejor y se deshacen fácil; unas 100 líneas suele ser razonable y
1000 suele ser demasiado, a criterio de quien revisa. Un cambio es una idea
completa, con sus pruebas adentro. En esta casa:

- **Un commit por paso que deja todo andando.** La serie «Entregas que van y
  vienen: el servidor», «...: la tarjeta y el revisor», «...: pruebas» es el
  modelo; mejor todavía si cada paso trae su prueba.
- **El asunto, en castellano, dice qué cambia para la gente y dónde:**
  «Adjuntos: la agencia ve el peso de cada archivo». No «fix», no «cambios
  varios», no `[Nocturno]` (era el aviso viejo por GitHub).
- **El cuerpo, si hace falta, cuenta el porqué** y lo que el diff no muestra
  (el caso real, la decisión, lo descartado): «El de octubre 2026 se cortó a
  la mitad: ... Ahora 16.000 con esfuerzo medio». Chris Beams resume la forma:
  asunto corto, línea en blanco, cuerpo con el qué y el porqué.
- **Nada de `git add -A` a ciegas:** `git status`, `git add <archivos>` y
  `git diff --cached` antes de cada commit (secretos, restos de prueba,
  archivos que no son tuyos). Y solo en la rama de la noche: ni `main`, ni
  push, ni force-push.

## La revisión de código

Las inspecciones de código nacieron en IBM (Michael Fagan las formalizó en
1976, en el IBM Systems Journal). En Facebook, donde nació Phabricator, cada
diff lleva su *Test Plan*: cómo se probó. Tu HECHO cumple ese papel: qué
cambiaste, cómo lo probaste y qué no se pudo probar.

La vara de Google para quien revisa: aprobar cuando el cambio mejora la salud
del código aunque no sea perfecto («no hay código perfecto, solo código
mejor»). Se mira el diseño, que le sirva a quien lo usa, que no sea más
complejo de lo necesario, las pruebas, los nombres, los comentarios, el
estilo, cada línea y el contexto.

**Tu autorevisión**, como si el cambio fuera de otro: `git diff
origin/main...HEAD` línea por línea. ¿Cada línea hace falta para el hallazgo?
¿Alguien que no estuvo esta noche entiende por qué está cada cosa? ¿Las
pruebas fallarían si alguien rompe esto mañana? Y la lista del `SKILL.md`.

## Recibir una corrección (de Ramiro, Lucía, Tomás o Ivan)

- **Es sobre el código, no sobre vos.** Primero pensá si tiene razón: Google
  le pide eso mismo a quien revisa cuando el autor discrepa, porque muchas
  veces el otro ve algo que vos no.
- **Si no entendió tu código, aclará el código** (un nombre, un comentario,
  una función), no el chat: el próximo va a tropezar igual.
- **Si es un error:** la prueba que lo hubiera atrapado y el arreglo exacto
  de eso, sin aprovechar para rehacer otras cosas.
- **Si no estás de acuerdo:** decilo con evidencia (archivo y línea, una
  prueba, una captura, una regla de `CONTEXTO.md`), una vez. Si es cuestión
  de gusto y el repo ya tiene un estilo, gana el estilo del repo.
- **Aprendé el patrón, no solo el caso:** ¿qué chequeo te faltó? Sumalo a tu
  autorevisión. Como en los postmortems sin culpables (Google, *Site
  Reliability Engineering*, cap. 15): se busca la causa, no un culpable.
- **No aceptes todo sin pensar:** una corrección que rompe una regla
  (permisos en el servidor, imágenes que no se borran, «Diseñadores» es una
  agencia externa) se discute, aunque venga dicha con seguridad.

## Cuestionar el plan

Señales de que el plan de Tomás tiene un problema: el permiso queda solo en
la pantalla, o la agencia vería algo interno; pide una migración evitable, o
una que no se puede deshacer; lleva a una consulta por fila, o a algo pesado
en un `async def`; choca con `CONTEXTO.md`; no entra terminado en la noche,
o suma una dependencia; en el celular o en Safari no va a andar como se describe.

Cómo plantearlo, corto y antes de programar:

```
OJO CON EL PLAN
Problema: <qué rompe, en una línea> (evidencia: archivo:línea / prueba / captura)
Alternativa: <la más simple que cumple>
Qué se pierde: <lo que no hace la alternativa>
Si no me dicen nada: <qué hago>
```

- **Lo más simple que puede funcionar** (Cunningham y Beck) y YAGNI (Ron
  Jeffries): sin parámetros «por si acaso», sin configuraciones que nadie
  pidió, sin generalizar para un segundo caso que no existe.
- **Si deciden igual** y no es seguridad ni una regla que no se discute: lo
  hacés bien y lo anotás en «Diferencias con el plan» (Amazon lo llama
  *disagree and commit*). Si es seguridad o una regla, no lo hacés, y lo decís.
