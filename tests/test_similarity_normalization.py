import unittest
from analyzers.similarity import tokens


class SimilarityNormalizationTests(unittest.TestCase):
    def test_comments_and_identifier_renaming_are_normalized(self):
        a = "int sum(int x, int y) { return x + y; }"
        b = "int add(int left, int right) { /* comment */ return left + right; }"
        self.assertEqual(tokens(a), tokens(b))

    def test_keywords_and_library_calls_remain_visible(self):
        result = tokens('int main(){ printf("%d", 42); return 0; }')
        self.assertIn("printf", result)
        self.assertIn("return", result)
        self.assertIn("<STRING>", result)
        self.assertIn("<NUMBER>", result)


if __name__ == "__main__":
    unittest.main()
