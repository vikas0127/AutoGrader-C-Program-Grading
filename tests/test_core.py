import tempfile
from src.runner import compile_c_program, run_compiled_program
import json
import unittest
import tempfile
from pathlib import Path

from analyzers.correctness import compare_outputs
from analyzers.similarity import analyze_similarity
from src.scoring import validate_rules, calculate_score, should_apply_score_cap, should_apply_score_cap


ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    
    
    def test_infinite_loop_times_out(self):
        source = ROOT / "tests" / "inputs" / "infinite_loop.c"

        with tempfile.TemporaryDirectory() as directory:
            compiled = compile_c_program(source, directory)

            self.assertEqual(
                compiled["status"],
                "ok",
                msg=compiled.get("stderr", "Compilation failed"),
            )

            result = run_compiled_program(
                compiled["executable_path"],
                timeout=1,
            )

            self.assertEqual(result["status"], "timeout")
            self.assertEqual(result["error"], "timeout")
    
    def test_compare_ignores_trailing_whitespace(self):
        self.assertTrue(compare_outputs("5  \n", "5"))

    def test_compare_rejects_different_values(self):
        self.assertFalse(compare_outputs("5\n", "6\n"))

    def test_compare_rejects_empty_vs_nonempty(self):
        self.assertFalse(compare_outputs("", "5\n"))

    def test_compare_accepts_both_empty(self):
        self.assertTrue(compare_outputs("", ""))

    def test_current_rules_are_valid(self):
        rules = json.loads(
            (ROOT / "rules" / "rules.json").read_text(encoding="utf-8")
        )
        validate_rules(rules)

    def test_weighted_score(self):
        rules = {
            "score_scale": 100,
            "missing_metric_policy": "error",
            "metrics": {
                "a": {"enabled": True, "weight": 0.4},
                "b": {"enabled": True, "weight": 0.6},
            },
        }
        results = [
            {"name": "a", "status": "ok", "score": 100},
            {"name": "b", "status": "ok", "score": 50},
        ]

        result = calculate_score(rules, results)
        self.assertEqual(result["overall_score"], 70)

    def test_missing_enabled_metric_is_rejected(self):
        rules = {
            "score_scale": 100,
            "missing_metric_policy": "error",
            "metrics": {
                "a": {"enabled": True, "weight": 1.0}
            },
        }

        with self.assertRaises(ValueError):
            calculate_score(rules, [])

    def test_disabled_metric_does_not_affect_score(self):
        rules = {
            "score_scale": 100,
            "missing_metric_policy": "error",
            "metrics": {
                "a": {"enabled": True, "weight": 1.0},
                "b": {"enabled": False, "weight": 0.0},
            },
        }
        results = [
            {"name": "a", "status": "ok", "score": 80}
        ]

        result = calculate_score(rules, results)
        self.assertEqual(result["overall_score"], 80)

    def test_similarity_missing_source_is_error(self):
        result = analyze_similarity(
            ROOT / "tests" / "file_that_does_not_exist.c",
            [],
        )
        self.assertEqual(result.status, "error")

    def test_similarity_without_references_is_skipped(self):
        result = analyze_similarity(
            ROOT / "tests" / "inputs" / "sum.c",
            [],
        )
        self.assertEqual(result.status, "skipped")

    def test_identical_source_similarity_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.c"
            reference = Path(directory) / "reference.c"

            code = "int main(void) { return 0; }\n"
            source.write_text(code, encoding="utf-8")
            reference.write_text(code, encoding="utf-8")

            result = analyze_similarity(source, [reference])

            self.assertEqual(result.status, "ok")
            similarity = result.evidence["best_similarity_percent"]
            self.assertGreaterEqual(similarity, 0)
            self.assertLessEqual(similarity, 100)
            self.assertEqual(similarity, 100)
            self.assertEqual(result.score, 0)

    def test_score_cap_for_all_timeout_cases(self):
        rules = {"score_scale":100,"missing_metric_policy":"renormalize_skipped",
                 "metrics":{"correctness":{"enabled":True,"weight":1.0}},
                 "grading_policy":{"all_correctness_tests_fail":{"enabled":True,"score_cap":20,
                 "trigger_statuses":["timeout","crash","execution_error"]}}}
        result = {"name":"correctness","status":"ok","score":0,
                  "evidence":{"cases":[{"passed":False,"status":"timeout"},{"passed":False,"status":"crash"}]}}
        self.assertEqual(should_apply_score_cap(rules,{"correctness":result}), (True,20,"All correctness test cases failed due to timeout or runtime failure."))

    def test_memory_safety_detects_out_of_bounds_when_gcc_available(self):
        import shutil
        if not shutil.which("gcc"):
            self.skipTest("GCC unavailable")
        from analyzers.memory_safety import check_memory_safety
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"oob.c"
            source.write_text("#include <stdio.h>\nint main(void){int a[2]={1,2}; printf(\"%d\\n\",a[3]); return 0;}\n",encoding="utf-8")
            result=check_memory_safety(source,[{"name":"oob","input":""}],timeout=3,params={"flags":["-fsanitize=address,undefined"]})
            if result.error == "sanitizer_runtime_unavailable":
                self.skipTest("GCC ASan runtime is incompatible in this environment")
            self.assertEqual(result.status,"ok")
            self.assertGreater(result.evidence["issues_detected"],0)

    def test_score_cap_for_all_timeout_cases(self):
        rules = {"score_scale":100,"missing_metric_policy":"renormalize_skipped",
                 "metrics":{"correctness":{"enabled":True,"weight":1.0}},
                 "grading_policy":{"all_correctness_tests_fail":{"enabled":True,"score_cap":20,
                 "trigger_statuses":["timeout","crash","execution_error"]}}}
        result = {"name":"correctness","status":"ok","score":0,
                  "evidence":{"cases":[{"passed":False,"status":"timeout"},{"passed":False,"status":"crash"}]}}
        self.assertEqual(should_apply_score_cap(rules,{"correctness":result}), (True,20,"All correctness test cases failed due to timeout or runtime failure."))

    def test_memory_safety_detects_out_of_bounds_when_gcc_available(self):
        import shutil
        if not shutil.which("gcc"):
            self.skipTest("GCC unavailable")
        from analyzers.memory_safety import check_memory_safety
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"oob.c"
            source.write_text("#include <stdio.h>\nint main(void){int a[2]={1,2}; printf(\"%d\\n\",a[3]); return 0;}\n",encoding="utf-8")
            result=check_memory_safety(source,[{"name":"oob","input":""}],timeout=3,params={"flags":["-fsanitize=address,undefined"]})
            if result.error == "sanitizer_runtime_unavailable":
                self.skipTest("GCC ASan runtime is incompatible in this environment")
            self.assertEqual(result.status,"ok")
            self.assertGreater(result.evidence["issues_detected"],0)

    @unittest.skipUnless(__import__("os").name == "posix", "POSIX resource limits required")
    def test_runner_enforces_address_space_limit(self):
        source_code = "#include <stdlib.h>\n#include <stdio.h>\nint main(void){char *p=malloc(128*1024*1024); if(!p){puts(\"allocation failed\"); return 0;} puts(\"allocated\"); free(p); return 0;}\n"
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"memory.c"
            source.write_text(source_code,encoding="utf-8")
            compiled=compile_c_program(source,directory)
            self.assertEqual(compiled["status"],"ok",msg=compiled.get("stderr"))
            result=run_compiled_program(compiled["executable_path"],timeout=2,memory_limit_mb=64)
            self.assertEqual(result["status"],"ok")
            self.assertIn("allocation failed",result["stdout"])


if __name__ == "__main__":
    unittest.main()
