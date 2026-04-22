from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import threading
import unittest

from ait.daemon_transport import (
    NDJSONSocketStream,
    TransportError,
    bind_unix_socket,
    connect_unix_socket,
    remove_socket_file,
)
from ait.protocol import EVENT_ATTEMPT_HEARTBEAT, AttemptHeartbeatPayload, ProtocolEnvelope


class DaemonTransportTests(unittest.TestCase):
    def test_bind_unix_socket_creates_parent_directory_and_accepts_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / ".ait" / "daemon.sock"
            server = bind_unix_socket(socket_path)
            self.addCleanup(server.close)
            self.addCleanup(remove_socket_file, socket_path)

            client = connect_unix_socket(socket_path, timeout=1.0)
            self.addCleanup(client.close)

            conn, _ = server.accept()
            conn.close()

    def test_ndjson_socket_stream_round_trips_envelope(self) -> None:
        server_sock, client_sock = socket.socketpair()
        self.addCleanup(server_sock.close)
        self.addCleanup(client_sock.close)

        expected = ProtocolEnvelope(
            schema_version=1,
            event_id="repo:evt-1",
            event_type=EVENT_ATTEMPT_HEARTBEAT,
            sent_at="2026-04-23T12:34:56Z",
            attempt_id="repo:attempt-1",
            ownership_token="token-1",
            payload=AttemptHeartbeatPayload(),
        )
        observed: list[ProtocolEnvelope] = []

        def reader() -> None:
            with server_sock.makefile("rwb") as handle:
                observed.append(NDJSONSocketStream(handle).read_envelope())

        thread = threading.Thread(target=reader)
        thread.start()
        with client_sock.makefile("rwb") as handle:
            NDJSONSocketStream(handle).write_envelope(expected)
        thread.join(timeout=2.0)

        self.assertEqual(observed, [expected])

    def test_read_envelope_rejects_oversized_message(self) -> None:
        server_sock, client_sock = socket.socketpair()
        self.addCleanup(server_sock.close)
        self.addCleanup(client_sock.close)

        with client_sock.makefile("wb") as writer:
            writer.write(b'{"x":"' + (b"a" * 128) + b'"}\n')
            writer.flush()
        with server_sock.makefile("rb") as reader:
            with self.assertRaisesRegex(TransportError, "exceeds max size"):
                NDJSONSocketStream(reader, max_message_bytes=32).read_envelope()

    def test_read_envelope_wraps_protocol_errors(self) -> None:
        server_sock, client_sock = socket.socketpair()
        self.addCleanup(server_sock.close)
        self.addCleanup(client_sock.close)

        with client_sock.makefile("wb") as writer:
            writer.write(b'{"schema_version":1}\n')
            writer.flush()
        with server_sock.makefile("rb") as reader:
            with self.assertRaisesRegex(TransportError, "event_type"):
                NDJSONSocketStream(reader).read_envelope()

    def test_remove_socket_file_refuses_non_socket_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            not_a_socket = Path(tmp) / "daemon.sock"
            not_a_socket.write_text("plain file\n", encoding="utf-8")

            with self.assertRaisesRegex(TransportError, "non-socket"):
                remove_socket_file(not_a_socket)


if __name__ == "__main__":
    unittest.main()
