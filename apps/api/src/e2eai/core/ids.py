import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7 (NFR-20): 48-bit ms timestamp, version 7, variant 10, 74 random bits.
    Python 3.12 has no uuid7() in the standard library."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms << 80) | (0x7 << 76) | (((rand >> 62) & 0xFFF) << 64) | (0b10 << 62) | (rand & ((1 << 62) - 1))
    return uuid.UUID(int=value)
