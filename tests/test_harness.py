from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.daemon_transport import bind_unix_socket, remove_socket_file
from ait.harness import AitHarness, HarnessError


class HarnessClientTests(unittest.TestCase):
    """Verify the harness round-trips NDJSON envelopes over a unix socket.

    This spins up a minimal in-process server that records every envelope
    the client sends and always replies `{"ok": true}`. The point is to
    confirm the wire protocol shape, not the real daemon behaviour (that
    is covered by test_events.py and test_protocol.py).
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._socket_path = Path(self._tmp.name) / "daemon.sock"
        self._server = bind_unix_socket(self._socket_path)
        self._server.settimeout(2.0)
        self._received: list[dict] = []
        self._serve_thread: threading.Thread | None = None

    def tearDown(self) -> None:
        try:
            self._server.close()
        finally:
            try:
                remove_socket_file(self._socket_path)
            except Exception:
                pass
            self._tmp.cleanup()

    def _start_serve(self, ok: bool = True) -> None:
        self._serve_thread = threading.Thread(
            target=self._serve_once,
            args=(ok,),
            daemon=True,
        )
        self._serve_thread.start()

    def test_harness_streams_expected_events_in_order(self) -> None:
        self._start_serve()
        harness = AitHarness.open(
            attempt_id="repo:nonce:01TESTATTEMPT",
            ownership_token="test-token",
            socket_path=self._socket_path,
            agent={
                "agent_id": "myhar:worker",
                "harness": "myhar",
                "harness_version": "0.0.1",
            },
        )
        try:
            harness.start()
            harness.record_tool(
                tool_name="Read",
                category="read",
                duration_ms=3,
                success=True,
                files=[{"path": "src/foo.py", "access": "read"}],
            )
            harness.record_tool(
                tool_name="Edit",
                category="write",
                duration_ms=7,
                success=True,
                files=[{"path": "src/foo.py", "access": "write"}],
            )
            harness.heartbeat()
            harness.finish(exit_code=0)
        finally:
            harness.close()

        self._serve_thread.join(timeout=2.0)

        event_types = [evt["event_type"] for evt in self._received]
        self.assertEqual(
            ["attempt_started", "tool_event", "tool_event", "attempt_heartbeat", "attempt_finished"],
            event_types,
        )
        for envelope in self._received:
            self.assertEqual(1, envelope["schema_version"])
            self.assertEqual("repo:nonce:01TESTATTEMPT", envelope["attempt_id"])
            self.assertEqual("test-token", envelope["ownership_token"])
            self.assertTrue(envelope["event_id"].startswith("harness:"))
        started = self._received[0]
        self.assertEqual("myhar:worker", started["payload"]["agent"]["agent_id"])
        first_tool = self._received[1]
        self.assertEqual("read", first_tool["payload"]["category"])
        self.assertEqual(
            [{"path": "src/foo.py", "access": "read"}],
            first_tool["payload"]["files"],
        )
        finished = self._received[-1]
        self.assertEqual(0, finished["payload"]["exit_code"])

    def test_harness_raises_on_daemon_error_response(self) -> None:
        self._start_serve(ok=False)

        harness = AitHarness.open(
            attempt_id="repo:nonce:01TESTATTEMPT",
            ownership_token="bad-token",
            socket_path=self._socket_path,
            agent={"agent_id": "myhar:worker", "harness": "myhar", "harness_version": "0"},
        )
        try:
            with self.assertRaises(HarnessError):
                harness.start()
        finally:
            harness.close()

    def test_context_manager_finishes_on_exception(self) -> None:
        self._start_serve()
        with self.assertRaises(RuntimeError):
            with AitHarness.open(
                attempt_id="repo:nonce:01TESTATTEMPT",
                ownership_token="test-token",
                socket_path=self._socket_path,
                agent={"agent_id": "myhar:worker", "harness": "myhar", "harness_version": "0"},
            ) as harness:
                harness.record_tool(
                    tool_name="Bash",
                    category="command",
                    duration_ms=1,
                    success=False,
                )
                raise RuntimeError("simulated failure")

        self._serve_thread.join(timeout=2.0)
        event_types = [evt["event_type"] for evt in self._received]
        # started, tool_event, finished (auto by __exit__ with non-zero exit)
        self.assertEqual(
            ["attempt_started", "tool_event", "attempt_finished"],
            event_types,
        )
        finished = self._received[-1]
        self.assertEqual(1, finished["payload"]["exit_code"])

    def test_context_manager_does_not_retry_failed_explicit_finish(self) -> None:
        self._serve_thread = threading.Thread(
            target=self._serve_close_on_finish,
            daemon=True,
        )
        self._serve_thread.start()

        with self.assertRaises(HarnessError):
            with AitHarness.open(
                attempt_id="repo:nonce:01TESTATTEMPT",
                ownership_token="test-token",
                socket_path=self._socket_path,
                agent={"agent_id": "myhar:worker", "harness": "myhar", "harness_version": "0"},
            ) as harness:
                harness.finish(exit_code=1)

        self._serve_thread.join(timeout=2.0)
        event_types = [evt["event_type"] for evt in self._received]
        self.assertEqual(["attempt_started", "attempt_finished"], event_types)

    def _serve_once(self, ok: bool = True) -> None:
        try:
            client, _ = self._server.accept()
        except (socket.timeout, OSError):
            return
        try:
            file = client.makefile("rwb")
            while True:
                line = file.readline()
                if not line:
                    return
                envelope = json.loads(line.decode("utf-8"))
                self._received.append(envelope)
                response = {"ok": ok}
                if not ok:
                    response["error"] = "forced rejection"
                file.write((json.dumps(response) + "\n").encode("utf-8"))
                file.flush()
        finally:
            client.close()

    def _serve_close_on_finish(self) -> None:
        try:
            client, _ = self._server.accept()
        except (socket.timeout, OSError):
            return
        try:
            file = client.makefile("rwb")
            while True:
                line = file.readline()
                if not line:
                    return
                envelope = json.loads(line.decode("utf-8"))
                self._received.append(envelope)
                if envelope["event_type"] == "attempt_finished":
                    return
                file.write((json.dumps({"ok": True}) + "\n").encode("utf-8"))
                file.flush()
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
