"""Correção estrita e não divulgação de gabaritos antes do envio."""

import json
import unittest

from backend.src.Memorix.study.grading import grade_answers, present_questions


def questionnaire(kind):
    citation = {"doc_id": "bio", "chunk_id": "nucleo", "quote": "CITAÇÃO PRIVADA"}
    if kind == "multipla_escolha":
        items = [
            {"question": "O que o núcleo contém?", "options": ["DNA", "Amido", "Clorofila", "Celulose"], "answer_index": 0},
            {"question": "Qual estrutura contém DNA?", "options": ["Parede", "Vacúolo", "Clorofila", "Núcleo"], "answer_index": 3},
        ]
    else:
        items = [
            {"question": "O núcleo contém DNA.", "answer": True},
            {"question": "O núcleo contém somente amido.", "answer": False},
        ]
    for item in items:
        item["explanation"] = "EXPLICAÇÃO PRIVADA"
        item["citations"] = [citation]
    return {"kind": kind, "items": items}


class GradingTests(unittest.TestCase):
    def test_questions_never_reveal_private_feedback_or_answer_fields(self):
        for kind in ("multipla_escolha", "verdadeiro_falso"):
            with self.subTest(kind=kind):
                questions = present_questions(questionnaire(kind))
                encoded = json.dumps(questions, ensure_ascii=False)
                self.assertNotIn("PRIVADA", encoded)
                self.assertNotIn("answer", encoded)
                self.assertNotIn("citations", encoded)
                self.assertNotIn("explanation", encoded)
                self.assertEqual([item["item_index"] for item in questions], [0, 1])

    def test_multiple_choice_marks_correct_and_wrong_indices_including_boundaries(self):
        snapshot = questionnaire("multipla_escolha")
        result = grade_answers(snapshot, [0, 0])
        self.assertEqual((result["correct_count"], result["total_count"], result["accuracy"]), (1, 2, 0.5))
        self.assertEqual([item["correct"] for item in result["items"]], [True, False])
        self.assertEqual(result["items"][1]["expected_answer"], 3)
        self.assertEqual(grade_answers(snapshot, [0, 3])["accuracy"], 1.0)
        self.assertEqual(grade_answers(snapshot, [3, 0])["accuracy"], 0.0)

    def test_true_false_scores_both_boolean_values_without_truthiness_conversion(self):
        snapshot = questionnaire("verdadeiro_falso")
        self.assertEqual(grade_answers(snapshot, [True, False])["correct_count"], 2)
        result = grade_answers(snapshot, [False, False])
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual([item["expected_answer"] for item in result["items"]], [True, False])
        self.assertEqual([item["correct"] for item in result["items"]], [False, True])

    def test_invalid_answer_types_indices_and_incomplete_submissions_are_rejected(self):
        cases = {
            "multipla_escolha": [[True, 3], [0, False], [0, 4], [-1, 3], [0.0, 3], ["0", 3], [0, None]],
            "verdadeiro_falso": [[1, False], [True, 0], ["true", False], [True, None], [True, []]],
        }
        for kind, answers in cases.items():
            snapshot = questionnaire(kind)
            for value in [*answers, None, {}, "respostas", [], [0], [0, 0, 0]]:
                with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                    grade_answers(snapshot, value)

    def test_non_objective_or_empty_material_is_not_automatically_scored(self):
        for snapshot in ({"kind": "flashcards", "items": [{}]}, {"kind": "aula", "items": [{}]}, {"kind": "multipla_escolha", "items": []}):
            with self.subTest(snapshot=snapshot):
                with self.assertRaises(ValueError):
                    present_questions(snapshot)
                with self.assertRaises(ValueError):
                    grade_answers(snapshot, [])


if __name__ == "__main__":
    unittest.main()
