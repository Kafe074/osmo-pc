import struct


class DUMLPacket:
    def __init__(self, length, sender_idx, sender, receiver_idx, receiver,
                 seq, cmd_set, cmd, raw, payload):
        self.length = length
        self.sender_idx = sender_idx
        self.sender = sender
        self.receiver_idx = receiver_idx
        self.receiver = receiver
        self.seq = seq
        self.cmd_set = cmd_set
        self.cmd = cmd
        self.raw = raw
        self.payload = payload

    def __repr__(self):
        return (f"len={self.length} {self.sender_idx}.{self.sender}->"
                f"{self.receiver_idx}.{self.receiver} seq={self.seq} "
                f"cmd_set=0x{self.cmd_set:02x} cmd=0x{self.cmd:02x} "
                f"| {self.payload.hex(' ')}")


class DUMLParser:
    # header(4) + sender/receiver(2) + seq(2) + reserved(1) + cmd_set(1) + cmd(1) + crc(2)
    MIN_LENGTH = 13

    def __init__(self):
        self.buffer = b''

    def feed(self, data):
        self.buffer += bytes(data)
        while self.buffer:
            if self.buffer[0] != 0x55:
                idx = self.buffer.find(b'\x55')
                if idx == -1:
                    self.buffer = b''
                    break
                self.buffer = self.buffer[idx:]
                continue
            if len(self.buffer) < 4:
                break
            length_raw = struct.unpack('<H', self.buffer[1:3])[0]
            length = length_raw & 0x3FF
            if length < self.MIN_LENGTH:
                self.buffer = self.buffer[1:]
                continue
            if len(self.buffer) < length:
                break
            packet_data = self.buffer[:length]
            self.buffer = self.buffer[length:]
            yield DUMLPacket(
                length=length,
                sender_idx=packet_data[4] & 0x7,
                sender=packet_data[4] >> 3,
                receiver_idx=packet_data[5] & 0x7,
                receiver=packet_data[5] >> 3,
                seq=int.from_bytes(packet_data[6:8], "little", signed=False),
                cmd_set=int(packet_data[9]),
                cmd=int(packet_data[10]),
                raw=packet_data,
                payload=packet_data[11:length - 2],
            )
