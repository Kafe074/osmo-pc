import argparse
import asyncio
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from gimbal import (
    Gimbal,
    find_gimbal_address,
    load_last_address,
    remove_registered_gimbals,
    save_last_address,
)

MAX_SPEED = 1500
DEAD_ZONE = 22
TICK_MS = 100

MODE_NAMES = {0: "PTF", 1: "FPV", 2: "SpinShot", 3: "PF"}


class GimbalBridge:
    def __init__(self, addr=None):
        self.addr = addr
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self.gimbal = None
        self.last_error = None
        self.connected = False
        self.link_lost = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def _submit(self, coro, on_error=True):
        self._ready.wait()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if on_error:
            def _check(done):
                try:
                    done.result()
                except Exception as e:
                    self.last_error = str(e)
            fut.add_done_callback(_check)
        return fut

    def connect(self, on_ok, on_fail):
        def cb(res):
            ok, addr, name, err = res
            if ok:
                on_ok(addr, name)
            else:
                on_fail(err)
        self._submit(self._connect()).add_done_callback(
            lambda fut: cb(fut.result()))

    async def _connect(self):
        try:
            if not self.addr:
                last_addr, _ = load_last_address()
                found = await find_gimbal_address(
                    retries=3, timeout=10, last_address=last_addr)
                if not found:
                    return False, None, None, "No se encontro el gimbal"
                self.addr, name = found
            else:
                name = self.addr
            await asyncio.to_thread(remove_registered_gimbals)
            g = Gimbal(self.addr, on_disconnect=self._on_link_lost)
            await g.connect()
            self.gimbal = g
            self.connected = True
            save_last_address(self.addr, name)
            return True, self.addr, name, None
        except Exception as e:
            return False, None, None, str(e)

    def _on_link_lost(self):
        # Called from the bridge's own asyncio thread by bleak's
        # disconnected_callback; just flip flags here and let the Tk
        # mainloop (_tick, polling on the UI thread) react safely.
        self.connected = False
        self.link_lost = True

    def move(self, yaw, pitch):
        if self.gimbal is not None and self.connected:
            self._submit(self.gimbal.rotate(
                yaw=yaw, pitch=pitch, roll=0, time=50,
                mode=self.gimbal.RotationMode.SPEED))

    def stop(self):
        if self.gimbal is not None and self.connected:
            self._submit(self.gimbal.stop())

    def center(self):
        if self.gimbal is not None and self.connected:
            self._submit(self.gimbal.center())

    def set_mode(self, mode):
        if self.gimbal is not None and self.connected:
            self._submit(self.gimbal.set_mode(mode))

    def disconnect(self):
        if self.gimbal is not None:
            self._submit(self.gimbal.disconnect())
            self.gimbal = None
            self.connected = False

    def telemetry(self):
        if self.gimbal is None:
            return None
        return (self.gimbal.position, self.gimbal.battery_level,
                self.gimbal.is_charging)


class App:
    def __init__(self, root, addr=None):
        self.root = root
        self.root.title("DJI Osmo Mobile - Control")
        self.root.geometry("520x590")
        self.root.resizable(False, False)

        self.bridge = GimbalBridge(addr)
        self.bridge.start()
        self.joy_active = False
        self.joy_vec = (0, 0)
        self.connected = False
        self._joy_moving = False

        self._build_widgets()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(TICK_MS, self._tick)

    def _build_widgets(self):
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(top, text="Joystick: arrastra dentro del circulo para mover")\
            .pack(anchor=tk.W)

        controls = tk.Frame(top)
        controls.pack(fill=tk.X, pady=4)
        self.btn_conn = tk.Button(controls, text="Conectar", command=self._connect,
                                  width=12)
        self.btn_conn.pack(side=tk.LEFT)
        self.btn_stop = tk.Button(controls, text="Detener", command=self._stop,
                                  width=12, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=6)
        self.btn_center = tk.Button(controls, text="Centrar", command=self._center,
                                    width=12, state=tk.DISABLED)
        self.btn_center.pack(side=tk.LEFT, padx=6)
        self.lbl_addr = tk.Label(controls, text="", fg="#444")
        self.lbl_addr.pack(side=tk.RIGHT)

        self.joy = tk.Canvas(self.root, width=300, height=300, bg="#1e1e2e",
                             highlightthickness=2, highlightbackground="#333")
        self.joy.pack(pady=10)
        self.cx = self.cy = 150
        self.radius = 120
        self.joy.create_oval(self.cx - self.radius, self.cy - self.radius,
                             self.cx + self.radius, self.cy + self.radius,
                             outline="#666", width=2)
        self.joy.create_oval(self.cx - self.radius, self.cy - self.radius,
                             self.cx + self.radius, self.cy + self.radius,
                             outline="#666", dash=(4, 4), width=1)
        self.joy.create_oval(self.cx - DEAD_ZONE, self.cy - DEAD_ZONE,
                             self.cx + DEAD_ZONE, self.cy + DEAD_ZONE,
                             outline="#555")
        self.joy.create_line(self.cx - self.radius, self.cy, self.cx + self.radius,
                             self.cy, fill="#333")
        self.joy.create_line(self.cx, self.cy - self.radius, self.cx, self.cy + self.radius,
                             fill="#333")
        self.joy.create_oval(self.cx - 10, self.cy - 10, self.cx + 10, self.cy + 10,
                             fill="#7aa2f7", outline="")
        self.joy.bind("<Button-1>", self._joy_press)
        self.joy.bind("<B1-Motion>", self._joy_drag)
        self.joy.bind("<ButtonRelease-1>", self._joy_release)

        info = tk.Frame(self.root)
        info.pack(fill=tk.X, padx=10)
        tk.Label(info, text="Telemetria", font=("TkDefaultFont", 10, "bold"))\
            .pack(anchor=tk.W)
        grid = tk.Frame(info)
        grid.pack(anchor=tk.W, pady=2)
        self.lbl_pos = tk.Label(grid, text="Posicion: --  --")
        self.lbl_pos.grid(row=0, column=0, sticky=tk.W)
        self.lbl_bat = tk.Label(grid, text="Bateria: --")
        self.lbl_bat.grid(row=0, column=1, padx=16, sticky=tk.W)

        modes = tk.Frame(self.root)
        modes.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(modes, text="Modo gimbal:", font=("TkDefaultFont", 10, "bold"))\
            .pack(anchor=tk.W)
        self.mode_var = tk.IntVar(value=0)
        self.mode_buttons = []
        for val in (0, 1, 2, 3):
            btn = tk.Radiobutton(modes, text=MODE_NAMES[val], value=val,
                                 variable=self.mode_var,
                                 command=lambda v=val: self._set_mode(v),
                                 state=tk.DISABLED)
            btn.pack(side=tk.LEFT, padx=4)
            self.mode_buttons.append(btn)

        self.status = tk.Label(self.root, text="Desconectado", anchor=tk.W,
                               relief=tk.SUNKEN, bd=1)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    def _connect(self):
        if self.connected:
            return
        self.btn_conn.config(state=tk.DISABLED, text="Buscando...")
        self.status.config(text="Buscando gimbal (enciendelo)...")
        self.bridge.connect(self._on_connected, self._on_connect_fail)

    def _on_connected(self, addr, name):
        def apply():
            self.connected = True
            self.btn_conn.config(state=tk.DISABLED, text="Conectado")
            self.btn_stop.config(state=tk.NORMAL)
            self.btn_center.config(state=tk.NORMAL)
            for btn in self.mode_buttons:
                btn.config(state=tk.NORMAL)
            self.lbl_addr.config(text=f"{name} ({addr})")
            self.status.config(text="Conectado. Arrastra el joystick.")
        self.root.after(0, apply)

    def _on_connect_fail(self, err):
        def apply():
            self.btn_conn.config(state=tk.NORMAL, text="Conectar")
            self.status.config(text=f"Error: {err}")
            messagebox.showerror("Conexion", f"No se pudo conectar:\n{err}")
        self.root.after(0, apply)

    def _handle_link_lost(self):
        self.connected = False
        self.joy_active = False
        self.joy_vec = (0, 0)
        self._joy_moving = False
        self._draw_handle(0, 0)
        self.btn_conn.config(state=tk.NORMAL, text="Conectar")
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_center.config(state=tk.DISABLED)
        for btn in self.mode_buttons:
            btn.config(state=tk.DISABLED)
        self.status.config(text="Conexion perdida. Pulsa Conectar para reintentar.")

    def _stop(self):
        self.bridge.stop()
        self.status.config(text="Detenido.")

    def _center(self):
        self.bridge.center()
        self.status.config(text="Centrando...")

    def _set_mode(self, mode):
        if not self.connected:
            self.mode_var.set(0)
            return
        self.bridge.set_mode(mode)
        self.status.config(text=f"Cambiando modo a {MODE_NAMES[mode]}...")

    def _joy_press(self, event):
        self.joy_active = True
        self._joy_drag(event)

    def _joy_drag(self, event):
        if not self.joy_active:
            return
        dx = event.x - self.cx
        dy = event.y - self.cy
        mag = (dx * dx + dy * dy) ** 0.5
        if mag > self.radius:
            dx = dx / mag * self.radius
            dy = dy / mag * self.radius
        self.joy_vec = (dx, dy)
        self._draw_handle(dx, dy)

    def _joy_release(self, _event):
        self.joy_active = False
        self.joy_vec = (0, 0)
        self._joy_moving = False
        self._draw_handle(0, 0)
        self.bridge.stop()

    def _draw_handle(self, dx, dy):
        self.joy.delete("handle")
        self.joy.create_oval(self.cx + dx - 14, self.cy + dy - 14,
                             self.cx + dx + 14, self.cy + dy + 14,
                             fill="#7aa2f7", outline="#f5a623", width=2,
                             tags="handle")

    def _tick(self):
        if self.bridge.link_lost:
            self.bridge.link_lost = False
            self._handle_link_lost()
        if self.bridge.last_error:
            self.status.config(
                text=f"Error de comunicacion: {self.bridge.last_error}")
            self.bridge.last_error = None
        dx, dy = self.joy_vec
        if self.joy_active and self.connected:
            mag = (dx * dx + dy * dy) ** 0.5
            if mag >= DEAD_ZONE:
                # Ease from the dead zone edge (0 speed) to the joystick's
                # outer radius (MAX_SPEED) with a quadratic curve, so small
                # movements near the center give finer low-speed control.
                t = min((mag - DEAD_ZONE) / (self.radius - DEAD_ZONE), 1.0)
                speed = t * t * MAX_SPEED
                ux, uy = dx / mag, dy / mag
                yaw = int(ux * speed)
                pitch = int(-uy * speed)
                self.bridge.move(yaw, pitch)
                self._joy_moving = True
            elif self._joy_moving:
                self.bridge.stop()
                self._joy_moving = False
        tel = self.bridge.telemetry()
        if tel and self.connected:
            pos, bat, charging = tel
            if pos:
                self.lbl_pos.config(
                    text=f"Posicion: pan={pos[0] / 10:.1f}deg  tilt={pos[1] / 10:.1f}deg")
            if bat is not None:
                extra = " (cargando)" if charging else ""
                self.lbl_bat.config(text=f"Bateria: {bat}%{extra}")
        self.root.after(TICK_MS, self._tick)

    def _on_close(self):
        if self.connected:
            self.bridge.stop()
            self.bridge.disconnect()
        self.root.destroy()


def main():
    ap = argparse.ArgumentParser(description="GUI de control para DJI Osmo Mobile")
    ap.add_argument("--address", help="MAC del gimbal (autodetecta si se omite)")
    args = ap.parse_args()
    root = tk.Tk()
    App(root, addr=args.address)
    root.mainloop()


if __name__ == "__main__":
    main()
