# Forward Deployed Engineer y producto entre empresas

## 1. Qué hace una Forward Deployed Engineer

Palantir popularizó el rol: ingenieros que trabajan pegados al cliente, en su
lugar y con sus datos, resuelven el problema concreto y llevan al producto
central lo que se repite de un cliente a otro. Ensayos públicos de ex
empleados (por ejemplo, el de Nabeel Qureshi) cuentan que buena parte del
producto salió de generalizar lo que se armaba en el terreno; en los últimos
años lo adoptaron también empresas de IA. Toyota lo decía desde antes:
*genchi genbutsu*, andá y mirá con tus propios ojos (Jeffrey Liker, *The
Toyota Way*, 2004).

Lo que la distingue: se hace cargo del **resultado** de la persona, no del
ticket; vive el flujo del otro antes de opinar; convierte un problema
desprolijo en algo construible y comprobable; separa lo general (va al
producto) de lo particular (no va); y traduce entre la gente y los
ingenieros. De la FDE tomás el lugar y el oficio, no el teclado: el recorrido
es tu terreno, las tres cuentas son tus clientes y Tomás y Bruno, el
producto central. Llegales con un problema bien cortado.

## 2. Del problema a algo construible

1. **El problema en una frase:** «Cuando <situación>, <persona> <lo que le
   pasa>, y eso le cuesta <impacto>.» Si no entra en una frase, son dos.
2. **Las restricciones antes que la solución:** las reglas que no se
   discuten (planes gratis, 500 MB, notebook y celular con Safari, contraste
   alto, nada de jerga) y lo que va a mirar Tomás (permisos en el servidor,
   migraciones, textos en tres idiomas).
3. **Un criterio de aceptación observable.** El Enterprise Design Thinking
   de IBM escribe los objetivos como *Hills*: **quién**, **qué** logra y el
   **wow** que lo hace notable. La vara de CONTEXTO.md ya tiene uno: una
   persona de agencia que entra por primera vez (quién) sabe qué le
   pidieron, para cuándo y cómo entregarlo sin que nadie le explique (qué),
   en un minuto (wow).
4. **La tajada más fina que se nota.** Mike Cohn propone cortar con SPIDR:
   *Spike* (averiguar antes, si no se sabe cómo), *Paths* (un camino
   primero), *Interfaces* (una pantalla primero), *Data* (un tipo de pieza
   primero), *Rules* (la regla principal primero). Cada tajada cumple INVEST
   (Bill Wake, 2003): independiente, negociable, valiosa, estimable, chica y
   comprobable. Acá «una interfaz primero» nunca es «solo notebook»: todo
   tiene que andar también en el celular.
5. **Un prototipo mínimo, sin código:** la captura marcada (`evidencia.py
   --marco`) con dónde va el cambio; el **texto exacto** de carteles,
   botones, estados vacíos y errores (el prototipo más barato y el que más
   discusiones ahorra); el antes/después contado en tres líneas; y la
   consigna de Martina que lo comprobaría.
6. **¿Es general?** ¿Le sirve a cualquier agencia, local o analista? Si
   sirve a uno solo, no va. Para «Diseñadores», nunca un caso especial: es
   una agencia como las otras (CONTEXTO.md).

## 3. Producto B2B: el usuario no es uno solo

En una herramienta entre empresas hay actores con intereses distintos: quien
pide (equipo), quien hace (agencia), quien carga (local) y quien administra
(jefatura). Lo que a uno le ahorra trabajo, a otro se lo puede sumar.
Jonathan Grudin («Why CSCW Applications Fail», 1988) mostró que las
herramientas colaborativas fracasan cuando quien hace el trabajo extra no es
quien recibe el beneficio. Pregunta obligatoria para cada propuesta: **con
este cambio, ¿quién trabaja más y quién gana?** Si la agencia o el local
trabajan más para que Tienda vea mejor, necesitan algo a cambio (menos idas
y vueltas, saber en qué está lo suyo) o lo van a usar a desgano.

Supuesto razonable, para confirmar: para una agencia, Core Tienda es la
herramienta de uno de sus clientes; por eso tiene que entenderse sola.

## 4. Permisos: seguridad que también es experiencia

El principio de **mínimo privilegio** (Jerome Saltzer y Michael Schroeder,
«The Protection of Information in Computer Systems», 1975) da a cada cuenta
lo justo para su trabajo; el control de acceso **por roles** (RBAC; David
Ferraiolo y Richard Kuhn, NIST, 1992) agrupa permisos por rol. Core Tienda
tiene cuatro capas (mapa, `entrada-admin-diseno.md` §3): los permisos de
cada persona (el rol solo los siembra), el **mundo** (de qué negocio), el
**alcance** del calendario (cuánto ve) y la **cuenta externa** (en la
práctica, su tablero). Los locales tienen su propia llave: el local.

Lo que mirás vos (producto, no auditoría):
1. **Nadie ve lo que no debe:** una agencia nunca ve a otra agencia ni lo
   interno (nota interna, análisis de la IA, precios). Probalo desde adentro
   de una tarjeta, no solo por ruta. Si falla, es 🔴.
2. **El «no» se explica:** por qué y a quién pedírselo. Un error de permiso
   disfrazado de otra cosa es un hallazgo (sospecha del mapa: Conexiones le
   dice «Contraseña incorrecta» a quien no tiene permiso).
3. **Lo que se ve, se puede hacer:** un botón que aparece y falla por
   permiso es peor que no mostrarlo.
4. **Administrar no rompe nada sin avisar** (sospecha del mapa: cambiar el
   rol pisa los permisos afinados).
5. **Los nombres dicen la verdad:** hay permisos que no hacen lo que dice su
   nombre (mapa, §3.5), y eso confunde a quien administra.

La regla técnica (se controla en el servidor; la pantalla solo esconde) es
de Tomás y Bruno. Tu traducción: **esconder no es proteger**, y proteger sin
explicar tampoco alcanza.

## 5. Flujos entre empresas: la pelota siempre tiene dueño

- En cada estado, la pantalla de las **dos** cuentas contesta: ¿quién tiene
  la pelota?, ¿qué tiene que hacer?, ¿para cuándo?, ¿cómo se entera el otro
  cuando cambia? Core Tienda ya lo hace en partes («Te toca», «Le toca a
  Publicis», columnas con su explicación): mirá que sea parejo en todas las
  vistas.
- **Avisos:** lo del tablero va solo por la campanita, sin mail (decisión
  del 19/11/2026, por el tope de mails); la agencia se entera si entra. Es
  una restricción real: los hallazgos de «no se enteró» se piensan con ella
  adentro (criterio-propio.md, §4).
- **Lo interno queda adentro:** la nota interna y el análisis de la IA son
  solo de Tienda. Mirá además que la pantalla del equipo deje claro qué va a
  leer la agencia, para que nadie escriba algo creyendo que es interno.
- **Todo cambio se prueba con las dos cuentas abiertas a la vez**, como en
  el ciclo de tareas.md.

## 6. Adopción

Everett Rogers (*Diffusion of Innovations*, 1962): se adopta lo que tiene
**ventaja** sobre lo anterior, es **compatible** con cómo ya se trabaja, es
**simple**, se puede **probar** sin riesgo y deja ver su **resultado**. Fred
Davis (modelo TAM, 1989): pesan la utilidad y la facilidad de uso que la
persona percibe. Las cuatro fuerzas de Moesta están en descubrimiento.md,
§2. Antes de proponer, cinco preguntas:

1. **Ventaja:** ¿qué le ahorra a quien lo usa (no a quien lo mira)?
2. **Compatibilidad:** ¿usa las palabras y el orden de su trabajo? ¿Rompe
   algo que ya aprendieron? (Si es feo pero cambiarlo rompe lo aprendido,
   es una duda para Ivan, como hace Lucía.)
3. **Simplicidad:** ¿una persona nueva lo entiende sola?
4. **Probar sin miedo:** ¿se puede deshacer? ¿Qué pasa si se equivoca?
5. **Resultado visible:** ¿se ve que funcionó? ¿El otro se entera?

IBM trabaja con *sponsor users*: usuarios reales que acompañan el diseño de
punta a punta. Acá no los hay; lo más parecido son los pedidos de Ivan y de
la gente de Tienda que llegan por mail, y las reuniones. Tratá cada uno como
oro: es la única voz directa que tiene el equipo.
