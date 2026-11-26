# Analítica de clientes en retail

Fader y Hardie (compra "hasta que muere", valor del cliente), Gupta y
Lehmann, category management (ECR), supervivencia y lo que se sabe desde
Galton sobre la regresión a la media. Criterio y listas: [SKILL.md](../SKILL.md).

## 1. La cohorte fija: lo primero

Los ~10.000 clientes VIP son los mismos todos los meses y se eligieron por lo
que compraban. Eso produce tres efectos que **no son el negocio**:

1. **Desgaste.** Un grupo cerrado solo pierde gente (se mudan, cambian de
   súper o de hábitos, fallecen) y nunca suma: aunque Tienda Inglesa esté
   bien, la venta del grupo baja.
2. **Regresión a la media.** Lo que compra un cliente en un período es su
   nivel habitual más la suerte del período; si lo elegiste porque compró
   mucho, también elegiste buena suerte, que no se repite. Lo esperado
   después es `μ + ρ·(x − μ)`, con ρ la correlación entre períodos de lo que
   compra un mismo cliente: el grupo cae `(1 − ρ)·(x̄_elegidos − μ)` sin que
   nada cambie.
3. **Efecto ventana.** Si la cohorte se eligió con lo que compraron en un
   período ("compró todos los meses de 2025", "superó tal monto en 2025"), en
   ese período nadie se fue por construcción. Después el desgaste se acumula:
   con una salida de h por mes, en el mes k después de la ventana queda
   activa una parte cercana a `(1 − h)^k`. **Firma típica: la variación
   interanual empeora mes a mes aunque el negocio no haya cambiado.** Entre
   dos años fuera de la ventana, debería estabilizarse.

Siempre: **preguntá la regla de selección** (período, criterio, umbral) y
anotala, porque sin ella no se lee la tendencia; **medí el desgaste** (por
mes, % con compra y % con 3 meses seguidos sin compra); **separá** salida de
cambio de los que siguen (sección 2); **compará con algo no seleccionado**
(la venta total de Tienda Inglesa o los clientes justo debajo del umbral: si
la empresa va bien y el grupo cae, es el grupo); **estimá ρ** con dos
períodos posteriores a la selección (en un grupo seleccionado sale más baja:
es una cota); y **decilo**: "parte de la caída es del grupo, no del negocio".

## 2. Cómo leer una caída

De lo más aburrido a lo más interesante: (1) ¿es real? (carga completa, mismo
perímetro, mismo calendario, nominal o real); (2) ¿cuánto es salida de
clientes y cuánto cambio de los que siguen?; (3) de los que siguen,
¿frecuencia o ticket?, y en el ticket, ¿unidades o precio?; (4) ¿dónde?
(canal, sucursal, categoría, marca propia); (5) recién ahí, ¿por qué?
(competencia, precios, surtido, servicio, el país), cada hipótesis con su
evidencia.

```
V = N × F × T    clientes activos × (tickets / N) × (V / tickets)
T = (unidades / ticket) × (venta / unidad)
aporte_i = Δ%V × ln(X_i,ahora / X_i,antes) / ln(V_ahora / V_antes)    (suman exacto el total)
```

**El puente de clientes**, contra el mismo mes del año anterior: venta base −
la de los que dejaron de comprar + la de los que volvieron ± el cambio de los
que compraron los dos meses = venta actual. Si "salieron" explica la mayor
parte, es desgaste; si es "siguen", es cuánto les vendés a los que quedan.

- **Canal:** si cae la tienda y suben e-commerce o Smart en los mismos
  clientes, es traspaso, no pérdida: mirá el total del cliente.
- **Sucursal:** mismas tiendas (abiertas los dos períodos enteros). Una caída
  concentrada suele ser local (obra, competidor nuevo, horario); quien cambió
  de sucursal principal se mudó de tienda, no se fue.
- **Categoría:** penetración (% de activos que la compran) × gasto por
  comprador; si cae la penetración de una ancla, alarma (sección 7).
- **Precio, volumen y mezcla** (p = venta / unidades, q = unidades, Q total,
  p̄₀ precio promedio de la base): precio `Σ (p₁ − p₀)·q₁`, volumen
  `(Q₁ − Q₀)·p̄₀`, mezcla `Σ p₀·q₁ − p̄₀·Q₁`; suman `V₁ − V₀`. "Unidades"
  mezcla kilos y unidades: usalo dentro de categorías parejas.
- **Simpson:** el total puede caer aunque todas las partes suban, si cambia
  la mezcla. Total y partes, siempre.

```python
import math
import pandas as pd

def descomponer(v0, n0, t0, v1, n1, t1) -> dict:
    """Puntos del cambio % que aporta cada factor (suman exacto el total)."""
    total = v1 / v0 - 1
    partes = {"clientes": math.log(n1 / n0), "frecuencia": math.log((t1 / n1) / (t0 / n0)),
              "ticket": math.log((v1 / t1) / (v0 / t0))}
    escala = 100 * total / math.log(v1 / v0) if v1 != v0 else 100
    return {k: escala * x for k, x in partes.items()} | {"total_%": 100 * total}

def puente(cm: pd.DataFrame, base: str, actual: str) -> dict:
    """cm = clientes_mes; base y actual: 'AAAA-MM'."""
    a = cm[(cm.mes == base) & (cm.venta > 0)].set_index("id_cliente")["venta"]
    b = cm[(cm.mes == actual) & (cm.venta > 0)].set_index("id_cliente")["venta"]
    comunes = a.index.intersection(b.index)
    return {"base": a.sum(), "salieron": -a.drop(comunes).sum(), "volvieron": b.drop(comunes).sum(),
            "siguen": (b[comunes] - a[comunes]).sum(), "actual": b.sum()}
```

Para `descomponer`, cada mes sale de `clientes_mes`: V = suma de `venta`, N =
clientes con `venta` > 0, tickets = suma de `tickets` (probado).

## 3. RFM, retención y fuga en contexto no contractual

- **RFM:** recencia (meses desde la última compra), frecuencia (meses,
  tickets o días con compra), monto (venta o, mejor, margen), por quintiles
  **dentro de la cohorte**. En un grupo VIP, F y M son altos por construcción
  y R casi siempre es "el mes pasado": usá días con compra y tickets de los
  últimos 3 meses contra los 3 anteriores. RFM describe; no predice ni dice
  qué pasa si hacés algo. De 5 a 8 grupos con nombre y acción, no 125 celdas.
- **Nadie avisa que se va:** la fuga se define, "k meses seguidos sin
  comprar". Elegí k con los datos (de los que pasan k meses sin comprar,
  ¿cuántos vuelven?) y decí cuántos vuelven con ese k.
- **Fuga parcial**, la más común en súper: sigue viniendo pero compra en otro
  lado parte de lo que compraba. Señales: menos días con compra, menos
  categorías, deja una ancla, ticket más chico. Medila contra su propia
  historia, no contra el promedio.
- **Curvas y supervivencia:** retención de clientes (% activo por mes) y de
  venta (contra el mismo mes del año anterior). Kaplan-Meier para el tiempo
  hasta la fuga (los que aún no se fueron, como censurados); el modelo de Cox
  dice cuánto cambia el riesgo con cada característica. Asociación, no causa.

## 4. Predecir por cliente: abandono, próxima categoría, potencial

**El puntaje de la plataforma es la línea base:** recalculalo como estaba en
un mes pasado M (la función `perfil` del servicio es pura) y mirá qué pasó
entre M+1 y M+3. Por deciles de puntaje, la tasa de fuga tiene que subir
decil a decil (el de arriba contra el promedio es el *lift*); el AUC (0,5
azar, 1 perfecto) compara puntajes.

**Riesgo de abandono como probabilidad (0 a 1):**

- Objetivo: "se fue" en los próximos 3 meses (k meses sin compra) o fuga
  parcial (cayó más de X% contra su propia base); decí cuál.
- Variables a la fecha M, solo con pasado: recencia; venta, tickets y días
  con compra de los últimos 3 meses contra los 3 anteriores y contra el año
  anterior; cantidad de categorías y si dejó una ancla; e-commerce y marca
  propia; sucursal; el puntaje de la plataforma.
- Primero regresión logística (se explica); árboles (LightGBM) solo si le
  ganan en validación temporal (entrenar hasta M − 3, probar después).
- Métricas: AUC, Brier, lift del decil de más riesgo y calibración (la tasa
  real de cada tramo parecida a la probabilidad; si no, calibrá, por ejemplo
  con regresión isotónica). Si no le gana al puntaje de la plataforma, no lo
  publiques. La plata en riesgo: `p × margen esperado`.

**Próxima categoría** (la que no compra, o compra poco, y es más probable que
compre), de lo simple a lo complejo: (1) línea base, lo más popular entre
clientes parecidos (segmento, sucursal, mezcla) que él todavía no compra; (2)
reglas de asociación (Agrawal y Srikant, Apriori): soporte `P(A y C)`,
confianza `P(C | A)` y lift `P(C | A) / P(C)`, donde lift mayor que 1 es más
que el azar; (3) vecinos con participaciones por categoría parecidas
(filtrado colaborativo); (4) un modelo de propensión por categoría. Validá
escondiendo los últimos 3 meses: ¿compró alguna de las k sugeridas? (acierto
en las primeras k, contra la línea base). La probabilidad que publiques es la
tasa de acierto observada en su tramo. "La va a comprar" no es "sugerírsela
suma venta": eso se mide con control ([decisiones.md](decisiones.md)).

**Potencial de venta adicional:** la brecha contra clientes parecidos (por
ejemplo, el percentil 75 de su grupo menos lo que compra él). Es un techo, no
una promesa: el tamaño del hogar no está en los datos (una persona sola no
llega al gasto de una familia), así que el tope es su propio máximo
histórico, y lo esperable es `potencial × probabilidad de captarlo` (sale de
pruebas con control). Nunca sumes potenciales sin descontar.

## 5. Valor de vida del cliente (CLV)

Con retención constante r, margen m por período y tasa de descuento d, con el
margen al final de cada período (Gupta y Lehmann): `CLV = m·r / (1 + d − r)`;
margen, no venta, y todo en la misma unidad de tiempo. En contexto no
contractual: compras esperadas (BG/NBD o Pareto/NBD) × margen esperado por
compra (Gamma-Gamma), descontado. Sirve para decidir: lo máximo razonable
para retener a un cliente es el aumento de su probabilidad de quedarse por
su CLV, y una campaña vale `Σ uplift·CLV − costo`. Errores típicos: CLV con
venta contra un costo; retención medida en un grupo elegido por bueno;
horizonte infinito para quien ya está bajando.

## 6. Modelos de compra "hasta que muere"

| Modelo | Supone | Necesita por cliente |
|---|---|---|
| Pareto/NBD (Schmittlein, Morrison y Colombo, 1987) | Vivo, compra al azar (Poisson) a su ritmo λ; "muere" en un momento al azar; ritmos y muertes varían entre clientes (Gamma) | x (compras repetidas), t_x (la última), T (desde la primera) |
| BG/NBD (Fader, Hardie y Lee, 2005) | Igual, pero solo muere justo después de comprar, con probabilidad p (Beta); más fácil de estimar | Lo mismo |
| BG/BB (Fader, Hardie y Shang, 2010) | Tiempo discreto: cada período, vivo, compra con probabilidad p y muere con θ | Sí o no por período |
| Gamma-Gamma (Fader, Hardie y Lee, 2005) | Gasto por compra alrededor del promedio de cada cliente; **independiente de la frecuencia** | Gasto promedio y cantidad de compras |

Dan la probabilidad de seguir "vivo", las compras esperadas y el gasto por
compra (encogido hacia la media). **No aplican**, y en Clientes VIP varias se
cumplen, con: fuga parcial (no muere, reparte su compra); ritmo que cambia
por estación, campañas o tendencia; compras regulares (todos los sábados es
más parejo que el azar; para eso, Pareto/GGG de Platzer y Reutterer); una
cohorte elegida por comprar mucho (la regresión a la media los sesga para
arriba); datos mensuales de quien compra varias veces por mes (hace falta la
fecha de cada compra); contratos (ahí va el sBG); y, en Gamma-Gamma, ticket
ligado a la frecuencia (chequealo). Calibrá con un período, predecí el
siguiente y compará cliente por cliente y en el acumulado (el gráfico de
Fader y Hardie): si no le ganan a "lo mismo que el año pasado, menos el
desgaste", no los uses. Librerías: `lifetimes` (BetaGeoFitter,
GammaGammaFitter; sin mantenimiento), el módulo de CLV de PyMC-Marketing,
CLVTools o BTYD en R.

## 7. Canasta y categorías

- **Descubrió y abandonó**, con definiciones que no se coman el ruido:
  "descubrió" = la compró en 2 o más de los últimos 3 meses y en ninguno de
  los 6 anteriores; "abandonó" = la compraba en 4 o más de 6 meses y en
  ninguno de los últimos 3. Los umbrales son una elección: decilos, y contá
  clientes y plata. Las categorías de estación (helados, juguetes) se
  comparan con los mismos meses del año anterior: no es abandono, es estación.
- **Roles (ECR):** destino (por lo que el cliente elige el súper), rutina,
  estacional u ocasional, conveniencia. Las de destino son las anclas:
  identificalas con datos (alta penetración, compra frecuente, y su pérdida
  precede a la caída del resto). Prueba: los que dejaron X, ¿qué hicieron con
  el resto de su gasto, contra parecidos que siguieron con X? Si cae más, X
  es ancla: perderla es perder el viaje.
- **Señales tempranas de fuga:** deja una ancla, compra menos categorías,
  pasa de una compra grande a varias chicas.

## 8. Marca propia, margen, canibalización e incrementalidad

- `margen % total = Σ participación_i × margen %_i`: se mueve por mezcla
  aunque ningún margen cambie. De 20% a 22% es +2 pp (+10% relativo): decí
  cuál. El margen de la marca propia y el de terceros se miden en
  `dimensiones`, no se suponen; si sube la marca propia, mirá el margen en
  pesos (quien cambia una marca cara por la propia puede bajar la venta y
  subir el margen). ¿Retiene o solo sustituye? La asociación no prueba nada:
  quien la compra puede ser distinto de entrada.
- Venta incremental de una promo = venta con promo − línea base (de un grupo
  de control o un modelo validado, nunca "el mes anterior"), y
  `incremental neto = (pico − línea base) − canibalización − rebote + halo`,
  en margen. Canibalización: lo que se sacó de otros productos de la tienda;
  rebote: lo que solo se adelantó; halo: el arrastre sobre complementarios.
  La descomposición del pico promocional (Van Heerde, Leeflang y Wittink)
  muestra que buena parte suele venir de cambio de marca y stock en casa.
- Una venta que pasa de la tienda al e-commerce no es incremental para la
  empresa, y el descuento a quien igual iba a comprar es margen regalado.
