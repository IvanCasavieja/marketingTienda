@echo off
title MKTG Platform — Scraper de Precios
color 0A
echo.
echo  ============================================================
echo   MKTG Platform — Scraper de Precios Supermercados Uruguay
echo  ============================================================
echo.

:: Cambiar al directorio del script
cd /d "%~dp0"

:: Verificar que existe .env
if not exist ".env" (
    echo  [ERROR] No se encontro el archivo .env
    echo  Copiá backend/.env.scraper a backend/.env y completá los valores.
    pause
    exit /b 1
)

:: Mostrar menu
echo  Que scan querés correr?
echo.
echo   [1] PARALLEL — Tata + Farmashop + GDU en paralelo  (RECOMENDADO, ~2h15min)
echo   [2] FULL     — Tata + Farmashop + GDU secuencial   (~3h)
echo   [3] GDU      — Geant + Disco + Devoto              (~2h)
echo   [4] TATA     — Solo Ta-Ta                          (~30min)
echo   [5] FARMASHOP — Solo Farmashop                     (~15min)
echo.
set /p OPCION="  Elegí una opción (1-5, o Enter para PARALLEL): "

if "%OPCION%"=="" set TIPO=parallel
if "%OPCION%"=="1" set TIPO=parallel
if "%OPCION%"=="2" set TIPO=full
if "%OPCION%"=="3" set TIPO=gdu
if "%OPCION%"=="4" set TIPO=tata
if "%OPCION%"=="5" set TIPO=farmashop

if not defined TIPO (
    echo  [ERROR] Opcion invalida.
    pause
    exit /b 1
)

echo.
echo  Iniciando scan: %TIPO%
echo  (Podés cerrar esta ventana — el proceso sigue corriendo)
echo.

python run_scan.py %TIPO%

echo.
if %ERRORLEVEL%==0 (
    echo  [OK] Scan completado exitosamente!
) else (
    echo  [ERROR] El scan terminó con errores. Revisá el log de arriba.
)
echo.
pause
