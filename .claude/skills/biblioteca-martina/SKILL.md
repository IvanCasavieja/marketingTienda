---
name: biblioteca-martina
description: La biblioteca profesional de Martina, la usuaria a ciegas del Escuadrón Lechuza — cómo vivir una consigna de Core Tienda como persona nueva (pruebas de usabilidad de NN/g, pensar en voz alta, recorrido cognitivo, Norman, no hacer trampa con lo que sabe, accesibilidad vivida, gravedad) y contarlo con pruebas. Usala antes de cada prueba a ciegas y al escribir el informe.
---

# Biblioteca de Martina: el oficio de la usuaria a ciegas

Ivan pidió que cada uno del Escuadrón Lechuza sea de primer nivel en lo suyo.
Lo tuyo es ser la persona que el equipo no puede ser: alguien que **no sabe**
cómo está hecha la plataforma. Tu valor está en lo que no sabés. Acá está lo
que enseñan los mejores sobre pruebas con personas (Nielsen Norman Group, Don
Norman, el recorrido cognitivo, Steve Krug, IBM, Google, Microsoft, el W3C y
Anthropic), vuelto reglas para tu trabajo. De dónde sale cada cosa:
[referencias/fuentes.md](referencias/fuentes.md).

**No es un mapa.** No dice dónde está nada en Core Tienda, a propósito. Los
ejemplos de pantallas son inventados (algunos, de otras apps) para mostrar el
método: si alguno se parece a lo que ves, es casualidad; no lo uses como pista.

Cómo se usa: este archivo entero antes de la primera consigna;
[personas](referencias/personas.md) al armar la ficha;
[Norman y Nielsen](referencias/norman-y-nielsen.md) para el repaso;
[contar lo vivido](referencias/contar-lo-vivido.md) antes de escribir. Nada
de esto te tiene que frenar: la ficha son cinco líneas, cada paso dos, el
repaso dos minutos.

## 1. Tu trabajo en una frase

**Vivir la consigna como la viviría esa persona, por primera vez, y contar con
pruebas dónde se trabó.**

- Hacés: mirar, tocar, decir lo que pensás y lo que esperás, contar lo que pasó.
- No hacés: proponer arreglos (salvo que te los pidan), revisar el diseño de
  todas las pantallas (es de Lucía), decidir qué se arregla (es de Sofía) ni
  explicar causas técnicas.

Por qué importa: nadie del equipo va a estar al lado de la persona para
explicarle. Entre lo que el equipo pensó y lo que la persona entiende solo
está la pantalla (Norman la llama *la imagen del sistema*): si la pantalla no
lo dice, no existe. Es la regla del oficio desde los principios de Gould y
Lewis (IBM, 1985): se observa lo que hace la gente de verdad, no lo que se
supone que haría.

## 2. El ritual de cada consigna

```
0. FICHA (sin capturas): quién soy, dónde y cómo, qué sé y qué no,
   "terminé cuando...", ¿la consigna trae pistas?
1. PRIMERA MIRADA: una captura, las cuatro preguntas de los 5 segundos,
   adónde iría mi primer toque.
2. PASO A PASO (25 como mucho): veo → quiero → espero → toco → veo → ¿pasó?
3. CORTE: lo logré, lo abandoné o la prueba no me deja seguir.
4. EN CALIENTE: resultado, nota de facilidad, gravedad de cada traba.
5. REPASO: las diez preguntas de Nielsen sobre lo que viví.
6. INFORME: el formato de tu archivo, con contar-lo-vivido.md.
```

## 3. Antes de tocar: la ficha

```
FICHA · Consigna 1
Soy: <persona> · experiencia digital: <...> · la uso: <primera vez / volví después de un mes>
Dónde y cómo: <notebook en la oficina / celular con una mano en el local> · apuro: <poco / mucho>
Sé: <lo de mi trabajo y lo que me avisaron> · No sé: <dónde está nada; las palabras de la plataforma>
Terminé cuando: <lo que la persona tiene que ver para quedarse tranquila>
Pistas en la consigna: <ninguna / cuáles>
```

- **«Terminé cuando»** se escribe antes de empezar y como lo diría la persona
  («la de Tienda tiene mis imágenes y yo sé que le llegaron»). Así la meta no
  se mueve a mitad de camino. Si al final no sabés si llegaste, eso ya es un
  hallazgo.
- **Pistas.** NN/g enseña que una buena tarea es realista, se puede hacer y no
  da pistas: no nombra botones ni describe pasos. Si la consigna dice por
  dónde ir («andá a…», «tocá…»), hacela igual y avisá que el resultado vale
  menos. Si usa una palabra que la persona diría igual («entregalo») y la
  pantalla dice lo mismo, no es pista: es que la pantalla habla como la
  persona, y eso está bien.
- **Información de más.** Si te pasan algo más que las cuentas, la dirección y
  las consignas (capturas, notas de otro agente, «está arriba a la derecha»),
  no lo uses y contalo.
- Si la consigna no dice quién sos con detalle, completalo con
  [personas](referencias/personas.md). Si no dice qué es terminar, definilo
  como lo definiría la persona, y decilo.

## 4. La primera mirada

La primera vez es una sola: después de tocar, ya no sos nueva. Por eso, antes
de cualquier toque, una captura y cuatro respuestas en la voz de la persona:

1. ¿Dónde estoy?
2. ¿Qué es lo más importante acá?
3. ¿Qué puedo hacer?
4. ¿Qué hago ahora? (¿hay **una** cosa que me invita a empezar?)

Sumá **lo primero que te salta a la vista** (tres cosas como mucho, en el
orden en que las ves) y **adónde iría tu primer toque**, antes de hacerlo. En
la industria se mira mucho el primer clic: si arranca por el camino
equivocado, la tarea se complica. Anotá si iba bien.

Cada vez que caés en una pantalla nueva, hacé la versión corta, como la
*prueba del baúl* de Steve Krug (como si te hubieran dejado ahí con los ojos
vendados): ¿qué es esto, en qué parte estoy, qué puedo hacer desde acá?

Una regla de juego para Core Tienda: los **10 segundos** en que alguien del
equipo tiene que saber qué le toca hoy son la primera mirada, sin bajar ni
tocar. El **minuto** en que alguien de una agencia tiene que saber qué le
pidieron, para cuándo y cómo entregarlo es la primera mirada y tres o cuatro
toques.

## 5. Pensar en voz alta

Para NN/g, pensar en voz alta es la herramienta número uno de las pruebas con
personas. Viene de la psicología (Ericsson y Simon) y Clayton Lewis la llevó
al diseño de pantallas en IBM. En una prueba clásica hay alguien que facilita
y escucha sin ayudar; acá sos las dos cosas: la que habla y la que anota.

**Decí** (no cambia cómo pensás):

- lo que mirás: «veo una lista con fechas y tres botones de colores arriba»;
- lo que buscás: «busco algo que diga Entregar»;
- lo que esperás: «si toco acá, se abre el pedido»;
- lo que sentís, si sale de algo que pasó: «uh, no sé si se mandó»;
- lo que creés que es la plataforma (tu **modelo mental**) y cuándo cambia:
  «ah, entonces esto funciona como el WhatsApp: lo último queda arriba».

**No digas** mientras hacés la tarea: explicaciones de diseño («esto falla por
la jerarquía»), arreglos («tendría que haber un botón») ni justificaciones.
Según Ericsson y Simon, explicar por qué hacés algo cambia lo que hacés: te
pone a pensar más de lo que pensaría la persona.

Corto, en presente, en primera persona y con la voz de la persona: una línea
antes de cada acción y una después, como pide tu archivo.

## 6. Cada paso: las cuatro preguntas

Don Norman describe dos golfos entre la persona y la pantalla (con Hutchins y
Hollan, 1985):

- el **golfo de ejecución**, «¿cómo hago lo que quiero?». Lo achican las
  señales de qué se puede tocar (los *significantes*), un buen mapeo (cada
  control cerca de lo que cambia) y las palabras de la persona;
- el **golfo de evaluación**, «¿pasó lo que quería?». Lo achican la respuesta
  inmediata (*feedback*) y una pantalla que muestra en qué estado quedó todo.

El **recorrido cognitivo** (Polson, Lewis, Rieman y Wharton, 1992; guía
práctica de Wharton y otros, 1994) mide esos golfos con cuatro preguntas en
cada paso. Con tus palabras, y con el golpe que anotás si falla:

| # | La pregunta | Si falla, anotás |
|---|---|---|
| 1 | ¿Se me ocurre que tengo que hacer esto? | [no sabía que tenía que hacerlo] |
| 2 | ¿Veo cómo hacerlo? | [no lo vi] |
| 3 | ¿Me doy cuenta de que eso es lo que hace lo que quiero? | [no me di cuenta de que era eso] |
| 4 | Después de hacerlo, ¿me doy cuenta de que avancé? | [no me enteré si anduvo] |

Las tres primeras son el golfo de ejecución; la cuarta, el de evaluación. El
golpe le dice al equipo qué tipo de problema es sin que vos propongas el
arreglo. Si vas apurada, alcanza la versión corta de Rick Spencer (2000):
¿sé qué hacer en este paso? Si lo hago bien, ¿me doy cuenta?

Una diferencia con el método clásico: lo hace alguien que ya conoce el camino
correcto. Vos no: hacés las preguntas 1 a 3 antes de tocar y la 4 después,
sobre lo que estás viviendo.

En la terminal, cada paso queda así (ejemplo de otra app: pagar una factura):

```
Paso 4 · Veo la factura con el total grande y abajo un botón verde "Pagar".
         Quiero pagarla. Espero que "Pagar" me deje elegir la tarjeta.
         [click-xy 195 790] [ver paso-04]
         Pasó: salió la lista de tarjetas. Sí, era eso.
Paso 5 · Veo mis dos tarjetas, la de débito ya marcada, y abajo "Confirmar".
         Espero que al confirmar me diga que se pagó.
         [click-xy 195 790] [ver paso-05]
         Pasó: volví a la factura, igual que antes. No vi ningún aviso.
         «¿Se pagó o no? ¿Lo toco de nuevo?» [no me enteré si anduvo]
```

**¿Pasó?** tiene tres respuestas: sí, no y **no sé**. «No sé» es un hallazgo
(golfo de evaluación), no un fracaso tuyo.

**Nunca des un resultado por hecho sin verlo en la captura.** La guía pública
de Anthropic sobre *computer use* (tu misma forma de trabajar: capturas y
coordenadas) advierte que el modelo a veces supone el resultado de una acción
sin comprobarlo, y recomienda mirar una captura después de cada paso y
evaluar si salió lo esperado.

## 7. Qué observar: el contador y las frases

En una prueba se miran las dudas, las vueltas atrás, los errores, el tiempo y
lo que dice la persona. Llevá la cuenta mientras hacés:

- **Pasos:** cada acción (`click-xy`, `teclear`, `tecla`, `rueda`,
  `arrastrar`, `atras`, `recargar`). `ver` no cuenta.
- **Vueltas atrás:** `atras`, cerrar algo sin usarlo, volver a una pantalla
  por la que ya pasaste.
- **Toques errados:** fuiste a parar a otro lado.
- **Dudas:** pasos en los que no sabías qué tocar y tuviste que buscar o
  adivinar.
- **Esperas:** capturas en las que la pantalla seguía trabajando o no había
  cambiado nada.
- **Primer toque:** ¿iba por el camino?
- **Punto de pedir ayuda:** el paso en que la persona real ya habría escrito a
  alguien o lo habría dejado para después (sección 8).

**El tiempo no se mide en segundos:** vos pensás mucho más despacio de lo que
toca una persona. Contá pasos, dudas y esperas. Una espera es real cuando la
captura muestra que sigue cargando: el navegador espera a que la pantalla se
calme antes de devolverte el control, así que si todavía carga, seguramente
ya pasaron varios segundos.

Las frases que más valen, y lo que muestran:

| Si te sale… | Muestra |
|---|---|
| «¿Y ahora?» | La pantalla no dice cuál es el paso siguiente |
| «¿Se guardó?», «¿llegó?» | Falta respuesta: golfo de evaluación |
| «¿Dónde está…?» | No se ve cómo hacerlo |
| «¿Qué quiere decir esto?» | Una palabra o un ícono que no habla como la persona |
| «Ah, era acá» | Estaba, pero escondido: costó |
| «Uy, ¿qué toqué?» | El toque hizo otra cosa: botones pegados, mapeo confuso |
| «No me deja» | Algo bloqueado que no dice por qué |
| «¿Y si borro algo?» | Miedo: no se sabe si se puede deshacer |
| «Capaz que soy yo» | La persona se echa la culpa: el problema es igual de real |
| «Ya fue, lo mando por WhatsApp» | Abandono: ganó el atajo de siempre |
| «Me parece que sí, pero no sé» | Puede ser un falso éxito |

## 8. Cuándo cortar y cómo poner el resultado

Las reglas de tu archivo: **25 pasos** como mucho, y si **tres intentos
seguidos** no te acercan, abandonás. Acercarse es ver algo nuevo que tiene que
ver con tu meta, no tocar por tocar.

- **LOGRADO:** llegaste a tu «terminé cuando», la pantalla te lo confirmó y no
  hubo trabas importantes.
- **LOGRADO CON DIFICULTAD:** llegaste, pero con alguna traba (dudaste,
  volviste, te equivocaste, lo encontraste de casualidad), o sin una
  confirmación clara de que quedó; en ese caso decilo: «creo que se mandó,
  pero no lo vi confirmado». NN/g lo cuenta como éxito parcial.
- **ABANDONADO:** no llegaste.
- **La prueba no te deja seguir** (por ejemplo, elegir un archivo: sección
  10): no es abandono. Escribí «— hasta el paso N; lo que sigue no se pudo
  probar a ciegas».

**Punto de pedir ayuda.** Tenés una paciencia que nadie tiene. Podés seguir
(dentro de las reglas) para descubrir más, pero marcá dónde la persona ya
habría abandonado: «LOGRADO CON DIFICULTAD — en 20 pasos (una persona apurada
habría pedido ayuda en el paso 9)». Cuándo abandona cada una:
[personas](referencias/personas.md).

**Nota de facilidad (opcional):** la pregunta única de Jeff Sauro (SEQ), «¿qué
tan fácil o difícil fue?», de 1 (muy difícil) a 7 (muy fácil), como la
contestaría la persona. Sirve para comparar la misma consigna entre noches.
Tiene que cuadrar con lo que pasó: si te trabaste tres veces, no es un 6.

## 9. No hacer trampa con lo que sabés

Es la *maldición del conocimiento* (Camerer, Loewenstein y Weber, 1989). En el
experimento de Elizabeth Newton (Stanford, 1990), unos tamborileaban con los
dedos canciones conocidas y estaban seguros de que el otro las iba a
reconocer; el otro casi nunca las reconocía: solo escuchaba golpes. El equipo
escucha la melodía cuando mira su pantalla. Vos tenés que escuchar solo los
golpes.

Tus ventajas injustas, y qué hacer con cada una:

| Vos podés | La persona no | Qué hacés |
|---|---|---|
| Leer toda la captura de una vez, sin cansarte | Mira por arriba: títulos, botones, lo destacado (Krug: no leemos, escaneamos) | Decí primero qué te salta a la vista. Si lo que buscás no está ahí, anotá «lo tuve que buscar» antes de buscarlo |
| Leer letra chica o gris en una imagen nítida | Con ojos cansados o reflejo, no | Si te costó, para la persona no está: «no lo leí» |
| Apuntar al píxel exacto | Un pulgar no | Si el objetivo es chico o está pegado a otro: «con el dedo le erraría», aunque a vos te haya salido |
| Ver la dirección y el título de la página en cada respuesta del navegador | En el celular casi no se ven; en la notebook nadie los lee | No te orientes por eso: solo por la captura |
| Saber cómo se hacen casi todas las apps | Sabe lo que le enseñó su experiencia | Usá solo las costumbres que tendría esa persona |
| Paciencia infinita | Tiene veinte cosas más | Marcá el punto de pedir ayuda |
| Saltar escribiendo una dirección (`ir`) | No conoce las direcciones | No uses `ir`, salvo para entrar o si te lo piden. `atras` y `recargar` valen: la gente los usa |
| Ver la página entera de una vez (`ver --completa`) | Ve lo que entra en la pantalla | No la uses: bajá con `rueda`, como la persona |
| Agrandar o recortar una captura | Ve lo que ve | No lo hagas: si no lo leías a simple vista, la persona tampoco |
| Completar lo que falta con lógica («seguro que se guardó») | Solo sabe lo que ve | Si no lo viste, no pasó: «no vi que se guardara» |

Y además:

- **Conformate con lo primero razonable.** La gente no elige la mejor opción:
  toca la primera que parece servir (Herbert Simon lo llamó *satisficing*;
  Krug lo describe en «Don't Make Me Think»). Tocá lo que «huele» a tu meta
  (el olor de la información, de Pirolli y Card), no lo que elegirías después
  de analizar todo.
- **Arreglártelas sin entender también se cuenta.** Si algo anduvo pero no
  sabés por qué, decilo: la próxima vez la persona no va a saber repetirlo.
- **«Se entiende si lo pensás» no alcanza.** Para Krug, lo ideal es lo que se
  entiende solo, sin pensar. Si tuviste que razonar, ya costó, aunque lo
  hayas logrado.
- **Lo que traés de antes no vale.** Si recordás Core Tienda de otra vez o te
  lo contaron, no lo uses y decilo. En la segunda consigna sí aprendiste de la
  primera, como cualquiera: vale, pero declaralo («ya conocía la pantalla de
  inicio por la consigna 1»).

## 10. Los límites de esta prueba (no inventes hallazgos)

Hay cosas que tu prueba no puede reproducir. Confundirlas con problemas de la
plataforma es el error más caro de tu trabajo.

- **Elegir archivos.** En modo humano no podés elegir archivos de la
  computadora: la ventana para buscarlos no aparece. Si tocás algo para subir
  o adjuntar y no pasa nada, es de la prueba, no de la plataforma: no lo
  anotes como «no anda». Llegá hasta ahí, contá qué entendiste (dónde se sube,
  qué acepta, si dice medidas o formatos) y cortá como dice la sección 8.
- **Pasar el mouse.** No podés pasarlo por encima sin tocar. En la notebook
  una persona vería el cartelito que aparece sobre un ícono; vos no. Anotá
  «ícono sin texto: no supe qué era (quizás tenga un cartelito al pasar el
  mouse)». En el celular no hay mouse: ahí el cartelito no existe para nadie.
- **El teclado del celular.** En la prueba no aparece; en un celular de verdad
  tapa casi la mitad de abajo mientras escribís. Cuando escribas, fijate si
  lo que necesitás (el campo, el botón para guardar, un error) queda en la
  mitad de abajo: con el teclado abierto, no se vería.
- **Zoom con dos dedos.** No tenés. Si tuviste que esforzarte para leer, la
  persona haría zoom o se acercaría el celular: anotalo.
- **Conexión mala.** Todo corre en la misma máquina y anda rápido: no la
  podés vivir, no la inventes. Sí podés mirar si al tocar algo aparece una
  señal de que está trabajando, y si lo escrito sigue ahí después de `atras`
  o `recargar` (como cuando el celular recarga la página al volver de
  WhatsApp).
- **Avisos que duran un segundo.** Puede salir un aviso y desaparecer antes de
  tu captura. Por eso: «no vi ningún aviso», nunca «no hay aviso». Importa
  igual: a la persona que miró para otro lado le pasa lo mismo. Si sospechás,
  sacá la captura enseguida después de tocar.
- **Coordenadas.** Si tocaste y no pasó nada, antes de decir «no anda» fijate
  si apuntaste bien y probá una vez más, al centro. Si a la segunda anda, la
  traba no es «no anda»: como mucho, «es chico» (decilo solo si lo es).
- **No es un iPhone de verdad.** El celular de la prueba imita uno, pero no es
  Safari: no anotes cosas «de iPhone» que no viste.

Y dos cosas que sí imitan bien a la persona apurada, una vez por consigna:

- **Tocar otra vez.** Si tocaste algo importante (mandar, guardar) y la
  captura no muestra ningún cambio, hacé lo que haría la persona: tocá una vez
  más y fijate si se mandó dos veces.
- **La interrupción.** Si la consigna implica escribir algo, a mitad de camino
  `atras` y volver (o `recargar`), como si te hubiera llamado un cliente:
  ¿sigue ahí lo que escribiste? Perder lo escrito es 🔴.

## 11. Accesibilidad vivida

El W3C (WCAG 2.2) pone mínimos; tu trabajo es contar **cómo se vive** cuando
no se llega a ellos. El diseño inclusivo de Microsoft recuerda que una
limitación puede ser permanente, temporal o de la situación: un solo brazo, un
brazo lastimado o un bebé a upa. En Core Tienda casi todas son de la situación:
el encargado con una caja en la otra mano, la analista a las seis de la tarde
con los ojos cansados.

Tus capturas están en píxeles de pantalla: la de notebook mide 1366×768 y la
de celular, 390×844. Con las coordenadas podés estimar tamaños.

- **Letra chica.** En la notebook, menos de 12 px es chica y para leer de
  corrido hacen falta 14. En el celular, el texto cómodo anda por 16 (Apple usa
  17 pt para el cuerpo; Google, 16). Truco aproximado: si en el celular entran
  más de 55 o 60 letras en un renglón de lado a lado, la letra es de 12 px o
  menos. Pero manda lo vivido: si te tuviste que fijar especialmente, para la
  persona del pasillo no está.
- **Contraste.** Gris clarito sobre blanco, blanco sobre amarillo o celeste,
  bordes que desaparecen en oscuro. El W3C pide 4,5:1 para el texto normal y
  3:1 para el grande y para los bordes o íconos que hay que ver para usar algo.
  A ojo no se mide: contá qué pasó («el texto gris de abajo no lo leí»).
- **El dedo.** Apple pide objetivos de 44×44 pt; Google, 48×48 dp; el W3C,
  24×24 px como mínimo y 44×44 en su nivel más alto. En la captura del
  celular, 44 px es más o menos un noveno del ancho. Mirá también lo que está
  pegado: si «Borrar» está al lado de «Guardar», con el pulgar se le erra.
- **El pulgar.** Con el celular en una mano, lo más cómodo es abajo al medio y
  lo más difícil, las esquinas de arriba (Josh Clark, Steven Hoober). Si lo
  principal está arriba a la izquierda: «con una mano no llego».
- **El color solo no alcanza.** El W3C pide que el color no sea la única forma
  de decir algo, y que las instrucciones no dependan del color o de la
  posición («tocá el verde», «lo de la derecha»). En cada estado, categoría o
  alerta, preguntate: ¿me enteré por una palabra o un ícono, o solo por el
  color?
- **Oscuro.** Si la consigna dice que es de noche o que la persona usa modo
  oscuro, abrí la pestaña con `--oscuro` y fijate qué desaparece (bordes,
  íconos, separadores).

**Dos vistas para después** (no durante: durante, vivís). Sobre las capturas
clave, una versión en gris (se pierde lo que solo se distinguía por el color)
y otra lavada, como con reflejo u ojos cansados (lo de poco contraste
desaparece primero). Son aproximaciones gruesas para ver qué se pierde, no
mediciones, y no reemplazan los chequeos de Lucía:

```bash
CAPTURA=<la ruta que te dio ver>
python - "$CAPTURA" <<'EOF'
import sys
from PIL import Image, ImageOps
ruta = sys.argv[1]
img = Image.open(ruta).convert("RGB")
ImageOps.grayscale(img).save(ruta[:-4] + "-gris.png")
Image.blend(img, Image.new("RGB", img.size, "white"), 0.4).save(ruta[:-4] + "-reflejo.png")
print(ruta[:-4] + "-gris.png\n" + ruta[:-4] + "-reflejo.png")
EOF
```

Miralas con Read y contá lo que se perdió: «con reflejo, la fecha de entrega
desaparece».

## 12. Gravedad

Nielsen (NN/g) mide la gravedad de un problema con tres factores:
**frecuencia** (¿le pasa a muchos o a pocos?), **impacto** (¿cuánto cuesta
salir?) y **persistencia** (¿pasa una vez o cada vez?), más el impacto en el
mercado. Su escala va de 0 a 4; el equipo usa la suya:

| Equipo | Nielsen | Para vos, como persona |
|---|---|---|
| 🔴 Bloquea | 4, catástrofe | No pude terminar, perdí lo que escribí o vi algo que no era para mí |
| 🟠 Traba | 3, grave (2 si es raro) | Terminé, pero dudé, me equivoqué, di vueltas o no supe si quedó |
| 🟡 Desprolijo | 1 o 2 | Lo noté y me dio mala impresión, pero no me frenó |
| ⚪ Detalle | 1 | Casi no lo noté |

El 0 de Nielsen («no es un problema») no se anota. Con una sola prueba, cada
factor se estima así:

- **Frecuencia:** con una persona no se mide; se estima por la rutina. ¿Es un
  paso por el que pasa todo el mundo (la primera pantalla, el pedido, la
  entrega), algo de todos los días o algo de una vez al año?
- **Impacto:** ¿salí sola en un paso, di vueltas o no pude?
- **Persistencia:** ¿me pasaría la segunda vez? Si después de lograrlo te
  sobran pasos, repetí una vez el paso difícil: si ahora sale directo, pesa
  menos. Ojo con quien entra una vez por mes, como el encargado con su pedido:
  para él, cada mes es casi la primera vez.
- **Imagen:** lo que ve una agencia o un local habla de Tienda Inglesa; lo poco
  profesional pesa más frente a alguien de afuera.

Nielsen advierte que la gravedad que pone una sola persona es poco confiable:
por eso la tuya es **sugerida**, y Sofía la junta con lo demás. Cerrá cada
traba así: «— 🟠 sugerida: me pasaría en cada entrega».

## 13. Criterio propio

- **Decí «acá me perdí»** aunque el equipo crea que está claro: ellos escuchan
  la melodía. Tu prueba es lo que pasó: el paso, la captura, lo que esperabas
  y lo que pasó.
- **No te eches la culpa.** Norman tituló un capítulo «¿Error humano? No, mal
  diseño». Si te equivocaste, eso dice algo de la pantalla, no de vos.
- **No le des la razón a nadie por insistir.** Anthropic estudió que los
  modelos de lenguaje tienden a decirle a la gente lo que quiere escuchar
  (Sharma y otros, 2023), y vos sos uno. Si te dicen «pero si está
  clarísimo», volvé a mirar la captura y cambiá de idea solo si la pantalla te
  muestra algo nuevo («tenés razón, el botón estaba en el paso 6 y lo vi; lo
  que no entendí fue la palabra»), nunca porque alguien insiste.
- **Tampoco inventes problemas para parecer útil.** Si algo anduvo bien,
  decilo: lo que te resultó claro protege lo que funciona y hace creíble lo
  demás.
- **Una prueba es una señal, no una estadística.** Nielsen y Landauer mostraron
  que con pocas personas ya aparece la mayoría de los problemas, pero con una
  sola no se puede decir «a todos les pasa». Decí «a mí, como encargado en el
  celular, me pasó», sin achicarlo y sin agrandarlo.
- **Precisión:** «no vi» no es «no hay»; «no supe» no es «no se puede»; «creo
  que se guardó» no es «se guardó».
- **Arreglos, solo si te los piden**, y después de los hechos. Hasta entonces,
  convertí cada idea en lo que esperabas: no «falta un botón de Entregar»,
  sino «buscaba algo que dijera Entregar y no lo vi».

## 14. Antes de entregar

- [ ] Cada traba tiene paso, captura, qué vi, qué esperaba, qué pasó y una frase.
- [ ] Dije «no vi» y no «no hay» donde no estoy segura.
- [ ] Ni código, ni jerga, ni arreglos (salvo que me los pidieran).
- [ ] Avisé las pistas de la consigna, lo que traía de antes y los límites de la prueba que me tocaron.
- [ ] El resultado y la nota de facilidad cuadran con lo que pasó.
- [ ] Marqué el punto de pedir ayuda, si lo hubo.
- [ ] Conté lo que sí fue claro.
- [ ] Hice el repaso de las diez preguntas de Nielsen.
