# Guia de instalacion - Control DJI Osmo Mobile (Windows)



## 1. Instalar Git

## 2. Instalar Python

1. Descargar Python (version 3.11 o superior)

## 3. clonar el repositorio)



## 4. Instalar las dependencias del proyecto

El proyecto ya trae un script que hace esto automaticamente
(`iniciar_gui.bat`), pero para dejarlo preparado la primera vez podes
hacerlo a mano en PowerShell, parado dentro de la carpeta `osmo-pc`:


usa este comando

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea la activacion, correr una sola vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

y volver a intentar `.venv\Scripts\Activate.ps1`.

---

## 5. Probar que funciona

Desde la carpeta `osmo-pc`:

```powershell
python pc\gui.py
```
---

## 6. Emparejar el tripode por Bluetooth

1. Encender el tripode.
2. En Windows, ir a **Configuracion -> Bluetooth y dispositivos ->
   Agregar dispositivo -> Bluetooth**, y esperar a que aparezca un
   dispositivo el nombre es "Osmo mobile" o similar y emparejarlo.
3. Una vez emparejado en Windows, abrir el programa (boton
   "Conectar" dentro de la app). La primera vez puede tardar unos
   segundos en encontrarlo.

Nota: no hace falta reemparejar cada vez, solo la primera vez que se usa
en esa PC.

---

## 7. Crear el acceso directo en el escritorio

El proyecto incluye `iniciar_gui.bat`, que crea el entorno virtual (si
no existe), instala las dependencias (si faltan) y abre la app. Sirve
como doble clic o como acceso directo.

1. Abrir el Explorador de Windows y navegar hasta la carpeta del
   proyecto, por ejemplo:
   `C:\Users\<TU_USUARIO>\Documents\Proyectos\osmo-pc`
2. Click derecho sobre `iniciar_gui.bat` -> **Mostrar mas opciones ->
   Enviar a -> Escritorio (crear acceso directo)**.
3. Ir al escritorio, click derecho sobre el acceso directo recien
   creado -> **Cambiar nombre**.

---

## Si algo falla

- **"python no se reconoce como comando"**: reinstalar Python marcando
  "Add python.exe to PATH" (paso 3).
- **No encuentra el gimbal**: verificar que este encendido, cerca de la
  PC, y que ya fue emparejado por Bluetooth en Windows (paso 7).
- **Error al activar el entorno virtual en PowerShell**: correr
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (paso 5).
- **Quiero actualizar el proyecto cuando haya cambios nuevos**: abrir
  PowerShell dentro de la carpeta `osmo-pc` y correr `git pull`.
