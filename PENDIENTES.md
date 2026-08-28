# Estado y pendientes — 29/08/2026

Para retomar desde otra PC. Todo el código está pusheado y desplegado
(último commit `5d916c3`, Render y Vercel al día, CI verde con 34 tests).

## Cómo arrancar en la otra PC

1. Seguir `ONBOARDING.md` (clonar, `npm install` en frontend, `.env.local`).
2. Para tocar datos/backend en local: crear `backend/.env` con el
   `DATABASE_URL` que está en **Render → servicio backend → Environment**.
3. Decirle a Claude: *"Leé PENDIENTES.md y seguí desde ahí"*.

## 🔴 PENDIENTE CALIENTE — el bug del precio $2 (diagnosticado, falta el OK)

**Síntoma**: el listado `CENEFAS BEBIDAS_MARGINADORAS MRP.xlsx` genera cenefas
Mega Rompe Precios con `precioOferta = 2` en 9 de 24 filas (todos los combos).

**Causa, probada con el archivo real** (la plantilla está BIEN, el problema es
el Convertidor):

- Ese export NO trae columna OFERTADET (headers: CODIGO, NOMBREARTICULO,
  MONEDA, REGULAR, PRECIO, OFERTA).
- Sin OFERTADET no se clasifica la mecánica → el `2x$258` de OFERTA queda sin
  interpretar → la fila cae a "Precio Final".
- La columna PRECIO trae la letra chica escrita ("Comprando 2 $129 unidad") y
  `_parse_price_or_none` (convertidor.py) agarra el "2" del principio.

**Verificado**: si a esa fila se le dice "Combo", `resolver_mecanica` da
exactamente lo correcto: `tipoOferta="2x"`, `precioOferta=258` (total),
`mecanica="Comprando 2, $129 la unidad."` (idéntico a lo que gestión escribió).

**Propuesta esperando el OK de Ivan (respuesta pendiente a "¿Avanzo con 1 y 2?")**:

1. Cuando el export NO trae columna OFERTADET, inferir la familia del literal
   de OFERTA con las regex existentes (`2x$258`→combo, `2x1`→mxn,
   `2da al 50%`→segunda). La regla "OFERTADET decide" queda intacta para
   cuando la columna existe.
2. Guarda en `_parse_price_or_none`: si la celda no es un número de punta a
   punta (tolerando "148 unidad"), queda vacía + warning rojo — nunca más un
   texto convertido en precio mudo.

**Decisión de diseño aparte**: la plantilla Mega 3xA4 no tiene cuadro de
`tipoOferta` ni `mecanica` — un combo saldría "OFERTA $258" sin el "2x" a la
vista. Si los combos van a Mega, agregarle uno de esos cuadros al PPTX (por el
picker → "Reemplazar", NO por el editor, que pierde el arte).

## 🔴 Seguridad — HACER YA

- **Rotar la contraseña de la base**: quedó pegada en el chat del 28/08.
  Supabase → Settings → Database → Reset password → actualizar en Render
  (DATABASE_URL) y en `backend/.env` de cada PC.

## 🟡 Otros pendientes

- **Alcohol**: ¿excluir "vaso/copa/jarra de" del detector de la leyenda?
  (hoy un vaso de cerveza la imprime — exceso aceptado, decisión de Ivan).
- **Botón masivo de "Generar descripciones con IA"** en la grilla (Ivan dijo
  "después"). Las filas rojas se completan de a una mientras tanto.
- **Backups de los borrados del diccionario**: están SOLO en la PC vieja, en
  `backend/backups/` (gitignoreado). Copiarlos a un drive.

## Reglas de trabajo (Ivan las marcó con énfasis)

- Nombres textuales de variables SIEMPRE (`tipoOferta`, `unidadMoneda`...).
  Nada de jerga: "Cocarda" en la UI es la imagen (`imagen`), no otra cosa.
- TODO el vocabulario en camelCase (hay test en CI que lo fija).
- Límites: solo lo pedido; ante un nombre ambiguo, preguntar antes de
  interpretar. Contexto = estado ACTUAL del código, no comentarios históricos.

## Lo hecho esta semana (resumen)

- `unidadMoneda` (variable 32): el símbolo `$`/`U$S` automático desde la
  columna MONEDA; las 5 plantillas de redexpres operadas con su placeholder.
- Tabla de mecánicas final: precio fijo sin cocarda; combo = `tipoOferta="2x"`
  + `precioOferta=total`; `promoOferta` SOLO en M×N (y tapa precio + cocarda).
- Diccionario partido: singular/plural en solapas, con descarga a Excel;
  borradas 826 claves plurales + 3.355 genéricas (backups locales).
- Ciclo de vida: verificación humana al terminar el lote ("¿salieron bien?"),
  retención 7 días para no verificadas, rescate de jobs colgados al arrancar.
- 34 tests en CI + fix del solapamiento precio/descripción en 3xA4 + fix del
  crash del mapeo + campos de entrada renombrados a camelCase (migración 0050).
- Referencia del sistema: https://claude.ai/code/artifact/8da1b53f-cced-4be9-9636-b7d1adde6d3a
