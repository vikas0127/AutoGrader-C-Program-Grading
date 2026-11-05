import unittest
from analyzers.logical import analyze_logical


class LogicalAnalyzerTests(unittest.TestCase):
    def test_skips_when_no_assignment_specific_cases_are_configured(self):
        result = analyze_logical("/does/not/matter", [], params={})
        self.assertEqual(result.status, "skipped")
        self.assertIn("no unrelated", result.feedback.lower())

    def test_does_not_apply_legacy_addition_cases_to_other_assignments(self):
        result = analyze_logical("/does/not/matter", [], params={"problem": "instructor_assignment"})
        self.assertEqual(result.status, "skipped")


if __name__ == "__main__":
    unittest.main()
