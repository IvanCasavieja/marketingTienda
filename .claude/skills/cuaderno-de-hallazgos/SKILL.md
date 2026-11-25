---
name: cuaderno-de-hallazgos
description: La memoria del Equipo nocturno de Core Tienda — un cuaderno con todo lo que se encontró recorriendo la plataforma (con número, gravedad, captura y estado), que vive en la rama `equipo-nocturno/cuaderno` y se actualiza cada noche. Usalo para leer qué ya se sabe antes de recorrer, anotar hallazgos nuevos, marcar lo que se arregló o se descartó, y publicar las capturas que van en el informe a Ivan.
---

# Cuaderno de hallazgos

Sin memoria, cada noche redescubre lo mismo y propone lo primero que ve. El
cuaderno es el **backlog** del equipo: todo lo que una persona notaría
recorriendo Core Tienda, con su prueba, para elegir cada noche lo que más
vale la pena y no repetir lo descartado.

## Dónde vive

Rama **`equipo-nocturno/cuaderno`** (no es `main`: se escribe directo, sin
PR; GitHub no le corre pruebas ni Vercel la publica). Adentro:

```
cuaderno/CUADERNO.md                       el backlog (abajo, el formato)
cuaderno/historial.md                      una línea por noche
cuaderno/recorridos/AAAA-MM-DD/resumen.md  el resumen del barrido automático de esa noche
cuaderno/recorridos/AAAA-MM-DD/*.jpg       las capturas de evidencia (y antes/después)
```

Ivan lo puede leer en GitHub:
`https://github.com/<dueño>/<repo>/blob/equipo-nocturno/cuaderno/cuaderno/CUADERNO.md`.

## Traerlo al empezar la noche

```bash
git fetch origin equipo-nocturno/cuaderno 2>/dev/null
if git rev-parse -q --verify origin/equipo-nocturno/cuaderno >/dev/null; then
  git worktree add -q $S/cuaderno -B equipo-nocturno/cuaderno origin/equipo-nocturno/cuaderno
else   # la primera noche: se crea vacío
  git worktree add -q $S/cuaderno -b equipo-nocturno/cuaderno origin/main
  mkdir -p $S/cuaderno/cuaderno/recorridos
  cp .claude/skills/cuaderno-de-hallazgos/plantilla.md $S/cuaderno/cuaderno/CUADERNO.md
  echo "# Historial del Equipo nocturno" > $S/cuaderno/cuaderno/historial.md
fi
```

`$S/cuaderno/cuaderno/CUADERNO.md` es lo que se lee y se edita.

## Qué se hace con él cada noche

1. **Antes de recorrer (Sofía):** leer el cuaderno. Así el recorrido busca
   también si lo anotado **sigue pasando** y no pierde tiempo en lo
   descartado.
2. **Poner al día lo de noches anteriores:**
   - «En curso» cuyo PR ya está en `main` (`git log origin/main --oneline`
     o el PR mergeado) → pasa a **Hechos** con la fecha.
   - «En curso» cuyo PR se cerró sin mergear (Ivan dijo no) → **Descartados**
     con «Ivan dijo no (fecha)». No se vuelve a proponer nunca.
   - Abiertos que el recorrido ya no encuentra → **Hechos** con «ya no pasa
     (fecha)».
3. **Anotar lo nuevo** con el formato de abajo. Antes de anotar, buscá si ya
   está (por pantalla y por lo que le pasa a la persona): si está, sumá la
   fecha en «Visto» y, si hay, la captura nueva. Nada de duplicados.
4. **Ordenar Abiertos** por prioridad: gravedad × cuánta gente × cuán
   seguido ÷ esfuerzo (ver los criterios del skill `recorrido-humano`).
5. **Lo elegido para esta noche** pasa a **En curso** con el nombre de la
   rama.
6. **Historial:** una línea: fecha, pantallas recorridas, hallazgos nuevos,
   qué se hizo.
7. **Subir** (siempre, haya o no código esa noche):

```bash
cd $S/cuaderno
git add cuaderno
git commit -qm "Cuaderno: noche AAAA-MM-DD (N nuevos, M hechos)"
git push -q origin equipo-nocturno/cuaderno
```

El mensaje **nunca** empieza con `[Nocturno]` (eso dispara el mail del
informe). Si el push falla, contalo en el informe y seguí: el cuaderno es
importante pero no frena la noche.

## El formato de cada hallazgo

```markdown
### H-012 · <Título en criollo: lo que le pasa a la persona>
- **Gravedad:** 🟠 Traba · **Quién:** agencia · **Dónde:** Tablero `/entregas`, celular claro
- **Qué ve una persona:** <sin código>
- **Por qué importa:** <qué le cuesta>
- **Cómo repetirlo:** <pasos, cuenta y datos>
- **Evidencia:** ![H-012](recorridos/2026-11-25/H-012.jpg) <y la medida automática, si hay>
- **Idea de arreglo:** <una línea, opcional>
- **Visto:** 25/11 · 26/11
```

- El número es correlativo y no se reusa: el siguiente al más alto del
  cuaderno.
- Al pasar a Hechos o Descartados se mueve el bloque entero y se le agrega
  una línea **Estado:** con la fecha, el PR o el motivo.

## Las capturas

Usá `scripts/evidencia.py` para que no pesen y para marcar el problema:

```bash
E=.claude/skills/cuaderno-de-hallazgos/scripts/evidencia.py
D=$S/cuaderno/cuaderno/recorridos/$(TZ=America/Montevideo date +%F)
python $E $S/capturas/012-agencia-tablero.png --salida $D/H-012.jpg --marco 40,300,310,60
python $E $S/capturas/antes.png $S/capturas/despues.png --salida $D/H-012-antes-despues.jpg
cp $S/recorrido/resumen.md $D/resumen.md
```

Máximo ~15 capturas por noche: solo evidencia de hallazgos y el antes/después
de la mejora. El barrido completo NO se sube (son cientos de imágenes).

## Las capturas en el informe a Ivan

El repo es público, así que una imagen subida a la rama del cuaderno se puede
mostrar en el informe (el mail y el issue la muestran). La dirección es:

```
https://raw.githubusercontent.com/<dueño>/<repo>/equipo-nocturno/cuaderno/cuaderno/recorridos/AAAA-MM-DD/H-012.jpg
```

`<dueño>/<repo>` sale de `git remote get-url origin` (las dos últimas partes;
hoy `IvanCasaviejaTI/marketingTienda`). Clara las pone en el informe como
`![Antes y después](esa-dirección)`. Por eso el cuaderno se sube **antes**
del commit del informe.
