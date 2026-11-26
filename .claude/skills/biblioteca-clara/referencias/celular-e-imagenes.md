# El celular, el HTML del mail y las imágenes

## Cómo se lee en una pantalla

En pantalla la gente no lee: escanea (Jakob Nielsen, «How Users Read on the
Web», 1997). Mira el principio de los títulos y de los párrafos, y baja: es
el patrón en F que describió Nielsen Norman Group en 2006. En el celular,
con una mano y entre otras cosas, todavía más. Por eso:

- **El título dice de qué es la sección** y la primera frase dice lo
  principal (Google: «Write a great opening sentence»).
- **Lo importante, al principio** de cada título, frase e ítem (Microsoft:
  «Front-load keywords for scanning»).
- **Párrafos de 1 a 3 frases** (README: 3 líneas como mucho). Lo que en la
  notebook ocupa 3 líneas, en el celular ocupa casi el doble.
- **Un emoji por título y ninguno en el texto.** Los del molde ordenan; los
  de más hacen ruido (y los de gravedad están prohibidos).
- **«Cómo verlo» en una línea con flechas:** «Entrá como un local → **Mi
  pedido** → confirmá el mes: aparece la pregunta y después el cartel
  verde.»

## Lo que hace `correo.py` con tu Markdown

El script del skill `correo-del-equipo` convierte el Markdown en HTML con
los estilos escritos en cada elemento, que es lo que mejor aguantan Outlook
y Gmail. Es simple y va línea por línea. Probado el 25/11/2026:

- **Cada línea es un párrafo.** Un párrafo partido en dos líneas sale como
  dos párrafos separados. Escribí cada párrafo en una sola línea, por larga
  que quede en el archivo.
- **Cada ítem de lista, en una sola línea.** Si un ítem sigue en la línea de
  abajo, la lista se corta y el resto sale como párrafo suelto.
- **Sin sublistas:** la sangría se pierde y el subítem queda al mismo nivel.
- **Sin tablas ni citas con `>`:** salen las rayitas `|` y el `>` tal cual
  (y una tabla, en el celular, igual se cortaría). Para citar, «comillas».
- **Cursiva con `_guion bajo_`;** con `*un asterisco*` salen los asteriscos.
  Negrita con `**dos asteriscos**`.
- **Todos los títulos, de `#` a `######`, salen como título:** usá `###`,
  como el molde. Una línea con `---` sale como raya separadora (la usa el
  pie).
- **Una línea que empieza con «número, punto, espacio» se vuelve lista** y
  se renumera desde 1. Si una frase empieza con un número, reescribila
  («Fueron 3 cambios», no «3. cambios»). Una lista numerada cortada por una
  imagen o un párrafo vuelve a empezar en 1.
- **Imágenes, solo con dirección `https://`.** Con una ruta local
  (`/tmp/...`) no sale la imagen: sale el texto `![...](/tmp/...)` crudo. El
  texto alternativo no puede llevar `]`, y la dirección no puede llevar
  espacios ni `)`.
- **El pie con el búho** («Respondé este mail (a todos) para hablar con
  nosotros») lo agrega el script: no lo repitas.
- **La versión de texto plano es tu Markdown tal cual.** Otra razón para que
  se entienda sin formato: que nada dependa de un color o de una negrita.

## Outlook y Gmail

En Tienda Inglesa hay usuarios corporativos de Microsoft
(`docs/AZURE.md`): contá con que una parte del hilo lee en Outlook, en la PC
o en el celular. Lo que conviene saber:

- **Outlook clásico de Windows arma los mails con el motor de Word.** Ignora
  parte de los estilos (las esquinas redondeadas, algunos anchos máximos).
  El texto aguanta bien; las imágenes pueden salir más grandes de lo
  pensado. Si alguien dice que la imagen se ve gigante en la PC, es eso:
  contáselo al coordinador para que lo vea el equipo de día (se arregla en
  `correo.py`, dándole a la imagen el ancho como atributo). No lo resuelvas
  sacando la imagen.
- **Outlook suele bloquear las imágenes de afuera** (sobre todo el clásico)
  hasta que la persona las habilita. Lo primero que ve es el texto
  alternativo: tiene que contar el cambio solo.
- **Gmail muestra las imágenes, pero recorta los mails muy pesados** (más de
  unos 102 KB de HTML) con un «Ver mensaje completo». Un mail como el
  nuestro no llega ni cerca: no pegues bloques largos de texto copiado.
- **El modo oscuro:** algunas aplicaciones invierten los colores del mail.
  No le confíes el mensaje al color: «un cartel verde que dice "Ya
  confirmaste el pedido"», no solo «un cartel verde».
- **El asunto se corta pronto** en la lista del celular: por eso los 45
  caracteres del README, con lo que cambia al principio.
- **La vista previa** (la línea gris debajo del asunto, en la bandeja y en
  la notificación) es el principio del cuerpo: la primera frase de «Qué
  cambia» tiene que alcanzar sola.

## Contar con imágenes

«Ivan es visual: una captura vale más que un párrafo» (tu archivo). Pero una
imagen mala confunde más que un párrafo malo. Lo que enseñan los que más
saben de ilustrar (Google en *Technical Writing Two*, Cole Nussbaumer
Knaflic, Edward Tufte), aplicado al antes y ahora:

1. **Mirala vos antes de escribir.** Abrí el archivo con Read (si solo tenés
   la dirección, pedí la ruta local). Las capturas se miran, no se describen
   de memoria (README).
2. **Escribí primero el epígrafe** (Google: «Write the caption first»): qué
   tiene que llevarse Ivan de la imagen, en una frase. Si no te sale, la
   imagen no sirve o muestra demasiado.
3. **Una imagen, una idea** (Google: «Constrain the amount of information in
   a single drawing»): el antes y ahora de un solo cambio. Una imagen por
   cambio y dos como mucho en el mail (tu archivo).
4. **Que se lea en el celular.** `evidencia.py` pone las capturas de celular
   lado a lado y las de notebook una arriba de la otra, de hasta 1000 px de
   ancho. Una pantalla entera de notebook achicada al ancho de un celular no
   se lee si el cambio es chico. Probalo achicándola a unos 400 px y
   mirándola con Read; si no podés leer el texto que importa, pedile al
   coordinador un recorte de la zona que cambia o la versión de celular:

   ```bash
   python3 -c "import sys;from PIL import Image;im=Image.open(sys.argv[1]).convert('RGB');im.resize((400,round(im.height*400/im.width))).save('/tmp/al-ancho-del-celular.jpg')" <la imagen>
   ```
5. **Llevá la vista a lo que cambió** (Google: «Focus the reader's
   attention»). Si el cambio no salta a la vista, pedí el recuadro rojo de
   `evidencia.py --marco`.
6. **Que el antes y el ahora se puedan comparar:** la misma vista, el mismo
   zoom y los mismos datos (los *small multiples* de Tufte: mismo marco,
   misma escala). Si cambian otras cosas, el ojo busca diferencias que no
   son el cambio: pedilas de nuevo.
7. **Que no se vea nada que no debe:** ninguna contraseña, dirección de mail
   ni dato real. El repo y el cuaderno son públicos.

## El texto alternativo y el epígrafe

Son dos cosas distintas y hacen falta las dos.

**El texto alternativo** (`![esto](dirección)`) es lo que aparece si la
imagen no carga o si Outlook la bloquea, y lo que lee un lector de pantalla.
Tiene que dar la misma información que la imagen (WCAG 2, criterio 1.1.1; el
«árbol de decisión del alt» de la W3C ayuda a elegir qué poner). Una frase,
sin «imagen de»: qué se ve y qué cambió, con el texto clave de la pantalla.

- ✗ `![captura](…)` o `![Antes y después](…)`
- ✓ `![Antes y ahora en el celular del local: antes no decía nada; ahora, un cartel verde «Ya confirmaste el pedido»](…)`

El skill del cuaderno muestra `![Antes y después](…)` solo como forma; el
texto, como pide tu archivo, dice qué se ve.

**El epígrafe** es para quien sí ve la imagen: corto, con la conclusión y
debajo de la imagen (Google). Las franjas ANTES y AHORA ya rotulan, así que
el epígrafe dice **qué mirar**. Muchas veces la frase de arriba ya lo hace
(«ahora ve un cartel verde…») y no hace falta otro. Si hace falta, una línea
en cursiva:

```markdown
_Fijate arriba: el cartel verde ahora dice a quién pedirle un cambio._
```
