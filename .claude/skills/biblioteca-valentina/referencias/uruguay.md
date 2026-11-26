# Uruguay y su consumo: qué investigar y verificar

Esta guía dice **qué mirar y dónde buscarlo**; no trae datos. Lo que depende
del mundo real se verifica en la web antes de usarlo y va a la memoria con la
fuente y la fecha de consulta. Marcas: **[calculado]** sale del calendario
(Pascua, el cuarto jueves de noviembre), igual verificá qué hizo Tienda
Inglesa esos días; **[verificá]** depende del mundo real o de una ley que
puede cambiar; lo demás son hipótesis de qué mueve qué, a confirmar con tus
datos. Criterio y listas: [SKILL.md](../SKILL.md).

## 1. Calendario comercial

| Evento | Cuándo | Qué puede mover | Cómo tratarlo |
|---|---|---|---|
| Año Nuevo y Reyes (6/1) | Enero | Juguetes en Reyes; bebidas y comida de fiesta | Días previos |
| Temporada de verano | Enero y febrero | Suben las sucursales de la costa y Punta del Este; Montevideo puede bajar | Por sucursal; depende del turismo argentino y brasileño |
| Carnaval | Lunes y martes antes del Miércoles de Ceniza. [calculado] 3–4/3/2025, 16–17/2/2026, 8–9/2/2027 | Feriado; corre venta entre febrero y marzo | Días del mes |
| Semana de Turismo (Semana Santa) | [calculado] 14–20/4/2025, 30/3–5/4/2026, 22–28/3/2027 | Viajes, compras previas, menos movimiento en la ciudad | Si cambia de mes, marzo y abril juntos |
| Día de la Madre | [verificá] en Uruguay suele ser el segundo domingo de mayo; no es la fecha de Argentina | Regalos, perfumería, electro | Días previos |
| Aguinaldo | Junio y diciembre. [verificá] los plazos de pago | Compras grandes, electro | Mes de cobro |
| Día del Padre, Día del Niño, vacaciones de julio | [verificá] las fechas de cada año | Regalos, juguetes, salidas | Días previos |
| Noche de la Nostalgia (24/8) y feriado del 25/8 | Agosto | Bebidas, picadas, fiesta | Días previos |
| CyberLunes | [verificá] fechas y organizador de cada edición; no siempre coincide con el Cyber Monday de EE.UU. | E-commerce, electro | Días de campaña |
| Black Friday | Viernes después del cuarto jueves de noviembre. [calculado] 28/11/2025, 27/11/2026, 26/11/2027; el lunes siguiente: 1/12/2025, 30/11/2026, 29/11/2027 | Electro, televisores, e-commerce | Días de campaña; ojo en qué mes cae el lunes |
| Navidad y fin de año | 24, 25 y 31/12, 1/1 | Alimentos, bebidas, regalos | [verificá] horarios reducidos y cierres de Tienda Inglesa |
| Feriados | [verificá] la lista oficial del año: cuáles son no laborables (en general 1/1, 1/5, 18/7, 25/8 y 25/12) y cuáles se trasladan a lunes | Cierres, menos horas, fines de semana largos | Variable por día |
| Paros generales | [verificá] fechas en la prensa | Cierres o menos horas, transporte | Pulso de un día |
| Mundial y Copa América | Mundial 2026: [verificá] junio y julio de 2026 | Televisores antes; bebidas y picadas en los partidos de Uruguay | Evento único: no lo repitas el año siguiente |
| Clima | Lluvia, ola de calor o de frío | Menos visitas a la tienda, más e-commerce; bebidas, helados, estufas | Datos diarios de INUMET |

**Los días de cada mes** contra el mismo mes del año anterior (código en
[pronostico.md](pronostico.md)). [calculado] Octubre 2026 tuvo un sábado más
y un miércoles menos que octubre 2025; noviembre 2026 tiene un sábado menos y
un lunes más que noviembre 2025; diciembre 2026 cambia un lunes por un
jueves, y el 24 y el 31 caen jueves (en 2025, miércoles).

## 2. El ciclo del mes, la temporada y el turismo

- **Sueldos:** en general, en los primeros días hábiles del mes ([verificá]
  el plazo legal y los pagos quincenales); pasividades, según el calendario
  del BPS [verificá]. La compra grande sigue al cobro: si un fin de semana o
  un feriado lo corre, corre venta entre el fin de un mes y el principio del
  otro. Aguinaldo en junio y diciembre; otros pagos puntuales, [verificá].
- **Temporada:** Punta del Este, Maldonado y la costa de Rocha y Canelones
  viven en enero y febrero, y en fines de semana largos, Turismo y Carnaval.
  Las sucursales "de temporada" se reconocen por su forma estacional, no por
  el nombre; el turismo argentino y brasileño depende del tipo de cambio
  ([verificá] visitantes en el Ministerio de Turismo). El VIP de Montevideo
  que veranea en la costa pasa su compra de sucursal: no es pérdida.

## 3. Inflación: venta nominal y real

- Los montos están en pesos corrientes. En pesos constantes:
  `V_real,t = V_t × IPC_base / IPC_t`. Variación real interanual:
  `(1 + g_nominal) / (1 + π_12 meses) − 1`, casi `g − π`.
- Qué índice: el IPC general del INE para una lectura amplia; el de alimentos
  y bebidas (y el de cada división) para súper; mejor aún, un índice propio
  por categoría (venta / unidades), con unidades comparables y separando
  precio de mezcla ([retail-y-clientes.md](retail-y-clientes.md), sección 2).
- Salario real (Índice Medio de Salarios del INE, deflactado por IPC): el
  poder de compra de los hogares.
- Los montos son sin IVA; si cambió una tasa o un beneficio (por ejemplo, la
  rebaja de IVA por pagar con débito), [verificá] si afecta los precios que
  ve el cliente.

## 4. Tipo de cambio y frontera

- Cuando Argentina o Brasil están baratos en dólares para un uruguayo, parte
  de la compra de la frontera y del litoral cruza; cuando están caros, se
  revierte (y vienen ellos). [Verificá] la diferencia de precios del período:
  prensa, centros comerciales de frontera, consultoras.
- Dónde mirar: sucursales de departamentos de frontera o del litoral, si las
  hay, y categorías fáciles de transportar (bebidas, almacén, limpieza,
  higiene).
- Importados (televisores, electro): el precio en pesos sigue al dólar
  (cotización del BCU); una suba puede adelantar compras y después frenarlas.
  Las compras por internet al exterior compiten con electro: [verificá] el
  régimen vigente de franquicias.

## 5. Fuentes

| Para | Dónde buscar ([verificá] nombre de la serie y fecha) |
|---|---|
| Precios | INE: IPC mensual, general y por división; Área de Defensa del Consumidor (MEF): relevamientos de precios |
| Salarios, empleo, hogares | INE: Índice Medio de Salarios, Encuesta Continua de Hogares, censo 2023 y proyecciones |
| Actividad y dólar | BCU: cotizaciones, indicador mensual de actividad económica, cuentas nacionales, encuesta de expectativas |
| Pagos y clima | BPS: calendario de pasividades. INUMET: datos diarios por estación |
| Turismo | Ministerio de Turismo: estadísticas de visitantes |
| Comercio | Cámara Nacional de Comercio y Servicios; la asociación de supermercados; centros comerciales departamentales (los de frontera hablan del cruce); la cámara de economía digital (CyberLunes, e-commerce) |
| Expectativas | Ceres (índice líder); índice de confianza del consumidor de la Universidad Católica; consultoras |
| Prensa | El País, El Observador, Búsqueda, la diaria, Montevideo Portal |
| Países vecinos | Argentina: INDEC, BCRA. Brasil: IBGE, Banco Central do Brasil |
| Interno | Calendario de acciones de promo y marca (en Core Tienda), horarios y cierres de sucursales, compras (costos, quiebres) |

Preferí la fuente primaria (el INE) a la nota que la cita; anotá serie,
período, fecha de publicación y de consulta (las series se revisan); si no
encontraste un dato, no lo inventes ("no encontré X; usé el supuesto Y"); si
dos fuentes difieren, decí cuál usás y por qué.

## 6. Datos personales y memoria

- Los datos de clientes están protegidos por la ley de protección de datos
  personales (Ley 18.331; la autoridad de control es la URCDP). Antes de
  proponer campañas personalizadas o cruces de datos, [verificá] qué permite
  y qué consentimientos hacen falta. En los informes, nunca nombres.
- Lo verificado va a la memoria con tema, el dato con su período y la fuente
  (institución, serie, dirección, fecha de consulta); si se actualiza, la
  nota vieja se retira. Antes de cada informe, chequeá que tus notas cubran
  el mes que pronosticás y su par del año anterior.
