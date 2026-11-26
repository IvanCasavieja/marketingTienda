# Usabilidad aplicada

## Las 10 heurísticas de Nielsen, en Core Tienda

Jakob Nielsen y Rolf Molich (1990), versión de Nielsen de 1994; Nielsen
Norman Group las mantiene con ejemplos actuales. Sirven para revisar sin
usuarios y para nombrar el problema con un principio reconocido.

| # | Heurística | La pregunta | Ejemplo de Core Tienda |
|---|---|---|---|
| 1 | Visibilidad del estado del sistema | ¿Sé qué está pasando? | Alta de usuario sin «Creando…» (Ivan, 25/11/2026: «no me muestra que esté cargando ni nada»). Pantalla de carga muda con el servidor dormido |
| 2 | Coincidencia con el mundo real | ¿Habla como la gente? | «versión», «pieza», «tablero»; no «jobs», «upload», «status», «Template» |
| 3 | Control y libertad | ¿Puedo salir y deshacer? | «Atrás» en medio de una entrega borra todo sin preguntar (H-039); carteles sin salida (H-003) |
| 4 | Consistencia y estándares | ¿Lo mismo se ve y se llama igual? | Tres botones principales; «Análisis IA», «La Triada» y «El análisis con IA» para lo mismo; «Avisos» y «Notificaciones» |
| 5 | Prevención de errores | ¿El diseño evita el error antes del mensaje? | «Otro» y «Otra cosa» juntos (H-047); borrar una acción se lleva las entregas (H-001) |
| 6 | Reconocer antes que recordar | ¿Tengo a la vista lo que necesito? | Al entregar la corrección, mostrarle a la agencia qué tenía que cambiar (H-037) |
| 7 | Flexibilidad y eficiencia | ¿Quien sabe va más rápido sin trabar al nuevo? | Filtros que se recuerdan, acciones en lote, Escape y Enter que hacen lo esperable |
| 8 | Diseño estético y minimalista | ¿Cada cosa merece la atención que pide? | Login con cuatro tarjetas que venden IA; «Powered by…»; mascotas |
| 9 | Reconocer, diagnosticar y salir de los errores | ¿El error dice qué pasó y qué hacer? | «Error desconocido» en cenefas v2 (H-008); «Contraseña incorrecta» cuando falta un permiso (H-013) |
| 10 | Ayuda y documentación | ¿Encuentro ayuda en el momento? | Guía de uso desactualizada; Don Tino siempre en el mismo lugar |

Nielsen gradúa la gravedad de 0 a 4; el cuaderno usa bloquea / traba /
desprolijo / detalle. Para elegir qué hacer: gravedad × cuánta gente × cuán
seguido ÷ esfuerzo (`criterios.md`).

## Leyes de UX, con sus límites

Recopiladas por Jon Yablonski en *Laws of UX*. Usalas como argumento, no como
dogma: cada una tiene un alcance.

| Ley | Qué dice | Cómo se usa acá | Su límite |
|---|---|---|---|
| **Fitts** (Paul Fitts, 1954) | Alcanzar un objetivo tarda más cuanto más lejos y más chico está | Botones grandes y cerca de la mano: las acciones de una fila, en la fila; el principal, abajo en el celular | Mide el movimiento, no la decisión: un botón enorme que no se entiende no ayuda |
| **Hick–Hyman** (Hick, 1952; Hyman, 1953) | Decidir tarda más cuantas más opciones hay | Las 13 pastillas de «¿Qué se pide?» frenan: lista en una columna o desplegable, ordenada por uso, con una sola «Otra» | Una lista ordenada que la persona conoce, con buscador, es rápida aunque sea larga (60 locales) |
| **Jakob** (Jakob Nielsen) | La gente pasa casi todo su tiempo en otros sitios y espera que el tuyo funcione igual | Campanita arriba a la derecha (Ivan, 18/11/2026), logo que lleva al inicio, X arriba a la derecha, Escape cierra, tablero como Trello, patrones de Microsoft 365 | No es copiar: de COR se toma cómo funciona, no su diseño |
| **Miller** (George A. Miller, 1956) | La memoria de corto plazo retiene pocos elementos («siete, más o menos dos») | No hacer recordar cosas entre pantallas: mostrar lo pedido, el código del local, lo que hay que corregir | Habla de memoria, **no** de cuántos ítems puede tener un menú. Nelson Cowan (2001) lo bajó a unos 4 bloques. «Máximo 7 opciones» es un mal uso |
| **Doherty** (Doherty y Thadani, IBM, 1982) | La productividad sube cuando el sistema contesta en menos de unos 400 ms | Responder a cada toque al instante, aunque sea con un estado; lo pesado, en segundo plano | Es una meta de respuesta, no permiso para animaciones de relleno |
| **Tesler** (Larry Tesler) | La complejidad no desaparece: alguien la carga | Que la cargue la plataforma: aceptar ZIP, PDF, links. Ivan: «tiene que adaptarse a su forma de trabajar, no al revés» (25/11/2026) | Esconder complejidad no es borrar opciones que la gente necesita |
| **Postel** (principio de robustez) | Sé tolerante con lo que recibís | Aceptar «099 123 456» y «099123456»; «1/12» y «01/12/2026»; precios con punto o coma | Tolerante al leer, estricto al guardar y al mostrar |
| **Estética-usabilidad** (Kurosu y Kashimura, 1995) | Lo lindo se percibe como más fácil de usar | Prolijidad = confianza, sobre todo para las agencias | También esconde problemas: una pantalla linda puede trabar igual. Probá con tareas, no con opiniones |

## Formularios

Base: Luke Wroblewski (*Web Form Design*), GOV.UK Design System, NN/g.

- Una columna. Etiqueta **arriba** del campo y siempre visible. El texto de
  ejemplo adentro del campo no es etiqueta: desaparece al escribir (NN/g lo
  documentó como dañino).
- Pedí solo lo necesario y marcá lo opcional con «(opcional)» en lugar de
  llenar de asteriscos lo obligatorio (GOV.UK). Valores por defecto
  inteligentes: la fecha de hoy, quien carga como responsable, el mundo en el
  que está. El ancho del campo anticipa el dato.
- Validá al salir del campo y al enviar, no en cada tecla. El error va debajo
  del campo, con texto (no solo borde rojo), y el foco va al primero; con
  varios, un resumen arriba con un link a cada campo (GOV.UK).
- **Nunca se pierde lo escrito:** borrador automático, aviso antes de salir
  con cambios sin guardar (H-039) y, si el envío falla, los datos quedan.
- El botón dice lo que hace («Crear tarea», «Entregar versión 2»). El orden
  de los botones varía entre plataformas y NN/g concluye que lo que importa es
  la consistencia: elegí uno y usalo siempre. En el celular, el principal
  ocupa el ancho, abajo.
- Un botón gris porque falta algo esconde **qué** falta («Confirmar» en
  Finanzas, H-046). Mejor habilitado y que al tocarlo marque lo que falta; si
  queda deshabilitado, al lado dice qué falta.
- En el celular: teclado justo (`type="email"`, `inputmode="numeric"`),
  `autocomplete` (WCAG 1.3.5) y campos de 16 px.
- Doble clic no manda dos veces: el botón pasa a «Guardando…» y se bloquea.

## Navegación

- El menú marca dónde estás y esa marca está a la vista (H-026); el título de
  la pantalla coincide con el ítem del menú.
- **Olor a información** (Pirolli y Card, teoría de búsqueda de
  información): la etiqueta anticipa lo que hay detrás. «Mes», al lado del
  selector de mes, se leía como «este mes» e Ivan no encontró «el calendario
  general de todo» (12/11/2026).
- Lo diario, a un toque y nunca escondido en «Más»: el núcleo arriba,
  Herramientas plegado.
- En el celular, barra de abajo con 3 a 5 destinos (Material y Apple coinciden
  en ese rango) y «Más» para el resto, sin nada flotante encima (H-025). Quien
  no tiene barra igual necesita ver sus avisos.
- Un solo lugar para lo mismo (dos botones para cambiar de mundo, H-004) y
  una salida en cada cartel, error y página inexistente (H-003, H-058).
- Los links llevan adonde dicen: el del mail abre la tarea, también después de
  iniciar sesión (H-040).
- Nada de navegación para un solo contenido: Ivan sacó las pestañas de la
  ficha porque «al tener solo las tareas, tener todas esas pastillas es al
  pedo» (24/11/2026).

## Tablas y filtros

- Texto a la izquierda; números a la derecha con `tabular-nums`; encabezado
  alineado como su columna; fechas como en Uruguay (25/11/2026).
- Encabezado fijo al bajar, en texto normal de 12–14 px, no en mayúscula
  espaciada como el `.table-th` de hoy. Filas separadas por una línea que se
  vea (el borde `slate-50` de hoy casi no se ve) o por aire.
- Acciones de la fila: la más común, visible y con texto; el resto en «⋯» con
  nombre accesible. Acciones en lote con una barra que aparece al seleccionar
  (Carbon).
- Filtros en una fila (desplegables o pestañas subrayadas); los activos se
  ven y se quitan de a uno, con «Limpiar filtros»; contá los resultados («12
  tareas») y recordalos. En el celular, en una hoja con «Ver 12 resultados».
- Buscar le gana a filtrar cuando la lista es larga y la persona sabe el
  nombre (H-044). El orden por defecto contesta la pregunta: lo vencido
  primero.
- En el celular, cada fila pasa a ser una tarjeta con 2 o 3 datos clave; la
  tabla con scroll de costado, solo si hay que comparar columnas.
- Paginación o «Cargar más» antes que scroll infinito: se puede volver al
  mismo lugar.

## Acciones destructivas y confirmaciones

Escala de protección según el daño (NN/g; Aza Raskin, «Never Use a Warning
When You Mean Undo», 2007):

1. **Reversible y frecuente:** se hace y el aviso ofrece **Deshacer** por unos
   segundos. Ej.: archivar, sacar a alguien de una tarea.
2. **Irreversible y poco frecuente:** confirmación **adentro de la
   pantalla** (no la ventanita gris del navegador, H-070) que nombra la cosa
   y la consecuencia: «¿Borrar la acción “Black Friday 2026”? Se borran
   también sus 3 tareas.» Botones: «Borrar acción» en rojo y «Cancelar».
3. **Irreversible y grave:** pedir que escriba el nombre, o no permitirlo.
4. **Prohibido por una regla:** no se ofrece. Las imágenes de las entregas no
   se borran nunca: en lugar de «Borrar con sus entregas», «Archivar» (H-001).

La confirmación que sale siempre se acepta sin leer: confirmá solo lo que no
tiene vuelta. El botón destructivo va en rojo, separado del principal, nunca
como acción por defecto con Enter, y en las graves el foco arranca en
«Cancelar». En Conexiones, borrar usa el azul principal: está mal.

## Feedback y tiempos de respuesta

Los tres límites de Robert B. Miller (1968), difundidos por Jakob Nielsen
(*Usability Engineering*, 1993):

- **0,1 s:** se siente instantáneo. Todo toque tiene respuesta visible en ese
  tiempo: el botón se hunde, el tilde aparece, la fila se marca.
- **1 s:** el hilo de pensamiento no se corta, aunque la espera se note.
  Hasta acá no hace falta indicador; uno que aparece y desaparece enseguida
  molesta más que ayuda, así que conviene demorarlo un instante.
- **10 s:** se pierde la atención. Pasado el segundo, mostrá que está
  trabajando (esqueleto, circulito, «Guardando…»); más de 10 s, cuánto falta,
  poder cancelar o seguir con otra cosa, y aviso al terminar («Generando 48
  cenefas…»).

Para diseñar, usá esos límites. Para anotar hallazgos, la vara de
`criterios.md` (punto 13): más de 3 s sin indicación es hallazgo, y más de 6 s
lo es igual, aunque haya indicación.

- Cada acción termina en un cambio visible y un aviso de qué pasó y qué
  sigue: «Entrega enviada. Tienda ya tiene el aviso.» El éxito se va solo; el
  error se queda hasta que la persona lo cierra.
- Optimista cuando el riesgo es bajo: tildar una tarea la muestra tildada ya;
  si falla, se destilda y se avisa.
- Nada salta mientras carga: reservá el lugar (Ivan, 25/11/2026, sobre el
  visor de versiones: «eso está mal»). Y nada de scroll dentro del scroll
  (17/11/2026), salvo dos columnas que se leen por separado, como la imagen y
  los comentarios al revisar.
