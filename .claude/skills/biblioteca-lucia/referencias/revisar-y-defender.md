# Revisar con ojo profesional, convencer y tener criterio propio

## Lista de control de una pantalla, en pasadas

No mires todo a la vez: hacé pasadas cortas, cada una con una sola pregunta, y
anotá con la captura. Los 14 puntos de `criterios.md` son la vara; esto es el
orden para no saltearte nada.

1. **Primera impresión (5 s):** dónde estoy, qué es lo importante, qué puedo
   hacer, qué hago ahora. Es la idea de Steve Krug (*Don't Make Me Think*): si
   hay que pensar para entender la pantalla, la pantalla falla.
2. **Desenfocada:** ¿lo que resalta es lo importante? ¿Una sola acción
   principal?
3. **En grises:** ¿se entiende sin color? ¿Algún estado depende solo de él?
4. **Alineación y espacio:** bordes izquierdos comunes, espacios de la
   escala, nada tocando el borde, ninguna caja dentro de otra.
5. **Letra:** ¿cuántos tamaños y pesos? ¿Algo debajo de 12 px? ¿Mayúsculas
   espaciadas? ¿Cortado lo que identifica?
6. **Color:** un solo acento, cada color con significado, contraste medido
   (4,5:1 texto, 3:1 controles).
7. **Palabras:** las de la gente, botones con verbo + objeto, nada de más
   (marketing, instrucciones que el diseño debería volver innecesarias).
8. **Estados:** vacío, cargando, error, sin permiso, mucho contenido, nombre
   larguísimo, servidor dormido.
9. **Interacción:** ¿lo tocable parece tocable? ¿Responde en 0,1 s? ¿Doble
   clic? ¿Lo destructivo confirma o deja deshacer?
10. **Teclado y lector:** foco visible y no tapado, orden lógico, Escape
    cierra, nombres accesibles.
11. **Celular (390×664):** primera pantalla útil, 44 px, nada de costado ni
    flotando encima, el teclado no tapa.
12. **Oscuro:** bordes, íconos, cajas blancas, contraste.
13. **Coherencia:** el mismo encabezado, botón, campo y cartel que la
    pantalla hermana del núcleo.
14. **Cara de IA:** el conteo de `sin-cara-de-ia.md`.
15. **Flujo:** ¿lleva a lo siguiente? ¿Cuántos pasos? ¿Lo que hace uno le
    llega al otro (equipo, agencia, local)?

**Prueba de estrés del contenido:** un nombre de 80 caracteres con tildes y
ñ; 0, 1 y 200 elementos; un precio de siete cifras; la pantalla en inglés y
en portugués (los textos cambian de largo).

## Cómo escribir el hallazgo para que se entienda

Con el formato del cuaderno (`criterios.md`): lo que ve la persona, no la
clase CSS, con el número medido si lo hay («contraste 2,5:1; el mínimo es
4,5:1»); por qué le importa (tiempo, errores, confianza); el principio que lo
respalda (heurística, criterio WCAG, regla del informe), que le da peso pero
no reemplaza lo que le pasa a la persona; y una idea de arreglo en una línea.
Que se note qué viste (hecho), qué deducís (inferencia) y qué te parece
(opinión).

## El antes/después que convence

1. **Mismas condiciones:** la misma vista (notebook 1366×768 y celular
   390×664 en claro, oscuro si tocaste color), los mismos datos, el mismo
   estado, el mismo recorte. Si cambia algo más que el diseño, el antes/después
   miente.
2. **Datos reales del entorno de pruebas** (Black Friday, Navidad, Redexpres
   con 60 locales), no un vacío prolijo.
3. **Juntas**, con `evidencia.py antes.png despues.png --salida ...` (arma
   «ANTES» y «AHORA»). Si lo que cambió quedó en el mismo lugar, marcalo con
   `--marco` (el recuadro sale en las dos); como mucho tres marcas, nombradas
   en el texto en el mismo orden.
4. **Una línea por cambio, con la persona y la medida:** «el título ocupaba 8
   renglones; ahora 1 y la primera tarjeta se ve sin bajar»; «contraste de
   2,5:1 a 7,4:1»; «de 3 toques a 1»; «de 4 estilos de encabezado a 1»;
   «señales de IA: de 9 a 0».
5. **El caso difícil también:** nombre largo, vacío, error, oscuro. Es lo
   que demuestra que el diseño aguanta.
6. **Lo que no cambió a propósito:** si respetaste algo que la gente ya
   conoce, decilo; da confianza.
7. **Honestidad:** si algo empeoró (más alto, un paso más), decilo con el
   porqué.

## Criterio propio: discutir con argumentos

Sos la diseñadora: tu trabajo no es obedecer ni imponer, es que la plataforma
funcione para la gente que la usa. Ante un pedido de diseño:

1. **Separá la necesidad de la solución pedida.** Ivan pidió «esa cocarda
   visible de si es un mega evento, si es un evento normal, si es un especial,
   para saber también lo que es la importancia» (12/11/2026). La necesidad es
   ver la importancia de un vistazo; la forma se discute. Se resolvió con
   «cantidad de tinta» y no con un color nuevo, porque ámbar, rojo y verde ya
   significan otra cosa (`Cocarda.tsx`).
2. **Si la solución pedida empeora algo, nombralo con prueba:** usabilidad
   (qué tarea se traba y a quién), accesibilidad (qué criterio, con el
   número), coherencia (qué patrón rompe y dónde ya lo aprendió la gente).
3. **Proponé una alternativa que cubra la misma necesidad** y, si podés,
   mostrá las dos (maqueta o antes/después de cada una).
4. **Decí qué se gana y qué se pierde** con cada opción.
5. **La decisión es de Ivan.** Si elige la suya, hacela bien y anotá el
   riesgo; si es de accesibilidad grave, que quede escrito. No reabras una
   decisión sin evidencia nueva.

**Cómo decirlo:** «Entiendo que necesitás [necesidad]. Hacerlo con [solución]
tiene un problema: [qué le pasa a quién, con prueba]. Propongo [alternativa],
que cubre lo mismo y además [ventaja]. Si preferís la original, la hago con
[cómo bajar el riesgo].»

**Frases que valen:** «Esto empeora la experiencia de la agencia en el
celular porque el botón queda tapado.» · «Rompe la coherencia con el
calendario: la gente ya aprendió que el azul es el botón principal.» · «Con
este gris el texto queda en 2,5:1; el mínimo es 4,5:1.» · «No tengo pruebas
de que esto moleste: lo dejo como duda.»

**Lo que no vale:** «no me gusta», «no está de moda», «los buenos
diseñadores no hacen eso», citar una regla sin decir qué le pasa a la persona.

**Cuándo no discutir:** decisiones de marca dentro de las reglas (el tono lo
decide Ivan); lo que la gente ya aprendió y funciona aunque no sea ideal (va
como duda); lo que está en «Ya decidido: NO proponer» de `CONTEXTO.md`.

**Propuesta para Ivan, en seis líneas:** problema (quién, dónde, prueba) ·
propuesta · por qué (principio y medida) · alternativa que descartaste y por
qué · qué cambia para la gente (lo que tiene que reaprender) · antes/después.

## Aprender de las correcciones de Ivan sin aceptar a ciegas

Cada corrección trae un principio más general que el caso. Anotalo y
aplicalo en las pantallas hermanas, pero chequeá que no choque con otro
principio o con otra decisión. Estas son reales, copiadas de comentarios del
código, mensajes de commit y `cuaderno/DECISIONES.md`:

| Ivan dijo (fecha) | El caso | El principio que se generaliza |
|---|---|---|
| «está todo muy colorinche (…) tendría que ser algo mucho más minimalista» (19/11/2026) | Las marcas sobre la imagen, un color por tipo | Un color por significado; si todo tiene color, nada informa |
| «que sea azul da impresión de estar bien» (24/11/2026) | Lo que falta y lo que vio la IA, en azul o violeta | El color de un estado coincide con lo que significa: lo que falta, en rojo |
| «el espacio libre da tranquilidad» (19/11/2026) | La ventana de aprobación, chica | Al revisar una pieza, la imagen manda y necesita aire |
| Las versiones viejas «en versión minimalista, cerraditas», y que se puedan abrir (19/11/2026) | El historial de la entrega | Lo que se consulta poco va plegado |
| «necesitamos aclarar. No oscurecer más» (12/11/2026) | El menú azul noche en el tema claro | En claro, superficies claras; lo oscuro es un modo, no un estilo |
| «el ícono de notis debe ser más visible (…) debería estar arriba a la derecha» (18/11/2026) | La campanita al pie del menú | Lo importante va donde la gente ya lo espera |
| «un botoncito que te diga marcar como leída» (19/11/2026) | Un circulito que no se entendía como botón | Lo que se toca parece tocable y dice qué hace (lo que Don Norman llama *significante*) |
| «el calendario no debería tener scroll» (17/11/2026) | Una barra de desplazamiento propia | Evitá el scroll dentro del scroll |
| «el cambiar de una imagen a otra (…) provoca que cambien las alturas de las pantallas; eso está mal» (25/11/2026) | El visor de versiones | Nada salta: reservá el lugar |
| «al tener solo las tareas, tener todas esas pastillas es al pedo» (24/11/2026) | Pestañas en la ficha de una acción | Nada de navegación para un solo contenido |
| «no me muestra que esté cargando ni nada» (25/11/2026) | El alta de un usuario | Toda acción muestra que está trabajando |
| «bien legibles y en todos» (08/10/2026) | Precios a 10 px en gris claro | Lo que se usa para decidir se lee sin esfuerzo |
| «siempre tenemos que tener a Don Tino presente en las pestañas como una burbuja abajo a la derecha» (25/11/2026) | Don Tino solo en Inicio | La ayuda, siempre a mano y en el mismo lugar (WCAG 3.2.6) |
| «está quedando ambas mascotas, cuidado, eso está mal» (25/11/2026) | Dos burbujas, una arriba de la otra | Un solo ayudante flotante por pantalla |
| «Dontino sigue siendo Dontino aunque deje de verse como un robot (…) Mantienen su nombre y su identidad» (25/11/2026) | La auditoría proponía un solo asistente | Sacar lo decorativo no es sacar la identidad. Corrigió una propuesta tuya: el minimalismo tiene límites, y los marca Ivan |
| «tiene que adaptarse a su forma de trabajar, no al revés» (25/11/2026) | Las agencias | La complejidad la carga la plataforma |

**Cómo usarlas:**

- Antes de proponer, buscá precedentes: esta tabla, `cuaderno/DECISIONES.md`
  y `cuaderno/CEREBRO.md` (rama `equipo-nocturno/cuaderno`) y los
  comentarios del código que citan a Ivan con fecha
  (`grep -rn "Ivan" frontend/components frontend/app frontend/lib`).
- Lo nuevo que aprendas de una corrección va a `cuaderno/CEREBRO.md`, como
  pide `docs/equipo-nocturno/CRITERIO.md`; si no te toca escribir en el
  cuaderno, devolvéselo al coordinador. Acá entra solo si cambia una regla.
- Si un pedido nuevo choca con un precedente, no elijas en silencio: mostrá
  el choque. La cocarda de «Mega evento» la pidió Ivan y la auditoría propone
  sacarle la estrella y la mayúscula: se conserva la información (la
  importancia, de un vistazo) y cambia la forma.
- Dos pedidos que parecen chocar casi siempre se pueden cumplir juntos. La
  burbuja de Don Tino va en todas las pantallas, pero nunca encima de un
  botón ni del foco (H-025, WCAG 2.4.11), y puede dejar de ser un robot sin
  dejar de ser Don Tino. La idea del informe de llevarlo a la barra de arriba
  no tiene el ok de Ivan: si querés moverlo, es una duda, no un cambio.
- Si una corrección empeora la accesibilidad (un gris más claro «para que
  sea más minimal», una letra más chica «para que entre»), hacé la versión
  que cumple y explicá por qué; si Ivan insiste, que quede escrito el riesgo.
- Cuando te corrigen, preguntate qué principio no viste y sumalo a tu lista
  de control de la próxima pantalla.
