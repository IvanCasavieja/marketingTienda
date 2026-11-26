# Permisos y seguridad a nivel QA (OWASP)

Ramiro no es pentester: hace lo que un QA de primer nivel hace con OWASP.
Prueba que cada cuenta llega solo a lo suyo, por la pantalla **y** por la
API, y que nada sensible se escapa. Siempre contra el entorno de pruebas.

## El marco

- **OWASP Top 10:** el control de acceso roto encabeza la edición 2021 y
  sigue primero en la 2025. Con agencias externas, locales y datos de
  clientes, en Core Tienda también es el riesgo número uno.
- **OWASP API Security Top 10 (2023):** API1, autorización por objeto (BOLA,
  el viejo IDOR); API3, por propiedad (campos de más en lo que se responde o
  se acepta); API4, consumo de recursos sin límite; API5, por función (BFLA).
- **ASVS** (4.0.3 y su sucesora, la 5.0) da requisitos verificables por
  niveles (el 1 es el mínimo) y la **WSTG** (Web Security Testing Guide),
  cómo probar cada uno. **STRIDE** (Microsoft), seis preguntas por cambio:
  ¿alguien puede hacerse pasar por otro, cambiar lo ajeno, actuar sin dejar
  registro, ver lo que no debe, trabar la plataforma o darse más permisos?

## Las cuentas que hacen falta

| Cuenta | Para qué | Cómo |
|---|---|---|
| Equipo nocturno (superadmin) | Dueña de los datos | Ya está |
| Interna común (rol Usuario) | El equipo sin superpoderes; aprobar entre dos | `/admin` → Nuevo usuario → Del equipo → Usuario |
| Interna recortada | BFLA: sin `calendario.tareas` o sin `platform.users.manage` | `/admin`, destildando |
| Agencia de prueba / Agencia B | «Una agencia mirando lo de otra» | La A ya está; la B, en `/admin` («Otra agencia») o por API |
| Local de prueba | Sucursal de Redexpres | Ya está |

Para bloquear, desactivar o probar el límite de intentos: una cuenta
descartable, **nunca** Equipo nocturno (te deja afuera hasta reiniciar).

```bash
API=http://localhost:8000/api/v1
token() {  # una vez por cuenta: el login acepta 10 por minuto
  curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
}
pedir() { curl -s -o /dev/null -w "%{http_code}  $1 $2\n" -X "$1" -H "Authorization: Bearer $3" "$API$2"; }
T_EQ=$(token equipo-nocturno@example.com "$CLAVE_EQUIPO_NOCTURNO")
T_AG=$(token agencia-de-prueba@example.com "$CLAVE_AGENCIA_DE_PRUEBA")
T_LO=$(token local-de-prueba@example.com "$CLAVE_LOCAL_DE_PRUEBA")
# Agencia B: nace con clave temporal y en el primer ingreso tiene que cambiarla
CLAVE_B="Qb-$(python -c 'import secrets; print(secrets.token_urlsafe(9))')"
NUEVA_B="Qn-$(python -c 'import secrets; print(secrets.token_urlsafe(9))')"
curl -s -X POST "$API/admin/users" -H "Authorization: Bearer $T_EQ" -H 'Content-Type: application/json' \
  -d "{\"email\":\"agencia-b@example.com\",\"full_name\":\"Agencia B\",\"password\":\"$CLAVE_B\",\"es_externo\":true,\"empresa\":\"Agencia B\"}"
T=$(token agencia-b@example.com "$CLAVE_B")
curl -s -X POST "$API/auth/change-password" -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d "{\"current_password\":\"$CLAVE_B\",\"new_password\":\"$NUEVA_B\"}"
T_AGB=$(token agencia-b@example.com "$NUEVA_B")
```

Los tokens duran 30 minutos y no van a ningún informe.

## Por objeto: lo ajeno pedido por su id (BOLA / IDOR)

1. Como dueña, creá el objeto y anotá su id: está en la dirección
   (`/entregas?tarea=ta-…`, `/calendario?accion=br-…`).
2. Pedí ese id con la otra cuenta, por API, para leer **y** para escribir.
3. Esperado: **404** (la convención de la plataforma: lo que no ves «no
   existe»; un 403 parejo también sirve), nunca 200 con datos. Después de
   una escritura, confirmá con la dueña que no cambió nada.
4. Por pantalla: la dirección con el id, pegada en la pestaña de la otra
   cuenta, no muestra nada.

```bash
TAREA=ta-...   # la tarjeta de «Agencia de prueba», sacada de la dirección
pedir GET "/calendario/tareas/$TAREA/entregas" "$T_AG"    # 200: es suya
pedir GET "/calendario/tareas/$TAREA/entregas" "$T_AGB"   # 404: para B no existe
pedir GET "/calendario/tareas/$TAREA/entregas" "$T_LO"    # 403: el local no tiene calendario
```

Objetos que valen un intento: la tarea y sus entregas, las imágenes
(`/calendario/entregas/imagenes/{id}`), el ZIP
(`/calendario/versiones/{id}/zip`), los adjuntos del pedido, la acción, la
foto de colocación (`/colocacion/fotos/{id}`) y la fila de otro local en
Redexpres. El patrón ya tiene prueba con base
(`test_lo_que_no_se_ve_tampoco_se_toca_por_su_id`): si la rama suma un
endpoint con id y no suma ahí su caso, decíselo a Bruno.

## Por función y por campo (BFLA y BOPLA)

- **Función:** la agencia no decide (`POST /calendario/versiones/{id}/decision`)
  ni ve métricas ni nada interno (`/calendario/entregas/metricas`,
  `/admin/users`, `/redexpres/meses`: 403 aunque sepa la ruta). Una interna
  sin `platform.users.manage` no crea cuentas (403, «Acceso denegado —
  permiso de gestión de usuarios requerido»).
- **Campos que se escapan:** a la agencia no le llegan la nota interna, ni
  mails, ni el análisis de la IA (salvo su control previo), ni personas
  fuera de su empresa y de quienes aprueban. Lo mismo que mira
  `test_agencia_externa_api.py`:
  `curl -s -H "Authorization: Bearer $T_AG" "$API/calendario/tareas/$TAREA/entregas" | grep -cE 'notaInterna|@'`
  tiene que dar 0.
- **Campos de más en lo que se manda:** sumá `"es_externo": false`,
  `"permissions": [...]` o `"is_superuser": true` a un cambio legítimo: se
  ignoran o dan 422 (confirmalo con un GET).
- **Escalar:** nadie da un permiso, un mundo o más calendario que los que
  tiene; un Admin no toca a otro Admin; a una externa solo se le da
  `calendario.view` (también lo frena la base). Hasta el 15/11 un gestor
  podía crearse una cuenta «títere» con rol Admin (commit `0b1e23a`).

## Cambios con la sesión abierta

- El servidor lee la cuenta en cada pedido (`get_current_user`): un permiso
  que se saca vale desde el próximo pedido; el menú cambia recién al
  recargar (documentado). Sacale `calendario.edit` a una interna con el
  calendario abierto y que intente crear una acción: 403 con un cartel
  claro.
- Desactivar una cuenta descartable con la sesión abierta: el próximo
  pedido da 401 (la consulta exige que esté activa).

## Sesión, login y CSRF

- **CSRF:** todo lo que escribe (POST, PUT, PATCH, DELETE) exige el header
  `Authorization: Bearer`; la cookie sola no alcanza (`core/deps.py`). Un
  endpoint nuevo que lea la sesión de otra forma es ROJO.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$API/notificaciones/marcar-todas-leidas" --cookie "access_token=$T_EQ"   # 401
for o in http://localhost:3000 https://otro-sitio.example; do   # el primero es el control: tiene que aparecer
  echo "$o → $(curl -s -D - -o /dev/null -H "Origin: $o" "$API/auth/me" | grep -i access-control-allow-origin)"
done                                                                                                                   # el segundo: vacío
```

- **Salir:** sospecha del mapa que el código sostiene al 25/11 (`logout`
  solo borra las cookies): el token sigue sirviendo. Con una cuenta
  descartable: guardá su token, salí y pedí `/auth/me`. Si da 200, es un
  hallazgo de antes (cuaderno), salvo que la rama haya tocado la sesión.
- **Login:** el mismo mensaje para mail inexistente, contraseña mal y cuenta
  bloqueada (desde el 15/11); bloqueo a los 5 fallos por 15 minutos; 429 al
  pasar los 10 por minuto, que frena a todos los que entran desde esa
  conexión: hacelo al final.
- **Recuperar la contraseña:** el link dura una hora, sirve una vez, en la
  base va su hash y salen como mucho 3 por hora.
- **Política:** de 6 a 20 caracteres. ASVS 4.0.3 pide al menos 12 y aceptar
  64, pero Ivan lo decidió el 19/11 (commit `3f04150`): se prueba lo
  decidido, y la diferencia, si se menciona, va como dato y no como ROJO.

## Archivos, inyección y recursos

- **Subidas:** un texto llamado `.jpg`, un SVG (puede llevar código),
  nombres con `../`, dobles extensiones. Lo que se baja (ZIP, originales) se
  baja como archivo, no se abre como página.
- **Inyección:** React escapa el texto; el riesgo está en
  `dangerouslySetInnerHTML`, en los links armados con datos de la gente y en
  las respuestas con formato de Don Tino. Los casos de link de
  `test_seguridad_urgente.py` se repiten en cada campo de link nuevo.
- **Recursos:** después de actualizar dependencias, probá que el límite de
  pedidos salta de verdad (estuvo apagado de julio al 15/11, `c5b1ff6`).
  `BASE_TOPE_MB` deja de guardar y avisa; nunca borra.

## Datos confidenciales

- **Clientes VIP** son datos de clientes (`clientes_vip.view`, que ningún rol
  trae). En Uruguay rige la Ley 18.331 de protección de datos personales. Se
  prueba con un CSV inventado y la pantalla del entorno queda vacía.
- **El cuaderno y el repo son públicos:** ninguna captura con contraseñas (el
  cartel ámbar de la contraseña temporal en `/admin`), tokens, mails reales
  ni datos de clientes. Las trazas de Playwright guardan lo tipeado: quedan
  en `$S`.
