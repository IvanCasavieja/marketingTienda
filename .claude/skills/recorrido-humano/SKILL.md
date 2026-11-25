---
name: recorrido-humano
description: Recorrer Core Tienda como una persona de verdad (el equipo de promo y marca, una agencia externa, un local de Redexpres) con un navegador manejable paso a paso, capturas en notebook y celular, un barrido automático de todas las pantallas y una prueba a ciegas; y juzgar cada pantalla por lo que se VE, no por el código. Usalo para el recorrido de cada noche, para probar una mejora en la pantalla y para sacar capturas de antes y después.
---

# Recorrido humano

El equipo nocturno puede leer el HTML, los IDs y las clases. La gente que usa
Core Tienda no: ve la pantalla y nada más. Este skill sirve para que el
recorrido sea el de una persona: **usá el código para moverte, la captura para
juzgar** (ver [criterios.md](criterios.md)).

## Las tres capas del recorrido

1. **Barrido automático** (`scripts/recorrido_completo.py`, unos minutos):
   todas las pantallas × las tres cuentas × notebook/celular/oscuro. Deja
   capturas, hojas de contacto (9 pantallas por imagen), medidas automáticas
   y la lista de a qué pantallas llegó cada cuenta (si la agencia o el local
   entran a algo interno, sale en 🔴). Es la red para no perderse ningún
   rincón.
2. **Tareas reales** con el navegador paso a paso (`scripts/navegador.py`):
   hacer el trabajo de cada persona de punta a punta ([tareas.md](tareas.md):
   el ciclo pedido → entrega → corrección → aprobación todas las noches, y una
   zona a fondo según el día).
3. **Prueba a ciegas** (agente `martina-usuaria`): una usuaria que solo ve
   capturas y toca por coordenadas intenta 2 tareas sin que nadie le diga
   dónde está nada.

Conviene correr el barrido **después** de las tareas reales: así las
pantallas tienen datos y no solo estados vacíos (corré los dos si hay tiempo:
vacío primero, con datos después).

## Preparar

Con la plataforma andando (README del equipo, *La plataforma andando*) y las
dependencias:

```bash
pip install -q playwright pillow && python -m playwright install --with-deps chromium
K=.claude/skills/recorrido-humano/scripts
export NAVEGADOR_CAPTURAS=$S/capturas          # $S = tu scratchpad
```

## El navegador paso a paso

Queda abierto entre comandos (lo arranca solo el primer comando). Cada pestaña
es una persona y una vista:

```bash
python $K/navegador.py abrir equipo                          # notebook 1366x768, claro
python $K/navegador.py entrar equipo-nocturno@example.com "$CLAVE_EQUIPO_NOCTURNO" --mundo "Tienda Inglesa"
python $K/navegador.py ver calendario                        # -> ruta de la captura: miralá con Read
python $K/navegador.py click "Nueva acción"                  # por lo que se LEE
python $K/navegador.py escribir "Nombre" "Ciberlunes"
python $K/navegador.py click "Crear" --exacto
python $K/navegador.py medidas                               # desborde, letra chica, contraste
python $K/navegador.py errores                               # consola y pedidos fallidos
python $K/navegador.py abrir equipo-cel --celular --como equipo   # misma sesión, en el celular
python $K/navegador.py abrir agencia --celular
python $K/navegador.py entrar agencia-de-prueba@example.com "$CLAVE_AGENCIA_DE_PRUEBA"
python $K/navegador.py cerrar                                # al terminar
```

`python $K/navegador.py ayuda` lista todo (`subir`, `arrastrar`, `rueda`,
`tecla`, `elegir`, `pasar`, `click-xy`...). Reglas:

- **Después de cada paso importante, `ver` y mirá la captura con Read.** Es lo
  único que cuenta como «lo que ve una persona».
- Si `click "X"` no encuentra X por su texto, no lo fuerces con selectores:
  anotá que una persona no lo encuentra (o que solo hay un ícono) y seguí
  con `elementos` para destrabarte.
- `js` es solo para preparar datos o destrabar, nunca para juzgar.
- No hay mails de verdad ni IA de verdad: la IA está simulada (juzgá la
  pantalla y el flujo, no la respuesta).
- El login acepta 10 intentos por minuto: entrá una vez por cuenta y usá
  `--como` para abrir más pestañas con la misma sesión.

Para las entregas, generá piezas de mentira con la medida escrita:

```bash
python $K/imagenes_de_prueba.py --salida $S/piezas 1920x400 1080x1080 --zip
python $K/navegador.py subir $S/piezas/pieza-1920x400.png $S/piezas/pieza-1080x1080.png
```

## El barrido automático

```bash
python $K/recorrido_completo.py \
  --cuenta equipo=equipo-nocturno@example.com:"$CLAVE_EQUIPO_NOCTURNO" \
  --cuenta agencia=agencia-de-prueba@example.com:"$CLAVE_AGENCIA_DE_PRUEBA" \
  --cuenta local=local-de-prueba@example.com:"$CLAVE_LOCAL_DE_PRUEBA" \
  --mundo "Tienda Inglesa" --salida $S/recorrido
```

Leé `$S/recorrido/resumen.md` (alertas ordenadas por gravedad y tabla por
pantalla) y **mirá las hojas de contacto** (`$S/recorrido/hojas/*.jpg`) con
Read: en pocas imágenes ves todas las pantallas de una cuenta y una vista.
Abrí la captura grande de lo que te llame la atención. Opciones:
`--vistas notebook-claro,celular-claro,notebook-oscuro,celular-oscuro` y
`--rutas /calendario,/entregas` para repetir solo algunas (por ejemplo,
antes y después de una mejora).

El barrido sabe a qué pantallas puede llegar la agencia y el local
(`PERMITIDAS` en el script). Si una pantalla nueva es para ellos, sumala ahí
en el mismo PR.

## Qué se entrega

Los hallazgos van al cuaderno (skill `cuaderno-de-hallazgos`) con el formato
de [criterios.md](criterios.md): lo que ve una persona, por qué importa, cómo
repetirlo, la captura y la gravedad.
