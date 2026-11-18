import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """
    Generate an RFC 9562 compliant time-ordered UUIDv7.
    48-bit big-endian Unix epoch milliseconds + 4-bit version (7) + 12-bit rand_a
    + 2-bit variant (10) + 62-bit rand_b.
    """
    unix_ts_ms = time.time_ns() // 1_000_000
    rand_bytes = os.urandom(10)

    # First 48 bits: timestamp in ms
    time_bytes = unix_ts_ms.to_bytes(6, byteorder="big")

    # Byte 6: version (0111) + 4 random bits
    b6 = (0x70 | (rand_bytes[0] & 0x0F)).to_bytes(1, "big")
    # Byte 7: 8 random bits
    b7 = rand_bytes[1:2]
    # Byte 8: variant (10) + 6 random bits
    b8 = (0x80 | (rand_bytes[2] & 0x3F)).to_bytes(1, "big")
    # Bytes 9..15: 7 random bytes
    b9_15 = rand_bytes[3:10]

    return uuid.UUID(bytes=time_bytes + b6 + b7 + b8 + b9_15)
