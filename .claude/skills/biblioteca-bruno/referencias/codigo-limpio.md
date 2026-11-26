# Código limpio sin dogmas

La meta no es «código limpio»: es código que el próximo (otra noche, otro
agente, Ivan) entienda y cambie sin miedo. Ousterhout (*A Philosophy of
Software Design*) define la complejidad como lo que hace difícil entender y
modificar un sistema, y le ve tres síntomas: un cambio chico que obliga a
tocar muchos lugares, la carga mental para entender algo, y lo que no sabés
que no sabés. Todo lo de abajo apunta a bajar eso.

## Clean Code y sus críticas

*Clean Code* (Robert C. Martin, 2008) dejó buenas costumbres: nombres que
dicen la intención, funciones que hacen una cosa, no repetirse, errores con
excepciones, pruebas legibles. Tomadas al pie de la letra (funciones de pocas
líneas, casi cero comentarios, abstraer cada repetición), sus reglas tienen
críticas serias y públicas:

- **Ousterhout:** muchas funciones chiquitas dan módulos «playos» (mucha
  interfaz para lo poco que esconden) y obligan a saltar entre diez lugares
  para entender una idea. Prefiere módulos profundos: interfaz simple, mucho
  trabajo adentro. Él y Martin publicaron un debate escrito sobre esto (largo
  de las funciones, comentarios, TDD); vale leerlo entero.
- **Sandi Metz** («The Wrong Abstraction», 2016): la duplicación es mucho más
  barata que la abstracción equivocada. Dan Abramov («Goodbye, Clean Code»,
  2020) cuenta el mismo error en primera persona.
- **Casey Muratori** («"Clean" Code, Horrible Performance», 2023): la
  indirección y el polimorfismo por reflejo cuestan rendimiento.

**Para esta casa:** seguí el estilo de alrededor. Este repo prefiere
funciones medianas con un docstring que cuente el porqué, comentarios con la
fecha y el pedido de Ivan, y la lógica pura separada del IO. Eso le gana a
cualquier libro.

## Nombres

- Textuales y enteros: camelCase en el front (`tipoOferta`), snake_case en
  Python (`hay_lugar`); nada de `tOf` ni `data2`. Una prueba controla el
  camelCase del vocabulario visible (`test_campos_de_entrada_en_camel_case`).
- Que digan qué es para la gente, no cómo está hecho: `entra(ocupan, nuevos,
  tope)` se lee como una frase. Booleanos como pregunta: `puedeAdjuntar`,
  `es_externo`, `hay_lugar`.
- El mismo concepto con la misma palabra en todas las capas. Cuando la
  palabra cambia, lo nuevo usa la nueva: la pantalla dice «versión» desde #86
  y en el código viejo todavía aparece «ronda».
- Si te cuesta nombrarlo, probablemente hace dos cosas (Ousterhout: la
  dificultad para nombrar es una señal de diseño).

## Funciones y módulos

- **Una cosa, a un nivel de abstracción.** `adjuntar` se lee como una receta:
  tarea visible → puede → cuántos hay → validar cada uno → hay lugar →
  guardar. Cada paso tiene nombre; los detalles están en `reglas`.
- **Módulos profundos:** `reglas.validar(nombre, datos)` esconde extensiones,
  firmas de archivo, tamaños y mensajes detrás de dos argumentos. Lo que hay
  que evitar: la función que solo le pasa los argumentos a otra, y una clase
  por cada cosa.
- **Que el módulo sufra para que quien lo usa no** (*pull complexity
  downwards*): `nombre_limpio` nunca falla; sin nombre, devuelve «archivo».
- **Argumentos:** pocos; los booleanos solo por nombre (`*, gestiona, pide`).
  Más de tres o cuatro piden un objeto (Fowler: *Introduce Parameter Object*).
- **Cláusulas de guarda** en vez de pirámides de `if`: `if fila is None:
  raise ...` arriba, y el camino feliz sin sangría.
- **Constantes con nombre y porqué:** `MAX_BYTES_ADJUNTO = 10 * MB`, con el
  comentario del Excel de 1.000 productos que pesa unos 140 KB.

## Efectos secundarios

- **Separá lo que calcula de lo que hace** (Gary Bernhardt, «Functional
  Core, Imperative Shell»): un núcleo puro y probado (`validar`,
  `puede_adjuntar`, `aplanar` en la migración 0090) y una cáscara fina que
  lee, escribe y responde. En este repo los docstrings dicen «Pura.» cuando lo es.
- **Una función que pregunta no cambia nada** (Fowler: *Separate Query from
  Modifier*): `es_tarea_propia` no escribe.
- **Sin estado global mutable nuevo** (el que existe, las colas de
  `lib/calendario/store.ts`, está documentado y probado), y **no mutes lo que
  te pasaron:** devolvé algo nuevo (`{**r, "parentId": None}` en la 0090). En
  React el estado se reemplaza, no se muta.

## Manejo de errores

- PEP 20: los errores nunca deberían pasar en silencio, salvo que se los
  silencie a propósito. Un `except Exception` lleva su porqué al lado, como
  en `_zip_con`: «cualquier cosa que no se pueda abrir no es un ZIP».
- **Capturá lo que esperás y sabés manejar** (`except ValueError as exc`),
  no todo; y `raise NuevoError(...) from e` para no perder la causa.
- **Dos clases de error:** los de la persona (dato malo, sin permiso, sin
  lugar) se dicen en castellano con qué hacer; los del sistema (un bug, la
  base caída) se loguean con contexto (`exc_info=True`) y a la persona le
  llega algo genérico.
- **Definí los errores fuera de existencia** cuando se pueda (Ousterhout):
  `nombre_limpio("")` devuelve «archivo» en vez de tirar; sacar algo que ya
  no está puede ser «listo», si a la persona le da lo mismo.
- **En el front,** cada `catch` le dice algo a la persona (un toast, un
  `role="alert"`), salvo que el silencio tenga su porqué escrito (como en
  `AdjuntosDeLaTarea`). Nunca un `catch {}` mudo y sin comentario.

## Comentarios

- El código dice qué y cómo; el comentario dice **por qué** y lo que el
  código no puede decir (Ousterhout: lo que no es obvio). Los de la casa
  traen el pedido de Ivan con fecha, el caso real o el número medido.
- **En castellano, y que sigan siendo verdad:** un comentario viejo es peor
  que ninguno. Dos ejemplos reales de después de la 0090 (desde entonces no
  hay tareas que cuelguen de otras): el docstring de
  `backend/app/models/adjuntos.py` todavía dice que las piezas que cuelgan
  ven los adjuntos de su tarea, y en `frontend/lib/api.ts`,
  `adjuntosApi.listar` dice «y los de la tarea de la que cuelga». Si tocás
  código con comentarios así, corregilos en el mismo commit.
- Nada de código comentado (para eso está git). Un `TODO` solo con su
  porqué; mejor, en «Diferencias con el plan».

## Duplicación y abstracción

- **Regla de tres** (Don Roberts, citada por Fowler en *Refactoring*): la
  primera vez lo hacés, la segunda lo duplicás a disgusto, la tercera abstraés.
- **Antes de escribir una ayuda, buscá si existe.** `Adjuntos.tsx` tiene su
  propio `detalleDeError`, y `lib/errors.ts` ya tenía `extractErrorDetail`,
  que además entiende los errores de Pydantic. Lo nuevo usa el que ya está.
- La misma regla en Python y en TS (tipos de archivo, huérfanos) se acepta si
  una prueba las ata.

## Para cerrar

- **Diseñalo dos veces** (Ousterhout): antes de algo no trivial, dos diseños
  y compará. En el plan de una noche alcanzan dos líneas: «A: columna nueva y
  migración. B: el JSON que ya existe. Voy con B: evita la migración».
- **Las cuatro reglas del diseño simple de Kent Beck,** en orden: pasa las
  pruebas, revela la intención, no tiene duplicación, tiene la menor cantidad
  de elementos. Y «make it work, make it right, make it fast» (atribuida a
  Beck): en ese orden, y midiendo antes de lo tercero.
