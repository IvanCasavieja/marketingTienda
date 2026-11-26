# Contar lo que viviste

El formato es el de tu archivo (PRUEBA A CIEGAS…). Acá, cómo llenar cada
parte. Tu informe lo lee Sofía, que lo suma al cuaderno con lo demás; los
pasos y las capturas son la prueba, y las mejores frases pueden terminar en
el mail a Ivan. Por eso: pasos exactos y frases humanas.

## Parte por parte

- **Consigna:** textual, con persona y vista. Si traía una pista, sumá
  «(la consigna decía por dónde ir: …)».
- **Resultado:** según la sección 8 de SKILL.md, con los pasos y, si los hubo,
  las vueltas atrás, el punto de pedir ayuda y la nota de facilidad:
  «LOGRADO CON DIFICULTAD — en 14 pasos (2 vueltas atrás; un encargado
  apurado habría llamado a la oficina en el paso 8) · facilidad 3/7».
- **Primera impresión:** dos líneas en primera persona, escritas antes de
  tocar nada: qué creés que es esto, qué te salta a la vista, qué harías
  primero.
- **Dónde me trabé:** una viñeta por traba, en el orden en que pasaron. Si lo
  mismo te pasó dos veces, una sola viñeta con «(me pasó en los pasos 4 y
  9)»: eso también dice que persiste.
- **Lo que me resultó claro:** una o dos cosas concretas, con el paso. Protege
  lo que funciona y hace creíble lo demás.
- **Lo que una persona no sabría:** palabras, íconos e ideas que no
  entendiste, cortito: «"Status": no sé qué quiere decir acá», «el ícono de la
  nube con flecha: ¿sube o baja?».

## Cómo se arma una traba

```
- Paso N (captura <ruta>): vi <...>, esperaba <...>, pasó <...>. «<frase>» [golpe] — <gravedad> sugerida: <por qué>
```

- **Vi:** lo que hay en la captura, como lo describiría cualquiera: dónde
  (arriba a la derecha), cómo es (un botón gris, una lista), qué dice (entre
  comillas, tal cual). Nada de código ni nombres de componentes.
- **Esperaba:** tu modelo mental. Es la parte que más le sirve al equipo.
- **Pasó:** el hecho, comprobado en la captura. Si no lo viste, «no vi».
- **Frase:** lo que diría la persona en voz alta. Corta, puede tener emoción.
- **Golpe:** cuál de las cuatro preguntas falló (SKILL.md, sección 6).
- **Gravedad sugerida:** con el porqué en pocas palabras (frecuencia,
  persistencia).

Chequeo rápido con el mapa de empatía que usan IBM y NN/g (dice, piensa,
hace, siente): ¿tu traba cuenta lo que **hiciste** (el paso), lo que
**pensabas** (esperaba), lo que **dirías** (la frase) y cómo te **sentiste**?
Si le falta una, completala.

## Mal y bien (ejemplo inventado: no describe Core Tienda)

Mal:

```
- Paso 6: la UX de la entrega no es intuitiva, falta feedback y el CTA no se destaca.
```

Bien:

```
- Paso 6 (captura .../006-martina-paso-06.png): vi el pedido abierto con un texto
  largo y, abajo de todo, dos botones grises iguales, «Guardar» y «Listo»;
  esperaba algo que dijera Entregar o Mandar; toqué «Listo» y la ventanita se
  cerró sin decir nada. «¿Lo mandé o solo lo guardé? ¿Le llega a la de Tienda?»
  [no me enteré si anduvo] — 🟠 sugerida: me pasaría en cada entrega.
```

## De opinión a vivencia

Nielsen lo escribió en 2001 y sigue valiendo: importa lo que la gente hace
más que lo que dice que querría («First Rule of Usability? Don't Listen to
Users»). Tus expectativas son datos; tus ideas de diseño no son tu trabajo.

| En vez de… | Contá… |
|---|---|
| «Falta un botón de Entregar» | «Buscaba algo que dijera Entregar y no lo vi» |
| «El botón es muy chico» | «Le erré con el dedo» o «es chiquito y está pegado a otro» |
| «No hay feedback» | «Toqué Guardar y no cambió nada: no sé si se guardó» |
| «La jerarquía es confusa» | «Lo primero que vi fue X; lo que buscaba estaba abajo, chiquito» |
| «Es poco intuitivo» | «No supe qué tocar: probé A y B antes de dar con C» |
| «Debería pedir confirmación» | «Toqué Borrar y se borró, sin preguntarme» |
| «Tiene poco contraste» | «El texto gris de abajo no lo leí» |
| «Usa jerga» | «"Status" no sé qué quiere decir acá» |
| «Está bien diseñado» | «Lo encontré de una: el botón decía exactamente lo que buscaba» |

## Palabras de persona

| No digas | Decí |
|---|---|
| modal, pop-up | ventanita, cartel |
| toast, snackbar | aviso, cartelito |
| dropdown | lista que se despliega |
| CTA, botón primario | el botón principal, el botón azul |
| hover, tooltip | el cartelito que sale al pasar el mouse |
| feedback | que me avise, que me diga algo |
| menú kebab, hamburguesa | los tres puntitos, las tres rayitas |
| input | el lugar para escribir |
| intuitivo, poco intuitivo | «lo encontré de una», «no supe qué hacer» |
| UX, usabilidad, affordance | nada: contá lo que pasó |

## Si te piden ideas

Solo si te las piden, y después de los hechos, en una parte aparte. Desde la
necesidad de la persona («me habría servido ver, al lado de lo que me
pidieron, si ya lo había mandado»), nunca como receta técnica. Una línea por
traba, como mucho.
