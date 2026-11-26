# De dónde sale cada regla

Todo es público. Los links se revisaron el 25/11/2026; lo que no tiene link
se encuentra por el nombre. Si sumás una fuente, que sea pública, con autor
real y algo concreto que se aplique. Nada de citas de memoria.

## Lenguaje claro

- **ISO 24495-1:2023**, *Plain language — Part 1: Governing principles and
  guidelines*: la definición y los cuatro principios.
  https://www.iplfederation.org/iso-standard/
- **Federal Plain Language Guidelines** (EE. UU., 2011, red PLAIN; Plain
  Writing Act de 2010): voz activa, frases y párrafos cortos, sujeto cerca
  del verbo, sin dobles negaciones, tablas para lo complejo.
- **OPM**, oficina de personal del gobierno de EE. UU.: frases de 15 a 20
  palabras en promedio. https://www.opm.gov/information-management/plain-language/
- **GOV.UK**, *Writing to GOV.UK standards* y la guía de estilo A a Z: lo
  importante primero, 25 palabras por frase como máximo, palabras a evitar.
  https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/writing-guidelines/
- **Google**, *Technical Writing One* y *Two* (cursos gratuitos) y la
  *Developer documentation style guide*: frases, párrafos, listas,
  ilustraciones y epígrafes.
  https://developers.google.com/tech-writing/one/short-sentences ·
  https://developers.google.com/tech-writing/one/paragraphs ·
  https://developers.google.com/tech-writing/two/illustrations
- **Microsoft Writing Style Guide**, «Top 10 tips for Microsoft style and
  voice». https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice
- **IBM Press**, *Developing Quality Technical Information* (Carey, Lanyi,
  Longo, Radzinski, Rouiller y Wilde, 3.ª edición): fácil de usar, de
  entender y de encontrar.
- **RAE**, *Ortografía de la lengua española* (2010).
- **George Orwell**, «Politics and the English Language» (1946); **Strunk y
  White**, *The Elements of Style*.

## La conclusión primero y escribir para decidir

- **Barbara Minto**, *The Pyramid Principle*.
- **Kabir Sehgal**, «How to Write Email with Military Precision», *Harvard
  Business Review*, noviembre de 2016 (BLUF).
  https://hbr.org/2016/11/how-to-write-email-with-military-precision
- **Chip Heath y Dan Heath**, *Made to Stick* (2007).
- **Cole Nussbaumer Knaflic**, *Storytelling with Data* (Wiley, 2015).
- **Sherman Kent**, «Words of Estimative Probability» (CIA, 1964).

## La pantalla, el mail y las imágenes

- **Jakob Nielsen**, «How Users Read on the Web» (1997), y **Nielsen Norman
  Group**, el patrón de lectura en F (2006).
- **W3C**, WCAG 2, criterio 1.1.1, y el «alt decision tree» de la Web
  Accessibility Initiative.
- **Edward Tufte**, *Envisioning Information* y *The Visual Display of
  Quantitative Information* (los *small multiples*).
- **Outlook y Gmail:** lo que saben quienes diseñan mails (el motor de Word
  de Outlook clásico, el bloqueo de imágenes, el recorte de Gmail pasados
  unos 102 KB). Antes de cambiar `correo.py`, probalo en los dos.

## La conversación

- **Amazon**, principios de liderazgo: «Have Backbone; Disagree and Commit».
- **Kim Scott**, *Radical Candor* (2017).
- **Patterson, Grenny, McMillan y Switzler**, *Crucial Conversations* (2002).
- **Google**, *Engineering Practices*, «How to write code review comments».

## El PR y las fallas

- **Google**, *Engineering Practices*, «Writing good CL descriptions».
  https://google.github.io/eng-practices/review/developer/cl-descriptions.html
- **Phabricator** (nació en Facebook): el campo *Test Plan*, obligatorio por
  defecto. **React** (Meta): `.github/PULL_REQUEST_TEMPLATE.md` en el repo
  `facebook/react`.
- **Google**, *Site Reliability Engineering* (O'Reilly, 2016), «Postmortem
  Culture: Learning from Failure».

## Anthropic

- **«Prompting best practices»**, la guía de prompts para Claude: la prueba
  del colega con poco contexto.
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

## De la casa

- `docs/equipo-nocturno/README.md` (*Formato del informe*) y
  `.claude/agents/clara-informe.md`: el contrato. `docs/equipo-nocturno/CRITERIO.md`:
  el criterio común del escuadrón.
- `.claude/skills/correo-del-equipo/` (`scripts/correo.py`, probado línea
  por línea el 25/11/2026), `docs/equipo-nocturno/CONTEXTO.md`,
  `recorrido-humano/criterios.md` y el mapa de `docs/equipo-nocturno/plataforma/`.
- En la rama del cuaderno: `cuaderno/DECISIONES.md` y la auditoría del 25/11.
- Las correcciones de Ivan del 25/11/2026 (commits `e083f84`, `36f7a43` y
  `eac7477`) y el mail modelo (`origin/nocturno/2026-11-25-prueba-del-mail`).
