import argparse
import asyncio
import sys

from gimbal import (
    Gimbal,
    find_gimbal_address,
    load_last_address,
    remove_registered_gimbals,
    save_last_address,
)


async def find_address():
    last_addr, _ = load_last_address()
    found = await find_gimbal_address(retries=1, timeout=15, last_address=last_addr)
    if found:
        addr, name = found
        print(f"Encontrado: {name} ({addr})")
        save_last_address(addr, name)
        return addr
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address")
    args = ap.parse_args()

    remove_registered_gimbals()
    addr = args.address or await find_address()
    if not addr:
        sys.exit("No se encontro el gimbal.")

    async with Gimbal(addr) as g:
        await asyncio.sleep(1.5)
        print(f"\nSerial: {g.serial_number}")
        print(f"Bateria: {g.battery_level}%")

        def pos():
            p = g.position
            if not p:
                return "?"
            return (f"v1={p[0]/10.0:.1f}  v2={p[1]/10.0:.1f}  "
                    f"v3={p[2]/10.0:.1f}  v4={p[3]/10.0:.1f}")

        await asyncio.sleep(1)
        print(f"\nReposo:      {pos()}")

        print("\n-- Giro YAW speed +1200 x3s --")
        await g.rotate(yaw=1200, pitch=0, roll=0, time=10, mode=g.RotationMode.SPEED)
        for _ in range(6):
            await asyncio.sleep(0.5)
            print(f"  {pos()}")
        await g.stop()
        await asyncio.sleep(1)
        print(f"Tras stop:   {pos()}")

        print("\n-- Recenter (angulo absoluto 0,0,0) --")
        await g.rotate(yaw=0, pitch=0, roll=0, time=15, mode=g.RotationMode.ABSOLUTE)
        await asyncio.sleep(2)
        print(f"Absoluto:    {pos()}")
        await g.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
