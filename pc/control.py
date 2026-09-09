import argparse
import asyncio
import os
import sys
import time

if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios
    import tty

from gimbal import (
    Gimbal,
    find_gimbal_address,
    load_last_address,
    remove_registered_gimbals,
    save_last_address,
)

KEYMAP = {
    b"\x1b[A": ("yaw", 1200),
    b"\x1b[B": ("yaw", -1200),
    b"\x1b[C": ("tilt", 1200),
    b"\x1b[D": ("tilt", -1200),
    b"w": ("yaw", 1200),
    b"s": ("yaw", -1200),
    b"d": ("tilt", 1200),
    b"a": ("tilt", -1200),
}

# msvcrt.getch() reports arrow keys as a two-byte sequence: a b"\x00"/b"\xe0"
# prefix followed by a scan code. These are the scan codes for the arrows.
WIN_ARROW_SCANCODES = {
    b"H": ("yaw", 1200),
    b"P": ("yaw", -1200),
    b"M": ("tilt", 1200),
    b"K": ("tilt", -1200),
}

HOLD_TIMEOUT = 0.4
LOOP = 0.05


def get_key_posix(fd):
    r, _, _ = select.select([sys.stdin], [], [], 0)
    if not r:
        return None
    data = os.read(fd, 64)
    if data == b"\x03":
        return "QUIT"
    if data in (b"\n", b"\r", b" "):
        return "STOP"
    return KEYMAP.get(data)


def get_key_windows():
    if not msvcrt.kbhit():
        return None
    ch = msvcrt.getch()
    if ch == b"\x03":
        return "QUIT"
    if ch in (b"\r", b"\n", b" "):
        return "STOP"
    if ch in (b"\x00", b"\xe0"):
        # The scan code always follows the prefix as part of the same key
        # event; block briefly for it instead of polling with kbhit(),
        # otherwise a slow second byte gets dropped and read back on the
        # *next* call as a bogus standalone key.
        return WIN_ARROW_SCANCODES.get(msvcrt.getch())
    return KEYMAP.get(ch)


async def find_address():
    print("Buscando gimbal... (enciendelo y dejalo quieto)")
    last_addr, _ = load_last_address()
    found = await find_gimbal_address(retries=3, timeout=12, last_address=last_addr)
    if found:
        addr, name = found
        print(f"Encontrado: {name} ({addr})")
        save_last_address(addr, name)
        return addr
    return None


async def do_test(gimbal, duration):
    await gimbal.connect()
    print("Conectado. Probando pan...")
    loop = asyncio.get_running_loop()
    end = loop.time() + duration / 2
    while loop.time() < end:
        await gimbal.rotate(yaw=1200, pitch=0, roll=0, time=50,
                            mode=gimbal.RotationMode.SPEED)
        await asyncio.sleep(0.2)
    await gimbal.stop()
    await asyncio.sleep(duration / 2)
    print("Probando tilt...")
    end = loop.time() + duration / 2
    while loop.time() < end:
        await gimbal.rotate(yaw=0, pitch=1200, roll=0, time=50,
                            mode=gimbal.RotationMode.SPEED)
        await asyncio.sleep(0.2)
    await gimbal.stop()
    print(f"\nBateria: {gimbal.battery_level}%"
          + (" (cargando)" if gimbal.is_charging else ""))
    await gimbal.disconnect()


async def main():
    ap = argparse.ArgumentParser(description="Controla el joystick del DJI Osmo Mobile via BLE")
    ap.add_argument("--address", help="MAC del gimbal (autodetecta si se omite)")
    ap.add_argument("--test", type=float, default=0, help="Prueba automatica de N segundos")
    ap.add_argument("--no-clean", action="store_true",
                    help="No limpiar el registro de BlueZ antes de conectar")
    args = ap.parse_args()

    if not args.no_clean:
        remove_registered_gimbals()

    addr = args.address or await find_address()
    if not addr:
        sys.exit("No se encontro el gimbal. Enciendelo y verifica Bluetooth.")

    link_lost = False

    def on_disconnect():
        nonlocal link_lost
        link_lost = True

    gimbal = Gimbal(addr, on_disconnect=on_disconnect)

    if args.test > 0:
        await do_test(gimbal, args.test)
        return

    await gimbal.connect()
    await asyncio.sleep(1)

    if sys.platform == "win32":
        get_key = get_key_windows
    else:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd, termios.TCSANOW)
        get_key = lambda: get_key_posix(fd)

    pending = None
    last_event = 0.0
    print("Flechas/WASD = pan y tilt | Espacio = detener | Ctrl+C = salir")
    try:
        while True:
            if link_lost:
                sys.stdout.write("\nConexion perdida con el gimbal.\n")
                break
            now = time.time()
            key = get_key()
            if key == "QUIT":
                break
            if key == "STOP":
                pending = None
                await gimbal.stop()
            elif key is not None:
                pending = key
                last_event = now

            moving = pending is not None and (now - last_event) < HOLD_TIMEOUT
            if pending and not moving:
                pending = None
                await gimbal.stop()

            if pending and moving:
                axis, value = pending
                if axis == "yaw":
                    await gimbal.rotate(yaw=value, pitch=0, roll=0, time=50,
                                        mode=gimbal.RotationMode.SPEED)
                else:
                    await gimbal.rotate(yaw=0, pitch=value, roll=0, time=50,
                                        mode=gimbal.RotationMode.SPEED)

            bat = gimbal.battery_level
            bat_str = f"{bat}%" if bat is not None else "--"
            p = gimbal.position
            pos_str = (f"yaw={p[0] / 10:.1f} tilt={p[1] / 10:.1f}") if p else "pos=?"
            sys.stdout.write(
                f"\rBateria: {bat_str:<6} | {pos_str:<22} | moviendo: {'SI' if moving else 'no'}"
            )
            sys.stdout.flush()
            await asyncio.sleep(LOOP)
    finally:
        if sys.platform != "win32":
            termios.tcsetattr(fd, termios.TCSANOW, old)
        if gimbal.is_connected:
            await gimbal.stop()
            await gimbal.disconnect()
        print("\nDesconectado.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSalida.")
