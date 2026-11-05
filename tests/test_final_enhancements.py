import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runner import compile_c_program, run_compiled_program
from analyzers.correctness import evaluate_correctness
from analyzers.similarity import analyze_similarity


class FinalEnhancementTests(unittest.TestCase):
    def test_reference_executable_supplies_expected_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            student = root / "student.c"
            reference = root / "reference.c"
            student.write_text('#include <stdio.h>\nint main(void){int x; if(scanf("%d",&x)!=1)return 1; printf("%d\\n",x*2);}\n')
            reference.write_text('#include <stdio.h>\nint main(void){int x; if(scanf("%d",&x)!=1)return 1; printf("%d\\n",x+x);}\n')
            student_build = compile_c_program(student, root / "student_build")
            ref_build = compile_c_program(reference, root / "ref_build")
            self.assertEqual(student_build["status"], "ok", student_build.get("stderr"))
            self.assertEqual(ref_build["status"], "ok", ref_build.get("stderr"))
            result = evaluate_correctness(student_build["executable_path"],
                [{"name":"ref_case","input":"21\n"}], reference_executable=ref_build["executable_path"])
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.evidence["passed"], 1)
            self.assertEqual(result.evidence["cases"][0]["expected_output"], "42\n")

    def test_reference_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            student = root / "student.c"
            reference = root / "reference.c"
            student.write_text('#include <stdio.h>\nint main(void){puts("wrong");}\n')
            reference.write_text('#include <stdio.h>\nint main(void){puts("right");}\n')
            sb = compile_c_program(student, root / "sb")
            rb = compile_c_program(reference, root / "rb")
            result = evaluate_correctness(sb["executable_path"], [{"input":""}],
                reference_executable=rb["executable_path"])
            self.assertEqual(result.evidence["passed"], 0)
            self.assertEqual(result.evidence["cases"][0]["expected_output"], "right\n")

    def test_similarity_reports_both_signals(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td)/"a.c", Path(td)/"b.c"
            a.write_text("int main(){int x=2; return x;}")
            b.write_text("int main(){int y=3; return y;}")
            result = analyze_similarity(a, [b])
            self.assertEqual(result.status, "ok")
            comparison = result.evidence["comparisons"][0]
            self.assertIn("token_pair_similarity_percent", comparison)
            self.assertIn("sequence_similarity_percent", comparison)
            self.assertTrue(result.evidence["human_review_required"])

    def test_bubblewrap_requested_but_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)/"x.c"
            src.write_text("int main(void){return 0;}")
            built = compile_c_program(src, td)
            with patch("src.runner.shutil.which", return_value=None):
                result = run_compiled_program(built["executable_path"], sandbox_mode="bubblewrap")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"], "sandbox_unavailable")


if __name__ == "__main__":
    unittest.main()
