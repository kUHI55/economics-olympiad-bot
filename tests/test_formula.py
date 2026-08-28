import unittest

from app.services.quiz.formula import FormulaComparator


class FormulaComparatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.comparator = FormulaComparator()

    def test_accepts_equivalent_division_and_negative_power(self) -> None:
        result = self.comparator.compare("U * LF^-1", "u = U / LF")
        self.assertTrue(result.equivalent)

    def test_rejects_inverted_formula(self) -> None:
        result = self.comparator.compare("LF / U", "U / LF")
        self.assertFalse(result.equivalent)

    def test_reports_unsupported_addition(self) -> None:
        result = self.comparator.compare("U + LF", "U / LF")
        self.assertEqual(result.reason, "unsupported")
