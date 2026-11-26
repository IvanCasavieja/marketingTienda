# Pruebas exploratorias: charters, heurísticas y el catálogo para romper

Cem Kaner acuñó el término «prueba exploratoria» en los años 80; James Bach
y Michael Bolton la volvieron método (Rapid Software Testing): diseñar,
ejecutar y aprender a la vez, con un objetivo y un tiempo. No es «tocar a
ver qué pasa»: es la capa 5, la que encuentra lo que nadie previó.

## El charter y la sesión

Elisabeth Hendrickson (*Explore It!*): **Explorá** ‹zona› **con** ‹recursos,
ataques, cuentas› **para descubrir** ‹qué información›.

- Explorá **la entrega de la agencia** con ZIP de 40 MiB justos y uno más,
  red lenta y doble clic, para descubrir si tope, avisos y lo guardado
  coinciden y si algo se duplica o se pierde.
- Explorá **lo que ve la agencia B** pidiendo por id lo de la agencia A, para
  descubrir fugas por pantalla y por API.
- Explorá **el calendario** con una acción que cruza de año y el navegador
  en UTC, para descubrir fechas corridas.

«Probar entregas» no es un charter: no dice con qué ni para qué. La sesión
(SBTM, de Jonathan y James Bach) tiene tiempo fijo (los 15 minutos de la
capa 5) y una hoja:

```
CHARTER: ...                CUENTAS Y VISTAS: ...          DATOS: ...
NOTAS:  lo que probé, en orden, con la hora
ROTO:   bloques ROTO        DUDAS: lo que no sé si está bien (a Tomás o al cuaderno)
TIEMPO: preparar __ % · probar __ % · investigar y reportar __ %
```

Si investigar se come la sesión, cortá y contá lo que tenés.

## SFDIPOT: qué mirar (James Bach, *Heuristic Test Strategy Model*)

El original era SFDPOT; después Bach sumó la I de interfaces.

| Letra | En una mejora de Core Tienda |
|---|---|
| Estructura | Archivos y endpoints que cambian, migración, dónde se guarda cada archivo |
| Función | Cada botón, cada cartel de error, cada aviso que sale |
| Datos | Topes, formatos, unicode; el JSON; el Excel que baja; los 500 MB |
| Interfaces | Pantalla ↔ API, Excel, campanita, Don Tino leyendo los datos |
| Plataforma | Chromium y WebKit, iPhone, 1366×768, Render que se duerme, Supabase, Vercel |
| Operaciones | La agencia a las 19 h con veinte archivos; el local con poca señal; la analista con diez pestañas |
| Tiempo | Sondeos de 4 y 6 s, esperas, sesión de 30 minutos, fechas, concurrencia |

## Tours (James Whittaker, *Exploratory Software Testing*)

| Tour | En Core Tienda |
|---|---|
| Del dinero: lo que justifica el producto | El ciclo central y lo que la rama promete en el informe |
| De los hitos: de pantalla clave en pantalla clave | Calendario → ficha → tablero → campanita → Mis tareas, y al revés |
| FedEx: seguir un dato de punta a punta | Un comentario del equipo hasta la agencia; la cantidad del local hasta el Excel de la Planilla |
| Del barrio peligroso: donde ya hubo defectos | Entregas, guardado automático, cuentas externas |
| Del saboteador: quitarle recursos | Red, servidor, permisos, espacio |
| Antisocial y obsesivo-compulsivo | Datos inválidos, cancelar en el peor momento; doble clic, mandar dos veces, ir y volver |
| De toda la noche: dejarla abierta | Más de 30 minutos de sesión con la pantalla quieta |
| Del museo: lo viejo | Login, perfil, panel, conexiones: el sistema visual viejo |

## Oráculos: cómo sabés que algo está mal (Michael Bolton, HICCUPPS y FEW)

Si no podés nombrar tu oráculo, todavía no tenés un defecto: tenés una duda.
**Historia** (¿así andaba antes? el barrido de la noche, `main`) ·
**Imagen** (¿parece un producto profesional?) · **Comparables** (COR y
Trello, solo por cómo funcionan) · **Afirmaciones** (el plan, el PR, la
Guía, la propia pantalla: «se guarda automáticamente», ¿es cierto?) ·
**Deseos de la gente** (las personas de `criterios.md`) · **Producto**
(consistente consigo mismo: «versión» en todas partes) · **Propósito** (que
la agencia entregue rápido, que el equipo sepa en 10 segundos qué le toca) ·
**Normas** (WCAG 2.2, OWASP, CONTEXTO) · **Problemas conocidos** (el error
disfrazado de vacío, el permiso solo en la pantalla, la última tecla) ·
**Explicable** (si no podés explicar por qué se comporta así, investigá) ·
**Mundo** (Uruguay está en UTC−3 todo el año, se escribe «2,5», febrero de
2028 tiene 29 días).

## El catálogo para romper (capa 5)

Dos o tres ataques bien hechos, elegidos por riesgo, valen más que diez
apurados. Lo que el navegador paso a paso no hace (red lenta, sin red, doble
clic de verdad, dos pestañas, traza) está en el guion de
[navegador-y-visual](navegador-y-visual.md).

**1. Doble clic y repetición.** «Entregar», «Aprobar», «Pedir cambios»,
«Crear tarea», «Confirmar pedido», «Pedir foto a N locales»: `dblclick`
contando las escrituras que salen, y el mismo pedido dos veces a la vez por
API (`curl … & curl … & wait`). ROJO: dos tarjetas, dos versiones, dos
avisos, o un error feo en el segundo.

**2. Carreras entre dos.** Aprobar en una pestaña y pedir cambios en otra
(409 explicado, nada mezclado). Equipo y agencia moviendo la misma tarjeta.
La agencia entrega mientras el equipo revisa (la versión queda
«reemplazada»: quien decide tarde tiene que ver por qué). Dos entregas con
ZIP grande a la vez: el 19/11 pasaban las dos el tope (arreglado el 21/11,
`b32f204`); se prueba con dos conexiones de verdad. Escribir en Mi pedido y
cambiar de mes antes de los 800 ms del guardado (sospecha fuerte del mapa).

**3. Red lenta, sin red, servidor caído.** Lenta: ¿muestra que trabaja, el
botón se puede tocar dos veces, algo se duplica? Sin red a mitad de una
acción: el calendario guarda el cambio como pendiente y lo manda al volver;
el tablero, después de la primera carga, no avisa que se cortó (sospecha
del mapa). Caído: `pkill -f servidor_ia_simulada` con la pantalla abierta,
hacé algo y levantalo (paso 3 del README). ROJO si dice «guardado» y no
guardó, o si al volver se pierde o se duplica.

**4. Interrupciones y pestañas.** Recargar mientras sube una entrega o
mientras corre el control previo (hasta un minuto); «Atrás» después de
mandar; cerrar un cuadro con texto escrito (el de la Planilla se cierra al
tocar afuera: sospecha del mapa). La misma persona editando la misma acción
en dos pestañas; salir en una y seguir en la otra; más de 30 minutos
abierta (en Safari la sesión se cortaba hasta el 15/11); cambiar la
contraseña en una pestaña (las otras sesiones dejan de servir).

**5. Datos raros** (*Test Heuristics Cheat Sheet*, de Hendrickson, Lyndsay
y Emery: Ricitos de Oro, cero-uno-muchos, crear-leer-editar-borrar):
- Vacío, solo espacios, muy largo sin espacios (un link de 300 caracteres en
  un nombre: ¿rompe la tarjeta en el celular?).
- Tildes, ñ, MAYÚSCULAS ACENTUADAS (el buscador del tablero fallaba con ellas
  hasta el 16/11), emoji, tildes «descompuestas» (NFD, como vienen a veces
  los nombres de archivo de una Mac).
- `<img src=x onerror=alert(1)>` se tiene que ver como texto;
  `javascript:alert(1)` en todo campo de link (se ejecutaba en las listas de
  precios hasta el 15/11; los casos de `test_seguridad_urgente.py` sirven
  para cualquier link nuevo); `=HYPERLINK("http://x";"clic")` en un nombre
  que baja a Excel (OWASP lo documenta como «CSV Injection»).
- Números: 0, negativo, «2,5» y «2.5», «1.000», `1e400` (daba error 500
  hasta el 16/11). El mail con mayúsculas o con un espacio al final, como lo
  deja el autocompletar del celular (sospecha del mapa en el login).

**6. Archivos.** 0 bytes; una «.jpg» que es texto; un PNG enorme; una
panorámica de 3000 × 600 (H-019: la foto de colocación se rechaza); HEIC o
WebP; los topes justos (4 imágenes, 40 MiB, 3 fotos) y uno más; ZIP sin
imágenes, con carpetas o con nombres repetidos; un Excel de 10.000 filas
(¿dice cuál es el tope?). Y siempre: **nada borra imágenes de entregas**
(CONTEXTO; H-001, abierto al 25/11: borrar una acción o tarea las borra).

**7. Tiempo y Montevideo.**
- Uruguay está en UTC−3 todo el año (sin horario de verano desde 2015). Si
  el servidor o la base piensan en UTC, de 21:00 a 23:59 ya es mañana:
  probá «vence hoy», «atrasada» y «Hoy» en esa franja, con datos creados
  para esas fechas. Una fecha sin zona leída como local corre todo 3 horas:
  comentá algo y mirá que diga «hace unos segundos», no «hace 3 horas».
- Fin de mes, año nuevo, 29/02/2028 y «Copiar al año que viene» desde ese
  día (2029 no tiene 29 de febrero); una acción que cruza de mes o de año.
- Playwright cambia la zona (`timezone_id`) y el reloj (`page.clock`, desde
  la 1.45) **solo del navegador**: lo que calcula el servidor (vencidas,
  archivado, los 60 días) se prueba con datos en el borde o con pruebas del
  backend.

**8. Permisos a mitad de camino.** Con el calendario abierto como agencia,
un admin le pone «No lo ve»: la próxima pregunta da 403 y la manda a su
tablero (recorrido 9 del mapa). A alguien con la pantalla abierta le sacan
un permiso: el menú cambia recién al recargar (documentado), pero el
servidor se niega en el momento.

**9. Celular.** Girar, el teclado abierto, pellizcar, una sola mano, y la
barra de abajo o una burbuja tapando un botón (H-025: Don Tino tapaba
«Más»). El teclado se aproxima como dice
[accesibilidad-celular-rendimiento](accesibilidad-celular-rendimiento.md).
