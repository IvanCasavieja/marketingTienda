# Causalidad y decisiones

Pearl (diagramas causales), Angrist y Pischke, Cunningham, Kohavi, Tang y Xu
(los experimentos de Microsoft, Google y LinkedIn), CausalImpact (Google),
GeoLift (Meta), Kahneman y la teoría clásica de decisión (el problema del
canillita, *newsvendor*). Criterio y listas: [SKILL.md](../SKILL.md).

## 1. Correlación no es causa

Dos cosas se mueven juntas sin que una cause la otra por un **confusor** (los
clientes de e-commerce gastan más: ¿por el canal, o porque son hogares
grandes que además usan e-commerce?), por **causalidad inversa** (a quien más
compra se le mandan más promos; "los que reciben más promos compran más" no
dice que funcionen) o por **selección** (mirás un grupo elegido: los VIP, los
que contestaron, los que siguen activos).

Dibujá el diagrama causal (flechas de causa a efecto) antes de mirar los
datos (Pearl; el curso "Causal Diagrams" de Miguel Hernán). Controlá por los
confusores; **no** por un mediador (lo que está en el camino causal) ni por
un colisionador (una consecuencia común de las dos variables, que fabrica
asociaciones falsas: el sesgo de Berkson). El efecto de una acción es lo que
pasó con ella menos lo que hubiera pasado sin ella (el contrafáctico, en el
marco de Rubin), y eso se construye con un grupo de control. Sin control no
hay efecto medido: hay una historia.

## 2. Experimentos para campañas a clientes VIP

El estándar de oro, y con 10.000 clientes identificados se puede:

1. **Antes de lanzar:** la métrica principal (venta o margen incremental por
   cliente en N semanas, no la tasa de canje), la población, la duración y el
   efecto mínimo que vale la pena.
2. **Control al azar** que no recibe la campaña, con **estratos** (segmento,
   decil de gasto, sucursal) para que los grupos arranquen parejos.
3. **Tamaño por grupo** (5% de significancia, 80% de potencia):
   `n ≈ 2·(z_(1−α/2) + z_(1−β))²·σ²/δ² ≈ 15,7·(c/δ)²`, con c el coeficiente
   de variación del gasto mensual por cliente y δ el efecto en proporción.
   Con supuestos (medí c en tus datos): c = 0,8 y δ = 3% dan unos 11.200 por
   grupo, más que la cohorte entera.
4. **CUPED** (Deng, Xu, Kohavi y Walker, Microsoft, 2013): con el gasto previo
   X, `Y* = Y − θ·(X − X̄)`, `θ = cov(Y, X) / var(X)`; la varianza baja por
   `(1 − ρ²)`. Con ρ = 0,8 (supuesto), el ejemplo pasa a unos 4.000 por grupo.
   En súper el gasto de un cliente es muy estable: CUPED es casi obligatorio.
5. **No mires todos los días para cortar cuando "da"** (inflás los falsos
   positivos); si hay que mirar, definí antes cuándo.
6. **El efecto, con intervalo, en margen y menos el costo** (los descuentos
   de todos los que canjearon, también de los que iban a comprar igual).
7. **Elasticidad a campañas:** efecto incremental por punto de descuento,
   variando la profundidad entre grupos al azar (no la venta bruta).

Errores típicos: comparar a los que canjearon con los que no (se eligieron
solos); un control que recibe la oferta por otro canal; mirar 20 métricas y
contar la que dio; creerle a las primeras semanas (efecto novedad).

## 3. Uplift: a quién conviene contactar

Hay cuatro tipos de cliente frente a una campaña (Radcliffe y Surry; lo
popularizó Eric Siegel): **persuadibles** (compran solo si los contactás: los
únicos que dejan ganancia), **seguros** (compran igual: el descuento regala
margen), **perdidos** (no compran igual: puro costo) y **no molestar**
(contactarlos los hace comprar menos o irse). Un modelo de uplift estima por
cliente `P(compra | contacto) − P(compra | sin contacto)` y solo se entrena
con un experimento con control al azar: un modelo por grupo y restar, y se
evalúa con la curva Qini o el uplift por decil (`causalml`, `scikit-uplift`).
Pide bastantes más clientes que un A/B: hoy, primero el A/B, y después el
efecto por segmento sin multiplicar comparaciones.

## 4. Sin experimento: diseños cuasi-experimentales

| Diseño | Cuándo | Supuesto clave | Chequeo |
|---|---|---|---|
| Diferencias en diferencias | Una acción en unas sucursales o clientes y no en otros | Sin la acción, los grupos habrían seguido en paralelo | Tendencias paralelas antes, mes a mes |
| Control sintético; CausalImpact (Google); GeoLift (Meta) | Una sola unidad tratada (una sucursal, una zona) | Una combinación de no tratadas reproduce su pasado | Ajuste previo; placebos con otras unidades |
| Serie interrumpida (antes y después) | No hay control | Nada más cambió en ese momento | Estación, calendario, regresión a la media |
| Discontinuidad de regresión | Hay un umbral (el monto para ser VIP) | Justo arriba y justo abajo son parecidos | Nadie se acomoda al umbral; densidad pareja |
| Emparejamiento (matching, propensity score) | Comparar con no tratados parecidos | No quedan confusores sin medir | Balance; análisis de sensibilidad |

Diferencias en diferencias: `efecto = (Y_T,después − Y_T,antes) −
(Y_C,después − Y_C,antes)`; en logs queda en % (el clásico: Card y Krueger,
1994). Una campaña lanzada después de un mes malo "funciona" sola, por
regresión a la media: para eso está el control. Para la inversión en medios,
el repo tiene `meridian_mmm/` (MMM bayesiano de Google), que no sirve por
cliente ni con pocos meses de inversión.

## 5. Sesgos que te van a aparecer

| Sesgo | Cómo aparece en Clientes VIP | Antídoto |
|---|---|---|
| Supervivencia | El ticket de los activos "sube" porque se fueron los de ticket bajo (Wald y los aviones: el blindaje va donde los que volvieron no tenían agujeros) | Mirar a todos, también a los que se fueron |
| Selección | La cohorte VIP, los que usan la app, los que contestan encuestas | Preguntar cómo se eligió el grupo |
| Simpson | El margen sube en todas las categorías y baja en el total, por la mezcla | Total y partes, siempre |
| Regresión a la media | Los peores del mes pasado "mejoran" y los mejores "empeoran" solos | Control, o comparar con lo esperado |
| Fuga de información | El backtest usa algo que no se sabía en el momento | Cada pronóstico con lo que había ese día |
| Comparaciones múltiples | Entre decenas de categorías y sucursales, varias saltan por azar | Tamaño (lo que no pesa 1% de la venta no es noticia), consistencia en varios meses, Benjamini y Hochberg; si probaste muchos cortes, decilo (Gelman) |
| Bases chicas | Una categoría de $ 5.000 que cae 99% (pasó con AUTOLIQUIDABLES) | Montos, no solo % |
| Narrativa | Una historia coherente convence más que un dato (Kahneman: "lo que ves es todo lo que hay") | A cada historia, su evidencia y su alternativa aburrida |
| Anclaje | El número del informe anterior o el que trae quien pregunta | Estimar antes de mirar el de otros |

## 6. La incertidumbre para decidir

- **Escenarios** con supuestos explícitos, no "±10%" simétrico: cada uno
  cuenta una historia ("Black Friday rinde como el año pasado", "la mitad",
  "la competencia hace uno más fuerte") con su probabilidad. **Rangos** de
  80% para decidir, y qué haría que el real caiga afuera.
- **Valor esperado** `E = Σ p_s·resultado_s`: elegí la mejor opción, salvo
  que una cola sea inaceptable; entonces decilo y elegí la que la evita.
- **Costo asimétrico:** pronosticar de más cuesta ___ (stock a liquidar,
  capital parado); de menos, ___ (venta perdida, cliente que se va). Escribí
  la tabla: la decisión óptima **no es el pronóstico puntual**, se corre
  hacia el lado del error barato.
- **Reversibilidad:** lo corregible (un segundo pedido, una campaña que se
  corta) tolera más incertidumbre; lo irreversible (una gran compra
  importada) pide más información antes.

## 7. Newsvendor: cuánto comprar

Para productos con una ventana de venta y sobrante que se liquida
(televisores para una temporada, artículos de campaña):
`Cu` (quedarse corto, por unidad) = precio − costo, más el daño al cliente;
`Co` (que sobre una) = costo − lo que se recupera al liquidar, más el costo
de tenerla. La cantidad óptima deja una probabilidad `Cu / (Cu + Co)` de no
quedarse corto (el fractil crítico): `Q* = F⁻¹(Cu / (Cu + Co))`; con demanda
normal, `Q* = μ + z·σ`, `z = Φ⁻¹(Cu / (Cu + Co))`.

Ejemplo con índices (base 100; no son números de Tienda Inglesa): precio 100
y costo 75, Cu = 25. Si lo que sobra se liquida a 60, Co = 15, fractil
0,625, z = 0,32: comprar la media más un tercio de σ. Si se liquida a 45,
Co = 30, fractil 0,45, z = −0,11: comprar **menos** que la media. Mismo
pronóstico, decisión distinta: manda la asimetría. Por eso, para una compra,
el pronóstico se pide como distribución (media y σ, o escenarios).

Cuidados: con quiebre se vende lo que había (**demanda censurada**: corregí
con los días sin stock o tratá esos meses como "al menos"); el horizonte es
el plazo de entrega más el período que cubre el pedido (si se puede reponer,
el problema es otro: stock de seguridad); y los VIP no son toda la demanda.

**Caso: cuántos televisores comprar.** (1) La ventana, el plazo de entrega y
qué pasa con lo que sobra (liquidación, devolución). (2) Demanda histórica en
unidades de toda la empresa, corregida por quiebres, precios y campañas. (3)
Eventos únicos: 2026 fue año de Mundial ([uruguay.md](uruguay.md)); es
esperable que haya adelantado compras: comprobalo en los meses previos contra
el año anterior y no uses 2026 como base de 2027 sin corregirlo. (4) Tipo de
cambio: se importan. (5) Fermi como chequeo ([fermi.md](fermi.md)). (6)
Newsvendor con Cu y Co reales (pedíselos a compras). (7) Recomendación con
cantidad, rango, costo esperado de quedarse corto o largo, y qué la cambiaría.

## 8. Valor de la información

Antes de pedir un dato o una prueba: ¿cambiaría la decisión? Si ninguna
respuesta posible la cambia, no vale la pena; si puede, vale más o menos la
probabilidad de que la cambie por cuánto mejora el resultado. Pedí primero lo
barato que más mueve: la venta diaria, la regla de la cohorte, el calendario
de campañas, los costos de quedarse corto o largo.

## 9. De dato a recomendación

> - **Recomiendo** [acción concreta, quién, cuándo].
> - **Vale** unos $ X (entre $ A y $ B), porque [el cálculo en una línea].
> - **Riesgo principal:** [qué puede salir mal, qué tan probable, cuánto costaría].
> - **Lo cambiaría si** [dato o evento].
> - **Cómo lo vamos a medir:** [grupo de control, métrica, fecha].

Por ejemplo (sin números reales): "Recomiendo una campaña de reactivación
para quienes dejaron una categoría ancla en los últimos 3 meses, con un 10%
como control. Vale entre $ A y $ B de margen en 3 meses si recupera entre p1%
y p2% (supuesto; lo mide el control). Riesgo: regalar margen a quienes iban a
volver solos. La cortaría si en 4 semanas no aparece diferencia."
