# Cómo comunicar a gerencia

Barbara Minto (*The Pyramid Principle*), Edward Tufte (*The Visual Display of
Quantitative Information*), Cole Nussbaumer Knaflic (*Storytelling with
Data*), Sherman Kent ("Words of Estimative Probability") y lo que Ivan ya
pidió: corto, claro, que se lea en el celular, sin jerga. Criterio y listas:
[SKILL.md](../SKILL.md).

## 1. La conclusión primero

- La primera línea es la respuesta con la cifra clave: "La venta del grupo
  cayó X% contra octubre del año pasado; la mayor parte son clientes que
  dejaron de venir."
- La pirámide de Minto: la respuesta, 2 o 3 razones, los datos de cada una.
  Para abrir un tema nuevo, SCQA: situación, complicación, pregunta,
  respuesta. Si te piden un número, va primero; lo técnico, al final.

## 2. Números

- Dos cifras significativas en el texto ("unos $ 2,4 millones", no
  "$ 2.437.912"); el detalle, en una tabla aparte. Todos los dígitos de un
  pronóstico aparentan una precisión que no tiene.
- Siempre unidad y base: "pesos sin IVA", "contra el mismo mes de 2025",
  "nominal" o "real". Un margen de 20% a 22% es +2 pp (+10% relativo).
- Traducí a una escala conocida (por cliente, por día, por sucursal). Si unos
  pocos clientes pesan mucho, el promedio engaña: mostrá la mediana o cuánto
  pesa el 10% de arriba (medilo).

## 3. Comparaciones correctas

- Contra el mismo mes del año anterior, no contra el mes anterior (la
  estacionalidad engaña), y con el mismo calendario: por día equivalente o
  diciéndolo ("con un sábado menos").
- El mismo perímetro (mismas sucursales abiertas los dos períodos enteros,
  mismos clientes, mismo canal). Nominal o real: crecer menos que los precios
  es caer.
- Acumulado del año contra el mismo acumulado; nunca un mes incompleto contra
  uno completo; Turismo y Carnaval, cuando cambian de mes, con los dos meses
  juntos. Y que se sepa que es un grupo cerrado: parte de la caída es
  esperable.

## 4. La incertidumbre, en palabras y en números

- Siempre el rango ("esperamos $ X, entre $ A y $ B, con 80% de confianza")
  y lo que haría cambiar el pronóstico, en una línea.
- Las palabras de probabilidad se leen distinto según quién: Sherman Kent lo
  mostró en la CIA y propuso una escala (casi seguro ≈ 93%, probable ≈ 75%,
  parejo ≈ 50%, probablemente no ≈ 30%, casi seguro que no ≈ 7%). Usá el
  número, o definí la palabra.
- Distinguí "no sé" (falta un dato que se puede conseguir) de "no se puede
  saber" (es azar). Escenarios con nombre y probabilidad.

## 5. Gráficos honestos

- Barras desde cero. Las líneas pueden no empezar en cero si el eje lo
  muestra y el movimiento no se exagera (Tufte: el "factor de mentira", el
  efecto en el gráfico dividido por el efecto en los datos, cerca de 1).
- Para comparar con el año anterior, una línea por año sobre enero–diciembre;
  el pronóstico, punteado y con su banda de 80%.
- Nada de dos ejes verticales, 3D ni tortas con muchas porciones; etiquetas
  sobre las líneas; poca tinta que no sea dato.
- El título dice la conclusión ("La caída viene de clientes que dejaron de
  venir"), no el tema ("Venta por mes"). Que se lea en el celular, en claro y
  en oscuro.

## 6. El informe y el mail

La forma del informe y del mail está en el skill `clientes-vip-analisis`.
Dentro de esa forma, esta biblioteca suma:

- **En "Lo que viene":** el rango de 80%, la frase que explica por qué no es
  igual al último mes y **cómo te fue con el pronóstico anterior** (valor,
  rango, real, qué aprendiste). Contar un error genera confianza.
- **En "Qué haría":** de 1 a 3 recomendaciones con la forma de
  [decisiones.md](decisiones.md) (acción, monto con rango, riesgo, qué la
  cambiaría, cómo se mide). Si no hay nada que hacer, decilo: "No recomiendo
  nada distinto este mes; lo que veo es lo esperable por X."
- **Al final, "Cómo lo calculé":** método, backtest (MAPE y contra la línea
  base), supuestos y fuentes verificadas con su fecha.
- **El mail:** más corto que el informe; la conclusión en la primera línea y
  la recomendación con su monto; sin tablas, sin jerga, sin nombres de
  modelos; lo confidencial, solo lo necesario.

## 7. Errores típicos

- Empezar por la metodología, o meter tablas de 20 filas en el cuerpo.
- Variaciones contra el mes anterior en una serie estacional; decimales de
  más; porcentajes de bases chicas.
- "La venta cayó por la economía" sin evidencia, o una sola causa para un
  movimiento que tiene varias.
- Esconder que el pronóstico anterior falló.
- Jerga (MASE, BG/NBD, ETS, p-valor) en el texto principal: si hace falta, va
  al final y explicada en una línea.
