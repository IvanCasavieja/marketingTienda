# setup_tarea_programada.ps1
# Configura Windows Task Scheduler para correr el scan diariamente.
# Ejecutar UNA SOLA VEZ como administrador:
#   Right-click → "Run as Administrator"
#   o desde PowerShell: .\setup_tarea_programada.ps1

param(
    [string]$Hora   = "02:00",   # Hora del scan diario (formato HH:mm, horario Uruguay)
    [string]$Tipo   = "parallel",  # parallel | full | gdu | tata | farmashop
    [switch]$Borrar              # Pasar -Borrar para eliminar la tarea
)

$NOMBRE_TAREA  = "MKTG-Scraper-Precios"
$BACKEND_DIR   = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON        = (Get-Command python -ErrorAction SilentlyContinue).Source
$SCRIPT        = Join-Path $BACKEND_DIR "run_scan.py"
$LOG_DIR       = Join-Path $BACKEND_DIR "..\logs"
$LOG_FILE      = Join-Path $LOG_DIR "scraper_scheduler.log"

# ── Borrar tarea existente ────────────────────────────────────────────────────
if ($Borrar) {
    Unregister-ScheduledTask -TaskName $NOMBRE_TAREA -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] Tarea '$NOMBRE_TAREA' eliminada." -ForegroundColor Green
    exit 0
}

# ── Validaciones ──────────────────────────────────────────────────────────────
if (-not $PYTHON) {
    Write-Host "[ERROR] Python no encontrado en PATH." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $SCRIPT)) {
    Write-Host "[ERROR] No se encontro run_scan.py en $BACKEND_DIR" -ForegroundColor Red
    exit 1
}

# Crear carpeta de logs si no existe
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

# ── Configurar tarea ──────────────────────────────────────────────────────────
$accion = New-ScheduledTaskAction `
    -Execute $PYTHON `
    -Argument "run_scan.py $Tipo >> `"$LOG_FILE`" 2>&1" `
    -WorkingDirectory $BACKEND_DIR

$trigger = New-ScheduledTaskTrigger -Daily -At $Hora

$config = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Highest

# Borrar si ya existía
Unregister-ScheduledTask -TaskName $NOMBRE_TAREA -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName   $NOMBRE_TAREA `
    -Action     $accion `
    -Trigger    $trigger `
    -Settings   $config `
    -Principal  $principal `
    -Description "MKTG Platform — scan diario de precios de supermercados" | Out-Null

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "   Tarea programada configurada exitosamente!" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Nombre:   $NOMBRE_TAREA"
Write-Host "  Hora:     $Hora (diario)"
Write-Host "  Tipo:     $Tipo"
Write-Host "  Script:   $SCRIPT"
Write-Host "  Logs:     $LOG_FILE"
Write-Host ""
Write-Host "  Para cambiar la hora:" -ForegroundColor Yellow
Write-Host "    .\setup_tarea_programada.ps1 -Hora 03:00 -Tipo parallel"
Write-Host ""
Write-Host "  Para eliminar la tarea:" -ForegroundColor Yellow
Write-Host "    .\setup_tarea_programada.ps1 -Borrar"
Write-Host ""
Write-Host "  Para correr ahora mismo (sin esperar):" -ForegroundColor Yellow
Write-Host "    Start-ScheduledTask -TaskName '$NOMBRE_TAREA'"
Write-Host ""
