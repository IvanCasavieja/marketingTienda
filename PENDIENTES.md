# Estado y pendientes — 01/09/2026

Para retomar desde cualquier PC. Todo el código está pusheado y desplegado
(último commit `149663c`, Render y Vercel al día, CI verde con 57 tests en
6 archivos).

## Cómo arrancar en otra PC

1. Seguir `ONBOARDING.md` (clonar, `npm install` en frontend, `.env.local`).
2. Para tocar datos/backend en local: crear `backend/.env` con el
   `DATABASE_URL` que está en **Render → servicio backend → Environment**.
3. Decirle a Claude: *"Leé PENDIENTES.md y seguí desde ahí"*.

## 🔴 Seguridad — HACER YA

- **Rotar la contraseña de la base**: quedó pegada en el chat del 28/08 y ya
  pasaron 4 días. Supabase → Settings → Database → Reset password →
  actualizar en Render (DATABASE_URL) y en `backend/.env` de cada PC.

## 🟡 Decisión que espera el OK de Ivan

- **La plantilla Mega 3xA4 no tiene cuadro de `tipoOferta` ni `mecanica`**:
  un combo saldría "OFERTA $258" sin el "2x" a la vista. Si los combos van a
  Mega, agregarle uno de esos cuadros al PPTX (por el picker → "Reemplazar",
  NO por el editor, que pierde el arte).

## 🟡 Otros pendientes

- **Backups de los borrados del diccionario**: viven SOLO en la PC de Ivan,
  en `Desktop\marketingTienda-main\backend\backups\` (gitignoreado). Son la
  única copia de las ~4.180 claves borradas. Copiarlos a un drive.
- **Botón masivo de "Generar descripciones con IA"** en la grilla (Ivan dijo
  "después"). Ojo: el panel de Tinín ya abre el modal de IA con TODAS las
  filas sin descripción de una vez (existe desde julio, `8840db4`); antes de
  programar nada, aclarar con Ivan qué le falta a ese flujo para ser el
  "masivo" que pidió.

## Decidido y fijado por test (no tocar sin nuevo OK de Ivan)

- **Alcohol**: "vaso/copa/jarra de cerveza" imprime la leyenda — exceso
  aceptado, fijado por `test_alcohol_vaso_de_cerveza_es_exceso_aceptado`.
- **Bug del precio $2**: resuelto en `dd19026`. Los exports SIN columna
  OFERTADET infieren la familia del literal de OFERTA (2x$258→combo,
  2x1→mxn, 2da al 50%→segunda) y el parseo de precio tiene guarda de punta
  a punta: una celda con texto queda vacía y roja, nunca un valor inventado.
  Verificado con el archivo real; Redexpres intacto (fijado por test).
- **Costo por cenefa**: $49 desde el 01/09 (`149663c`), configurable desde
  la pantalla del informe.

## Reglas de trabajo (Ivan las marcó con énfasis)

- Nombres textuales de variables SIEMPRE (`tipoOferta`, `unidadMoneda`...).
  Nada de jerga: "Cocarda" en la UI es la imagen (`imagen`), no otra cosa.
- TODO el vocabulario en camelCase (hay test en CI que lo fija).
- Límites: solo lo pedido; ante un nombre ambiguo, preguntar antes de
  interpretar. Contexto = estado ACTUAL del código, no comentarios históricos.

## Lo hecho desde el traspaso anterior (29/08 → 01/09)

- Privacidad de corridas: el listado ya no muestra corridas ajenas, nadie
  puede desverificar (ni borrarle el archivo a) la corrida de otro, con
  tests de pertenencia (`cb84c05`, `a7f3fa9`).
- Robustez: levantar el backend en una PC ya no le mata la corrida a quien
  esté generando (`82874ab`), y un lote ya no puede encolar miles de
  corridas de un saque (`882ac12`).
- Don Tino pasó a Claude con cache y los 5 agentes comparten un solo modelo
  (`9843f8f`); la home ya no dice que corre sobre Llama (`790a87a`).
- Tinín ya no enseña la regla vieja del combo (`a1ab40c`), con test de
  conocimiento que fija la tabla de mecánicas vigente.
- El informe de cenefas separa lo real de lo reprocesado (`d905156`) y el
  titular muestra lo real, no el bruto (`0a95541`).
- El costo por defecto del informe pasó de $45 a $49 (`149663c`).
- Referencia del sistema: https://claude.ai/code/artifact/8da1b53f-cced-4be9-9636-b7d1adde6d3a
