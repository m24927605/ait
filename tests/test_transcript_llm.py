from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from ait.memory_policy import SummarizerLLMConfig
from ait.transcript_llm import (
    LLMSummarizerError,
    SYSTEM_PROMPT,
    llm_summary,
)
from ait.transcript_summarizer import TranscriptEvent


class FakeHTTPResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _events_with_decision() -> list[TranscriptEvent]:
    return [
        TranscriptEvent(role="user", text="fix retry"),
        TranscriptEvent(role="assistant", text="going with durable queue"),
        TranscriptEvent(role="tool_use", tool="Edit", files=("src/retry.py",)),
        TranscriptEvent(role="tool_result", ok=True),
    ]


class AnthropicProviderTests(unittest.TestCase):
    def test_missing_api_key_raises(self) -> None:
        config = SummarizerLLMConfig(provider="anthropic", api_key_env="AIT_TEST_NOKEY")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIT_TEST_NOKEY", None)
            with self.assertRaises(LLMSummarizerError) as ctx:
                llm_summary(_events_with_decision(), config=config)
        self.assertIn("AIT_TEST_NOKEY", str(ctx.exception))

    def test_anthropic_request_payload_and_extraction(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                json.dumps(
                    {
                        "content": [
                            {"type": "text", "text": "Switched retry to durable queue."}
                        ]
                    }
                ).encode("utf-8")
            )

        config = SummarizerLLMConfig(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key_env="AIT_TEST_ANTHROPIC_KEY",
            max_chars=300,
        )
        with patch.dict(os.environ, {"AIT_TEST_ANTHROPIC_KEY": "sk-test"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                summary = llm_summary(_events_with_decision(), config=config)

        self.assertEqual("Switched retry to durable queue.", summary)
        self.assertEqual(
            "https://api.anthropic.com/v1/messages",
            captured["url"],
        )
        body = captured["body"]
        assert isinstance(body, dict)
        self.assertEqual(config.model, body["model"])
        self.assertEqual(SYSTEM_PROMPT, body["system"])
        self.assertEqual("user", body["messages"][0]["role"])
        self.assertIn("durable queue", body["messages"][0]["content"])
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual("sk-test", headers["x-api-key"])
        self.assertIn("anthropic-version", headers)

    def test_anthropic_truncates_to_max_chars(self) -> None:
        long_text = "x" * 1000

        def fake_urlopen(request, timeout):
            return FakeHTTPResponse(
                json.dumps({"content": [{"type": "text", "text": long_text}]}).encode(
                    "utf-8"
                )
            )

        config = SummarizerLLMConfig(
            provider="anthropic",
            api_key_env="AIT_TEST_ANTHROPIC_KEY",
            max_chars=80,
        )
        with patch.dict(os.environ, {"AIT_TEST_ANTHROPIC_KEY": "sk-test"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                summary = llm_summary(_events_with_decision(), config=config)

        self.assertLessEqual(len(summary), 80)
        self.assertTrue(summary.endswith("…"))

    def test_http_error_raises_llm_summarizer_error(self) -> None:
        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"bad key"}'),
            )

        config = SummarizerLLMConfig(
            provider="anthropic",
            api_key_env="AIT_TEST_ANTHROPIC_KEY",
        )
        with patch.dict(os.environ, {"AIT_TEST_ANTHROPIC_KEY": "sk-bad"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(LLMSummarizerError) as ctx:
                    llm_summary(_events_with_decision(), config=config)
        self.assertIn("HTTP 401", str(ctx.exception))

    def test_network_error_raises_llm_summarizer_error(self) -> None:
        def fake_urlopen(request, timeout):
            raise urllib.error.URLError("connection refused")

        config = SummarizerLLMConfig(
            provider="anthropic",
            api_key_env="AIT_TEST_ANTHROPIC_KEY",
        )
        with patch.dict(os.environ, {"AIT_TEST_ANTHROPIC_KEY": "sk-test"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(LLMSummarizerError) as ctx:
                    llm_summary(_events_with_decision(), config=config)
        self.assertIn("network error", str(ctx.exception))

    def test_anthropic_empty_text_raises(self) -> None:
        def fake_urlopen(request, timeout):
            return FakeHTTPResponse(json.dumps({"content": []}).encode("utf-8"))

        config = SummarizerLLMConfig(
            provider="anthropic",
            api_key_env="AIT_TEST_ANTHROPIC_KEY",
        )
        with patch.dict(os.environ, {"AIT_TEST_ANTHROPIC_KEY": "sk-test"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(LLMSummarizerError):
                    llm_summary(_events_with_decision(), config=config)


class OpenAICompatProviderTests(unittest.TestCase):
    def test_default_base_url_and_response_extraction(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                json.dumps(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": "summary text"}}
                        ]
                    }
                ).encode("utf-8")
            )

        config = SummarizerLLMConfig(
            provider="openai-compat",
            model="gpt-4o-mini",
            api_key_env="AIT_TEST_OPENAI_KEY",
        )
        with patch.dict(os.environ, {"AIT_TEST_OPENAI_KEY": "sk-openai"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                summary = llm_summary(_events_with_decision(), config=config)

        self.assertEqual("summary text", summary)
        self.assertEqual(
            "https://api.openai.com/v1/chat/completions",
            captured["url"],
        )
        body = captured["body"]
        assert isinstance(body, dict)
        self.assertEqual(config.model, body["model"])
        roles = [m["role"] for m in body["messages"]]
        self.assertEqual(["system", "user"], roles)
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual("Bearer sk-openai", headers["authorization"])

    def test_custom_base_url_for_local_server(self) -> None:
        captured: dict[str, str] = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            return FakeHTTPResponse(
                json.dumps(
                    {"choices": [{"message": {"content": "summary"}}]}
                ).encode("utf-8")
            )

        config = SummarizerLLMConfig(
            provider="openai-compat",
            model="llama3.2",
            api_key_env="AIT_TEST_LOCAL_KEY",
            base_url="http://localhost:11434/v1",
        )
        with patch.dict(os.environ, {"AIT_TEST_LOCAL_KEY": "ollama"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                summary = llm_summary(_events_with_decision(), config=config)

        self.assertEqual("summary", summary)
        self.assertEqual(
            "http://localhost:11434/v1/chat/completions",
            captured["url"],
        )

    def test_missing_choices_raises(self) -> None:
        def fake_urlopen(request, timeout):
            return FakeHTTPResponse(json.dumps({}).encode("utf-8"))

        config = SummarizerLLMConfig(
            provider="openai-compat",
            api_key_env="AIT_TEST_OPENAI_KEY",
        )
        with patch.dict(os.environ, {"AIT_TEST_OPENAI_KEY": "sk-test"}, clear=False):
            with patch("ait.transcript_llm.urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(LLMSummarizerError) as ctx:
                    llm_summary(_events_with_decision(), config=config)
        self.assertIn("missing choices", str(ctx.exception))


class UnsupportedProviderTests(unittest.TestCase):
    def test_unknown_provider_raises_when_called(self) -> None:
        config = SummarizerLLMConfig(
            provider="unknown",
            api_key_env="AIT_TEST_OPENAI_KEY",
        )
        with patch.dict(os.environ, {"AIT_TEST_OPENAI_KEY": "x"}, clear=False):
            with self.assertRaises(LLMSummarizerError) as ctx:
                llm_summary(_events_with_decision(), config=config)
        self.assertIn("unsupported provider", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
