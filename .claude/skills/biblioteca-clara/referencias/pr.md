# El detalle del PR

## Para quién es

Para quien quiera ver todo: el equipo de día que mergea, quien revise el
código, Ivan si quiere profundizar y quien, dentro de seis meses, busque por
qué se cambió algo. Acá sí van los códigos, los números y los nombres de
archivos y de agentes (README, *El detalle*).

## Lo que enseñan los que más revisan código

- **Google** (*Engineering Practices*, «Writing good CL descriptions»): la
  primera línea es un resumen corto de lo que hace el cambio y se entiende
  sola. El cuerpo cuenta el problema, por qué esta solución es la mejor, sus
  limitaciones y el contexto (números de error, mediciones, documentos de
  diseño). Como los links se rompen, el texto se tiene que entender sin
  ellos. Ejemplos de descripciones malas que da la guía: «Fix bug», «Phase
  1», «Add patch». Y antes de cerrar, se relee la descripción: el cambio
  pudo cambiar durante la revisión.
- **Meta:** Phabricator, la herramienta de revisión que nació en Facebook,
  trae por defecto un campo *Test Plan* obligatorio: cómo se probó, con
  pasos que alguien sin contexto pueda repetir. La plantilla de PR de React
  lo sigue pidiendo («How did you test this change?»: los comandos exactos y
  lo que devolvieron, y capturas si cambia la pantalla), junto con la
  motivación del cambio.
- **IBM** (*Developing Quality Technical Information*, IBM Press): la
  información técnica de calidad es fácil de usar (orientada a la tarea,
  exacta y completa), fácil de entender (clara, concreta y con estilo) y
  fácil de encontrar (ordenada, ubicable y con buen apoyo visual).

## El molde

El del README, *El detalle (descripción del PR)*, campo por campo y en el
mismo orden, con un renglón en blanco entre campos (si no, GitHub los junta
en un solo párrafo). Al final, dos campos más que pide la buena práctica y
el molde todavía no trae:

```markdown
**Riesgos:** qué se puede romper, a quién, y cómo se evita o se detecta.

**Cómo revertir:** el camino concreto (ver abajo).
```

## Campo por campo

- **Qué cambia:** la frase madre del mail. Si alguien lee solo esto, sabe
  qué hace el PR.
- **Hallazgos que resuelve y Qué vio el recorrido:** los códigos y los
  números del cuaderno, tal cual. Es el contexto: por qué existe el cambio.
- **Qué se hizo, paso a paso:** un renglón por agente, con lo que decidió
  cada uno. Ahí se ve el «por qué esta solución» que pide Google.
- **Cómo se probó:** el resultado de Ramiro con números (N pasaron, N
  fallaron, N salteadas y por qué) y, debajo, lo que no se pudo probar, con
  nombre y razón. Sumá las limitaciones del entorno cuando aplican:
  - la IA está simulada (Don Tino contesta con reglas): las pantallas se
    prueban, lo que diría Claude no;
  - el celular se prueba con Chromium al tamaño de un iPhone, no con Safari;
  - sin Postgres se saltean las pruebas que lo necesitan (las corre el CI
    de GitHub al abrir el PR).
- **Migración:** «no», o el número y qué cambia en la base.
- **Lo que se descartó esta noche:** una línea por propuesta frenada, con
  el motivo de Tomás.
- **Riesgos:** el de «Ojo» y los demás del plan de Tomás, más lo que
  encontró Ramiro al intentar romperla. Cada uno con a quién afecta y cómo
  se evita o se detecta.
- **Cómo revertir:** lo que tendría que hacer el equipo de día si algo sale
  mal después de publicar.
  - Sin migración: «Revertir el PR (botón *Revert* de GitHub, o
    `git revert -m 1 <commit del merge>` en `main`). La vuelta atrás se
    publica sola, igual que el cambio.»
  - Con migración: avisá que revertir el código no deshace la base. Hay que
    bajar la migración (`alembic downgrade <la anterior>`) y decir si se
    pierde algún dato al hacerlo; si no se puede bajar sin perder datos,
    decilo bien claro.

## Estilo

- **El título del PR es el mismo que el del mail** (README).
- **Frases cortas y voz activa también acá:** técnico no quiere decir
  enredado.
- **Tablas, sí:** GitHub las muestra y las guías federales de EE. UU. las
  recomiendan para el material complejo (las cinco capas de Ramiro, por
  ejemplo).
- **El mismo hecho que el mail, con más detalle, nunca otra versión.** El PR
  puede sumar riesgos menores, pero si uno le importa a Ivan, ya estaba en
  «Ojo». Si el mail dice «Nada que veamos», el PR dice, por ejemplo,
  «Riesgos: ninguno conocido; se revisaron los permisos de la agencia y del
  local».
- **Releelo al final,** como pide Google: si hubo vueltas entre Ramiro y
  Bruno, el detalle cuenta la versión que se sube, no la primera.
