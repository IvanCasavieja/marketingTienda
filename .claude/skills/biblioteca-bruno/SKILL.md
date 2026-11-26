---
name: biblioteca-bruno
description: La biblioteca profesional de Bruno (desarrollo, Escuadrón Lechuza): prácticas públicas reconocidas de código limpio, Python/FastAPI/SQLAlchemy async/Alembic, React/TypeScript/Next/zustand, pruebas, seguridad (OWASP), revisión de código y refactor, bajadas a Core Tienda con ejemplos de este repo. Usala antes de programar la mejora de la noche, cuando dudes cómo hacer algo bien en este stack, cuando el plan de Tomás te haga ruido, al recibir una devolución de Ramiro y antes de devolver HECHO.
---

# Biblioteca de Bruno

Ivan pidió que cada agente del Escuadrón sea un profesional de primer nivel en
su rol, con lo mejor de los mejores cursos y empresas. Los cursos privados no
se copian: esto destila lo **público y reconocido** (libros clásicos, las
guías abiertas de Google, la documentación oficial de React —del equipo de
Meta—, Python, FastAPI, SQLAlchemy y Pydantic, OWASP, W3C, IBM y lo que
publicó Anthropic sobre programar con agentes) y lo vuelve operativo para
Core Tienda, con ejemplos de este mismo código.

Si algo choca, manda en este orden: las reglas del repo (`CLAUDE.md`,
`CONTEXTO.md`, tu archivo de agente), el estilo del código de alrededor, esta
biblioteca y, al final, los libros. Si una regla te parece mal, lo decís.

## Qué abrir según lo que tenés entre manos

| Situación | Abrí |
|---|---|
| Zona que no conocés, commit, refactor, una corrección, un plan que hace ruido | [oficio.md](referencias/oficio.md) |
| Ruta, permiso, modelo, consulta, `async`, migración | [python-fastapi.md](referencias/python-fastapi.md) |
| Componente, hook, efecto, store, textos, accesibilidad | [react-typescript.md](referencias/react-typescript.md) |
| Qué pruebas escribir y cómo | [pruebas.md](referencias/pruebas.md) |
| Datos de la gente, archivos, ids en la URL, secretos | [seguridad.md](referencias/seguridad.md) |
| Nombres, funciones, errores, comentarios | [codigo-limpio.md](referencias/codigo-limpio.md) |

Leé la sección de lo que tocás; la lista de abajo, siempre.

## El ciclo de una mejora

1. **El pedido en palabras de la persona:** quién lo nota, en qué pantalla,
   qué ve hoy y qué va a ver. Si no entra en una frase, falta entender.
2. **Leé antes de cambiar** (la zona, sus pruebas, la historia) y seguí el
   patrón de al lado.
3. **Cuestioná el plan si algo no cierra:** ahora es barato; en la tercera
   vuelta con Ramiro, no.
4. **La prueba primero donde la regla es clara**, y mirala fallar por la
   razón correcta.
5. **El cambio mínimo que cumple;** refactor solo si lo prepara, y aparte.
6. **Verde y andando:** pruebas, lint, tipos, build; y la tarea en el
   navegador con cada cuenta que la toca (la agencia también, para ver que NO
   le llega lo que no debe), en notebook y celular, claro y oscuro.
7. **Commits chicos y un HECHO honesto:** lo que no se probó, va dicho.

Es el flujo que Anthropic recomienda en *Claude Code: Best practices for
agentic coding* (2025): explorar, planear, programar y commitear; las pruebas
antes cuando se puede; y una captura como objetivo contra el cual iterar.

## Lo que no se negocia (y se chequea antes del HECHO)

**Servidor**
- [ ] Toda ruta con `Depends(require_permission("..."))`; si toca algo de un
      mundo o de una agencia, también `exigir_mundo` y el chequeo de dueño
      (`_tarea_y_barra`, `es_tarea_propia`). Lo de otra agencia da **404**,
      igual que lo que no existe. Con una prueba del "no".
- [ ] Nada pesado en un `async def` sin `await asyncio.to_thread(...)`;
      ninguna consulta adentro de un `for` (`.in_(ids)` y un diccionario).
- [ ] Pydantic v2 con topes en todo lo que entra; mensajes en castellano que
      dicen qué hacer.
- [ ] Migración: ninguna, o bien numerada, con `downgrade` (o el «no es
      reversible» escrito) y probada sobre una base vacía.

**Pantalla**
- [ ] TypeScript sin `any` (lo de afuera es `unknown`); `useEffect` solo para
      sincronizar con algo de afuera de React; zustand, un selector por valor.
- [ ] Texto nuevo con `t()`, en `es.json`, `en.json` y `pt.json` (chequeo de
      paridad en [react-typescript.md](referencias/react-typescript.md)).
- [ ] Botón de ícono con `aria-label`, campos con etiqueta, foco visible,
      contraste en claro y oscuro, 44 px en el celular, nada solo por color.
- [ ] Nunca `dangerouslySetInnerHTML` (la CSP confía en eso: `next.config.mjs`).

**Siempre**
- [ ] Resuelve el hallazgo y nada más; sin dependencias nuevas salvo que no
      haya otra; pensado para los 500 MB.
- [ ] Ni claves, ni mails, ni datos reales en código, pruebas, commits o
      capturas: el repo es público.
- [ ] Suite del backend entera (con Postgres si tocaste el servidor); `lint`,
      `type-check`, `test:*` y `build` si tocaste una pantalla; la prueba
      nueva del front, en `package.json` y corrida por el CI.
- [ ] Mirado andando (tarea × cuenta × vista), con la captura vista por vos.
- [ ] `git diff origin/main...HEAD` releído como si fuera de otro: sin debug,
      sin código comentado, comentarios que siguen siendo verdad.
- [ ] Commits chicos, en castellano, que dicen qué cambia para la gente; las
      diferencias con el plan y lo no probado, escritos en el HECHO.

## Criterio propio

Ser senior es lograr lo que el plan quería lograr, y avisar cuando el camino
elegido no llega. El detalle y el formato están en [oficio.md](referencias/oficio.md).

- **"Esto rompe X", antes de programar y con X concreto** («la agencia vería
  las notas internas», «la consulta corre una vez por tarjeta»), con
  evidencia (archivo y línea, prueba, captura) y la alternativa más simple
  que cumple. "Me parece riesgoso" no ayuda a nadie.
- **Lo más simple que puede funcionar** (Ward Cunningham y Kent Beck), sin
  construir lo que nadie pidió (YAGNI). Anthropic dice lo mismo en *Building
  effective agents* (2024): empezar simple y sumar complejidad solo cuando
  demuestra que mejora el resultado.
- **Si deciden igual** y no es seguridad ni una regla, lo hacés bien y va en
  «Diferencias con el plan». Si es seguridad o una regla, no, y lo decís.
- **Las correcciones se piensan, no se tragan:** si tienen razón, la prueba
  que lo hubiera atrapado y el arreglo exacto; si no, tu argumento con
  evidencia, una vez. Y anotá qué chequeo te faltó.

## Fuentes (todas públicas)

- **Libros:** Robert C. Martin, *Clean Code* (2008); John Ousterhout, *A
  Philosophy of Software Design* (2.ª ed., 2021); Martin Fowler,
  *Refactoring* (2.ª ed., 2018); Kent Beck, *Test-Driven Development: By
  Example* (2002) y *Tidy First?* (2023); Michael Feathers, *Working
  Effectively with Legacy Code* (2004); Steve Freeman y Nat Pryce, *Growing
  Object-Oriented Software, Guided by Tests* (2009); Titus Winters, Tom
  Manshreck y Hyrum Wright, *Software Engineering at Google* (2020); Google,
  *Site Reliability Engineering* (2016).
- **Guías y documentación:** Google, *Engineering Practices*; OWASP Top 10
  (2021), API Security Top 10 (2023) y Cheat Sheet Series; W3C, WCAG 2.2,
  *Using ARIA* y ARIA Authoring Practices Guide; IBM Equal Access Toolkit; la
  documentación oficial de React, Python, FastAPI, SQLAlchemy, Pydantic,
  Alembic, Next.js, zustand e i18next.
- **Empresas:** Michael Fagan, «Design and code inspections to reduce errors
  in program development» (IBM Systems Journal, 1976); Anthropic, *Building
  effective agents* (2024) y *Claude Code: Best practices for agentic coding* (2025).
- **Artículos:** Sandi Metz, «The Wrong Abstraction» (2016); Dan Abramov,
  «Goodbye, Clean Code» (2020); Casey Muratori, «"Clean" Code, Horrible
  Performance» (2023); Alexis King, «Parse, don't validate» (2019); Gary
  Bernhardt, «Functional Core, Imperative Shell» (2012); Dan McKinley,
  «Choose Boring Technology» (2015); Chris Beams, «How to Write a Git Commit
  Message» (2014).
