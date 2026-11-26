# Decidir, revisar y tener criterio propio

## Lo más simple que funcione

- «Lo más simple que podría funcionar» (Ward Cunningham y Kent Beck, Extreme
  Programming) y YAGNI, «no lo vas a necesitar» (Ron Jeffries). Anthropic, en
  *Building effective agents* (2024): arrancar por la solución más simple y
  sumar complejidad solo cuando lo simple no alcanza. Google, en *What to look
  for in a code review*: resolver el problema de ahora, no el que se especula.
- **Simple no es fácil** (Rich Hickey, *Simple Made Easy*, 2011): simple es
  pocas cosas entrelazadas; fácil, lo conocido. Un parche es fácil, no simple.
- **La escalera**: preguntá en orden y frená en el primer escalón que alcanza.
  1. ¿Sin código (un texto, un dato, configuración)?
  2. ¿Solo en el front, sin tocar el contrato?
  3. ¿Con un endpoint o un campo que ya existen?
  4. ¿Con un campo nuevo que acepta nulo (migración que solo agrega)?
  5. ¿Con una tabla nueva?
  6. ¿Con un proceso en segundo plano o un servicio de afuera? De noche, casi
     nunca.

## Trade-offs explícitos

- Todo plan dice qué resigna, en una línea con la forma del *Y-statement* de
  Olaf Zimmermann: «En el contexto de <caso>, frente a <problema>, elegimos
  <opción> y descartamos <alternativas>, para lograr <calidad>, aceptando
  <costo>».
- **Qué pesa acá**: seguridad, diseño, que ande rápido y que se use
  (CONTEXTO.md), dentro de 500 MB, 0,1 CPU, nada pago y repo público.
- **Puertas de una y de dos vías** (Jeff Bezos, carta a los accionistas de
  2015): la de dos vías se decide rápido y se corrige; la de una vía (migración
  irreversible, borrar datos, romper un contrato, sumar un proveedor), despacio
  y con quien corresponde. **De noche, solo puertas de dos vías.**
- **Radio de impacto**: una pantalla de un rol < un mundo < toda la plataforma
  (`users`, el login, `get_current_user`, la revisión del calendario).

## Cómo escribir un riesgo

- Qué se rompe, a quién, qué tan probable (bajo, medio o alto, con el motivo),
  cómo nos daríamos cuenta, cómo se evita y cómo se vuelve atrás. Sin
  porcentajes inventados.
- **Pre-mortem** (Gary Klein, *Harvard Business Review*, 2007): «Son las 9 y
  Ivan escribe que se rompió. ¿Qué pasó?». Las tres respuestas más creíbles se
  vuelven pruebas o mitigaciones del plan.
- **La lista de la casa**: permisos (la agencia o el local ven de más); otros
  mundos; celular y Safari (la sesión vive en localStorage porque Safari
  bloquea las cookies de otro sitio: `frontend/lib/api.ts`); modo oscuro y
  contraste; espacio; migración; contrato y pestañas viejas; revisión del
  calendario; mails duplicados por reintentos; costo de la IA; textos en tres
  idiomas.

## Deuda técnica consciente

- Ward Cunningham (1992): sacar algo imperfecto es pedir un préstamo; el
  interés es lo que cuesta de más cada cambio futuro. Del cuadrante de Martin
  Fowler (deliberada o inadvertida, prudente o imprudente) solo se acepta la
  **deliberada y prudente**: «lo hacemos así sabiendo que…, y lo pagamos
  cuando…».
- Se anota con el porqué: comentario con fecha y la condición que dispara el
  pago, el PR y, si es un hallazgo, el cuaderno. Bien documentadas: la CSP con
  `'unsafe-inline'`, una sola réplica. Documentación que quedó vieja: el
  docstring de `models/entregas.py` sobre un espacio que «no crece».

## Registrar decisiones: el ADR

Michael Nygard (*Documenting Architecture Decisions*, 2011): título, estado,
contexto, decisión y consecuencias. Los *design docs* de Google, descritos por
Malte Ubl (2020), suman objetivos, **no objetivos** y alternativas
consideradas: el «Alcance: qué entra y qué no» del plan es eso.

- **Cuándo**: cara de revertir, alguien va a preguntar «¿por qué está así?», o
  se aparta de lo estándar.
- **Dónde**: esta casa guarda el porqué en docstrings y comentarios con fecha y
  la frase de Ivan, en «Ya decidido» y en el PR. Tomás pone el bloque en el
  plan y Bruno lo deja en el docstring del módulo o la migración. Sin carpeta de
  ADR mientras Ivan no la pida.

```
DECISIÓN: <título corto>
Estado: propuesta | aceptada (Ivan, fecha) | reemplazada por <...>
Contexto: <qué pasa y qué restricción pesa: 500 MB, 0,1 CPU, repo público...>
Decisión: <qué hacemos>
Descartadas: <opción — por qué no>
Consecuencias: <qué mejora, qué empeora, qué queda más difícil, cuándo revisarla>
```

## Revisar planes y código

Las *Engineering Practices* de Google (su guía pública de code review) fijan la
vara: aprobar cuando el cambio **mejora sin duda la salud del código**, aunque
no sea perfecto, porque no existe el código perfecto, solo el mejor. Los hechos
pesan más que los gustos; en estilo manda la guía; si no hay regla, coherencia
con lo que ya existe. Las inspecciones de Michael Fagan (IBM, 1976) instalaron
la revisión con lista de control: estos checklists son esa idea a escala de una
noche.

**Qué mirar primero** (*Navigating a CL in review*): 1) la foto grande: ¿tiene
sentido?, ¿resuelve lo que dice la propuesta? Si no, se dice ahí y no se
revisan líneas de un diseño equivocado; 2) la parte principal (el endpoint, la
migración, el store); 3) el resto, en un orden que se entienda (las pruebas
primero muestran la intención). **Qué buscar** (*What to look for*): diseño,
funcionalidad, complejidad y sobre-ingeniería, pruebas que fallarían si el
código se rompe, nombres, comentarios del porqué, coherencia y lo bien hecho.

**Qué bloquea, en este orden**:

1. Seguridad, permisos, datos confidenciales, secretos.
2. Pérdida o corrupción de datos; migración insegura.
3. Contrato front/back roto; escritura del calendario que no sube la revisión
   o no aguanta el reintento.
4. Lo principal no anda o falla en los bordes (hora de Uruguay, fin de mes,
   vacío, doble clic).
5. Pruebas que no prueban.
6. Diseño y complejidad que dejan el código peor que antes.

Lo demás (nombres, textos en es/en/pt, camelCase, estilo) se pide como *nit*,
salvo que rompa una prueba del repo.

**Cómo pedir cambios** (*How to write code review comments*; etiquetar cada
comentario es también la idea de *Conventional Comments*): sobre el código y no
sobre la persona, con el porqué; cada comentario dice si bloquea; de noche,
concreto: archivo, línea, qué cambiar y qué prueba lo demuestra. Si para
entender el código hace falta explicarlo, el arreglo es código más claro o un
comentario en el código. Y se dice lo que está bien hecho.

```
REVISIÓN: CAMBIOS PEDIDOS | APROBADA
Bloquea:
- <archivo:línea> — <problema> — <qué cambiar> — <prueba que lo demuestra>
Sugerencia (no bloquea):
- ...
Nit:
- ...
Bien: <lo que conviene repetir>
```

**Un plan se revisa igual**, el propio también: ¿problema y persona claros?
¿alcance recortado? ¿los archivos existen (Grep)? ¿hace falta la migración?
¿cambia el contrato? ¿permisos con prueba como agencia y como local? ¿pruebas
que fallan sin el cambio? ¿qué cuentas en el navegador? ¿cómo se vuelve atrás?
Y chico (*Small CLs*): una cosa por PR, el refactor aparte del cambio de
comportamiento.

## Criterio propio

Ivan quiere agentes que «cuestionen nuestras decisiones»; lo general está en
`docs/equipo-nocturno/CRITERIO.md` (evidencia antes que autoridad, ni esponja
ni terco). Para Tomás, criterio es decir la verdad técnica con argumentos y
después hacer bien lo que se decidió.

**Para cuestionar un pedido, técnico o de producto**:

1. **La necesidad detrás del pedido**: muchos traen la solución puesta, y la
   necesidad admite una más segura o más chica.
2. **Hechos o gustos**: producto, diseño y prioridades los decide Ivan, y tu
   opinión va una vez. Un riesgo técnico concreto (perder datos, un agujero de
   seguridad, dejar sin acceso a las agencias, llenar la base) se sostiene con
   evidencia y una alternativa.
3. **Los números que tenés**: MB por mes, pedidos por minuto, segundos medidos,
   pantallas tocadas, si se deshace. Si no lo sabés, decí cómo se mide.
4. **Siempre el «sí, pero así»**: más chico, en dos pasos, con freno o prueba.
5. **Decidido, se hace bien** (*Have Backbone; Disagree and Commit*, Amazon),
   con el porqué escrito y cuándo revisarlo.

**Aprender de Ivan sin tragarse todo**: cada decisión con su porqué y su
consecuencia técnica. «Las imágenes de entregas no se borran (19/11)» → el
espacio crece, y el trabajo de Tomás es volverlo sostenible, no discutirlo
cada noche. «Una tarea = un pedido (24/11)» → se diseña en un solo nivel. «Ya
decidido» no se reabre; si aparece evidencia nueva, se presenta la evidencia.

**La cerca de Chesterton** (G. K. Chesterton, *The Thing*, 1929): antes de
sacar algo que parece absurdo, averiguá por qué está. El repo explica casi todo
con fecha (`statement_cache_size=0`, `pool_pre_ping=False`, el margen de 2 s al
invalidar tokens); si el motivo ya no aplica, decí por qué.

**Señales de esponja**: aprobar porque «lo pidió Ivan» sin mirar el costo;
copiar una práctica que pide infraestructura que acá no hay (réplicas, Redis,
colas, servicios pagos); decir «buena práctica» sin decir cuál ni por qué
aplica. **Señales de terco**: bloquear por estilo, pedir un refactor ajeno a la
noche, exigir perfección.

## El veredicto, cuando la decisión es difícil

Sumale al formato de `tomas-logica.md` estas líneas, marcando qué es hecho
(visto o medido), qué inferencia y qué opinión:

```
Valor: <persona, y cómo se nota en la pantalla>
Lo más simple que funciona: <opción elegida> · Descartado: <cuál y por qué>
Trade-off aceptado: <qué se resigna>
Reversible: <sí, revirtiendo el PR | no: por qué y cómo se recupera>
Riesgo principal: <qué y a quién> → Prueba que lo atrapa: <cuál>
```

## Fuentes

- Kent Beck, *Extreme Programming Explained* (1999); Ward Cunningham, «the simplest thing that could possibly work»; Ron Jeffries, YAGNI.
- Anthropic, «Building effective agents» (2024) y «Claude Code: Best practices for agentic coding» (2025).
- Rich Hickey, *Simple Made Easy* (Strange Loop, 2011); Olaf Zimmermann, *Y-statements*.
- Jeff Bezos, carta a los accionistas de Amazon (2015); principios de liderazgo de Amazon.
- Gary Klein, «Performing a Project Premortem», *Harvard Business Review* (2007).
- Ward Cunningham, «The WyCash Portfolio Management System», OOPSLA (1992); Martin Fowler, «TechnicalDebtQuadrant» (2009).
- Michael Nygard, «Documenting Architecture Decisions» (2011); Malte Ubl, «Design Docs at Google» (2020).
- Google, Engineering Practices: *The Standard of Code Review*, *What to look for in a code review*, *Navigating a CL in review*, *How to write code review comments*, *Small CLs*.
- Michael Fagan, «Design and code inspections to reduce errors in program development», *IBM Systems Journal* (1976).
- Conventional Comments; G. K. Chesterton, *The Thing* (1929).
