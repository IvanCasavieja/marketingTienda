# Pronóstico

El método de *Forecasting: Principles and Practice* (Hyndman y
Athanasopoulos; la 3.ª edición está libre en la web), aplicado a una serie
mensual corta de una cohorte fija. Criterio y listas: [SKILL.md](../SKILL.md).

Hyndman: se pronostica mejor cuanto más se entiende lo que lo mueve, más datos
hay, más se parece el futuro al pasado y menos lo altera el pronóstico. Acá:
calendario claro, campañas futuras inciertas, 22 meses, cohorte que se gasta.

## 1. Mirar y ajustar antes de modelar

- **Gráficos de siempre:** la serie con los meses de campaña marcados; el
  estacional (una línea por año sobre enero–diciembre: ¿la brecha entre años
  es pareja o se abre?); la **variación interanual** de cada mes,
  `y_t / y_(t−12) − 1`, la serie más informativa que tenés porque la
  estacionalidad se cancela sola; y lo mismo para clientes activos, tickets
  por cliente y venta por ticket ([retail-y-clientes.md](retail-y-clientes.md)).
- **Los cuatro ajustes de Hyndman:** calendario (venta por día equivalente,
  sección 3); población (venta por cliente activo: "compran menos" o "quedan
  menos"); inflación (pesos constantes, [uruguay.md](uruguay.md)); logaritmos
  (en retail los efectos son proporcionales; la diferencia de logs es casi la
  variación %, y al volver `exp(media del log)` da la mediana, no la media).

## 2. Descomposición y estacionalidad

- Aditiva `y = T + S + R` o multiplicativa `y = T × S × R` (la de retail; en
  logs se vuelve aditiva). Hyndman recomienda STL (Cleveland y otros).
- **Con 22 meses no se estima la estacionalidad propia con confianza:** de
  enero a octubre cada mes aparece dos veces; noviembre y diciembre, una. La
  descomposición clásica de statsmodels se niega con menos de 24 meses,
  Holt-Winters no puede inicializar los estacionales y STL corre, pero
  inventa.
- Qué hacer: (1) **trabajar con la variación interanual**, cada mes contra su
  par, sin estimar estacionalidad (lo de casi siempre); (2) **pedir prestada
  la estacionalidad** a una serie larga, la venta mensual total de Tienda
  Inglesa de 3 a 5 años, el dato que más mejoraría tus pronósticos; (3) si
  hace falta una forma estacional, 1 o 2 pares de términos de Fourier (2 o 4
  parámetros) en vez de 11 variables por mes; (4) explicar parte de la
  diferencia entre meses con el calendario, que se conoce de antemano.

## 3. Regresión con variables de calendario

La más útil con poca historia: el calendario no hay que pronosticarlo.

- Variables del mes: cantidad de cada día de la semana (o solo sábados y
  domingos); feriados y días con cierre u horario reducido; días de Turismo y
  Carnaval (se mueven entre febrero, marzo y abril); días e intensidad de
  campaña; **rebote** (la campaña adelanta compras y el mes siguiente puede
  caer: la variable con un mes de rezago); eventos (Mundial, paros, lluvia).
  Intervenciones: pulso (un mes), escalón (un cambio permanente, como una
  sucursal que cierra), rampa.
- En diferencias interanuales, para cancelar la estación:
  `z_t = β0 + β1·Δsábados_t + β2·ΔTurismo_t + β3·Δcampaña_t + e_t`, con
  `z_t = log y_t − log y_(t−12)` y Δ la diferencia contra el mismo mes del
  año anterior. Con 10 datos, no más de 1 o 2 coeficientes estimados.
- Mejor: **fijá los coeficientes de calendario con datos diarios** (la venta
  total del grupo por día, unas 30 filas por mes: pedila) y estimá solo la
  tendencia. Con un peso por día de la semana `w_d` relativo a un día
  promedio, los **días equivalentes** son `E_t = Σ_d n_(d,t)·w_d`, y se
  compara `y_t / E_t`.

## 4. La línea base y las variantes simples

**Naive estacional:** `ŷ_(T+h) = y_(T+h−12)` (h ≤ 12), "el mismo mes del año
pasado". Toda propuesta tiene que ganarle en backtesting; si ninguna le gana,
se publica la línea base y se dice. Con una cohorte que se gasta, sobreestima
siempre: su sesgo mide el desgaste. Las variantes son formas de pronosticar z
y multiplicar, `ŷ_(T+h) = y_(T+h−12) × exp(ẑ)`:

| Variante | Pronóstico de z | Equivale a |
|---|---|---|
| Naive estacional | 0 | ARIMA(0,0,0)(0,1,0)12 |
| Con deriva | el promedio de z | lo mismo, con constante |
| Último valor | el z del último mes | ARIMA(0,1,0)(0,1,0)12 |
| Tendencia de 3 meses (la de la plataforma) | más o menos el promedio de los últimos 3 z | — |
| Suavizado exponencial simple sobre z | el nivel suavizado de z | ARIMA(0,1,1)(0,1,0)12 |
| Tendencia amortiguada sobre z | Holt amortiguado | — |

Decide el backtest, junto con el razonamiento sobre la cohorte: si la
variación interanual empeora mes a mes porque se acumula el desgaste
([retail-y-clientes.md](retail-y-clientes.md), sección 1), el promedio de 3
meses llega tarde; una tendencia amortiguada sobre z lo sigue, pero solo si
sabés por qué empeora y hasta cuándo.

## 5. ETS, ARIMA, Prophet y aprendizaje automático

- **ETS** (Error, Tendencia, Estacionalidad: cada una ninguna, aditiva,
  amortiguada o multiplicativa). El simple: `ℓ_t = α·y_t + (1 − α)·ℓ_(t−1)`;
  α cerca de 1 es memoria corta, cerca de 0 promedio largo. Uno estacional
  mensual estima nivel, tendencia, 11 estacionales y 3 o 4 parámetros, casi
  tantos como datos: con 22 meses, ETS **sin estacionalidad** sobre z o sobre
  la serie desestacionalizada con una estacionalidad prestada.
- **ARIMA:** la serie diferenciada hasta ser estable, explicada por sus
  valores y errores pasados. La diferencia estacional deja 10 datos: alcanza
  para un parámetro (las variantes de la tabla). Rinde con 60 meses o más, o
  con datos semanales o diarios.
- **Elegir por AICc o con `auto.arima` entre decenas de modelos con 10 o 22
  datos es sobreajuste:** elegí por razonamiento y confirmá con backtest.
- **Prophet** (Meta, "Forecasting at Scale") rinde con datos diarios y varios
  años; con 22 puntos mensuales no da más que una regresión simple. Los
  **árboles** (LightGBM) dominaron la competencia M5 (ventas de Walmart) con
  miles de series diarias: para esta serie, no; por cliente y mes, sí,
  validando por tiempo ([retail-y-clientes.md](retail-y-clientes.md), sección 4).

## 6. Lo honesto con 22 meses

| Se puede | No se puede con esta serie sola | Qué haría falta |
|---|---|---|
| Nivel actual y variación interanual de 10 meses | Estacionalidad propia confiable (noviembre y diciembre se vieron una vez) | Venta mensual de la empresa, 3 a 5 años |
| Ver si la variación interanual empeora o se estabiliza | Separar el efecto de una campaña del ruido de un mes | Calendario de campañas; grupos de control |
| Descomponer la caída en clientes, frecuencia y ticket | El efecto de cada día de la semana y de cada feriado | Venta total por día |
| Comparar métodos simples con 7 a 10 pronósticos fuera de muestra | Intervalos de 95% confiables (10 errores no alcanzan para las colas) | Más meses; mientras tanto, 80% y decirlo |
| Pronóstico a 1–3 meses con rango | Tendencia de largo plazo, ciclo económico | Series de INE y BCU, más historia |

En el informe alcanza una línea: "Con 22 meses de historia este número tiene
más incertidumbre de la que parece; el rango es de 80%".

## 7. Validación: backtesting rodante

1. **Horizonte = plazo de la decisión:** si la compra se decide con 3 meses de
   anticipación, evaluá a h = 3.
2. Para cada mes t desde el primero posible: con los datos hasta t − 1, y
   solo esos, pronosticá t + h − 1. Métricas sobre **los mismos meses** para
   todos los métodos.
3. Mirá el **sesgo** (¿siempre para el mismo lado?), la **consistencia** (¿en
   cuántos meses le gana a la línea base?) y la **cobertura** (¿el intervalo
   de 80% contiene al real 8 de cada 10 veces?).
4. Quedate con el más simple que gane de forma consistente; si ninguno, la
   línea base.

**Fuga de información**, el error más común: un factor estacional calculado
con el año entero, un mes recargado después, una campaña decidida más tarde.
Con 7 a 10 errores, un MAPE de 3,1% contra uno de 3,4% es ruido: contá en
cuántos meses gana cada uno (9 o 10 de 10 es señal, con una prueba de signos
p ≈ 0,01; 6 o 7 de 10 no distingue) y desconfiá del que gana por un mes raro.

## 8. Métricas

Error `e_t = y_t − ŷ_t` (negativo = sobreestimó).

| Métrica | Fórmula | Cuándo |
|---|---|---|
| MAE | media de abs(e) | En pesos; fácil de explicar |
| RMSE | raíz de la media de e² | Cuando los errores grandes duelen más |
| MAPE | media de abs(e) / y, × 100 | El total del grupo (sin ceros); es el "se equivoca en promedio" de la pantalla |
| sMAPE | media de 200·abs(e) / (y + ŷ) | Solo si te la piden; Hyndman no la recomienda |
| MASE | MAE / media de abs(y_t − y_(t−12)) en la historia | Comparar métodos; menos de 1 le gana al naive estacional (Hyndman y Koehler) |
| WAPE | suma de abs(e) / suma de y | Por cliente, categoría o sucursal (ceros, escalas distintas) |
| Sesgo | media de e / y | Siempre: un sesgo grande es un método mal planteado |

El MAPE premia pronosticar de menos (para arriba no tiene techo; para abajo,
no pasa de 100%) y explota con ceros: nunca por cliente. Con la escala del
MASE calculada sobre los meses del backtest, el naive estacional da MASE = 1
exacto: es la vara. Para intervalos, la puntuación de Winkler: el ancho más
2/α veces lo que el real quedó afuera (α = 0,2 para 80%).

## 9. Intervalos, combinación y ajustes de juicio

- Un pronóstico sin rango es un deseo. Normal: `ŷ ± z·σ_h`, con z = 1,28
  (80%), 1,64 (90%) o 1,96 (95%). Con pocos datos, el empírico: σ = el error
  típico porcentual del backtest (raíz de la media de los errores % al
  cuadrado, que incluye el sesgo), intervalo `ŷ × (1 ± 1,28·σ)`.
- **± el MAPE no es un intervalo de 80%:** con errores normales, ± un error
  medio cubre cerca del 57%; el 80% pide ± 1,6 errores medios y el 95%,
  ± 2,5. Los intervalos de los modelos suelen quedar cortos (no incluyen la
  incertidumbre de haber elegido el modelo): chequeá la cobertura y, si
  faltan casos, ensanchalos y decilo. Mostrá el 95% cuando la cola cuesta
  caro (una compra grande).
- **Combinar** métodos distintos suele ganarle a elegir "el mejor" (Bates y
  Granger, 1969; las competencias M de Makridakis). Con pocos datos, pesos
  iguales. Combiná información distinta (la serie del grupo y la suma de
  clientes; con y sin calendario): si se equivocan igual, no suma.
- **Ajustes de juicio** (Hyndman; Fildes y Goodwin en empresas reales): solo
  por información que el modelo no tiene (una campaña nueva, un cierre, un
  cambio de precios); los chicos casi nunca mejoran, los grandes con motivo
  sí, y los de para arriba tienden a ser optimistas. Escribilos ("base X;
  + Y por la campaña Z, fuente") y no mezcles pronóstico con objetivo.
- **Total y partes:** pronosticá el total con tu mejor método y las partes
  con naive estacional ajustado, escaladas para que sumen (la reconciliación
  óptima, MinT, es de Wickramasuriya, Athanasopoulos y Hyndman); aparte, las
  que tienen motivo propio (televisores en año de Mundial).

## 10. Caso: la proyección de noviembre que no cerró

El primer informe proyectó noviembre como "noviembre del año pasado ×
tendencia" (los últimos 3 meses contra los mismos 3 del año anterior). Ivan:
"¿por qué sería igual que octubre?". Con g = la tendencia de 3 meses y r_oct
= la variación interanual de octubre:

```
ŷ_nov / y_oct = (y_nov,año pasado / y_oct,año pasado) × (g / r_oct)
```

Si el año pasado noviembre vendió casi lo mismo que octubre y la variación de
octubre se parece a la de los 3 meses, sale octubre: el método supone que
noviembre se porta respecto de octubre igual que el año pasado. No razonó:

1. **Calendario** [calculado]: octubre 2025 tuvo 4 sábados y octubre 2026, 5;
   noviembre 2025 tuvo 5 y noviembre 2026 tiene 4 (cambia un sábado por un
   lunes). Si el sábado vende más que un día promedio, el método sobreestima
   dos veces: octubre 2026 viene inflado por su sábado de más (y entra en la
   tendencia) y noviembre 2026 pierde uno.
2. **Campañas:** Black Friday cae en noviembre los dos años (28/11/2025 y
   27/11/2026, calculado); el lunes siguiente cayó el 1/12 en 2025 y cae el
   30/11 en 2026: si la acción se extiende a ese lunes, este año queda en
   noviembre. CyberLunes de Uruguay: verificá las fechas de los dos años. Y
   preguntale a promo y marca si este año las campañas son más largas, más
   profundas o en otras categorías.
3. **Cohorte:** si la variación interanual empeora mes a mes por desgaste, una
   tendencia de 3 meses llega tarde y subestima la caída que sigue.
4. **Precios:** es venta nominal; la inflación de 12 meses, y la de las
   categorías que pesan en noviembre, mueve la comparación.

Bien hecho: `ŷ_nov = y_nov,año pasado × tendencia subyacente × ajuste de
calendario × ajuste de campañas`. La tendencia, limpia de calendario y con
una regla explícita para el desgaste (sigue o se frena, y por qué); el
calendario, con pesos de la venta diaria o, sin ella, con un rango de
supuestos ([fermi.md](fermi.md), el del sábado); las campañas, con días e
intensidad contra el año anterior según promo y marca. Cada factor con su
rango; juntos dan el intervalo de 80% y, si la campaña es incierta,
escenarios. Y la respuesta a Ivan en dos líneas: "Noviembre pierde un sábado
que octubre tuvo de más, suma Black Friday y el grupo sigue perdiendo
clientes. Por eso espero X, entre A y B."

## 11. Código mínimo (Python, probado)

```python
import calendar, math
from datetime import date
import pandas as pd

def dias_por_tipo(anio: int, mes: int) -> dict[str, int]:
    nombres = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
    cuenta = dict.fromkeys(nombres, 0)
    for d in range(1, calendar.monthrange(anio, mes)[1] + 1):
        cuenta[nombres[date(anio, mes, d).weekday()]] += 1
    return cuenta

def naive_estacional(hist: pd.Series, h: int) -> float:
    return hist.iloc[-12 + h - 1]            # el mismo mes del año anterior (h <= 12)

def con_tendencia(hist: pd.Series, h: int, k: int = 3) -> float:
    g = hist.iloc[-k:].sum() / hist.iloc[-12 - k:-12].sum()
    return hist.iloc[-12 + h - 1] * g        # el cálculo rápido de la plataforma

def backtest(serie: pd.Series, metodo, h: int = 1, desde: int = 15) -> pd.DataFrame:
    """Origen rodante: con los datos hasta t, pronostica t+h. Nada del futuro entra."""
    filas = [{"mes": serie.index[t + h - 1], "real": serie.iloc[t + h - 1],
              "pron": metodo(serie.iloc[:t], h)} for t in range(desde, len(serie) - h + 1)]
    df = pd.DataFrame(filas).set_index("mes")
    df["error"] = df["real"] - df["pron"]    # negativo = sobreestimó
    return df

def metricas(df: pd.DataFrame, serie: pd.Series, m: int = 12) -> dict:
    e, y, pct = df["error"], df["real"], df["error"] / df["pron"]
    return {"MAE": e.abs().mean(), "MAPE_%": 100 * (e.abs() / y).mean(),
            "MASE": e.abs().mean() / serie.diff(m).abs().mean(),
            "sesgo_%": 100 * (e / y).mean(),
            "error_tipico_%": 100 * math.sqrt((pct ** 2).mean()), "n": len(e)}
```

Serie con índice mensual (`pd.period_range(...).to_timestamp()`). Mismo
`desde` para todos los métodos (15 deja 3 meses para la tendencia); `h=2` o
`h=3` si la decisión lo pide. Intervalo de 80%: `pron × (1 ± 1,2816 ×
error_tipico_% / 100)`.
