# Tareas reales: lo que hace cada persona en Core Tienda

Un recorrido no es «abrir pantallas»: es **hacer el trabajo de alguien** de
punta a punta y ver dónde se traba. Cada tarea dice quién, qué tiene que
lograr y cuándo está bien hecha. El detalle de cada pantalla (qué hay, qué
endpoint llama, qué datos necesita) está en `docs/equipo-nocturno/plataforma/`.

La base del entorno de pruebas arranca **vacía**: lo que haga falta ver, se
crea como lo haría la gente (y así se prueba también la carga).

## El ciclo de todas las noches (siempre)

Es el corazón de la plataforma. Se hace completo, con dos pestañas abiertas
(equipo y agencia) y, al menos una vez, con la agencia en el celular:

1. **Equipo:** crear una acción del mes (nombre, fechas, color) y ponerle
   categoría.
2. **Equipo:** en la acción, crear una tarea **para la agencia** (por ejemplo
   Banners con dos opciones tildadas), con fecha y un adjunto si se puede.
3. **Agencia:** encontrar el pedido en su tablero sin que nadie le diga
   dónde. Leer qué le piden. Pasarlo a En proceso.
4. **Agencia:** entregar imágenes (generalas con
   `scripts/imagenes_de_prueba.py`, con una medida que falte a propósito) y
   ver qué le avisa la plataforma antes de mandar.
5. **Equipo:** enterarse de que llegó (campanita, Mis tareas), abrir la
   entrega, **pedir cambios** con un comentario.
6. **Agencia:** ver qué le corrigieron, entregar de nuevo.
7. **Equipo:** aprobar. Ver que la tarea queda hecha y la tarjeta en
   Finalizado.

Anotá en cada paso: cuántos clics, qué dudaste, qué no se entendía, qué le
llegó (o no) a la otra cuenta y cuánto tardó.

## Por día de la semana (además del ciclo)

| Día | Zona a fondo | Tareas |
|---|---|---|
| Lunes | Calendario | E1, E5, E6, E11 |
| Martes | Entregas y tablero | A1-A4, E3, E4 |
| Miércoles | Locales y Redexpres | L1, L2, E7 |
| Jueves | Materiales, precios, cenefas | E8, E9 |
| Viernes | Administración, perfil, ayuda, Don Tino | E10, E12, X1, X2 |

## Equipo de promo y marca (cuenta «Equipo nocturno», mundo Tienda Inglesa)

- **E1. Cargar el mes.** Crear 4-5 acciones de distintas categorías que se
  pisan en fechas. Bien hecha si: se ven en el mes, se distinguen las
  categorías, los choques se notan y se entiende qué es cada barra.
- **E2. Pedir una pieza a la agencia.** (Es el paso 2 del ciclo.) Bien
  hecha si: la agencia recibe exactamente lo pedido, con medidas y fecha.
- **E3. Revisar una entrega.** Abrir lo que mandó la agencia, compararlo
  con lo pedido, marcar qué cambiar. Bien hecha si: se ve qué falta sin
  abrir cada imagen y el comentario le llega a la agencia.
- **E4. ¿Qué tengo hoy?** Desde que entra: Mis tareas, campanita, tablero.
  Bien hecha si: en menos de 10 segundos sabe qué le toca y qué está
  atrasado.
- **E5. Copiar del año pasado / usar una plantilla.** Bien hecha si: no hay
  que recargar todo a mano y queda claro qué se copió.
- **E6. Mirar el mes en el celular** entre dos reuniones. Bien hecha si: se
  lee sin hacer zoom y se puede abrir una acción.
- **E7. Planilla de Redexpres.** Abrir el mes, ver lo que cargaron los
  locales. Bien hecha si: se encuentra un local y su pedido rápido.
- **E8. Cenefas.** Subir un listado, convertir descripciones, generar.
  (Necesita archivos de ejemplo: buscalos en `backend/tests`; si no hay,
  anotá que la zona no se pudo recorrer y por qué.)
- **E9. Buscar un precio** de un producto y sus listas.
- **E10. Administrar:** dar de alta una persona, cambiar sus permisos y su
  alcance del calendario, crear una cuenta externa de agencia.
- **E11. Vista Equipo y Lista** del calendario: ¿se entiende quién está con
  qué?
- **E12. Conectar mi calendario** (Outlook/Google): ¿se entiende qué hace y
  qué ven los demás?

## Agencia externa (cuenta «Agencia de prueba»)

- **A1. Primer ingreso:** entrar y entender qué es esto y qué le toca, sin
  ayuda.
- **A2. Entregar** imágenes, un ZIP y un link (WeTransfer o directo).
- **A3. Corregir** lo que le marcaron y re-entregar.
- **A4. Todo desde el celular:** ver el tablero, abrir una tarjeta,
  entregar.
- **Siempre:** probar que NO ve nada de más (otras agencias, calendario si
  no tiene alcance, pantallas internas). El recorrido automático ya lo
  chequea pantalla por pantalla; vos probalo desde adentro de una tarjeta.

## Local de Redexpres (cuenta «Local de prueba»)

- **L1. Cargar el pedido del mes** desde el celular: escribir cantidades,
  salir y volver, ver que quedó todo.
- **L2. Subir la foto de colocación** (si la pantalla está habilitada).

## Para cualquiera

- **X1. Olvidé mi contraseña:** el camino desde el login (sin mandar mails
  de verdad: en el entorno de pruebas no salen).
- **X2. Don Tino:** pedirle algo del calendario (la IA está simulada:
  juzgá la pantalla y el flujo, no lo que contesta).

## Prueba a ciegas (Martina)

Elegí **2 tareas** de la noche y dáselas a Martina con la consigna en
palabras de la persona («Te llegó un pedido de banners, entregalo»), sin
decirle dónde está nada. Ella solo ve capturas y toca por coordenadas. Lo
que la traba es lo que trabaría a una persona nueva.
