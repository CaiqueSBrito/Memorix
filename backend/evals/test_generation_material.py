"""Validação de respostas educacionais, sem modelo ou dependências de rede."""

from copy import deepcopy
import unittest

from backend.src.Memorix.contracts.generation import CONTENT_TYPES, GenerationRequest
from backend.src.Memorix.generation_adapter.material import validate_material
from backend.src.Memorix.ingestion.corpus import SearchHit


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.hits = [
            SearchHit(
                doc_id="documento-biologia",
                chunk_id="trecho-nucleo",
                title="Biologia real",
                source="/acervo/biologia.pdf",
                ordinal=1,
                text="A célula contém um núcleo. O núcleo contém DNA.",
                score=1.0,
                page=7,
            ),
            SearchHit(
                doc_id="documento-energia",
                chunk_id="trecho-energia",
                title="Energia real",
                source="/acervo/energia.txt",
                ordinal=0,
                text="A mitocôndria participa da produção de energia.",
                score=0.5,
                page=None,
            ),
        ]

    def request(self, kind="flashcards", count=1):
        return GenerationRequest(kind, "Célula", count=count, difficulty="intermediaria")

    def payload(self, kind="flashcards"):
        citation = {"chunk_id": "trecho-nucleo", "quote": "O núcleo contém DNA."}
        if kind == "flashcards":
            item = {"front": "O que o núcleo contém?", "back": "DNA."}
        elif kind == "multipla_escolha":
            item = {
                "question": "O que o núcleo contém?",
                "options": ["DNA", "Mitocôndria", "Célula", "Energia"],
                "answer_index": 0,
                "explanation": "O trecho informa que o núcleo contém DNA.",
            }
        elif kind == "verdadeiro_falso":
            item = {
                "question": "O núcleo contém DNA.",
                "answer": True,
                "explanation": "A afirmação consta do trecho.",
            }
        else:
            item = {"heading": "Núcleo", "content": "O núcleo da célula contém DNA."}
        item["citations"] = [citation]
        return {"title": "Estudo da célula", "items": [item]}

    def test_all_kinds_enrich_citations_from_sources_without_mutating_input(self):
        for kind in CONTENT_TYPES:
            with self.subTest(kind=kind):
                request = self.request(kind)
                payload = self.payload(kind)
                before = deepcopy(payload)
                result = validate_material(payload, request, self.hits)
                self.assertEqual(result["status"], "requires_review")
                self.assertEqual(result["items"][0]["citations"], [{
                    "doc_id": "documento-biologia",
                    "chunk_id": "trecho-nucleo",
                    "quote": "O núcleo contém DNA.",
                    "title": "Biologia real",
                    "source": "/acervo/biologia.pdf",
                    "page": 7,
                }])
                self.assertEqual(payload, before)

    def test_multiple_sections_and_citations_keep_their_actual_page(self):
        payload = self.payload("aula")
        payload["items"].append({
            "heading": "Energia",
            "content": "A mitocôndria participa da produção de energia.",
            "citations": [{"chunk_id": "trecho-energia", "quote": "produção de energia"}],
        })
        result = validate_material(payload, self.request("aula", 2), self.hits)
        citations = [item["citations"][0] for item in result["items"]]
        self.assertEqual([citation["page"] for citation in citations], [7, None])
        self.assertEqual(citations[1]["doc_id"], "documento-energia")
        self.assertEqual(citations[1]["source"], "/acervo/energia.txt")

    def test_only_quote_whitespace_is_normalized(self):
        payload = self.payload()
        payload["items"][0]["citations"][0]["quote"] = " \n O núcleo\tcontém  DNA. \n"
        result = validate_material(payload, self.request(), self.hits)
        self.assertEqual(result["items"][0]["citations"][0]["quote"], "O núcleo contém DNA.")

    def test_invented_reference_and_unsupported_or_wrong_chunk_quote_are_rejected(self):
        cases = [
            {"chunk_id": "inventado", "quote": "O núcleo contém DNA."},
            {"chunk_id": "trecho-nucleo", "quote": "O núcleo contém proteínas."},
            {"chunk_id": "trecho-nucleo", "quote": "produção de energia"},
            {"chunk_id": "trecho-nucleo", "quote": "o núcleo contém DNA."},
            {"chunk_id": "trecho-nucleo", "quote": "O nucleo contem DNA."},
        ]
        for citation in cases:
            with self.subTest(citation=citation):
                payload = self.payload()
                payload["items"][0]["citations"] = [citation]
                with self.assertRaises(ValueError):
                    validate_material(payload, self.request(), self.hits)
        with self.assertRaises(ValueError):
            validate_material(self.payload(), self.request(), [])

    def test_wrong_count_or_non_list_items_is_rejected_for_every_kind(self):
        for kind in CONTENT_TYPES:
            for items in ([], [self.payload(kind)["items"][0]] * 2, None, {}, "item"):
                with self.subTest(kind=kind, items=items):
                    payload = self.payload(kind)
                    payload["items"] = items
                    with self.assertRaises(ValueError):
                        validate_material(payload, self.request(kind), self.hits)

    def test_wrong_item_schema_and_missing_fields_are_rejected_for_every_kind(self):
        for kind in CONTENT_TYPES:
            for field in self.payload(kind)["items"][0]:
                with self.subTest(kind=kind, missing=field):
                    payload = self.payload(kind)
                    del payload["items"][0][field]
                    with self.assertRaises(ValueError):
                        validate_material(payload, self.request(kind), self.hits)
            for other in CONTENT_TYPES:
                if other != kind:
                    with self.subTest(kind=kind, wrong_schema=other), self.assertRaises(ValueError):
                        validate_material(self.payload(other), self.request(kind), self.hits)

    def test_choice_index_requires_real_integer_in_bounds(self):
        for answer in (-1, 4, True, False, 0.0, "0", None, []):
            with self.subTest(answer=answer):
                payload = self.payload("multipla_escolha")
                payload["items"][0]["answer_index"] = answer
                with self.assertRaises(ValueError):
                    validate_material(payload, self.request("multipla_escolha"), self.hits)
        for answer in (0, 1, 2, 3):
            payload = self.payload("multipla_escolha")
            payload["items"][0]["answer_index"] = answer
            result = validate_material(payload, self.request("multipla_escolha"), self.hits)
            self.assertEqual(result["items"][0]["answer_index"], answer)

    def test_options_require_four_distinct_nonempty_strings(self):
        invalid = [
            ["A", "B", "C"], ["A", "B", "C", "D", "E"],
            ["A", "B", "C", "A"], ["A", "B", "C", ""],
            ["A", "B", "C", " \n"], ["A", "B", "C", 4],
            ["A", "B", "C", ["D"]], "ABCD", {"A": 1}, None,
        ]
        for options in invalid:
            with self.subTest(options=options):
                payload = self.payload("multipla_escolha")
                payload["items"][0]["options"] = options
                with self.assertRaises(ValueError):
                    validate_material(payload, self.request("multipla_escolha"), self.hits)

    def test_true_false_answer_is_a_boolean_not_a_number_or_string(self):
        for answer in (0, 1, "true", "false", None, []):
            with self.subTest(answer=answer):
                payload = self.payload("verdadeiro_falso")
                payload["items"][0]["answer"] = answer
                with self.assertRaises(ValueError):
                    validate_material(payload, self.request("verdadeiro_falso"), self.hits)
        for answer in (True, False):
            payload = self.payload("verdadeiro_falso")
            payload["items"][0]["answer"] = answer
            result = validate_material(payload, self.request("verdadeiro_falso"), self.hits)
            self.assertIs(result["items"][0]["answer"], answer)

    def test_empty_and_non_string_text_fields_are_rejected(self):
        for kind in CONTENT_TYPES:
            template = self.payload(kind)
            fields = [key for key, value in template["items"][0].items() if isinstance(value, str)]
            for field in ["title", *fields, "chunk_id", "quote"]:
                for value in ("", " \t\n", None, False, 1, []):
                    with self.subTest(kind=kind, field=field, value=value):
                        payload = self.payload(kind)
                        if field == "title":
                            payload[field] = value
                        elif field in ("chunk_id", "quote"):
                            payload["items"][0]["citations"][0][field] = value
                        else:
                            payload["items"][0][field] = value
                        with self.assertRaises(ValueError):
                            validate_material(payload, self.request(kind), self.hits)

    def test_extra_fields_are_rejected_at_all_levels_including_forged_metadata(self):
        for kind in CONTENT_TYPES:
            for level in ("material", "item", "citation"):
                for extra in ("extra", "doc_id", "source", "page", "title"):
                    if level == "material" and extra == "title":
                        continue
                    with self.subTest(kind=kind, level=level, extra=extra):
                        payload = self.payload(kind)
                        target = payload
                        if level == "item":
                            target = payload["items"][0]
                        elif level == "citation":
                            target = payload["items"][0]["citations"][0]
                        target[extra] = "metadado inventado"
                        with self.assertRaises(ValueError):
                            validate_material(payload, self.request(kind), self.hits)

    def test_malformed_objects_and_citations_raise_value_error(self):
        for payload in (None, [], "JSON", True, {}, {"title": "Título"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_material(payload, self.request(), self.hits)
        for item in (None, [], "item", False):
            payload = self.payload()
            payload["items"] = [item]
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_material(payload, self.request(), self.hits)
        for citations in ([], None, {}, "citação", [None], [[]], [{}],
                          [{"chunk_id": "trecho-nucleo"}], [{"quote": "núcleo"}]):
            payload = self.payload()
            payload["items"][0]["citations"] = citations
            with self.subTest(citations=citations), self.assertRaises(ValueError):
                validate_material(payload, self.request(), self.hits)

    def test_invalid_later_item_or_citation_does_not_return_partial_or_mutate_input(self):
        for invalid_location in ("item", "citation"):
            payload = self.payload()
            payload["items"].append(deepcopy(payload["items"][0]))
            if invalid_location == "item":
                payload["items"][1]["back"] = ""
            else:
                payload["items"][1]["citations"].append({
                    "chunk_id": "inventado", "quote": "DNA",
                })
            before = deepcopy(payload)
            with self.subTest(location=invalid_location), self.assertRaises(ValueError):
                validate_material(payload, self.request(count=2), self.hits)
            self.assertEqual(payload, before)



if __name__ == "__main__":
    unittest.main()
