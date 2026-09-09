# Guia de instalacion - Control DJI Osmo Mobile (Windows)

Esta guia explica, paso a paso, como instalar y dejar funcionando este
programa en otra PC con Windows, igual que en la original, incluyendo
el acceso directo en el escritorio.

Requisitos de la PC: Windows 10/11 con Bluetooth (adaptador BLE integrado
o USB).

---

## 1. Pedir acceso al repositorio (si es privado)

El repositorio esta en GitHub como privado:
https://github.com/Kafe074/osmo-pc

Antes de nada, quien lo subio tiene que invitarte como colaborador desde
GitHub: **Settings del repo -> Collaborators -> Add people** y poner tu
usuario de GitHub. Vas a recibir un mail/notificacion para aceptar la
invitacion.

---

## 2. Instalar Git

1. Descargar Git para Windows: https://git-scm.com/download/win
2. Ejecutar el instalador y dejar todas las opciones por defecto
   (siguiente, siguiente, siguiente... Install).
3. Verificar que quedo instalado. Abrir **PowerShell** (buscar
   "PowerShell" en el menu inicio) y escribir:

   ```powershell
   git --version
   ```

   Tiene que mostrar algo como `git version 2.x.x`.

---

## 3. Instalar Python

1. Descargar Python (version 3.11 o superior) desde
   https://www.python.org/downloads/
2. Ejecutar el instalador. **Muy importante:** en la primera pantalla
   marcar la casilla **"Add python.exe to PATH"** antes de instalar.
3. Confirmar la instalacion en PowerShell:

   ```powershell
   py --version
   ```

   Tiene que mostrar algo como `Python 3.12.x`.

---

## 4. Descargar el proyecto (clonar el repositorio)

1. Elegir una carpeta donde vas a tener tus proyectos, por ejemplo
   `Documentos\Proyectos`. En PowerShell:

   ```powershell
   cd "$HOME\Documents"
   mkdir Proyectos -Force
   cd Proyectos
   git clone https://github.com/Kafe074/osmo-pc.git
   cd osmo-pc
   ```

   Esto va a pedir usuario/contrasena o abrir el navegador para loguearte
   en GitHub la primera vez (login normal de GitHub).

Al terminar deberias tener la carpeta:
`C:\Users\<TU_USUARIO>\Documents\Proyectos\osmo-pc`

---

## 5. Instalar las dependencias del proyecto

El proyecto ya trae un script que hace esto automaticamente
(`iniciar_gui.bat`), pero para dejarlo preparado la primera vez podes
hacerlo a mano en PowerShell, parado dentro de la carpeta `osmo-pc`:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea la activacion del entorno virtual con un error de
"ejecucion de scripts deshabilitada", correr una sola vez (como
administrador no hace falta):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

y volver a intentar `.venv\Scripts\Activate.ps1`.

---

## 6. Probar que funciona

Con el entorno activado (paso anterior), desde la carpeta `osmo-pc`:

```powershell
python pc\gui.py
```

Tiene que abrirse la ventana "DJI Osmo Mobile - Control" con el
joystick. Si se abre, esta todo instalado correctamente. Cerrar la
ventana para seguir con el paso del acceso directo.

---

## 7. Emparejar el gimbal por Bluetooth

1. Encender el DJI Osmo Mobile.
2. En Windows, ir a **Configuracion -> Bluetooth y dispositivos ->
   Agregar dispositivo -> Bluetooth**, y esperar a que aparezca un
   dispositivo cuyo nombre empieza con "OM" (por ejemplo "OM 4",
   "OM 5", etc.) y emparejarlo.
3. Una vez emparejado en Windows, abrir el programa (boton
   "Conectar" dentro de la app). La primera vez puede tardar unos
   segundos en encontrarlo.

Nota: no hace falta reemparejar cada vez, solo la primera vez que se usa
en esa PC.

---

## 8. Crear el acceso directo en el escritorio

El proyecto incluye `iniciar_gui.bat`, que crea el entorno virtual (si
no existe), instala las dependencias (si faltan) y abre la app. Sirve
como doble clic o como acceso directo.

1. Abrir el Explorador de Windows y navegar hasta la carpeta del
   proyecto, por ejemplo:
   `C:\Users\<TU_USUARIO>\Documents\Proyectos\osmo-pc`
2. Click derecho sobre `iniciar_gui.bat` -> **Mostrar mas opciones ->
   Enviar a -> Escritorio (crear acceso directo)**.
3. Ir al escritorio, click derecho sobre el acceso directo recien
   creado -> **Cambiar nombre**, y ponerle por ejemplo
   `Control Osmo Mobile`.
4. (Opcional) Para ponerle un icono lindo: click derecho sobre el
   acceso directo -> **Propiedades -> Cambiar icono...** y elegir uno.

A partir de ahora, con doble clic en ese icono del escritorio se abre
la app (la primera vez tarda un poco mas porque instala las
dependencias; las siguientes veces abre directo).

---

## Resumen para el dia a dia

- Encender el gimbal.
- Doble clic en el acceso directo del escritorio.
- Click en "Conectar" dentro de la app.

## Si algo falla

- **"python no se reconoce como comando"**: reinstalar Python marcando
  "Add python.exe to PATH" (paso 3).
- **No encuentra el gimbal**: verificar que este encendido, cerca de la
  PC, y que ya fue emparejado por Bluetooth en Windows (paso 7).
- **Error al activar el entorno virtual en PowerShell**: correr
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (paso 5).
- **Quiero actualizar el proyecto cuando haya cambios nuevos**: abrir
  PowerShell dentro de la carpeta `osmo-pc` y correr `git pull`.
