# Seguridad

## Lo que ya protege a Core Tienda (y no se rompe)

- **Sesión**: acceso de 30 minutos y renovación de 7 días;
  `tokens_invalidated_at` invalida los anteriores al salir o cambiar la
  contraseña; contraseña cada 60 días salvo los logins de sucursal; bcrypt con
  10 rondas (`app/core/security.py`, `app/core/deps.py`).
- **Permisos**: los de *Lo que este stack castiga* (SKILL.md), más
  `puede_tener`, que frena a un externo aunque tenga un permiso de más, y el
  CHECK de la 0069 en la base.
- **Además**: 200 pedidos por minuto por persona; headers de seguridad y CSP
  (la del front acepta `'unsafe-inline'` como trade-off documentado en
  `frontend/next.config.mjs`); documentación de la API solo en desarrollo; el
  servidor vuelve a controlar el tamaño de cada archivo (2 MB por imagen).

## OWASP Top 10, aplicado

Categorías de la edición 2021. OWASP publicó una revisión en 2025 que reordena
algunas: en un informe, nombrá la categoría y no el número.

| Categoría | Cómo se vería acá | Qué exigir en el plan |
|---|---|---|
| Control de acceso roto | La agencia ve algo interno, otro mundo o algo fuera de su alcance; cambiar un id en la URL abre lo de otro | Chequeo por objeto en el servidor y prueba con base como agencia y como local |
| Fallas criptográficas | Tokens o links guardados tal cual | Hash del link de recuperación (ya se hace); Fernet para tokens de terceros (`encrypt_token`) |
| Inyección | `text()` armado con f-strings; un link `javascript:` en una lista compartida (pasó en las listas de precios, auditoría del 15/11/2026) | Parámetros siempre; validar el esquema de las URL; nada de HTML crudo |
| Diseño inseguro | Una función nueva sin pensar quién la abusa (un link para compartir que no vence) | Modelo de amenazas en el plan (abajo) |
| Configuración insegura | Documentación abierta, CORS amplio, modo debug | No se tocan sin motivo |
| Componentes vulnerables o viejos | Dependencia nueva; actualización que cambia comportamiento (FastAPI 0.139 apagó el límite) | Sin dependencias nuevas salvo necesidad; actualizar con las pruebas de los controles |
| Identificación y autenticación | Mensajes que dicen si la cuenta existe; fuerza bruta | Mensaje único y bloqueo (ya están), más el límite de pedidos |
| Integridad de software y datos | Ejecutar una orden sin verificar de dónde viene | Verificar el origen (el «ok» por mail vale solo si viene de verdad de la casilla de Ivan) |
| Registro y monitoreo | Acciones de administración sin rastro | `AuditLog` con quién, qué y desde dónde |
| SSRF | El servidor pide una URL que escribió alguien | Lista de dominios permitidos, nada de IP internas, timeouts |

## OWASP API Security Top 10 (2023): las cuatro que más pegan

- **API1, autorización por objeto (BOLA)**: toda ruta con `{id}` verifica que el
  objeto sea de un mundo, alcance y empresa que la persona puede ver (patrón:
  `_barra_o_404`, `_exigir_mundo_de`). Prueba: la agencia pide el id de una
  tarea interna y recibe 404.
- **API3, autorización por propiedad (BOPLA)**: la respuesta trae campos que
  ese rol no debe ver (mails del equipo, `nota_interna`, el análisis de la IA,
  que es solo para Tienda) o el pedido escribe campos que no debería
  (`es_externo`, `permissions`, `is_superuser`, `creado_por_id`). Un schema por
  rol y operación; ante un `**payload.model_dump()`, mirá qué admite el schema.
- **API4, consumo sin límite**: subidas sin tope, listas sin `le=`, IA sin tope
  diario (existe `IA_REVISION_POR_DIA`). Acá pega además en los 500 MB, la
  décima de CPU o la cuenta de la IA.
- **API5, autorización por función (BFLA)**: cada ruta de `/admin` con su
  `require_permission`.

## ASVS: el nivel y los capítulos

El ASVS de OWASP da requisitos verificables en tres niveles; el 2 es el
recomendado para la mayoría de las aplicaciones con datos sensibles. Core
Tienda maneja datos personales del equipo, de las agencias y, en Clientes VIP,
de clientes: **la vara es el nivel 2**. La versión 5.0 (2025) renumeró la
4.0.3: citá el requisito por su texto. En una noche se eligen los capítulos que
se tocan y se escriben de dos a cuatro requisitos concretos en el plan:

- **Autenticación y sesiones**: ¿se crea otra forma de entrar o de seguir
  adentro?
- **Control de acceso**: el checklist de abajo.
- **Validación**: largo máximo, tipos, esquema de URL, nombres de archivo.
- **Errores, logs y datos**: mensajes que no filtran; logs sin secretos;
  `Cache-Control: no-store` y nada en localStorage si es confidencial.
- **Archivos**: tope; tipo por el contenido, no por la extensión; descarga con
  `Content-Disposition: attachment`; nunca con el content-type del cliente.
- **API**: el método correcto, sin escribir con GET, sin campos de más.

## Modelo de amenazas en diez minutos

Las cuatro preguntas de Adam Shostack (*Threat Modeling*, 2014): ¿en qué
estamos trabajando?, ¿qué puede salir mal?, ¿qué vamos a hacer?, ¿lo hicimos
bien? Para la segunda, STRIDE (Loren Kohnfelder y Praerit Garg, Microsoft,
1999):

| Amenaza | En Core Tienda | Control que tiene que estar |
|---|---|---|
| Suplantación | Usar la sesión de otro; falsear `X-Forwarded-For` | Tokens con invalidación; saltos de proxy de confianza |
| Alteración | Cambiar un id o un campo para tocar otro mundo u otra tarea | Chequeo por objeto; schemas cerrados |
| Repudio | «Yo no aprobé eso» | `AuditLog`, `actualizado_por_id`, decisiones con autor |
| Filtración | La agencia ve notas internas o mails; un error delata que algo existe; una clave en el repo | Campos por rol; el mismo 404 para todo; reglas del repo público |
| Denegación de servicio | Subidas grandes, listas sin tope, CPU pesada, saltear el límite | Topes, paginación, límite por persona |
| Elevación de privilegios | Un externo gana un permiso; alguien se edita sus permisos | `puede_tener` y el CHECK; editar permisos, solo admin |

En el campo «Riesgos» del plan van **solo las amenazas que aplican**, cada una
con su control y su prueba.

## Permisos del lado del servidor: el checklist

Saltzer y Schroeder (1975), aplicados: mediación completa (cada acceso se
chequea), negar por defecto (la lista blanca de externos), mínimo privilegio
(un externo, como mucho `calendario.view`) y diseño abierto (la seguridad no
depende de esconder el código: el repo es público).

1. ¿La ruta tiene `Depends(require_permission(...))`? ¿El permiso existe y se
   puede dar desde el panel?
2. ¿Valida el mundo (`exigir_mundo`, `puede_abrir`) si el dato es por mundo?
3. ¿Respeta el alcance (fuera de la ventana, 404)?
4. ¿Qué ve una cuenta externa? Fuera de `RUTAS_DE_EXTERNOS` la puerta ya da
   403; adentro, ¿filtra solo lo suyo?
5. ¿Y un login de sucursal de Redexpres?
6. ¿La respuesta trae algo que ese rol no debe ver? ¿El pedido escribe algo
   que no debería?
7. ¿Hay prueba con base que pida como agencia y como local y espere 403 o 404?
   El modelo: `backend/tests/test_agencia_externa_api.py`.
8. ¿Queda rastro (`AuditLog`) si es una acción sensible o de administración?

## Datos confidenciales

- **Tres clases**: secretos (claves, tokens): nunca en repo, logs ni capturas;
  datos personales (nombres, mails, logins de locales): lo mínimo, y nada de
  más a los externos; datos del negocio (Clientes VIP, campañas que no
  salieron, el calendario que Ivan empezó a cerrar con el alcance): con
  permiso, `no-store` y nunca para externos.
- **Uruguay**: los datos personales de clientes caen bajo la Ley 18.331 de
  Protección de Datos Personales (la controla la URCDP): finalidad, lo mínimo
  necesario, seguridad. Tomás no da consejo legal: un uso nuevo de datos de
  clientes va a Ivan con esa marca.
- **Pruebas**: nunca datos de verdad; Clientes VIP queda vacío en el entorno de
  pruebas (`docs/equipo-nocturno/plataforma/README.md`).
- **IA**: mandarle datos a la API de Claude es mandárselos a un tercero: solo
  lo necesario, y algo nuevo con datos confidenciales va a Ivan.
- **Se guarda según quién lo puede leer**: la memoria de los agentes vive en la
  base y no en el cuaderno, que es público (`models/agente_memoria.py`).

## Secretos con el repo público

- Repo público y claves sin rotar lo decidió Ivan: no se propone. La
  consecuencia es tolerancia cero a secretos en archivos.
- Configuración por variables de entorno (*The Twelve-Factor App*, «Config»).
  Los valores del README y del CI son de mentira a propósito.
- Antes de aprobar, buscá en el diff (y también mails, que no van al repo):

```bash
git diff origin/main...HEAD | grep -nEi \
  "api[_-]?key|secret|token|passw|bearer|PRIVATE KEY|postgres(ql)?(\+asyncpg)?://[^ ]*:[^ ]*@"
```

- GitHub escanea secretos en los repos públicos, pero no alcanza con eso.
- Si encontrás uno expuesto: no lo copies a ningún lado (ni al informe),
  avisale a Ivan una sola vez qué es y dónde está, y seguí.

## Fuentes

- OWASP: Top 10 (2021 y revisión 2025), API Security Top 10 (2023), ASVS (4.0.3 y 5.0), Cheat Sheet Series (Authorization, Password Storage, File Upload, Logging, Mass Assignment, Secrets Management, CSRF Prevention).
- Loren Kohnfelder y Praerit Garg, «The threats to our products», Microsoft (1999), origen de STRIDE.
- Adam Shostack, *Threat Modeling: Designing for Security* (2014).
- J. Saltzer y M. Schroeder, «The Protection of Information in Computer Systems» (1975).
- Uruguay, Ley N.º 18.331 de Protección de Datos Personales (2008).
- Adam Wiggins, *The Twelve-Factor App*.
