@echo off
setlocal

echo ============================================================
echo   CeciChic Print Agent - Instalador
echo ============================================================
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.11+ desde python.org
    pause
    exit /b 1
)

echo [1/4] Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

echo.
echo [2/4] Configurando registro de pywin32...
python -c "import win32serviceutil" >nul 2>&1
if errorlevel 1 (
    echo [WARN] pywin32 no disponible. El servicio Windows no estara disponible.
    echo        Puedes ejecutar en foreground con: python agent.py run
) else (
    python "%WINDIR%\system32\pythoncom*.dll" >nul 2>&1
    python -m pip install pywin32 --upgrade >nul 2>&1
)

echo.
echo [3/4] Creando configuracion inicial...
if not exist config.json (
    python -c "import config_manager; config_manager.load()"
    echo    config.json creado con valores por defecto.
) else (
    echo    config.json ya existe, no se sobreescribe.
)

echo.
echo [4/4] Instalando servicio Windows (requiere administrador)...
python agent.py install
if errorlevel 1 (
    echo [WARN] No se pudo instalar como servicio. Ejecuta como Administrador.
    echo        Puedes usar: python agent.py run   para ejecutar en foreground.
) else (
    echo    Servicio instalado: CeciChicPrintAgent
    echo    Para iniciar: python agent.py start
    echo    O desde Servicios de Windows.
)

echo.
echo ============================================================
echo   Instalacion completada.
echo.
echo   Proximos pasos:
echo   1. Abre http://localhost:8765 para configurar el agente
echo   2. Ingresa la URL del servidor y la clave de autorizacion
echo   3. Selecciona la impresora y haz una prueba de impresion
echo.
echo   Para ejecutar en primer plano (pruebas):
echo     python agent.py run
echo ============================================================
pause
