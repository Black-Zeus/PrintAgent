# Guía de instalación — GestionCom Print Agent

## Requisitos previos

- Windows 10 o superior (64-bit)
- Python 3.11 o superior → [python.org/downloads](https://www.python.org/downloads/)
  - Marcar **"Add Python to PATH"** durante la instalación
- Impresora térmica con driver instalado en Windows (USB, red o Bluetooth)
- Acceso a la red donde corre el servidor GestionCom
- Clave de autorización del punto de venta (generada desde el sistema, formato `XXXX-XXXX-XXXX-XXXX`)

---

## Opción A — Instalación rápida con script (recomendada)

1. Copia la carpeta `PrintAgent` en el equipo donde está la impresora (ej. `C:\GestionCom\PrintAgent`).

2. Abre una terminal **como Administrador** (`cmd` o PowerShell → botón derecho → "Ejecutar como administrador").

3. Navega a la carpeta:
   ```bat
   cd C:\GestionCom\PrintAgent
   ```

4. Ejecuta el instalador:
   ```bat
   install.bat
   ```

   El script realiza automáticamente:
   - Verifica que Python esté instalado
   - Instala las dependencias (`pip install -r requirements.txt`)
   - Crea `config.json` con valores por defecto
   - Instala el servicio Windows `GestionComPrintAgent`

5. Una vez instalado, el portal se abre en el navegador en `http://localhost:8765/config`. Completa la configuración (ver sección **Configuración inicial** más abajo).

---

## Opción B — Instalación manual paso a paso

### 1. Instalar dependencias

```bat
cd C:\GestionCom\PrintAgent
pip install -r requirements.txt
```

### 2. Registrar pywin32 (necesario para el servicio Windows)

```bat
python -m pywin32_postinstall -install
```

Si el comando no existe, prueba:
```bat
python "%WINDIR%\system32\pythoncom*.dll"
```

### 3. Instalar el servicio Windows

Abre una terminal **como Administrador** y ejecuta:

```bat
python agent.py install
```

Deberías ver: `Installed service GestionComPrintAgent`

---

## Configuración inicial

Después de instalar, abre el portal de configuración:

```bat
python agent.py config
```

O navega manualmente a `http://localhost:8765/config`.

Completa los campos:

| Campo | Valor de ejemplo |
|-------|-----------------|
| URL del servidor | `http://192.168.1.100` o `https://gestion.miempresa.cl` |
| Clave de autorización | `A1B2-C3D4-E5F6-G7H8` (obtenida desde el sistema en *Puntos de venta → Generar clave*) |
| Impresora | Selecciona de la lista o usa `auto` para detección automática |
| Puerto del portal | `8765` (no cambiar salvo conflicto) |
| Intervalo de polling | `2` segundos (recomendado) |

Guarda y vuelve al dashboard `/` para verificar que el agente muestra:
- **Servidor:** Conectado ✓
- **Impresora:** Disponible ✓

---

## Iniciar el agente

### Como servicio Windows (producción)

```bat
python agent.py start
```

El servicio arranca automáticamente con Windows. Para verificar:

```bat
python agent.py status
```

También visible en el panel de Servicios de Windows (`services.msc`) como **GestionCom Print Agent**.

### En primer plano (pruebas / desarrollo)

```bat
python agent.py run
```

El log aparece en la consola. Detener con `Ctrl+C`.

---

## Prueba de impresión

Desde el dashboard (`http://localhost:8765`) pulsa el botón **"Imprimir ticket de prueba"**. El ticket de prueba muestra la configuración actual del agente.

También puedes generar un ticket de prueba desde el sistema GestionCom en *Templates de impresión*.

---

## Actualizar el agente

1. Detén el servicio:
   ```bat
   python agent.py stop
   ```

2. Reemplaza los archivos `.py` con la nueva versión (no sobreescribas `config.json` ni `template_cache.json`).

3. Actualiza dependencias si es necesario:
   ```bat
   pip install -r requirements.txt --upgrade
   ```

4. Inicia el servicio:
   ```bat
   python agent.py start
   ```

---

## Desinstalar

```bat
python agent.py stop
python agent.py remove
```

Esto detiene y elimina el servicio Windows. Los archivos de configuración y log quedan en la carpeta; elimínalos manualmente si no son necesarios.

---

## Solución de problemas

### El portal no abre en el navegador

Verifica que el agente esté corriendo:
```bat
python agent.py status
```
O ejecuta en primer plano para ver el log en tiempo real:
```bat
python agent.py run
```

### "No se pudo abrir impresora"

- Verifica que la impresora esté encendida y aparezca en el Panel de Control → Dispositivos e impresoras.
- Prueba imprimir una página de prueba desde Windows.
- En el portal, selecciona la impresora por nombre exacto en lugar de `auto`.

### "Sin conexión al servidor"

- Verifica que la URL del servidor no tenga barra al final.
- Verifica acceso de red: `ping <ip-del-servidor>`.
- Verifica que el servidor GestionCom esté corriendo.
- Si el servidor usa HTTPS con certificado autofirmado, configura la URL con `http://` o agrega el certificado como confiable en Windows.

### "Access denied" al instalar el servicio

Abre la terminal **como Administrador** y vuelve a ejecutar `python agent.py install`.

### El servicio no arranca automáticamente tras reinicio

En el panel de Servicios (`services.msc`), busca **GestionCom Print Agent** y verifica que el tipo de inicio sea **Automático**.

---

## Log del agente

El log se encuentra en:
```
C:\GestionCom\PrintAgent\logs\agent.log
```

Para cambiar el nivel de detalle, edita `config.json` y cambia `log_level` a `DEBUG`.

---

## Puertos utilizados

| Puerto | Descripción |
|--------|-------------|
| 8765 | Portal web local (configurable) |

El agente solo realiza conexiones salientes hacia el servidor GestionCom. No requiere puertos de entrada abiertos en el firewall.
