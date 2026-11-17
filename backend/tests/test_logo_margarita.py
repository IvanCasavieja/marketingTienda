"""El logo de Tienda Inglesa es la margarita COMPLETA: siete pétalos alrededor
de la "i" (Ivan, 16/11/2026).

Por qué existe: el ícono de la plataforma (la pestaña del navegador) tenía una
margarita con solo cinco pétalos —le faltaban el de la derecha y el de abajo a
la derecha— y no era la primera vez que aparecía. Esta prueba falla si el ícono
vuelve a tener menos pétalos, o si ese dibujo incompleto aparece en otro
archivo del repositorio.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ICONO = RAIZ / "frontend" / "app" / "icon.svg"
AZUL, ROJO = "#0047ba", "#f6323e"

# Los dos pétalos de la izquierda, que el dibujo incompleto tenía sin su espejo.
PETALO_IZQ = "M15.78,40H5.47"
PETALO_ABAJO_IZQ = "M9.29,64.82"


def test_el_icono_es_la_margarita_completa():
    svg = ICONO.read_text(encoding="utf-8").lower()
    assert len(re.findall(rf'fill="{AZUL}"', svg)) == 7, "la margarita lleva 7 pétalos"
    assert len(re.findall(rf'fill="{ROJO}"', svg)) == 2, "y la «i»: el punto y el palito"
    # Los de la derecha son el espejo de los de la izquierda: cada uno, dos veces.
    assert svg.count(PETALO_IZQ.lower()) == 2 and svg.count(PETALO_ABAJO_IZQ.lower()) == 2


def test_la_margarita_incompleta_no_aparece_en_ningun_lado():
    incompletos = []
    for ruta in RAIZ.rglob("*"):
        if not ruta.is_file() or any(p in ruta.parts for p in ("node_modules", ".next", ".git", ".test-build", "venv")):
            continue
        if ruta.suffix.lower() not in {".svg", ".tsx", ".ts", ".html", ".css", ".py", ".json"}:
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # El dibujo incompleto: el pétalo de la izquierda sin su espejo.
        if texto.count(PETALO_IZQ) == 1 and ruta != pathlib.Path(__file__).resolve():
            incompletos.append(str(ruta.relative_to(RAIZ)))
    assert incompletos == [], f"margarita incompleta en: {incompletos}"
