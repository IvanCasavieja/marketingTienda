# Estimación de Fermi

Enrico Fermi estimaba en minutos lo que parecía imposible partiendo el
problema en escalones razonables (Tetlock lo pone entre los mandamientos de
los superpronosticadores). Sirve sin el dato, para chequear uno que te
pasaron y para saber qué dato buscar. Criterio y listas: [SKILL.md](../SKILL.md).

## El método

1. **Definí la pregunta:** qué se cuenta, dónde, en qué período, en qué
   unidad.
2. **Partila en factores** que se multiplican (o suman) y se razonan por
   separado.
3. **Estimá cada uno con un rango de 90%** y decí de dónde sale: dato con
   fuente, referencia parecida o supuesto.
4. **Combiná** sin exagerar el rango (abajo).
5. **Chequeo de cordura por otro camino:** de arriba hacia abajo y de abajo
   hacia arriba, contra un dato interno o un orden de magnitud conocido. Si
   dos caminos difieren en más de 3 veces, revisá el factor más dudoso.
6. **Buscá el factor que domina la incertidumbre** (el de rango más ancho en
   proporción): ahí vale la pena conseguir el dato. Verificado, va a la
   memoria con su fuente.

Todo número de un Fermi es un supuesto hasta que se verifica, y en el informe
se ve como supuesto.

**Combinar rangos.** Multiplicar todos los mínimos y todos los máximos da un
rango absurdo: que todo salga mal a la vez es muy improbable. Con factores
independientes, en logaritmos: para cada rango de 90% [L, H], centro `√(L·H)`
y `σ_i = ln(H/L) / 3,29`; el resultado tiene centro = producto (o cociente)
de los centros, `σ = √(Σ σ_i²)` y rango de 90% `centro × e^(±1,645·σ)`. Si
dos factores se mueven juntos (los hogares grandes tienen más televisores),
el rango real es más ancho.

## Ejemplo de escuela: ¿cuántos televisores hay prendidos ahora en el mundo?

Supuestos para practicar, no datos.

| Escalón | Rango de 90% | Centro |
|---|---|---|
| Personas en el mundo | 8.000 a 8.300 millones | 8.150 millones |
| Personas por hogar | 3 a 4,5 | 3,7 |
| → Hogares | | unos 2.200 millones |
| Hogares con televisor | 60% a 85% | 71% |
| Televisores por hogar con tele | 1,2 a 2 | 1,55 |
| → Televisores | | unos 2.450 millones |
| Parte del día que está prendido uno promedio | 5% a 15% (1,2 a 3,6 horas) | 8,7% |
| → **Prendidos en un momento promedio** | **110 a 410 millones** | **unos 210 millones** |

Domina la parte del día prendido (y depende de en qué lugares es de noche):
ahí buscarías datos de audiencia. Cordura: una de cada 40 personas del mundo
frente a un televisor prendido en un momento cualquiera; plausible. La
respuesta no es "212.583.000" sino "del orden de 200 millones, entre 100 y
400".

## Ejemplo Tienda Inglesa: televisores por año

¿Cuántos televisores se compran por año en Uruguay y cuántos le tocan a
Tienda Inglesa? **Todos los números son supuestos a verificar.**

| Escalón | Rango de 90% (supuesto) | Para verificarlo |
|---|---|---|
| Hogares en Uruguay | 1,2 a 1,4 millones | INE: censo 2023, Encuesta Continua de Hogares |
| Televisores por hogar | 1,3 a 2,2 | INE (equipamiento de los hogares), estudios de mercado |
| Vida útil de un televisor | 6 a 10 años | Fabricantes, estudios de mercado |
| → Reemplazo anual (hogares × televisores ÷ vida útil) | 195 a 410 mil | |
| Parte que se compra en Uruguay (no afuera ni por internet al exterior) | 70% a 95% | Prensa, cámaras, tipo de cambio ([uruguay.md](uruguay.md)) |
| Participación de Tienda Inglesa en televisores | 3% a 15% | Interno: unidades vendidas de la categoría |
| → **Televisores por año de Tienda Inglesa** | **6.000 a 38.000** | **unos 15.000** |

- Domina, por lejos, la participación: es el dato a conseguir (las unidades de
  la categoría). Con él, el Fermi pasa a ser el chequeo: si la empresa vende
  muy por fuera del rango, revisá los supuestos o el dato.
- De abajo hacia arriba: las unidades de televisores de los VIP, divididas por
  la parte de la categoría que compran los VIP (pedila, no la supongas).
- En un año de Mundial el reemplazo se adelanta: ese año se vende más y el
  siguiente, menos. Para decidir cuántos comprar, esto es el punto de
  partida; la decisión sale del newsvendor ([decisiones.md](decisiones.md)).

## Ejemplo con datos propios: ¿cuánto pesa un sábado menos en noviembre?

Noviembre 2026 cambia un sábado por un lunes respecto de noviembre 2025
(calculado). Con pesos por día relativos a un día promedio, `efecto ≈ (w_l −
w_s) / Σ_d n_d·w_d`, y en un mes de 30 días la suma vale cerca de 30. Sin
venta diaria: si el sábado vende entre 0,1 y 0,5 "días promedio" más que el
lunes (supuesto: en muchos súper el sábado es de los días fuertes; verificalo),
el efecto va de −0,3% a −1,7% de la venta del mes. Chequeo con tus datos: los
meses con distinta cantidad de sábados que su par del año anterior (octubre
2026 tuvo uno más), ¿se despegan de sus vecinos en el sentido esperado? Con
tan pocos casos es un indicio, no una prueba. Lo que lo resuelve: la venta
total del grupo por día.

## Errores típicos

Precisión falsa ("15.493 televisores": un Fermi da un orden de magnitud y un
rango); multiplicar los extremos o tratar como independientes factores que se
mueven juntos; olvidar un escalón (los que compran afuera, los que no tienen
el producto, los que compran dos); saltear el chequeo por otro camino;
presentar un supuesto como dato.
