from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
from typing import BinaryIO

from ait.protocol import ProtocolEnvelope, ProtocolError, encode_ndjson_message, parse_ndjson_message

DEFAULT_BACKLOG = 128
DEFAULT_MAX_MESSAGE_BYTES = 1024 * 1024


class TransportError(RuntimeError):
    """Raised when the Unix socket transport cannot read or write a message."""


@dataclass(slots=True)
class NDJSONSocketStream:
    stream: BinaryIO
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES

    def read_envelope(self) -> ProtocolEnvelope | None:
        line = self.stream.readline(self.max_message_bytes + 1)
        if line == b"":
            return None
        if len(line) > self.max_message_bytes:
            raise TransportError(
                f"message exceeds max size of {self.max_message_bytes} bytes"
            )
        if not line.endswith(b"\n"):
            raise TransportError("message is missing trailing newline")
        try:
            return parse_ndjson_message(line)
        except ProtocolError as exc:
            raise TransportError(str(exc)) from exc

    def write_envelope(self, envelope: ProtocolEnvelope) -> None:
        self.stream.write(encode_ndjson_message(envelope))
        self.stream.flush()


def bind_unix_socket(
    socket_path: str | Path,
    *,
    backlog: int = DEFAULT_BACKLOG,
) -> socket.socket:
    path = Path(socket_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_socket():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.2)
                probe.connect(str(path))
            except OSError:
                path.unlink()
            else:
                raise TransportError(f"socket path already has a live listener: {path}")
            finally:
                probe.close()
        else:
            raise TransportError(f"socket path already exists and is not a socket: {path}")

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(backlog)
    except Exception:
        server.close()
        raise
    return server


def connect_unix_socket(
    socket_path: str | Path,
    *,
    timeout: float | None = None,
) -> socket.socket:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    if timeout is not None:
        client.settimeout(timeout)
    client.connect(str(Path(socket_path).resolve()))
    return client


def remove_socket_file(socket_path: str | Path) -> None:
    path = Path(socket_path).resolve()
    if not path.exists():
        return
    if not path.is_socket():
        raise TransportError(f"refusing to remove non-socket path: {path}")
    path.unlink()
