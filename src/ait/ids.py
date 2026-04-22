from __future__ import annotations

from datetime import UTC, datetime
import random

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    timestamp_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    random_bits = random.getrandbits(80)
    value = (timestamp_ms << 80) | random_bits
    encoded: list[str] = []
    for _ in range(26):
        encoded.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(encoded))
