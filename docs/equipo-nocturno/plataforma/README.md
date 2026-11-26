# El mapa de Core Tienda

Qué hay en cada pantalla, quién la ve, qué se puede hacer, qué datos hacen
falta para probarla y qué parece flojo. Se armó leyendo el código de `main`
el 24/11/2026: lo marcado como **sospecha** hay que confirmarlo usando la
pantalla (el recorrido de la noche). Si una pantalla cambia, se actualiza su
parte acá en el mismo PR.

| Zona | Archivo | Qué cubre |
|---|---|---|
| El hilo de trabajo | [calendario-tareas-entregas.md](calendario-tareas-entregas.md) | Mundos, calendario (mes, lista, equipo), ficha de la acción, tareas = pedidos, plantillas, copiar, Mi agenda, Mis tareas, tablero de entregas y su ficha, campanita, cómo lo ve la agencia. 11 recorridos, con el ciclo completo con la agencia. |
| Materiales y locales | [materiales-precios-locales.md](materiales-precios-locales.md) | Cenefas (lote, plantillas, generar, historial, informe, conocimiento), Convertidor, Diccionario, Tinín, precios y listas, Redexpres (Mi pedido y Planilla), colocación y fotos, validación de redes, cómo lo ve un local, qué cambia por mundo y qué archivos de ejemplo hay. 10 recorridos. |
| Entrada, estructura y diseño | [entrada-admin-diseno.md](entrada-admin-diseno.md) | Login y contraseñas, Don Tino, perfil, conexiones, ayuda, administración, medios y finanzas, el menú y las barras, los 32 permisos y los roles, qué ve cada tipo de cuenta, y **el sistema visual** (colores, modo oscuro, letra, componentes, estados, inconsistencias). |

## Las pantallas de un vistazo

| Pantalla | Ruta | Quién | Zona |
|---|---|---|---|
| Iniciar sesión, olvidé mi contraseña, nueva contraseña | `/login`, `/forgot-password`, `/reset-password` | Todos | Entrada |
| Elegir mundo | `/mundos` | Quien entra a más de un mundo | Hilo |
| Don Tino (inicio de muchos) | `/home` | Con `ai.don_tino` (también los locales) | Entrada |
| Calendario (mes, lista, equipo) y ficha de la acción | `/calendario` | Equipo; agencia solo si su alcance lo deja | Hilo |
| Mis tareas | `/mis-tareas` | Equipo | Hilo |
| Tablero de entregas / Mi tablero | `/entregas` | Equipo y agencias | Hilo |
| Cenefas, plantillas, generar, historial, informe, conocimiento | `/materiales/cenefas…` | Equipo (algunas solo superadmin) | Materiales |
| Convertidor, Diccionario | `/materiales/convertidor`, `/materiales/diccionario` | Equipo | Materiales |
| Precios y listas | `/precios`, `/precios/listas` | Equipo | Materiales |
| Mi pedido (local) / Planilla (gestión) | `/redexpres/mi-pedido`, `/redexpres/planilla` | Locales / equipo de Redexpres | Materiales |
| Colocación, Fotos para subir | `/colocacion`, `/fotos` | Equipo / locales | Materiales |
| Validación de redes | `/redes-sociales/validacion` | Equipo | Materiales |
| Administración | `/admin` | Admin y superadmin | Entrada |
| Perfil, conexiones, ayuda | `/perfil`, `/settings`, `/ayuda` | Todos | Entrada |
| Medios y finanzas | `/dashboard`, `/analytics`, `/campaigns`, `/canales`, `/facturacion…` | Equipo con esos permisos | Entrada |
| Clientes VIP | `/clientes-vip` | Solo con `clientes_vip.view` (ningún rol lo trae); cargar, con `clientes_vip.cargar`. Solo Tienda Inglesa | — |

Clientes VIP (25/11/2026) son datos confidenciales de clientes: en el entorno
de pruebas está vacía y así tiene que quedar. Nunca cargues datos de verdad
ni saques capturas con datos de producción. Para probar la carga, armá un CSV
chico inventado con las columnas de `frontend/lib/clientes-vip/resumen.ts`.

## Lo que hay que saber antes de recorrer (resumen de los tres mapas)

- **Cuentas:** «Equipo nocturno» es superadmin y entra a los 5 mundos (elige
  al entrar). «Agencia de prueba» es externa y cae en su tablero. «Local de
  prueba» es una sucursal de Redexpres y cae en Don Tino.
- **No hay una cuenta interna común:** para ver la plataforma como alguien
  del equipo sin superadmin (o para probar aprobaciones entre dos), creala
  desde `/admin` (Nuevo usuario → Del equipo → rol «Usuario»).
- **«Agencia de prueba» está en «¿Quién la hace?»** desde el 26/11/2026
  (antes solo Publicis, Another Monday y «Diseñadores»): se le pide directo,
  y en Tableros tiene su pestaña.
- **No bloquees ni desactives la cuenta Equipo nocturno** (te deja afuera
  hasta reiniciar el servidor). Para probar bloqueos, una cuenta descartable.
- **La IA está simulada.** Don Tino y la revisión de piezas contestan con
  reglas. Tinín, Doña Tina y CatTi fallan (usan la API real con una clave
  falsa): eso no es un hallazgo del entorno, salvo cómo se muestra el error.
- **Archivos de ejemplo** para cenefas y Redexpres: ver «Archivos de ejemplo
  que hay en el repo» en el mapa de materiales.
- **Pantallas que no redirigen:** muchas se quedan en la ruta y muestran «No
  tenés acceso» o «Los precios no son de Redexpres». El barrido lo detecta.
