"""Erros e isolamento de rede do LLM local, sem modelo ou GPU."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
import os
from threading import Thread
import unittest
from unittest.mock import patch

from backend.src.Memorix.providers.local_llm import LocalLLM


@contextmanager
def local_server(body=b"invalid JSON", status=200, headers=None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.server.requests.append((self.command, self.path, dict(self.headers), data))
            self.send_response(self.server.response_status)
            for name, value in self.server.response_headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(self.server.response_body)
            self.close_connection = True

        do_GET = do_POST

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.response_body = body
    server.response_status = status
    server.response_headers = dict(headers or {})
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def chat_response(content='{"title": "Material", "items": []}', finish_reason="stop", **message):
    return json.dumps(
        {"choices": [{"finish_reason": finish_reason, "message": {"content": content, **message}}]}
    ).encode("utf-8")


class LocalLLMTests(unittest.TestCase):
    def test_invalid_endpoints_are_rejected_before_network_io(self):
        endpoints = [
            "https://127.0.0.1:8080/v1/chat/completions",
            "http://example.com/v1/chat/completions",
            "http://192.168.1.1/v1/chat/completions",
            "http://localhost:8080/v1/chat/completions",
            "http://127.1:8080/v1/chat/completions",
            "http://2130706433/v1/chat/completions",
            "http://127.0.0.2/v1/chat/completions",
            "http://[::ffff:127.0.0.1]/v1/chat/completions",
            "http://user:password@127.0.0.1/v1/chat/completions",
            "http://127.0.0.1/v1/chat/completions?token=secret",
            "http://127.0.0.1/v1/chat/completions?",
            "http://127.0.0.1/v1/chat/completions#secret",
            "http://127.0.0.1/v1/chat/completions#",
            "http://127.0.0.1:0/v1/chat/completions",
            "http://127.0.0.1:65536/v1/chat/completions",
            "http://127.0.0.1:-1/v1/chat/completions",
            "http://127.0.0.1:abc/v1/chat/completions",
            "http://127.0.0.1:/v1/chat/completions",
            "http://[::1]suffix/v1/chat/completions",
            "http://[::1/v1/chat/completions",
            " http://127.0.0.1/v1/chat/completions",
            "http://127.0.0.1\n.example.com/v1/chat/completions",
            "file:///tmp/model",
            "",
            None,
        ]
        with (
            local_server() as (server, endpoint),
            patch("socket.getaddrinfo", side_effect=AssertionError("DNS proibido")),
            patch("socket.socket.connect", side_effect=AssertionError("Conexão proibida")),
        ):
            endpoints.append(endpoint.replace("127.0.0.1", "localhost"))
            for endpoint in endpoints:
                with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                    LocalLLM(endpoint).complete(messages=[], schema={})
            self.assertEqual(server.requests, [])

    def test_rejects_empty_model_and_invalid_timeout(self):
        for model in ["", " \n", None, 1]:
            with self.subTest(model=model), self.assertRaises(ValueError):
                LocalLLM(model=model)
        for timeout in [0, -1, float("nan"), float("inf"), -float("inf"), None, "1", True, 10**1000]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                LocalLLM(timeout=timeout)

    def test_redirects_are_never_followed_or_retried(self):
        with local_server() as (target, target_endpoint), local_server() as (source, endpoint):
            for status in [300, 301, 302, 303, 307, 308]:
                for destination in [target_endpoint, "http://example.com/private"]:
                    with self.subTest(status=status, destination=destination):
                        source.response_status = status
                        source.response_headers = {"Location": destination}
                        before = len(source.requests)
                        with self.assertRaises(ValueError):
                            LocalLLM(endpoint).complete(messages=[], schema={})
                        self.assertEqual(len(source.requests), before + 1)
                        self.assertEqual(target.requests, [])

    def test_environment_proxies_and_tokens_are_not_used(self):
        with local_server() as (proxy, proxy_endpoint), local_server() as (target, endpoint):
            environment = {
                "http_proxy": proxy_endpoint,
                "HTTP_PROXY": proxy_endpoint,
                "https_proxy": proxy_endpoint,
                "HTTPS_PROXY": proxy_endpoint,
                "all_proxy": proxy_endpoint,
                "ALL_PROXY": proxy_endpoint,
                "no_proxy": "",
                "NO_PROXY": "",
                "OPENAI_API_KEY": "PRIVATE_API_TOKEN",
            }
            with patch.dict(os.environ, environment), self.assertRaises(ValueError):
                LocalLLM(endpoint).complete(messages=[{"role": "user", "content": "conteúdo local"}], schema={})
            self.assertEqual(proxy.requests, [])
            self.assertEqual(len(target.requests), 1)
            method, path, headers, body = target.requests[0]
            self.assertNotIn("authorization", {name.lower() for name in headers})
            self.assertNotIn(b"PRIVATE_API_TOKEN", body)

    def test_http_errors_are_actionable_without_leaking_body_or_prompts(self):
        secret = "PRIVATE_PROMPT_AND_RESPONSE"
        stdout, stderr = StringIO(), StringIO()
        with local_server(body=secret.encode()) as (server, endpoint):
            for status in [201, 204, 400, 401, 404, 429, 500]:
                with self.subTest(status=status):
                    server.response_status = status
                    with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(ValueError) as error:
                        LocalLLM(endpoint).complete(messages=[{"role": "user", "content": secret}], schema={})
                    self.assertNotIn(secret, str(error.exception))
            self.assertEqual(len(server.requests), 7)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_malformed_truncated_and_refused_responses_are_rejected(self):
        cases = {
            "invalid envelope": b"PRIVATE_RESPONSE_NOT_JSON",
            "invalid encoding": b"\xff",
            "truncated envelope": b'{"choices": [',
            "non-object envelope": b"[]",
            "missing choices": b"{}",
            "empty choices": b'{"choices": []}',
            "choices not a list": b'{"choices": {}}',
            "invalid first choice": b'{"choices": [null]}',
            "missing message": b'{"choices": [{"finish_reason": "stop"}]}',
            "invalid message": b'{"choices": [{"finish_reason": "stop", "message": []}]}',
            "truncated generation": chat_response(finish_reason="length"),
            "filtered generation": chat_response(finish_reason="content_filter"),
            "missing finish reason": b'{"choices": [{"message": {"content": "{}"}}]}',
            "refusal": chat_response(refusal="PRIVATE_REFUSAL"),
            "no content": chat_response(content=None),
            "structured content instead of string": chat_response(content={"title": "Material"}),
            "fenced JSON": chat_response(content='```json\n{"title": "Material"}\n```'),
            "truncated material": chat_response(content='{"title":'),
            "non-object material": chat_response(content="[]"),
            "null material": chat_response(content="null"),
            "trailing data": chat_response(content='{} PRIVATE_RESPONSE'),
            "non-JSON constant": chat_response(content='{"value": NaN}'),
        }
        with local_server() as (server, endpoint):
            for name, body in cases.items():
                with self.subTest(name=name):
                    server.response_body = body
                    before = len(server.requests)
                    with self.assertRaises(ValueError) as error:
                        LocalLLM(endpoint).complete(messages=[], schema={})
                    self.assertNotIn("PRIVATE", str(error.exception))
                    self.assertEqual(len(server.requests), before + 1)

    def test_incomplete_http_body_is_a_value_error(self):
        with local_server(body=b"{", headers={"Content-Length": "100"}) as (server, endpoint):
            with self.assertRaises(ValueError):
                LocalLLM(endpoint).complete(messages=[], schema={})
            self.assertEqual(len(server.requests), 1)

    def test_connection_failure_is_a_value_error(self):
        with local_server() as (_, endpoint):
            pass
        with self.assertRaises(ValueError):
            LocalLLM(endpoint, timeout=1).complete(messages=[], schema={})


if __name__ == "__main__":
    unittest.main()
