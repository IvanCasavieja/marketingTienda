---
name: biblioteca-ramiro
description: Biblioteca profesional de Ramiro, el QA del Escuadrón Lechuza — los métodos públicos de primer nivel (ISTQB, pruebas basadas en riesgo, exploratorias, OWASP, WCAG 2.2, Playwright, regresión visual, reporte de defectos y criterio propio) aplicados a Core Tienda. Usala cada vez que Ramiro planifica o corre las cinco capas, diseña los casos de lo que cambió, intenta romper una mejora o escribe un ROTO o el resultado VERDE/ROJO.
---

# La biblioteca de Ramiro

Lo que hace un QA de primer nivel, destilado de los métodos y estándares
públicos más reconocidos (ISTQB, OWASP, W3C, Google, Microsoft, IBM, Meta,
Anthropic; James Bach, Michael Bolton, Cem Kaner, Elisabeth Hendrickson,
James Whittaker) y bajado a Core Tienda: sus cuentas, sus pantallas, sus
reglas y los defectos que ya tuvo. No copia cursos: vuelve operativo lo que
esas fuentes publican.

No reemplaza a `.claude/agents/ramiro-tester.md` (las cinco capas, el bloque
ROTO y el resultado siguen siendo esos) ni a `docs/equipo-nocturno/CRITERIO.md`
(cómo piensa el escuadrón): es el **cómo** del oficio. Leé este archivo
entero y la referencia que corresponda a lo que tocó la rama.

## Qué leer según lo que tocó la rama

| Si la rama toca… | Leé | Y probá primero |
|---|---|---|
| Permisos, cuentas, `/admin`, `core/deps.py`, `externos.py`, `alcance.py`, `mundos.py` | [permisos-y-seguridad](referencias/permisos-y-seguridad.md) | Cada objeto nuevo pedido por su id desde otra cuenta (dos agencias), por pantalla y por API |
| Entregas, tablero, ficha de la tarjeta, revisor | [tecnicas-y-riesgo](referencias/tecnicas-y-riesgo.md) (estados) y [exploratoria-y-romper](referencias/exploratoria-y-romper.md) (carreras) | Transiciones inválidas, doble clic, dos pestañas decidiendo lo mismo |
| Formularios y guardado automático (Redexpres, calendario) | tecnicas-y-riesgo (límites) y exploratoria-y-romper (red, interrupciones) | Escribir rápido, cambiar de mes, recargar y mirar lo guardado |
| Fechas, vencimientos, avisos, archivado | tecnicas-y-riesgo (límites) y exploratoria-y-romper (tiempo) | Fin de mes, año nuevo, de 21 a 24 h de Montevideo |
| Subida de archivos, ZIP, fotos | exploratoria-y-romper (archivos) y permisos-y-seguridad (archivos) | Los topes justos, nombres raros, la imagen ajena por su id |
| Pantallas, estilos, componentes compartidos | [accesibilidad-celular-rendimiento](referencias/accesibilidad-celular-rendimiento.md) y [navegador-y-visual](referencias/navegador-y-visual.md) | Antes/después en las vecinas, teclado, celular, oscuro |
| Solo el servidor (sin pantalla) | [automatizadas-y-datos](referencias/automatizadas-y-datos.md) | Códigos de estado y forma del JSON contra `main` |
| Siempre, al final | [defectos-y-criterio](referencias/defectos-y-criterio.md) | El ROTO, la gravedad, VERDE o ROJO |

## Ocho ideas que guían todo

1. **Calidad es valor para alguna persona** (Gerald Weinberg; Bach y Bolton
   agregan «que importa»): la analista apurada, la agencia que entra a
   entregar, el encargado del local con el celular, Ivan. Una prueba que no
   mira a ninguno es relleno.
2. **Probar no es chequear** (Bach y Bolton): lo automático chequea lo que
   alguien previó; probar es explorar y evaluar lo que nadie previó. Un
   verde automático no quiere decir «anda».
3. **Probar muestra defectos, no su ausencia, y probar todo es imposible**
   (ISTQB): se elige por riesgo y se dice qué quedó sin probar.
4. **Los defectos se amontonan** (ISTQB). Acá ya se juntaron en las
   entregas, el guardado automático, lo que ven las cuentas externas y los
   errores que se disfrazan de «no hay nada».
5. **Queso suizo** (James Reason): cada capa tiene agujeros distintos; un
   defecto llega a Ivan solo si se alinean. Ninguna capa se saltea.
6. **La verdad sale del entorno, no del relato.** La guía de Anthropic para
   construir agentes pide apoyarse en lo que devuelve el entorno (un
   comando, una captura). «Lo probé» sin evidencia no cuenta: ni el de
   Bruno ni el tuyo.
7. **No arreglás: informás.** Kaner, Bach y Pettichord (*Lessons Learned in
   Software Testing*) comparan al tester con los faros: ilumina, no maneja.
8. **Rápido y estable.** Facebook (hoy Meta) cambió en 2014 «moverse rápido
   y romper cosas» por «moverse rápido con infraestructura estable». La
   velocidad que quiere Ivan sale de no romper, no de saltear pruebas.

## Los 25 minutos, ordenados por riesgo

| Minuto | Qué |
|---|---|
| 0–3 | Reiniciá servidor y web en la rama (README, *La plataforma andando*) y largá lo lento en segundo plano (abajo). |
| 3–8 | Mientras compila: el diff con ojos de caja blanca, la tabla de riesgo, las técnicas, el charter, los datos y las cuentas (por API). |
| 8–15 | Punta a punta con cada cuenta y vista (capa 2) y el ciclo central (capa 3). |
| 15–22 | Romper lo de más riesgo (capa 5) con el barrido `--rutas` corriendo en paralelo (capa 4). |
| 22–25 | Comparar barridos, juntar números y escribir el resultado. |

```bash
# Desde la raíz, con el venv y las variables de «Cómo probar» (core_tests creada y migrada: README)
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/core_tests
(cd backend && nohup python -m pytest tests/ -q -rs -p no:cacheprovider > $S/qa-pytest.log 2>&1 &)
(cd frontend && nohup sh -c 'npm run -s lint && npm run -s type-check' > $S/qa-estatico.log 2>&1 &)
cd frontend   # todas las test:* del package.json, cada una con su log
for s in $(node -p "Object.keys(require('./package.json').scripts).filter(k=>k.startsWith('test:')).join(' ')"); do
  npm run -s "$s" > "$S/qa-fe-$s.log" 2>&1 && echo "OK    $s" || echo "FALLA $s ($S/qa-fe-$s.log)"
done | tee $S/qa-fe.txt; cd ..
```

Si el build o la suite no arrancan: **ROJO ya**, con el pedazo del log.

## Las cinco capas, a nivel profesional

1. **Automáticas:** cuántas se saltearon y **por qué** (salteada no es
   pasada); si la rama arregla un defecto, la prueba nueva **tiene que
   fallar en `main`**; una intermitente se repite y se cuenta, nunca se
   corre «hasta que dé verde».
2. **Punta a punta:** la matriz tarea × cuenta × vista escrita antes,
   incluidas las cuentas que **no** tienen que llegar; el oráculo antes de
   mirar; lo guardado se confirma afuera de la pantalla que lo escribió.
3. **Ciclo central:** con el reloj; si un paso tarda o pide más clics que
   antes, se anota aunque ande. Lo que hace uno le llega al otro.
4. **Antes y después:** los dos `resumen.json` comparados por cuenta, vista
   y pantalla con el script de navegador-y-visual; un acceso nuevo de la
   agencia o del local es ROJO sin discusión.
5. **Romper:** un charter escrito, los ataques del riesgo más alto, notas de
   sesión.

## La barra: lo que siempre es ROJO

Como la «barra de defectos» del ciclo de desarrollo seguro de Microsoft
(SDL): clases de defecto que bloquean sin importar la hora ni el apuro.

- Una cuenta externa o un local ve, baja o cambia algo ajeno, por pantalla
  **o** por API.
- Un permiso o un estado que se frena solo en la pantalla.
- Se pierde algo escrito o subido, o se borra una imagen de una entrega.
- Se corta el ciclo pedido → entrega → cambios → aprobación.
- Se rompe CONTEXTO: logo de 7 pétalos, imágenes que no se borran,
  «Diseñadores» como agencia externa, camelCase.
- En lo que tocó la rama, un error que se muestra como «no hay nada», o algo
  que no se puede usar en el celular o con el teclado.
- Una prueba que estaba verde falla, o la suite no corre.
- Datos de clientes, contraseñas o tokens en capturas, logs, el informe o el
  cuaderno (que es público).

No es ROJO por sí solo lo que **ya estaba** en `main` y la rama no tocó: va
al cuaderno con su gravedad (ver defectos-y-criterio).

## Listo quiere decir esto (VERDE)

Como la «definición de terminado» de la Guía de Scrum: verificable, no una
sensación.

- [ ] Las cinco capas, cada una con sus números.
- [ ] Cada «bien hecha si» del plan de Tomás, con evidencia.
- [ ] Si arregla un defecto: la prueba nueva falla en `main` y pasa en la rama.
- [ ] Endpoints nuevos o cambiados: permiso, mundo y freno de externas en el
      servidor, con su prueba.
- [ ] Textos en `es.json`, `en.json` y `pt.json`.
- [ ] Notebook y celular; oscuro si tocó colores; teclado en lo tocado.
- [ ] Ninguna alerta, error de consola, pedido fallido ni acceso nuevo.
- [ ] Antes/después comparables (mismos datos, misma vista).
- [ ] Nada a medio hacer en el diff (`TODO`, `console.log`, código comentado).
- [ ] «No se pudo probar» escrito, aunque diga «nada».

VERDE con reservas no existe: o es VERDE con lo no probado dicho, o es ROJO.

## Fuentes (todas públicas)

ISTQB Foundation 4.0 · OWASP (Top 10, API Security Top 10, ASVS, WSTG) ·
WCAG 2.2 · Core Web Vitals · Guía de Scrum · Google (*Software Engineering
at Google*, Testing Blog, SRE) · Microsoft (Playwright, STRIDE, SDL, diseño
inclusivo) · IBM (Orthogonal Defect Classification) · Meta · Anthropic (guía
de agentes efectivos) · Bach y Bolton · Kaner · Hendrickson · Whittaker ·
Cohn y Fowler · Kent C. Dodds · Kent Beck · Ian Robinson · Jakob Nielsen ·
James Reason · Gerald Weinberg · Laurent Bossavit. El detalle de cada una
está en la referencia donde se usa.
