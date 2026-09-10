FROM python:3.11-slim

WORKDIR /app

# Sin esto los logs quedan en el buffer de Python y no salen por stdout hasta
# que se llena: en un contenedor eso se ve como un servicio mudo, y es lo
# primero que se mira cuando algo no arranca.
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

# Solo uvicorn. Las migraciones las corre la app sola al arrancar, en segundo
# plano (ver el lifespan de app/main.py), y NO se repiten acá.
#
# Hasta el 10/09/2026 este CMD era "alembic upgrade head && uvicorn ...", y eso
# era un agujero, no una redundancia: la versión de la app está detrás de
# settings.corre_mantenimiento, que existe porque el backend/.env de CUALQUIER
# máquina apunta a la base de PRODUCCIÓN. Un `docker run` con ese .env corría
# migraciones contra producción sin preguntar nada, salteándose el único freno
# que hay. Y en un servidor que sí tuviera que migrar, las corría dos veces.
#
# En un servidor propio (sin Render, o sea sin RENDER_GIT_COMMIT) el freno
# queda cerrado y las migraciones NO corren. Para que corran hay que pedirlo
# explícitamente con MANTENIMIENTO_AL_ARRANCAR=true, que además habilita la
# purga de archivos y los seis procesos periódicos. Es a propósito que haya que
# escribirlo: así ninguna copia del backend toca datos de producción por
# accidente, y la que sí tiene que hacerlo lo declara.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
