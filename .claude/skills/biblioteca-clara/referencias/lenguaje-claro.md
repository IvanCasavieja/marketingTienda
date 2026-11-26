# Lenguaje claro: que se entienda a la primera

## Qué es

La norma ISO 24495-1 (2023) adoptó la definición de la International Plain
Language Federation: un texto está en lenguaje claro cuando sus palabras, su
estructura y su diseño son tan claros que el lector al que va dirigido
encuentra lo que necesita, entiende lo que encuentra y puede usarlo. Habla
de **estructura y diseño**, no solo de palabras. Sus cuatro principios, en
el mail de la noche:

1. **Relevante:** Ivan recibe qué cambia, por qué y qué decide; lo demás va
   al PR.
2. **Fácil de encontrar:** los títulos con emoji, siempre en el mismo orden,
   y la decisión siempre al pie.
3. **Fácil de entender:** palabras de la gente, frases cortas, cada pantalla
   explicada.
4. **Fácil de usar:** «Cómo verlo» se puede seguir y la decisión cuesta una
   palabra.

Lenguaje claro no es escribir para chicos ni sacar información: es no
hacerle trabajar al lector lo que podés trabajar vos.

## La conclusión primero: tres escuelas, una regla

- **La pirámide invertida** (periodismo): lo más importante arriba; si el
  lector corta en cualquier punto, se lleva lo esencial.
- **El principio de la pirámide** (Barbara Minto, consultora de McKinsey,
  *The Pyramid Principle*): arriba, la idea que contesta la pregunta del
  lector; abajo, los grupos de razones que la sostienen, sin pisarse ni
  dejar huecos (MECE). Para arrancar: situación, complicación, pregunta y
  respuesta (SCQA).
- **BLUF** (*bottom line up front*, la escritura militar de EE. UU.): la
  primera frase dice para qué es el mail y qué se necesita. Kabir Sehgal lo
  explicó para el mail de oficina en *Harvard Business Review* (2016): el
  BLUF contesta «¿en qué me afecta este mail?».

Acá: el asunto es el titular; la primera frase de «Qué cambia» es la
conclusión (es lo que se ve en la notificación del celular); el «Por qué» es
la situación y la complicación de Minto, contadas como caso; en un hilo, la
primera línea contesta. El orden militar sí, el tono de cuartel no.

## Frases

- **Una idea por frase** (Google, *Technical Writing One*: «Focus each
  sentence on a single idea»). Un «y además», un «, que» y un «aunque» en la
  misma frase son tres frases.
- **Unas 15 palabras en promedio.** La OPM (la oficina de personal del
  gobierno de EE. UU.) pide de 15 a 20; GOV.UK, 25 como máximo. El mail
  modelo promedia 14, y su frase más larga (unas 30) es un caso contado: una
  larga se banca si es una historia; dos seguidas, no.
- **Sujeto, verbo y objeto cerca** (guías federales de EE. UU.): «El local
  ahora ve un cartel verde», no «Un cartel verde, que aparece cuando el
  equipo ya confirmó el pedido, es lo que ahora ve el local».
- **Voz activa.** Las guías federales: «Active voice makes it clear who is
  supposed to do what». En castellano la trampa es el «se»: «se corrigió» o
  «se detectó» esconden quién. Escribí «arreglamos», «el encargado ve».
- **Verbos, no sustantivos disfrazados:** «confirmar», no «realizar la
  confirmación».
- **Sin dobles negaciones:** «no es raro que no se guarde» → «a veces no se
  guarda».
- **Primero la condición** (guía de estilo de Google para desarrolladores):
  «Si el pedido ya está confirmado, el local ve el cartel».
- **Lo que se enumera, en lista** (Google: «Convert some long sentences to
  lists»), cada ítem en una sola línea.

Párrafos (Google): la primera frase dice lo central, un solo tema, y
contesta qué, por qué y cómo. En el celular, de 1 a 3 frases.

## Palabras

**Las de la gente.** Cada cosa se llama como la llama quien la usa: acción,
tarea, pieza, entrega, tablero, local (`recorrido-humano/criterios.md`). La
primera vez que aparece una pantalla, explicala con la línea «Para qué
sirve» del mapa (`docs/equipo-nocturno/plataforma/`), en criollo:

- «Mi pedido, donde cada local carga lo que necesita del mes»;
- «la Planilla, donde el equipo ve lo que pidió cada local»;
- «el tablero de entregas, donde se siguen las piezas pedidas a las
  agencias, como tarjetas de Trello»;
- «Mis tareas, donde cada uno ve lo que tiene asignado».

**Las del proceso y las técnicas, fuera del mail.** Lo prohibido del README
va al PR. En vez de *deploy*, *merge*, *bug*, *fix* o *feature*: publicar,
error, arreglo, función nueva. Si un término es inevitable, explicalo entre
paréntesis (o mejor, no lo uses).

**Las infladas.** GOV.UK mantiene una lista de palabras a evitar porque
suenan a mucho y dicen poco (*leverage*, *robust*, *streamline*,
*facilitate*, *key* cuando no es una llave). Sus primas en castellano:

- potenciar, optimizar → qué mejora: «abre más rápido»;
- implementar, realizar, gestionar → hacer, agregar, cargar, revisar;
- solución integral, sinergia, impacto positivo → el efecto concreto;
- a nivel de, en el marco de, de cara a → en, para;
- clave, fundamental, crucial → si importa, mostralo con el caso.

**Que no suene «hecho con IA».** Del diseño, Ivan dijo que «se ve muy
"hecho con IA"» y pidió algo «más tranqui, más chill, más minimal»
(`DECISIONES.md` y el pedido de la auditoría del 25/11). La vara sirve para
el texto. Señales de texto en serie: arrancar con «¡Excelente!», cerrar con
«En resumen», tres adjetivos seguidos, «no solo X, sino también Y», un emoji
por línea, elogios al equipo. Si suena a folleto, reescribilo como se lo
dirías en persona.

## El tono

- **Rioplatense y parejo:** vos (tenés, podés, mirá, respondé) y ustedes
  para varios. Nunca «usted» mezclado con «vos», nunca «vosotros».
- **Como se lo contarías en persona** (Microsoft: «Write like you speak»,
  leelo como si lo dijeras en voz alta). Si una frase pide aire en el medio,
  partila.
- **Nosotros para el equipo** («probamos», «encontramos»); yo cuando hablás
  vos.
- **Sin relleno:** nada de «Espero que estés bien», «Te comento que» o
  «Cabe destacar». Al grano (Microsoft: «Get to the point fast»).
- **Seguro donde hay certeza, prudente donde no** (`criterio-propio.md`).

## Cortar

Orwell («Politics and the English Language», 1946): si se puede sacar una
palabra, sacala. Strunk y White: «Omit needless words». Microsoft: «Use
bigger ideas, fewer words». Por orden: lo dicho dos veces; lo que no cambia
la decisión (va al PR); los arranques vacíos («Es importante destacar
que»); los adjetivos y adverbios sin dato («muy», «realmente»).

## La letra chica que se nota

- **Títulos sin punto final,** con mayúscula solo al principio y en los
  nombres propios (RAE; Microsoft: «When in doubt, don't capitalize»).
- **Comillas latinas** para citar una pantalla: «Ya confirmaste el pedido».
- **Números** como ya escribe el equipo: cifras para los datos («11 pasos»),
  punto para los miles y coma para los decimales (5.911; 0,8 s).
- **Fechas:** DD/MM en el asunto; en el texto, «el lunes 30/11». Horas de
  Montevideo.
- **Negrita** solo para la pantalla o lo que hay que tocar: si todo va en
  negrita, nada resalta.

## Antes y después de un mismo texto

Con situaciones reales de las noches del 24 y el 25/11:

- ✗ «Se implementó una mejora en el flujo de confirmación del módulo
  Redexpres que optimiza la experiencia del usuario.»
- ✓ «En "Mi pedido", el encargado del local ahora ve un cartel verde cuando
  su pedido ya está confirmado, y a quién pedirle si necesita cambiar algo.»
- ✗ «Se resolvió H-020 🟠, detectado en la zona del miércoles por Martina a
  ciegas.»
- ✓ «Probando como un encargado de local, quisimos corregir 300 cenefas a 30
  y no se podía: el pedido ya estaba confirmado, pero la pantalla no lo
  decía.»
- ✗ «Las pruebas fueron ejecutadas satisfactoriamente.» / «No se
  identificaron riesgos significativos.»
- ✓ «Todo en verde, también en el celular. Lo que contesta Don Tino no se
  pudo probar: acá la IA está simulada.» / «Nada que veamos.»
- ✗ «Existe una incidencia de superposición de componentes en la vista
  móvil.»
- ✓ «En el celular, el botón de Don Tino tapa "Más" en la barra de abajo:
  tocás "Más" y se abre el chat.»
