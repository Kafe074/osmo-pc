import argparse
import asyncio
import sys

from bleak import BleakClient

from duml import DUMLParser

FFF0 = "0000fff0-0000-1000-8000-00805f9b34fb"
FFF4 = "0000fff4-0000-1000-8000-00805f9b34fb"


class Dump:
    def __init__(self):
        self.parser = DUMLParser()

    def on_notify(self, _handle, data):
        for msg in self.parser.feed(data):
            print(f"[{msg.cmd_set:02x}/{msg.cmd:02x}] len={msg.length} "
                  f"{msg.sender}.{msg.sender_idx}->{msg.receiver}.{msg.receiver_idx} "
                  f"payload({len(msg.payload)}): {msg.payload.hex(' ')}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument("--seconds", type=float, default=60)
    args = ap.parse_args()

    dump = Dump()
    client = BleakClient(args.address, services=[FFF0])
    await client.connect()
    print("Conectado. Moviendo el gimbal con la mano veras los mensajes.", flush=True)
    await client.start_notify(FFF4, dump.on_notify)
    try:
        await asyncio.sleep(args.seconds)
    finally:
        try:
            await client.stop_notify(FFF4)
        except Exception:
            pass
        await client.disconnect()
    print("\nFin.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
