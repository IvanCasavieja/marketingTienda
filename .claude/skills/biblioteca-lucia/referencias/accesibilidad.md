# Accesibilidad: WCAG 2.2 nivel AA, en concreto

WCAG 2.2 es Recomendación del W3C desde octubre de 2023 y la vara es el nivel
AA. No es un extra para pocos: con luz de oficina, ojos cansados o el celular
en una mano en el local, todos tenemos alguna discapacidad situacional (así lo
plantea Microsoft Inclusive Design). Donde Core Tienda ya es más estricta que
WCAG (12 px de letra, 44 px para tocar), manda Core Tienda.

## Los criterios que más pesan acá

| Criterio | Qué exige | Cómo se mira en Core Tienda |
|---|---|---|
| **1.4.3 Contraste mínimo** (AA) | Texto 4,5:1; texto grande (24 px, o 18,66 px en negrita) 3:1 | `chequeos.py` lo estima: confirmalo en la captura. `slate-400` sobre blanco da 2,56:1 (no pasa), `slate-500` 4,76:1 (justo), `#52525B` 7,7:1. El texto blanco sobre el índigo 500 con que arranca el degradé de `.btn-primary` da 4,47:1: no llega |
| **1.4.11 Contraste de lo que no es texto** (AA) | 3:1 para lo que identifica un control y su estado (borde de campo, casilla, interruptor, ícono que informa, foco) y para los gráficos necesarios | El borde `slate-300` de `.campo` da 1,48:1: si el borde es lo único que muestra el campo, no alcanza. El `#8A8A93` del informe da 3,4:1. Los bordes de cajas decorativas no lo necesitan |
| **1.4.1 Uso del color** (A) | El color nunca es el único medio | Estado = puntito + palabra; las marcas sobre la imagen llevan número; los links dentro de un texto, subrayados |
| **2.4.7 Foco visible** (AA) | Se ve dónde está el foco del teclado | Hoy hay un contorno de 2 px con `:focus-visible` en `globals.css`: nunca `outline-none` sin un reemplazo igual de visible |
| **2.4.11 Foco no tapado** (AA, nuevo en 2.2) | Lo enfocado no queda tapado del todo por algo de la página | La burbuja de Don Tino, la barra de abajo, el cartel del entorno de pruebas y los encabezados fijos no pueden tapar el campo enfocado (`scroll-padding`, `scroll-margin`) |
| **2.5.8 Tamaño del objetivo** (AA, nuevo en 2.2) | 24×24 px como mínimo, o espacio libre suficiente alrededor | Es el piso. La regla de Core Tienda es 44 px en el celular (como Apple; Material pide 48 dp; el nivel AAA de WCAG, 2.5.5, pide 44). Los íconos de 27 a 32 px del panel de admin pasan el piso pero no llegan a 44 |
| **2.5.7 Movimientos de arrastre** (AA, nuevo en 2.2) | Todo lo que se hace arrastrando se puede hacer sin arrastrar | Tablero: «Mover» además de arrastrar; reordenar también con botones |
| **1.4.4 Cambiar el tamaño del texto** (AA) | Al 200 % no se pierde nada | Zoom del navegador al 200 % en la notebook: nada se pisa ni se corta |
| **1.4.10 Reflujo** (AA) | A 320 px de ancho, sin scroll de costado (salvo tablas, mapas y similares) | Equivale a 1280 px al 400 %. El mes del calendario es una excepción razonable; la vista Lista, no |
| **1.4.12 Espaciado del texto** (AA) | Si la persona agranda interlineado y espaciado, nada se corta | Nada de altos fijos en cajas con texto |
| **1.4.13 Contenido al pasar o enfocar** (AA) | Lo que aparece al pasar el mouse se puede cerrar (Escape), aguanta que el mouse pase por encima y no se va solo | Nada importante solo en un `title` |
| **2.1.1 Teclado y 2.1.2 Sin trampas** (A) | Todo se usa con teclado y de todo se sale | En las ventanas el foco queda adentro, Escape cierra y el foco vuelve al botón que la abrió (lo hace `useDialogo`); hay ventanas viejas que no cierran con Escape |
| **2.4.3 Orden del foco** (A) | El orden de Tab sigue el visual | No reordenar con CSS lo que el lector lee en otro orden |
| **2.4.6 Encabezados y etiquetas** (AA) y **3.3.2 Etiquetas** (A) | Encabezados y etiquetas describen | Un `h1` por pantalla; cada campo con su `<label>` |
| **2.5.3 Etiqueta en el nombre** (A) | El nombre accesible incluye el texto visible | Si el botón dice «Entregar», el lector también dice «Entregar» |
| **3.3.1 y 3.3.3 Errores** (A y AA) | Se identifica el error y se sugiere cómo arreglarlo | «Falta la fecha de entrega» al lado del campo, no solo el borde rojo |
| **3.3.4 Prevención de errores** (AA) | Lo que compromete datos se puede revisar, confirmar o deshacer | Confirmación en la pantalla o Deshacer (`usabilidad.md`) |
| **3.3.7 Entrada redundante** (A, nuevo en 2.2) | No pedir dos veces lo mismo en el mismo proceso | La agencia no vuelve a escribir lo que ya cargó en la versión anterior |
| **3.3.8 Autenticación accesible** (AA, nuevo en 2.2) | No obligar a memorizar o transcribir sin ayuda | El login deja pegar y usar el gestor de contraseñas (`autocomplete="current-password"`) |
| **3.2.6 Ayuda consistente** (A, nuevo en 2.2) | La ayuda que se repite está siempre en el mismo lugar | Don Tino y la Guía, en el mismo lugar en todas las pantallas |
| **4.1.2 Nombre, función y valor** (A) | Cada control expone qué es y en qué estado está | Botón de ícono con `aria-label`; lo que se despliega, con `aria-expanded` |
| **4.1.3 Mensajes de estado** (AA) | Los avisos se anuncian sin mover el foco | Avisos y «Guardado» con `role="status"` o `aria-live`. Los avisos de Sonner ya se anuncian (confirmalo con un lector); lo hecho a mano hay que revisarlo |
| **2.2.2 Pausar, detener, ocultar** (A) | Lo que se mueve solo más de 5 s se puede parar | Nada de latidos ni brillos permanentes |

## Calcular un contraste sin herramienta

La fórmula de WCAG, para dos colores en hex (confirmá con la captura cuando
hay transparencias o fondos de imagen):

```python
def lum(h):
    c = [int(h.lstrip('#')[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def contraste(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)
print(round(contraste('#0047BA', '#FFFFFF'), 2))  # 8.04
```

## Lectores de pantalla

- Primera regla de ARIA (W3C, *Using ARIA*): si hay un elemento HTML que ya
  hace lo que necesitás, usalo (`<button>`, `<a>`, `<label>`, `<dialog>`,
  `<table>`) antes que un `div` con `role`.
- Probá los flujos centrales con un lector de verdad: VoiceOver (Mac y
  iPhone), NVDA (Windows, gratis) o TalkBack (Android). La pasada mínima:
  recorrer con Tab y por encabezados, y escuchar si cada control dice qué es y
  en qué estado está.
- Imágenes con `alt` que diga lo que importa («Placa de Black Friday, versión
  2»); las decorativas, con `alt=""`.
- Un ícono sin texto necesita nombre accesible; y si una persona que ve no
  lo entiende sin pasar el mouse, también le falta texto visible.
- Tablas de datos con `<th scope>`; nada de tablas para maquetar.
- El idioma de la página (`lang`) acompaña al idioma elegido (es, en, pt).

## Movimiento reducido

- `globals.css` ya respeta `prefers-reduced-motion`: todo cambia de golpe,
  salvo el circulito de carga, a propósito (Ivan, 21/11/2026: quieto parecía
  colgado). Mantenelo en todo lo nuevo.
- Nada que destelle más de tres veces por segundo (2.3.1).
- Movimiento con propósito: 150 ms al abrir y cerrar; sin rebotes, latidos ni
  brillos. Animar lo que se agrega da contexto; animar por adorno, no.

## Cómo probarlo en una noche

1. **Contraste:** medí el par de colores y anotá el número.
2. **Teclado:** la tarea entera con Tab, Shift+Tab, Enter, Espacio y Escape.
   ¿Se ve siempre el foco? ¿Lo tapa algo?
3. **Zoom al 200 %** en la notebook, **ancho de 320 px**, **reducir
   movimiento** y **modo oscuro**.
4. **Lector de pantalla** en la tarea principal: cinco minutos alcanzan para
   lo grueso.
5. **Herramientas automáticas** (axe de Deque, Lighthouse, IBM Equal Access
   Accessibility Checker): encuentran solo una parte; no reemplazan mirar.

**Errores típicos:** quitar el contorno del foco «porque es feo»; un gris
clarito que se ve bien en un buen monitor y no se lee en una notebook de
oficina; ventanas que no devuelven el foco; íconos sin nombre; marcar el error
solo con rojo; burbujas flotantes que tapan lo que se está escribiendo.
