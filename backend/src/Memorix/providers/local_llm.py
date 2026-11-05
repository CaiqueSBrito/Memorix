"""Chat Completions restrito a um servidor HTTP no loopback literal."""

from http.client import HTTPException
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _reject_json_constant(value):
    raise ValueError("Constante não permitida em JSON.")


class LocalLLM:
    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8080/v1/chat/completions",
        model: str = "local",
        timeout: float = 120.0,
    ):
        if not isinstance(endpoint, str) or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in endpoint
        ):
            raise ValueError("Endpoint local inválido: use HTTP em 127.0.0.1 ou [::1].")
        try:
            parsed = urlsplit(endpoint)
            authority = re.fullmatch(r"(?:127\.0\.0\.1|\[::1\])(?::([0-9]+))?", parsed.netloc)
            port = parsed.port
        except ValueError:
            raise ValueError("Endpoint local inválido: confira o IP literal e a porta.") from None
        if (
            parsed.scheme != "http"
            or authority is None
            or "?" in endpoint
            or "#" in endpoint
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError(
                "Endpoint local inválido: use apenas HTTP em 127.0.0.1 ou [::1], "
                "sem credenciais, query ou fragmento, com porta entre 1 e 65535."
            )
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Informe um modelo local não vazio.")
        try:
            valid_timeout = (
                isinstance(timeout, (int, float))
                and not isinstance(timeout, bool)
                and math.isfinite(timeout)
                and timeout > 0
            )
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ValueError("O timeout deve ser um número positivo e finito de segundos.")
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def complete(self, *, messages: list[dict[str, str]], schema: dict) -> dict:
        try:
            body = json.dumps(
                {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "memorix_material",
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    "max_tokens": 4096,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            raise ValueError("Não foi possível serializar as mensagens e o schema em JSON.") from None
        request = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ValueError("O servidor local deve responder com HTTP 200.")
                raw = response.read()
        except HTTPError as error:
            code = error.code
            error.close()
            if 300 <= code < 400:
                raise ValueError(
                    "O servidor local respondeu com redirecionamento HTTP; "
                    "redirecionamentos são bloqueados. Configure o endpoint final."
                ) from None
            raise ValueError(
                f"O servidor local respondeu com HTTP {code}; confira o endpoint e o modelo."
            ) from None
        except (URLError, OSError, HTTPException):
            raise ValueError(
                "Falha na conexão com o LLM local; confira se o servidor está ativo, "
                "a porta e o timeout."
            ) from None
        try:
            envelope = json.loads(raw, parse_constant=_reject_json_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise ValueError("O servidor local retornou uma resposta HTTP que não é JSON válido.") from None
        if not isinstance(envelope, dict):
            raise ValueError("A resposta do servidor local deve ser um objeto Chat Completions.")
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("A resposta do servidor local não contém uma primeira choice válida.")
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            raise ValueError(
                "O LLM local não concluiu a geração (finish_reason diferente de stop); "
                "confira os limites de geração e o suporte ao schema."
            )
        message = choice.get("message")
        if not isinstance(message, dict) or message.get("refusal") is not None:
            raise ValueError("O LLM local recusou a geração ou retornou uma mensagem inválida.")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("O conteúdo gerado pelo LLM local deve ser uma string JSON.")
        try:
            material = json.loads(content, parse_constant=_reject_json_constant)
        except (ValueError, RecursionError):
            raise ValueError(
                "O LLM local não retornou JSON válido; configure saída estruturada sem fences Markdown."
            ) from None
        if not isinstance(material, dict):
            raise ValueError("O material gerado pelo LLM local deve ser um objeto JSON.")
        return material
