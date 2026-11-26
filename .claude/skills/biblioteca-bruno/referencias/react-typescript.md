# React, TypeScript, Next y zustand

Next 16 (App Router), React, TypeScript `strict`, zustand 5, Tailwind e
i18next. Ejemplo de referencia: `frontend/components/calendario/Adjuntos.tsx`
con su lógica pura `frontend/lib/calendario/adjuntos.ts`.

## TypeScript estricto

- **Nada de `any`.** Lo que viene de afuera (un error de axios, un JSON, un
  evento) es `unknown` y se angosta: `extractErrorDetail(err: unknown, ...)`
  en `lib/errors.ts`. Y pocos `as` y `!`: son promesas que nadie controla.
- **Estados como unión, no como booleanos sueltos:** `type Status = "idle" |
  "loading" | "loaded" | "error"` (`store/currentUser.ts`). «Que los estados
  imposibles no se puedan representar» (Yaron Minsky, Jane Street): mejor
  `{ estado: "error"; mensaje: string } | { estado: "listo"; datos: T }` que
  `cargando`, `error` y `datos` que pueden contradecirse.
- **Que el compilador te obligue:** `Record<ClaseDeArchivo, ...>` en
  `Adjuntos.tsx` hace que una clase nueva no compile hasta tener su ícono;
  `as const` para listas cerradas (`PERMISOS_CALENDARIO`).
- **Los tipos de lo que manda el servidor** viven en `lib/` (`type Adjunto`)
  y los usa `lib/api.ts`: si cambia el JSON del backend, cambian en el mismo PR.
- **La lógica pura va en `lib/`, sin React ni la API, con imports relativos**
  (`./zip`, `../types`, no `@/`): así compila con el `tsc` de las pruebas.

## Las reglas de los hooks

- Solo en el nivel de arriba del componente o de otro hook: nunca adentro de
  un `if`, un `for` o después de un `return` temprano (en `ListaDeAdjuntos`,
  el `return null` va después de todos los `useState`).
- Dependencias completas. Si el lint pide una que «sobra», no lo silencies:
  el problema es el diseño del efecto (react.dev, *Removing Effect Dependencies*).
- Varias reglas del React Compiler están en *warning* por deuda vieja
  (`eslint.config.mjs`). En código nuevo, cero advertencias nuevas.

## Efectos: cuándo sí y cuándo NO

*You Might Not Need an Effect* (react.dev): un efecto sincroniza el
componente con algo **de afuera de React**. Si no hay un afuera, no va un efecto.

Sí, como en este repo:
- Escuchar eventos del navegador, con su limpieza: los atajos de teclado de
  `BarraSuperior.tsx` (`addEventListener` / `removeEventListener`).
- Manejar el foco al abrir y cerrar: `useDialogo.ts`.
- Pedir datos al abrir algo, con limpieza para que una respuesta vieja no
  pise a una nueva: la bandera `vivo` de `AdjuntosDeLaTarea` (el mismo
  `let ignore = false` de react.dev).
- Leer `localStorage` después de hidratar (`I18nProvider.tsx`).

No:

| En vez de… | Hacé |
|---|---|
| `useEffect(() => setTotal(items.length), [items])` | `const total = items.length` (y `useMemo` solo si mediste que pesa) |
| un efecto que mira un estado `clickeado` | la lógica en el manejador del clic |
| un efecto que resetea el formulario cuando cambia la tarea | `<Ficha key={tareaId} />` |
| efectos que se disparan uno a otro | una función que calcula todo junto, en el manejador |
| un efecto que avisa al padre | llamar al callback en el mismo manejador (`onCambio(data.adjuntos)` en `subir`) |

Un ejercicio de lectura fina: en `AdjuntosDeLaTarea`, el pedido que dispara el
evento `EVENTO_ADJUNTOS` no guarda su limpieza, así que dos avisos seguidos
pueden resolverse en el orden equivocado. Si tocás ese componente, que cada
pedido nuevo invalide al anterior (un contador o un `AbortController`).

## zustand 5

- **Un selector por valor:** `const zoom = useCalendario(s => s.zoom)`. El
  componente se vuelve a pintar solo si cambia ese valor.
- **Nunca un selector que arme algo nuevo** (`s => ({ a: s.a, b: s.b })`,
  `s => s.barras.filter(...)`): cada vez parece distinto y en v5 puede
  terminar en un bucle infinito de renders. Varios selectores, `useShallow`
  (de `zustand/react/shallow`) o la lista calculada en el componente.
- **En manejadores y efectos, `useCalendario.getState()`** (como los atajos
  de `BarraSuperior`): lee el valor del momento sin suscribirse ni quedar con
  un valor viejo atrapado en un closure.
- **El store del calendario ya resuelve las carreras** (escrituras en vuelo,
  colas por acción, reintentos: `lib/calendario/store.ts`). Usá sus acciones;
  un `api.post` suelto por al lado se saltea todo eso.
- **`persist`, con cuidado:** guardá lo mínimo (`partialize`), cambiá
  `name`/`version` si cambia la forma, y `skipHydration` + rehidratar al
  montar para no chocar con el HTML prerenderizado (así está `calendario-mktg-v3`).
- **Lo local, en `useState`;** al store, solo lo que comparten partes lejanas
  (`useVistaEntregas`: la abren la ficha, el tablero y la campanita).

## Rendimiento

Primero medir: React DevTools (*Profiler*) y la pestaña *Performance* del
navegador, con la CPU ralentizada para parecerse a un celular.

- Lo que más cuesta acá es pedir o pintar de más. La pregunta del calendario
  cada 15 s ya viaja liviana (`huella`/`sinCambios`): colgate de esa.
- **`key` estable:** el `id`, nunca el índice si la lista se reordena o se
  borra del medio.
- **`useMemo`, `useCallback` y `memo`** cuando mediste un costo o cuando la
  identidad importa (dependencia de un efecto, prop de un hijo memorizado).
  No por reflejo: cada uno es código y dependencias para mantener.
- **Listas largas, sin dependencias nuevas:** paginar o «Ver más», y filtrar
  en el servidor. Virtualizar es el último recurso.

## Accesibilidad en componentes

La vara es WCAG 2.2 (W3C). Primera regla de *Using ARIA* (W3C): si hay un
elemento HTML que ya hace lo que necesitás, usalo; y la ARIA Authoring
Practices Guide avisa que ningún ARIA es mejor que un ARIA mal puesto.

- `<button>` para acciones, `<a href>` para navegar, `<label>` para campos
  (con `htmlFor` y un `id` de `useId()`). Nada de `div` con `onClick`.
- **Botón de solo ícono:** `aria-label` con la acción y el objeto (`Sacar
  ${a.nombre} del pedido`); mejor con texto visible («Bajar»). Íconos
  decorativos con `aria-hidden`.
- **Avisos:** `role="alert"` para errores (como en `ListaDeAdjuntos`),
  `role="status"` para lo que no apura (WCAG 4.1.3). El error dice qué hacer
  y va al lado del campo.
- **Teclado:** todo con Tab, Enter y Esc; foco visible (`focus-visible:`); lo
  que tapa la pantalla usa `useDialogo` (el foco entra, da la vuelta adentro
  y vuelve al botón que lo abrió).
- **Contraste:** 4,5:1 para texto (WCAG 1.4.3) y 3:1 para bordes de
  controles e íconos que informan (1.4.11), en claro **y** oscuro (`dark:`).
  Nada solo por color (1.4.1): el rojo de «cambios pedidos» va con palabras.
- **Tamaño:** WCAG 2.2 pide al menos 24×24 px (2.5.8); acá se usa 44 px en el
  celular (`min-h-[44px]`), como recomienda Apple.
- **Para revisar:** `navegador.py medidas` y, como segunda opinión, el
  Accessibility Checker gratuito del IBM Equal Access Toolkit.

## Next.js (App Router), como está armado acá

- Las pantallas son componentes de cliente (`'use client'`) que le piden a
  FastAPI por `lib/api.ts`. No hay Server Actions ni rutas de API de Next: la
  seguridad vive en FastAPI, y una ruta de Next que leyera datos por su
  cuenta se saltearía `require_permission`.
- `NEXT_PUBLIC_*` queda pegado en el JavaScript que baja cualquiera: nunca
  un secreto ahí.
- `window` y `localStorage` no existen al prerenderizar: leelos en un efecto
  o en un manejador, nunca en el cuerpo del render.
- `useSearchParams` en una página estática va dentro de `<Suspense>` (como
  en `calendario/page.tsx`); si no, `npm run build` falla.
- Pedidos con `api.*` (pone el `Authorization`) y `encodeURIComponent` en cada id.

## Textos en tres idiomas

- **Texto nuevo:** `const { t } = useTranslation()` y la clave en `es.json`,
  `en.json` y `pt.json`, agrupada por pantalla y en camelCase
  (`calendario.accessDenied`). Interpolación con `{{n}}`; plurales con `_one`
  y `_other` más `count`.
- **El calendario tiene mucho castellano escrito en el componente** (deuda
  vieja): lo tuyo va con `t()`; migrar lo viejo es otro PR, si Tomás lo pide.
- **`fallbackLng` es `es`:** una clave que falta en `en` o `pt` no rompe, se
  ve en castellano. Mirando no lo vas a notar: chequealo.

```bash
cd frontend && node -e '
const plano = (o, p = "") => Object.entries(o).flatMap(([k, v]) => v && typeof v === "object" ? plano(v, p + k + ".") : [p + k]);
const es = plano(require("./lib/locales/es.json"));
for (const l of ["en", "pt"]) {
  const otro = new Set(plano(require(`./lib/locales/${l}.json`)));
  const faltan = es.filter(k => !otro.has(k));
  console.log(`${l}: faltan ${faltan.length}`, faltan.slice(0, 20));
}'
```

Ya faltan claves de antes: lo que importa es que ninguna tuya aparezca en la
lista y que el número no crezca.

- **La lógica pura no traduce:** devuelve datos (una clave y números) y el
  componente arma la frase con `t()`. Hoy `sumarArchivos` devuelve frases en
  castellano; si lo tocás por los idiomas, que devuelva `{ clave, n }`.
- **Los `detail` del servidor vienen en castellano** y la pantalla los
  muestra tal cual: es la convención de hoy; no la cambies de paso.
- **Fechas y números** con `Intl` o date-fns con su locale; no armes
  «1.234,50» a mano. En `en` y `pt`, traducción natural, no literal.
