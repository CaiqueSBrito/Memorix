"""Limites do pedido e bloqueio de geração sem evidência recuperada."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from backend.src.Memorix.contracts.generation import GenerationRequest
from backend.src.Memorix.ingestion.corpus import Corpus
from backend.src.Memorix.pipeline.generation import generate_material
from backend.src.Memorix.providers.local_llm import LocalLLM


class GenerationRequestTests(unittest.TestCase):
    def test_rejects_invalid_requests_before_generation(self):
        cases = [
            {"kind": "outro", "topic": "biologia"},
            {"kind": "flashcards", "topic": " \n\t"},
            {"kind": "flashcards", "topic": "biologia", "count": 0},
            {"kind": "flashcards", "topic": "biologia", "count": 21},
            {"kind": "flashcards", "topic": "biologia", "count": True},
            {"kind": "flashcards", "topic": "biologia", "count": 1.5},
            {"kind": "flashcards", "topic": "biologia", "difficulty": "desconhecida"},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                GenerationRequest(**case)

    def test_no_retrieved_evidence_never_contacts_model(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(self.path)
                self.send_response(500)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = LocalLLM(f"http://127.0.0.1:{server.server_port}/v1/chat/completions")
            with Corpus(":memory:") as corpus:
                corpus.ingest_text("fotossíntese clorofila", source="bio", title="Biologia")
                with self.assertRaises(ValueError):
                    generate_material(
                        corpus, GenerationRequest("flashcards", "astronomia"), client=client
                    )
            self.assertEqual(received, [])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
