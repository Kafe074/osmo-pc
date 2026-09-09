"""Unit tests for the DUML packet parser and the low-level Gimbal helpers
that consume it. Run with: python -m unittest test_duml -v (from pc/).

There was no test coverage at all for the reverse-engineered protocol code
before this file, so a firmware/protocol change could silently break
parsing. These tests pin down the framing behavior (sync byte, length
field, fragmentation, garbage-skipping) independently of any real BLE link.
"""
import unittest

from duml import DUMLParser
from gimbal import Gimbal, _crc16


def build_packet(sender_idx, sender, receiver_idx, receiver, seq, cmd_set, cmd, payload):
    """Build a synthetic DUML frame. The parser never validates the CRC,
    so it's left as zero bytes here.

    Layout: 0x55, length(2, 10 bits used), version(1, unused by the parser),
    sender/receiver(2), seq(2), reserved(1), cmd_set(1), cmd(1), payload, crc(2).
    """
    length = 13 + len(payload)
    header = bytes([0x55]) + length.to_bytes(2, "little") + bytes([0xa9])
    body = bytes([
        (sender << 3) | sender_idx,
        (receiver << 3) | receiver_idx,
    ]) + seq.to_bytes(2, "little") + bytes([0x00, cmd_set, cmd])
    return header + body + payload + b"\x00\x00"


class TestCRC16(unittest.TestCase):
    def test_deterministic(self):
        data = b"\x02\x04\x01\x00\x00\x04\x0c"
        self.assertEqual(_crc16(data, init=0xdf0c), _crc16(data, init=0xdf0c))

    def test_sensitive_to_payload(self):
        a = _crc16(b"\x00\x00\x00\x00", init=0xdf0c)
        b = _crc16(b"\x00\x00\x00\x01", init=0xdf0c)
        self.assertNotEqual(a, b)

    def test_sensitive_to_init(self):
        data = b"\x01\x02\x03"
        self.assertNotEqual(_crc16(data, init=0x0000), _crc16(data, init=0xdf0c))


class TestDUMLParser(unittest.TestCase):
    def test_single_packet(self):
        pkt = build_packet(2, 4, 0, 4, seq=7, cmd_set=0x05, cmd=0x06, payload=b"\x64\x01")
        parser = DUMLParser()
        msgs = list(parser.feed(pkt))
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg.sender_idx, 2)
        self.assertEqual(msg.sender, 4)
        self.assertEqual(msg.receiver_idx, 0)
        self.assertEqual(msg.receiver, 4)
        self.assertEqual(msg.seq, 7)
        self.assertEqual(msg.cmd_set, 0x05)
        self.assertEqual(msg.cmd, 0x06)
        self.assertEqual(msg.payload, b"\x64\x01")
        self.assertEqual(parser.buffer, b"")

    def test_fragmented_feed(self):
        pkt = build_packet(0, 4, 2, 4, seq=1, cmd_set=0x04, cmd=0x57,
                            payload=bytes(range(8)))
        parser = DUMLParser()
        collected = []
        for i in range(len(pkt)):
            collected.extend(parser.feed(pkt[i:i + 1]))
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0].payload, bytes(range(8)))

    def test_skips_leading_garbage(self):
        pkt = build_packet(0, 4, 2, 4, seq=1, cmd_set=0x00, cmd=0x32, payload=b"SN123")
        parser = DUMLParser()
        msgs = list(parser.feed(b"\x01\x02\x03" + pkt))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].payload, b"SN123")

    def test_multiple_packets_in_one_feed(self):
        p1 = build_packet(0, 4, 2, 4, seq=1, cmd_set=0x05, cmd=0x06, payload=b"\x50\x00")
        p2 = build_packet(0, 4, 2, 4, seq=2, cmd_set=0x05, cmd=0x06, payload=b"\x51\x01")
        parser = DUMLParser()
        msgs = list(parser.feed(p1 + p2))
        self.assertEqual([m.seq for m in msgs], [1, 2])
        self.assertEqual([m.payload for m in msgs], [b"\x50\x00", b"\x51\x01"])

    def test_incomplete_packet_waits_for_more_data(self):
        pkt = build_packet(0, 4, 2, 4, seq=1, cmd_set=0x05, cmd=0x06, payload=b"\x50\x00")
        parser = DUMLParser()
        msgs = list(parser.feed(pkt[:-1]))
        self.assertEqual(msgs, [])
        msgs = list(parser.feed(pkt[-1:]))
        self.assertEqual(len(msgs), 1)

    def test_short_length_field_is_discarded_byte_by_byte(self):
        # A stray 0x55 followed by a too-small length must not desync the
        # parser from a real packet that immediately follows.
        bogus = bytes([0x55, 0x02, 0x00])
        pkt = build_packet(0, 4, 2, 4, seq=1, cmd_set=0x05, cmd=0x06, payload=b"\x50\x00")
        parser = DUMLParser()
        msgs = list(parser.feed(bogus + pkt))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].payload, b"\x50\x00")


class TestGimbalNotifyHandling(unittest.TestCase):
    def setUp(self):
        # No real BLE connection is made; the Gimbal object is only used
        # here to exercise its notification-parsing helpers directly.
        self.gimbal = Gimbal("00:11:22:33:44:55")

    def test_battery_update_charging(self):
        self.gimbal._update_battery(bytes([77, 0, 0, 1]))
        self.assertEqual(self.gimbal.battery_level, 77)
        self.assertTrue(self.gimbal.is_charging)

    def test_battery_update_not_charging(self):
        self.gimbal._update_battery(bytes([50, 0, 0, 0]))
        self.assertEqual(self.gimbal.battery_level, 50)
        self.assertFalse(self.gimbal.is_charging)

    def test_position_update(self):
        payload = (
            (100).to_bytes(2, "little", signed=True)
            + (-50).to_bytes(2, "little", signed=True)
            + (0).to_bytes(2, "little", signed=True)
            + (-1).to_bytes(2, "little", signed=True)
        )
        self.gimbal._update_position(payload)
        self.assertEqual(self.gimbal.position, (100, -50, 0, -1))

    def test_position_update_ignores_short_payload(self):
        self.gimbal._update_position(b"\x00\x00")
        self.assertIsNone(self.gimbal.position)

    def test_seq_increments_and_wraps(self):
        self.gimbal._seq = 0xFFFE
        self.assertEqual(self.gimbal._next_seq(), (0xFFFF).to_bytes(2, "little"))
        self.assertEqual(self.gimbal._next_seq(), (0x0000).to_bytes(2, "little"))
        self.assertEqual(self.gimbal._next_seq(), (0x0001).to_bytes(2, "little"))


if __name__ == "__main__":
    unittest.main()
