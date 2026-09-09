import asyncio
import json
import subprocess
from enum import IntEnum
from pathlib import Path

from bleak import BleakBackend, BleakClient, BleakScanner

from duml import DUMLParser

CONFIG_PATH = Path.home() / ".config" / "osmo-pc" / "last_gimbal.json"


def load_last_address():
    """Return the (address, name) saved from the last successful connection,
    or (None, None) if there isn't one."""
    try:
        data = json.loads(CONFIG_PATH.read_text())
        return data.get("address"), data.get("name")
    except Exception:
        return None, None


def save_last_address(address, name):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"address": address, "name": name}))
    except Exception:
        pass


async def find_gimbal_address(retries=3, timeout=10, last_address=None):
    """Locate a nearby DJI Osmo Mobile gimbal over BLE.

    If `last_address` is given, it's checked directly first (much faster
    than a full advertisement scan). Falls back to scanning for any device
    whose name starts with "OM". Returns (address, name) or None.
    """
    if last_address:
        try:
            device = await BleakScanner.find_device_by_address(last_address, timeout=5)
        except Exception:
            device = None
        if device:
            return device.address, device.name or device.address

    for _ in range(retries):
        stop = asyncio.Event()
        found = {}

        def on_detect(device, _adv):
            if device.name and device.name.upper().startswith("OM"):
                found[device.address] = device.name
                stop.set()

        async with BleakScanner(on_detect):
            try:
                await asyncio.wait_for(stop.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
        if found:
            return next(iter(found.items()))
    return None


def remove_registered_gimbals():
    try:
        out = subprocess.run(["bluetoothctl", "devices"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return
    for line in out.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[0] == "Device" and parts[2].upper().startswith("OM"):
            subprocess.run(["bluetoothctl", "remove", parts[1]], capture_output=True,
                           text=True, timeout=10)


class Gimbal:
    FFF0 = "0000fff0-0000-1000-8000-00805f9b34fb"
    FFF4 = "0000fff4-0000-1000-8000-00805f9b34fb"
    FFF5 = "0000fff5-0000-1000-8000-00805f9b34fb"

    class RotationMode(IntEnum):
        RELATIVE = 0x04
        ABSOLUTE = 0x05
        SPEED = 0x80

    class Mode(IntEnum):
        PTF = 0
        FPV = 1
        SPIN_SHOT = 2
        PF = 3

    def __init__(self, addr, timeout=30, on_disconnect=None):
        self.addr = addr
        self._parser = DUMLParser()
        self._on_disconnect_cb = on_disconnect
        self._disconnecting = False
        self._ble_client = BleakClient(
            addr, services=[self.FFF0], timeout=timeout,
            disconnected_callback=self._handle_disconnected)
        self._battery_level = None
        self._is_charging = False
        self._position = None
        self._serial_number = None
        self._seq = 0

    def _next_seq(self):
        # DUML command sequence number: must increase on every command sent,
        # or the gimbal can treat repeated/one-shot commands (stop, set_mode)
        # as stale duplicates and silently ignore them.
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq.to_bytes(2, "little")

    async def connect(self):
        await self._ble_client.connect()
        await self._ble_client.start_notify(self.FFF4, self._on_notify)
        if self._ble_client.backend_id == BleakBackend.BLUEZ_DBUS:
            try:
                await self._ble_client._backend._acquire_mtu()
            except Exception:
                # Best-effort: reaches into bleak's private BlueZ backend API,
                # which can change or fail independently of the connection.
                pass

    async def disconnect(self):
        if not self._ble_client.is_connected:
            return
        self._disconnecting = True
        try:
            await self._ble_client.stop_notify(self.FFF4)
        except Exception:
            pass
        try:
            await self._ble_client.disconnect()
        finally:
            self._disconnecting = False

    def _handle_disconnected(self, _client):
        # Fires on any link drop, intentional or not (radio out of range,
        # gimbal powered off, etc). Skip the callback for our own
        # disconnect() calls so callers only hear about *unexpected* loss.
        if self._disconnecting:
            return
        if self._on_disconnect_cb:
            self._on_disconnect_cb()

    async def rotate(self, yaw, pitch, roll, time, mode):
        header = bytes([0x55, 0x15, 0x04, 0xa9])
        body = bytearray([0x02, 0x04]) + self._next_seq() + bytearray([0x00, 0x04])
        body.append(0x0c if mode == self.RotationMode.SPEED else 0x14)

        yaw = yaw.to_bytes(2, "little", signed=True)
        pitch = pitch.to_bytes(2, "little", signed=True)
        roll = roll.to_bytes(2, "little", signed=True)
        mode = bytes([mode.value])
        time = bytes([time])

        payload = yaw + roll + pitch + mode + time
        crc = _crc16(body + payload, init=0xdf0c).to_bytes(2, "little")

        msg = header + body + payload + crc
        for chunk in self._chunk_msg(msg):
            await self._ble_client.write_gatt_char(self.FFF5, chunk)

    async def stop(self):
        # Send a short burst instead of a single shot: a lone BLE write can
        # be dropped, and a single zero-speed command can land inside the
        # window of a prior in-flight SPEED command and be superseded by it.
        for _ in range(3):
            await self.rotate(0, 0, 0, 5, self.RotationMode.SPEED)
            await asyncio.sleep(0.05)

    async def center(self):
        await self.rotate(0, 0, 0, 15, self.RotationMode.ABSOLUTE)

    async def set_mode(self, mode):
        if isinstance(mode, self.Mode):
            mode = mode.value
        header = bytes([0x55, 0x0f, 0x04, 0xa9])
        body = bytearray([0x02, 0x04]) + self._next_seq() + bytearray([0x00, 0x04, 0x4c])
        payload = bytes([mode, 0x00])
        crc = _crc16(body + payload, init=0xdf0c).to_bytes(2, "little")
        msg = header + body + payload + crc
        for chunk in self._chunk_msg(msg):
            await self._ble_client.write_gatt_char(self.FFF5, chunk)

    def _chunk_msg(self, msg):
        chunk_size = self._ble_client.mtu_size - 3
        for i in range(0, len(msg), chunk_size):
            yield msg[i:i + chunk_size]

    @property
    def battery_level(self):
        return self._battery_level

    @property
    def is_charging(self):
        return self._is_charging

    @property
    def position(self):
        return self._position

    @property
    def serial_number(self):
        return self._serial_number

    @property
    def is_connected(self):
        return self._ble_client.is_connected

    def _on_notify(self, _, data):
        for msg in self._parser.feed(data):
            if msg.cmd_set == 0x05 and msg.cmd == 0x06:
                self._update_battery(msg.payload)
            elif msg.cmd_set == 0x04 and msg.cmd == 0x57:
                self._update_position(msg.payload)
            elif msg.cmd_set == 0x00 and msg.cmd == 0x32:
                self._serial_number = msg.payload[2:].decode("latin-1", "ignore").strip("\x00")

    def _update_battery(self, data):
        if data:
            self._battery_level = data[0]
            self._is_charging = data[-1] == 1

    def _update_position(self, data):
        if len(data) >= 8:
            self._position = tuple(
                int.from_bytes(data[i:i + 2], "little", signed=True) for i in (0, 2, 4, 6)
            )

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


def _crc16(packet, init):
    tbl = [
        0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf,
        0x8c48, 0x9dc1, 0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7,
        0x1081, 0x0108, 0x3393, 0x221a, 0x56a5, 0x472c, 0x75b7, 0x643e,
        0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64, 0xf9ff, 0xe876,
        0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd,
        0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5,
        0x3183, 0x200a, 0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c,
        0xbdcb, 0xac42, 0x9ed9, 0x8f50, 0xfbef, 0xea66, 0xd8fd, 0xc974,
        0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9, 0x2732, 0x36bb,
        0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
        0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a,
        0xdecd, 0xcf44, 0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72,
        0x6306, 0x728f, 0x4014, 0x519d, 0x2522, 0x34ab, 0x0630, 0x17b9,
        0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3, 0x8a78, 0x9bf1,
        0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738,
        0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa862, 0x9af9, 0x8b70,
        0x8408, 0x9581, 0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7,
        0x0840, 0x19c9, 0x2b52, 0x3adb, 0x4e64, 0x5fed, 0x6d76, 0x7cff,
        0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324, 0xf1bf, 0xe036,
        0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
        0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5,
        0x2942, 0x38cb, 0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd,
        0xb58b, 0xa402, 0x9699, 0x8710, 0xf3af, 0xe226, 0xd0bd, 0xc134,
        0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e, 0x5cf5, 0x4d7c,
        0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3,
        0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb,
        0xd68d, 0xc704, 0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232,
        0x5ac5, 0x4b4c, 0x79d7, 0x685e, 0x1ce1, 0x0d68, 0x3ff3, 0x2e7a,
        0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3, 0x8238, 0x93b1,
        0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
        0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330,
        0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78,
    ]
    crc = init
    for i in range(0, len(packet)):
        crc = (crc >> 8) ^ tbl[((packet[i] ^ crc) & 0xFF)]
    return crc
