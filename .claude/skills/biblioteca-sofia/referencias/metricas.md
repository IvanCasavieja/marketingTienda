# Métricas de producto para una herramienta de trabajo

Core Tienda no es una app de consumo: la gente entra porque es su trabajo.
Que entre mucho no dice nada. Lo que importa es si hace su trabajo mejor,
más rápido y **adentro** de la plataforma.

## 1. Lo que la noche puede medir y lo que no

- El equipo no toca producción ni tiene claves: **no ve el uso real**.
- Lo que sí mide cada noche, sin instrumentar nada: el ciclo completo
  (pasos, decisiones, idas y vueltas, esperas, lo que no le llegó a la otra
  cuenta); la prueba a ciegas (logradas sobre intentadas, pasos, dónde se
  trabó); el barrido (alertas por gravedad, pantallas sin mirar); y el
  cuaderno (abiertos por flujo y gravedad, cuántos dejan de pasar).
- Llevalo como **tendencia**, con el mismo formato cada noche, en la línea
  del historial si entra: «Ciclo: <pasos>, <dudas>; Martina: <logradas> de
  <intentadas>». Una noche es un dato; diez son una curva.
- Lo que solo se ve en producción **se propone** (qué, de dónde, quién lo
  mira); no se mide de noche.

## 2. HEART (Google)

**Qué es.** Kerry Rodden, Hilary Hutchinson y Xin Fu, de Google, presentaron
en CHI 2010 («Measuring the User Experience on a Large Scale») el marco
HEART: *Happiness* (satisfacción), *Engagement* (compromiso), *Adoption*
(adopción), *Retention* (retención) y *Task success* (éxito en la tarea). Se
usa con el proceso **objetivos → señales → métricas**, y no hace falta usar
las cinco: se eligen las que importan.

**En Core Tienda** (señales para conversar; algunas dependen de lo que la
base ya guarde: confirmalo en el mapa o con Tomás antes de proponerlas):

| | Objetivo | Señal | Métrica posible |
|---|---|---|---|
| Satisfacción | Que la gente confíe en la plataforma | Pedidos y quejas por mail; frases en reuniones | Pedidos de corrección por mes (el cuaderno los anota); con gente real, la pregunta SEQ (Jeff Sauro) o el cuestionario SUS (John Brooke, 1986) |
| Compromiso | Poco útil acá: la gente entra porque tiene que entrar | Uso de lo opcional | Plantillas, copiar del año pasado, Mi agenda conectada |
| Adopción | Que lo nuevo se use | Pedidos hechos con la función nueva | % de los pedidos del mes que la usan |
| Retención | Que el trabajo no vuelva al mail, al WhatsApp o al Excel | Tarjetas que llegan a Finalizado sin ninguna entrega adentro; entregas que son solo un link | % de piezas aprobadas con al menos una entrega en la plataforma |
| Éxito en la tarea | Pedir, entregar, corregir y aprobar sin trabas | Rondas por pieza; tiempo del pedido a la primera entrega; tarjetas atrasadas | Mediana de rondas por pieza; % de piezas aprobadas antes de que empiece su acción |

En una herramienta obligatoria el compromiso casi no informa; las que más
dicen son **éxito en la tarea** y **retención** («el trabajo sigue adentro»).

## 3. North Star e indicadores de entrada

**Qué es.** La métrica North Star (difundida por Sean Ellis y por el *North
Star Playbook* de Amplitude, de John Cutler) resume en un número el valor
que recibe la gente, con tres a cinco **indicadores de entrada** que el
equipo sí puede mover.

**Candidata para Core Tienda** (para proponerle a Ivan; no está decidida):
**acciones que llegan a su fecha de inicio con todas sus piezas aprobadas.**
Junta el calendario (el core) con las entregas (el trabajo con las
agencias), y es lo que le importa al negocio: que la acción salga completa y
a tiempo. Indicadores de entrada posibles: pedidos completos al primer
intento (sin ida y vuelta por datos que faltaban); cuánto tarda la agencia
en arrancar un pedido; rondas por pieza; cuánto tarda el equipo en revisar;
tareas atrasadas que se ven a tiempo.

**Trampa:** toda métrica que se vuelve objetivo se puede ganar haciendo
trampa (§6). Si se mide «piezas aprobadas», se aprueba sin mirar. Por eso
cada métrica va con una **contra-métrica**: piezas devueltas después de
aprobadas (la plataforma permite devolver una pieza ya aprobada).

## 4. Embudos

El ciclo es un embudo: pedido creado → la agencia lo abre → en proceso →
primera entrega → revisada → aprobada (o vuelve con cambios). De noche, se
cae donde vos o Martina se traban. En producción, la señal son tarjetas
quietas en una columna más de lo normal: «Ingresado» quieto = la agencia no
arrancó (¿se enteró?); «Esperando feedback» quieto = le toca al equipo
(¿sabe que le toca?). En una herramienta interna, «caerse» rara vez es
abandonar: es demorarse o hacerlo por afuera.

## 5. Activación y retención en una herramienta de trabajo

- **Activación** no es crear la cuenta: es la primera vez que la persona
  completa su trabajo principal adentro y sin ayuda. Agencia: su primera
  entrega hecha sola desde que le llegó el pedido. Analista: su primer
  pedido que la agencia entiende sin preguntar. Local: su primer pedido del
  mes cargado y confirmado desde el celular. Jefatura: saber qué está
  atrasado sin preguntarle a nadie.
- **Tiempo hasta el valor:** la vara de CONTEXTO.md ya trae metas (un minuto
  para que una agencia nueva sepa qué le pidieron, diez segundos para que el
  equipo sepa qué le toca hoy): usalas como criterio de éxito con Martina.
- **Retención:** en una herramienta interna nadie «se da de baja»: lo que se
  pierde es trabajo que se va a un **canal paralelo** (WhatsApp, mail,
  Excel). Frases como «te lo mandé por mail» son la señal.

## 6. Medir sin instrumentar de más

Douglas Hubbard (*How to Measure Anything*, 2007): medir es **reducir
incertidumbre**, no conseguir precisión, y pocos casos ya enseñan mucho. Su
«regla de cinco»: con cinco casos tomados al azar, hay 93,75 % de
probabilidad de que la mediana de todos esté entre el menor y el mayor.

En Core Tienda, en este orden:
1. **Lo que la base ya tiene** (estados, rondas, fechas), sin escribir nada.
2. **Una muestra a mano:** cinco tarjetas recientes dicen más que ninguna.
3. **Recién entonces, algo nuevo y liviano:** la base tiene 500 MB para todo
   (CONTEXTO.md). Nada de registrar cada clic: contadores agregados, no
   eventos crudos.
4. **Flujos, nunca personas:** un ranking de quién tarda más convierte la
   métrica en vigilancia y la gente aprende a esquivarla. Charles Goodhart lo
   observó en economía (1975); la frase famosa, «cuando una medida se vuelve
   objetivo, deja de ser una buena medida», es de Marilyn Strathern (1997).
5. **Cada métrica con su contra-métrica:** velocidad con calidad (menos
   rondas, pero no más devoluciones).

## 7. «¿Cómo sabremos que funcionó?» en una propuesta

Anthropic, en su guía para construir con Claude, pide definir criterios de
éxito específicos y medibles **antes** de iterar. Acá igual: el criterio se
escribe antes de construir, dentro de «Cómo se va a notar».

```
Esta noche: <antes/después en las mismas vistas; la misma tarea en menos
pasos o decisiones; Martina la logra donde antes abandonaba>.
En producción, si Ivan quiere mirarlo: <señal>, sale de <dónde>, se
debería ver en <cuánto tiempo>.
```

Proponé al menos un indicador **adelantado** (la agencia arranca el pedido el
mismo día): se mueve antes que uno **atrasado** (la acción salió completa).
