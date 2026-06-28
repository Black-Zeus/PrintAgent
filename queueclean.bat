@echo off
:: Requiere ejecutar como Administrador
echo.
echo ========================================
echo  Limpieza de cola local de impresion
echo ========================================
echo.

net stop spooler
if errorlevel 1 (
    echo [ERROR] No se pudo detener el spooler.
    echo         Ejecuta este archivo como Administrador.
    pause
    exit /b 1
)

echo.
echo Eliminando trabajos atascados...
del /Q /F "%SystemRoot%\System32\spool\PRINTERS\*.*" 2>nul
echo Hecho.

echo.
net start spooler

echo.
echo ========================================
echo  Cola limpia. Listo para imprimir.
echo ========================================
echo.
pause

:: 
:: C:\Windows\System32\net.exe stop spooler
:: del /Q /F "%SystemRoot%\System32\spool\PRINTERS\*.*" 2>nul
:: C:\Windows\System32\net.exe start spooler