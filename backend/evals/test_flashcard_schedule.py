"""Transições de caixas e vencimentos determinísticos, sem esperar o relógio."""

from datetime import datetime, timedelta, timezone
import unittest

from backend.src.Memorix.study.flashcard_schedule import schedule_review, utc_instant


class FlashcardScheduleTests(unittest.TestCase):
    def setUp(self):
        self.instant = datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)

    def test_initial_ratings_reset_or_advance_with_explicit_intervals(self):
        cases = [
            ("again", 0, timedelta(minutes=10)),
            ("hard", 1, timedelta(days=1)),
            ("good", 1, timedelta(days=1)),
            ("easy", 2, timedelta(days=3)),
        ]
        for rating, box, interval in cases:
            with self.subTest(rating=rating):
                result = schedule_review(0, rating, self.instant)
                self.assertEqual(result["box"], box)
                self.assertEqual(datetime.fromisoformat(result["due_at"]), self.instant + interval)

    def test_successive_good_ratings_increase_and_cap_the_interval(self):
        box, instant = 0, self.instant
        for expected_box, days in [(1, 1), (2, 3), (3, 7), (4, 14), (5, 30), (6, 60), (6, 60)]:
            with self.subTest(box=box):
                result = schedule_review(box, "good", instant)
                self.assertEqual(result["box"], expected_box)
                due = datetime.fromisoformat(result["due_at"])
                self.assertEqual(due - instant, timedelta(days=days))
                box, instant = result["box"], due

    def test_hard_recedes_easy_advances_and_again_resets_a_mature_card(self):
        hard = schedule_review(6, "hard", self.instant)
        self.assertEqual(hard["box"], 5)
        self.assertEqual(datetime.fromisoformat(hard["due_at"]) - self.instant, timedelta(days=30))
        easy = schedule_review(5, "easy", self.instant)
        self.assertEqual(easy["box"], 6)
        self.assertEqual(datetime.fromisoformat(easy["due_at"]) - self.instant, timedelta(days=60))
        reset = schedule_review(6, "again", self.instant)
        self.assertEqual(reset["box"], 0)
        self.assertEqual(datetime.fromisoformat(reset["due_at"]) - self.instant, timedelta(minutes=10))

    def test_timezone_conversion_preserves_the_instant_across_day_boundary(self):
        local = datetime(2026, 2, 1, 0, 30, tzinfo=timezone(timedelta(hours=3)))
        result = schedule_review(0, "good", local)
        self.assertEqual(result["due_at"], "2026-02-01T21:30:00+00:00")
        self.assertEqual(utc_instant(local), datetime(2026, 1, 31, 21, 30, tzinfo=timezone.utc))

    def test_invalid_boxes_ratings_and_ambiguous_instants_are_rejected(self):
        for box in (-1, 7, True, 1.0, None):
            with self.subTest(box=box), self.assertRaises(ValueError):
                schedule_review(box, "good", self.instant)
        for rating in ("correct", "", None, 1, []):
            with self.subTest(rating=rating), self.assertRaises(ValueError):
                schedule_review(0, rating, self.instant)
        for instant in (None, "2026-01-31", datetime(2026, 1, 31), 1):
            with self.subTest(instant=instant), self.assertRaises(ValueError):
                schedule_review(0, "good", instant)
        with self.assertRaises(ValueError):
            utc_instant(datetime(2026, 1, 31))
        with self.assertRaises(ValueError):
            schedule_review(6, "easy", datetime.max.replace(tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
