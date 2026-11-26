# Accesibilidad, celular y rendimiento percibido

CONTEXTO lo pide: contraste alto para ojos cansados con luz de oficina,
notebook y celular (iPhone con Safari incluido), claro y oscuro, y nada que
tarde sin avisar. El diseño inclusivo de Microsoft lo explica con su
espectro de personas: lo que sirve a quien tiene una limitación permanente
sirve a quien la tiene por un rato o por la situación (el encargado con una
mano ocupada en el local, la analista con la vista cansada a las seis).

## WCAG 2.2 en lo que Core Tienda necesita

WCAG 2.2 (W3C, recomendación desde octubre de 2023): cuatro principios
(perceptible, operable, comprensible, robusto) y tres niveles (A, AA, AAA).
La vara razonable es AA; el equipo ya pide más en algunos puntos.

| Criterio | Qué pide | Dónde mirar en Core Tienda |
|---|---|---|
| 1.4.3 y 1.4.11 (AA) | 4,5:1 el texto (3:1 el grande); 3:1 bordes, íconos y foco | El `text-slate-400` y los bordes `slate-200` de las pantallas viejas; todo en oscuro |
| 1.4.1 Uso del color (A) | El color nunca solo | Semáforo, «Volvió con cambios», el rojo/ámbar/verde de la revisión: también texto o forma |
| 1.4.4 y 1.4.10 (AA) | Zoom al 200 %; a 320 px sin correr de costado | La Planilla puede tener scroll horizontal (la norma exceptúa lo que necesita dos dimensiones); el resto, no |
| 2.1.1, 2.1.2, 2.4.3 y 2.4.7 | Todo con teclado, sin trampas, orden lógico y foco visible | Casillas del panel que son dibujos y cuadros que no cierran con Escape (mapa C) |
| 2.4.11 Foco no tapado (AA, nuevo) | Lo enfocado no queda debajo de otra cosa | Barra de abajo, burbujas, pastilla del entorno de pruebas |
| 2.5.7 Arrastre (AA, nuevo) | Una alternativa sin arrastrar | El tablero la tiene («Mover a…»): si una mejora la saca, ROJO |
| 2.5.8 Tamaño del objetivo (AA, nuevo) | 24 × 24 px como mínimo, o espacio equivalente | El núcleo usa 44 (como el 2.5.5 AAA y las guías de Apple); el panel tiene botones de 27 a 32 px |
| 3.3.1, 3.3.2 y 3.3.7 (A) | Errores identificados, etiquetas, no volver a pedir lo cargado | Validación al lado del campo; reintentar una entrega no obliga a cargar otra vez el link |
| 3.3.8 Autenticación accesible (AA, nuevo) | Sin pruebas de memoria: se puede pegar y usar el gestor de contraseñas | Login y cambio de contraseña |
| 4.1.2 y 4.1.3 | Todo control con nombre; los avisos se anuncian sin mover el foco | El ojito de la contraseña no tiene nombre (mapa C); los toasts |
| 2.2.1 y 3.1.1 (A) | Tiempo para leer lo importante; el idioma declarado | El aviso rojo del login dura 10 s; `lang` acorde a es, en o pt |

`chequeos.py` (contraste aproximado, letra chica, dedo, solo ícono, campos
sin etiqueta) encuentra una parte; ninguna herramienta automática alcanza
sola. El resto se confirma mirando y con el teclado.

## Teclado y lector de pantalla

```bash
python $K/navegador.py ir /entregas
python $K/navegador.py tecla Tab      # repetí; cada 3 o 4, «ver» y mirá la captura
python $K/navegador.py ver foco-1     # y Enter, Escape, ArrowDown, Shift+Tab…
```

El foco se ve siempre (en claro y en oscuro) y sigue la lectura; todo lo que
se toca se alcanza y se activa con Enter o Espacio, «Mover a…» incluido;
Escape cierra y el foco vuelve a donde estaba; nada atrapa el foco; los
atajos del calendario (← → T N) no se disparan mientras se escribe.

En la nube no hay NVDA, JAWS, VoiceOver ni TalkBack: si la rama es de
accesibilidad, «No se pudo probar con un lector real» va en el resultado.
Lo que sí hay: el árbol de accesibilidad de Playwright (1.49 o más nueva),
con roles y nombres como los anunciaría un lector.
`print(page.locator("main").aria_snapshot())`: botones con un nombre que se
entienda, títulos en orden, campos con etiqueta, avisos con rol de estado.

## Celular

- **Vistas:** el iPhone 13 del barrido (390 px), 320 px para el reflujo y la
  notebook de 1366 × 768 al 200 %.
- **El motor:** el barrido emula el tamaño y el toque de un iPhone con
  Chromium; no es Safari. Si la rama toca sesión, cookies, campos de fecha,
  subida de archivos o formularios, probá también con WebKit
  (`python -m playwright install --with-deps webkit`) y decí que no es un
  iPhone de verdad.
- **Campos:** con letra de menos de 16 px, Safari del iPhone agranda la
  página al tocarlos. Por eso el núcleo usa `.campo` (16 px en el celular);
  las pantallas viejas con `.input` (14 px) lo tienen pendiente.
- **El teclado virtual:** Playwright no lo dibuja. Achicá el alto (por
  ejemplo, 390 × 420), poné el foco en el campo y mirá: el campo y su botón
  tienen que quedar a la vista.
- **El pulgar y lo que tapa:** lo principal al alcance, 44 px, lo que borra
  lejos de lo que guarda; la barra de abajo y las burbujas no tapan «Más»,
  «Avisos» ni el botón principal (H-025, del 25/11). Girar no rompe nada.

## Rendimiento percibido

- **Jakob Nielsen:** 0,1 s se siente instantáneo, 1 s no corta el hilo, 10 s
  es el límite de la atención. **La vara del equipo** (`criterios.md`):
  más de 3 s necesita una señal de que trabaja; más de 6 s es hallazgo (el
  barrido lo mide en `segundos` y avisa).
- **Core Web Vitals** (Google, web.dev): LCP bueno hasta 2,5 s y malo arriba
  de 4 s; INP bueno hasta 200 ms y malo arriba de 500 ms (reemplazó a FID en
  marzo de 2024); CLS bueno hasta 0,1 y malo arriba de 0,25. Se evalúan en
  el percentil 75 de visitas reales; acá son medidas de laboratorio, para
  comparar antes y después:

```python
MEDIR = """() => new Promise(fin => {
  let lcp = 0, cls = 0;
  new PerformanceObserver(l => { for (const e of l.getEntries()) lcp = e.startTime; })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
  const js = performance.getEntriesByType('resource').filter(r => r.initiatorType === 'script')
    .reduce((s, r) => s + r.encodedBodySize, 0);
  setTimeout(() => fin({lcpMs: Math.round(lcp), cls: +cls.toFixed(3), jsKb: Math.round(js / 1024)}), 3000);
})"""
print(page.evaluate(MEDIR))   # misma pantalla, mismos datos: en main y en la rama
```

- **La respuesta a un toque** (una aproximación a INP): `time.monotonic()`
  antes del `click` y después de `expect(...).to_be_visible()`.
- **La API:** `curl -s -o /dev/null -w "%{time_total}\n"` sobre lo tocado,
  cinco veces en `main` y cinco en la rama, con los mismos datos; se
  comparan medianas.
- **Sondeos:** una mejora que suma pedidos periódicos o los hace más pesados
  se multiplica por personas y pestañas: contalos con
  `page.on("request", …)`.
- **El servidor dormido:** Render, en su plan gratis, duerme el servidor; el
  login avisa a los 4 s, pero la pantalla de carga de quien ya tiene sesión
  no dice nada (sospecha del mapa). El entorno local no se duerme: si la rama
  toca el arranque, va a «No se pudo probar». Un plan pago nunca es la
  respuesta (CONTEXTO).
