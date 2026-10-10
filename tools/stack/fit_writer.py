"""A minimal FIT encoder for the stack's fake Intervals.icu: one activity file of `record` messages, parseable by
fitparse (the executor's parser), with only the fields a window's activities carry - so a window without a power
meter yields a frame without a power column, as the real loader does.

    fit_bytes = write_activity(records, fields=("heart_rate", "power", "speed", "distance", "cadence", "altitude"))

`records` is a list of dicts with a `timestamp` (an aware or naive UTC datetime) and any of the FIELDS below in
their natural units (m/s, m, bpm, W, rpm, m, degrees, degrees C); a missing value is written as the field's invalid
marker, which fitparse reads as None and the executor leaves out of the row.
"""
import struct
from datetime import datetime, timezone

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# the record message (global number 20): field number, base type, size, and the scale/offset fitparse applies
FIELDS = {
    "timestamp":     dict(num=253, base=0x86, size=4, fmt="<I", scale=1,    offset=0,   invalid=0xFFFFFFFF),
    "position_lat":  dict(num=0,   base=0x85, size=4, fmt="<i", scale=None, offset=0,   invalid=0x7FFFFFFF),   # semicircles
    "position_long": dict(num=1,   base=0x85, size=4, fmt="<i", scale=None, offset=0,   invalid=0x7FFFFFFF),
    "altitude":      dict(num=2,   base=0x84, size=2, fmt="<H", scale=5,    offset=500, invalid=0xFFFF),
    "heart_rate":    dict(num=3,   base=0x02, size=1, fmt="<B", scale=1,    offset=0,   invalid=0xFF),
    "cadence":       dict(num=4,   base=0x02, size=1, fmt="<B", scale=1,    offset=0,   invalid=0xFF),
    "distance":      dict(num=5,   base=0x86, size=4, fmt="<I", scale=100,  offset=0,   invalid=0xFFFFFFFF),
    "speed":         dict(num=6,   base=0x84, size=2, fmt="<H", scale=1000, offset=0,   invalid=0xFFFF),
    "power":         dict(num=7,   base=0x84, size=2, fmt="<H", scale=1,    offset=0,   invalid=0xFFFF),
    "temperature":   dict(num=13,  base=0x01, size=1, fmt="<b", scale=1,    offset=0,   invalid=0x7F),
}

_CRC_TABLE = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
              0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def crc16(data: bytes, crc: int = 0) -> int:
    for b in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[b & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(b >> 4) & 0xF]
    return crc


def _raw(name, value):
    f = FIELDS[name]
    if value is None:
        return f["invalid"]
    if name == "timestamp":
        ts = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int((ts - FIT_EPOCH).total_seconds())
    if name in ("position_lat", "position_long"):
        return int(round(value * (2 ** 31) / 180.0))
    return int(round((value + f["offset"]) * f["scale"]))


def write_activity(records, fields=("heart_rate", "power", "speed", "distance", "cadence", "altitude")) -> bytes:
    """The bytes of one FIT activity: a file_id message, one definition for the record message with `timestamp`
    and the given fields, then a data message per record."""
    fields = [f for f in fields if f in FIELDS and f != "timestamp"]
    body = bytearray()
    # file_id (global 0): type (0, enum, 1 byte) = 4 activity; manufacturer (1, uint16) = 255 development
    body += bytes([0x40, 0, 0]) + struct.pack("<H", 0) + bytes([2]) + bytes([0, 1, 0x00]) + bytes([1, 2, 0x84])
    body += bytes([0x00]) + bytes([4]) + struct.pack("<H", 255)
    # the record definition (local message 1)
    names = ["timestamp"] + fields
    body += bytes([0x41, 0, 0]) + struct.pack("<H", 20) + bytes([len(names)])
    for n in names:
        f = FIELDS[n]
        body += bytes([f["num"], f["size"], f["base"]])
    for r in records:
        body += bytes([0x01])
        for n in names:
            body += struct.pack(FIELDS[n]["fmt"], _raw(n, r.get(n)))
    header = bytearray(struct.pack("<BBHI4s", 14, 0x20, 2100, len(body), b".FIT"))
    header += struct.pack("<H", crc16(bytes(header[:12])))
    out = bytes(header) + bytes(body)
    return out + struct.pack("<H", crc16(out))
