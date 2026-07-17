# Marketing Mix Modeling con Google Meridian

Pipeline de dos pasos para medir el impacto incremental de cada canal de
medios sobre la revenue, usando [Google Meridian](https://developers.google.com/meridian)
(MMM bayesiano). Lee siempre de `campaign_metrics` — no importa si esas filas
son fixture o datos reales sincronizados, así que no hay que tocar nada
cuando las conexiones reales (Meta/TikTok/GA4) entren en producción.

## Por qué dos entornos

`.venv-meridian/` (gitignoreado) tiene `google-meridian` + TensorFlow/TFP
instalado, pero no tiene ni necesita acceso a Postgres. El backend
(`backend/venv`) sí tiene eso. Se separan en dos pasos con un CSV de por
medio para no mezclar dependencias de DB en el entorno de modelado.

## 1. Exportar los datos (con el venv del backend)

```
cd backend
venv/Scripts/python.exe scripts/export_metrics_for_meridian.py
```

Agrega `campaign_metrics` diario → semanal, pivotea a wide (una columna de
spend y otra de impresiones por canal pago con `spend > 0` en el rango), y
usa la revenue semanal de Google Analytics como KPI (el funnel de ecommerce
real del negocio — no la revenue que cada plataforma de ads se auto-atribuye,
para no romper la lógica de medición incremental). Escribe
`meridian_mmm/data/weekly_metrics.csv`.

## 2. Fitear el modelo (con .venv-meridian)

```
cd meridian_mmm
../.venv-meridian/Scripts/python.exe fit_model.py
```

Lee el CSV, corre el modelo (prior + posterior vía MCMC) y guarda el reporte
en `meridian_mmm/output/meridian_summary.html`, más un resumen compacto por
canal (ROI, % de contribución) en `meridian_mmm/output/meridian_channel_summary.csv`.

## 3. Importar el resumen a la base (con el venv del backend)

```
cd backend
venv/Scripts/python.exe scripts/import_meridian_summary.py
```

Sube ese CSV a la tabla `meridian_channel_summary` (reemplaza la corrida
anterior entera, no acumula historial) — de ahí lo lee
`debate_service.py` para dárselo como contexto a La Triada.

## Estado actual de los datos (2026-07-12)

Los fixtures de Meta/TikTok/GA4 cubren solo ~90 días (13-14 semanas) —
`generate_meta_fake_data.py` y compañía generan `DATE_FROM = DATE_TO -
timedelta(days=89)` a propósito, no es un bug. Meridian idealmente quiere 1+
año de historia semanal para resultados confiables; con esta cantidad de
datos, el reporte de hoy sirve para confirmar que el pipeline funciona de
punta a punta, no como insight de negocio (los intervalos de confianza van a
ser anchos). `fit_model.py` imprime este mismo aviso si detecta menos de 52
semanas de datos.

Los `n_chains`/`n_adapt`/`n_burnin`/`n_keep` en `fit_model.py` están
reducidos a propósito para que una corrida no tarde una eternidad con pocos
datos — subirlos una vez que haya más semanas de historia real.

## Conexión con La Triada

`debate_service._build_meridian_context()` arma un bloque con el ROI
incremental y % de contribución por canal (tabla `meridian_channel_summary`,
ver paso 3) y lo suma al contexto de datos que ven Claude/ChatGPT/Llama.
Queda dormido a propósito: solo se activa si TODAS las filas importadas
tienen `reliable=True` (52+ semanas de historia al fitear) — con los
fixtures actuales (14 semanas) el pipeline corre de punta a punta pero no
le dice nada a los modelos todavía. Se prende solo, sin tocar código, en
cuanto haya suficiente historia real y se reimporte una corrida confiable.
