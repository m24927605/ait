from __future__ import annotations

from datetime import UTC, datetime
import secrets
import threading

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_RANDOM_MASK = (1 << 80) - 1
_LOCK = threading.Lock()
_LAST_TIMESTAMP_MS = -1
_LAST_RANDOM_BITS = 0


def new_ulid() -> str:
    global _LAST_RANDOM_BITS, _LAST_TIMESTAMP_MS
    timestamp_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    with _LOCK:
        if timestamp_ms > _LAST_TIMESTAMP_MS:
            random_bits = secrets.randbits(80)
            _LAST_TIMESTAMP_MS = timestamp_ms
            _LAST_RANDOM_BITS = random_bits
        else:
            random_bits = (_LAST_RANDOM_BITS + 1) & _RANDOM_MASK
            if random_bits == 0:
                timestamp_ms = _LAST_TIMESTAMP_MS + 1
                _LAST_TIMESTAMP_MS = timestamp_ms
            else:
                timestamp_ms = _LAST_TIMESTAMP_MS
            _LAST_RANDOM_BITS = random_bits
    value = (timestamp_ms << 80) | random_bits
    encoded: list[str] = []
    for _ in range(26):
        encoded.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(encoded))
