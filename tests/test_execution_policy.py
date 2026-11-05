import json
import tempfile
import unittest
from pathlib import Path

from src.coordinator import evaluate_submission


@unittest.skipUnless(__import__("shutil").which("gcc"), "GCC required")
class ExecutionFailurePolicyTests(unittest.TestCase):
    def test_infinite_loop_is_not_reported_as_verified_correctness_and_is_capped(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "loop.c"
            source.write_text("int main(void){while(1){} return 0;}\n", encoding="utf-8")
            tests = root / "tests.json"
            tests.write_text(json.dumps([{"name":"smoke","input":"","expected_output":""}]), encoding="utf-8")
            rules = json.loads((project / "rules" / "rules.json").read_text())
            rules["time_limit_s"] = 0.2
            rules["grading_policy"]["first_pass_failure"] = {
                "enabled": True, "trigger_statuses": ["timeout", "crash", "error", "output_limit_exceeded"], "score_cap": 20
            }
            rules_path = root / "rules.json"
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            report = evaluate_submission(str(source), str(tests), str(rules_path), str(root / "reports"),
                                         timeout=0.2, memory_limit_mb=64)
            self.assertEqual(report["grade_status"], "execution_blocked")
            self.assertEqual(report["first_pass"]["correctness_verification"], "not_run")
            self.assertLessEqual(report["overall_score"], 20)
            self.assertTrue(report["score_summary"]["cap_applied"])
            self.assertTrue(any(f["type"] == "suspected_infinite_loop" for f in report["flags"]))

    def test_first_pass_stages_files_and_arguments_for_file_driven_program(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "read_file.c"
            source.write_text(
                '#include <stdio.h>\nint main(int argc,char **argv){(void)argc; FILE *f=fopen(argv[1],"r"); if(!f)return 2; int x=0; fscanf(f,"%d",&x); fclose(f); printf("%d\\n",x); return 0;}\n',
                encoding="utf-8")
            tests = root / "tests.json"
            tests.write_text(json.dumps([{"name":"file_case","input":"", "args":["input.txt"],
                "files":{"input.txt":"42\n"}, "expected_output":"42\n"}]), encoding="utf-8")
            rules = json.loads((project / "rules" / "rules.json").read_text())
            rules["metrics"]["logical"]["enabled"] = False
            rules["metrics"]["logical"]["weight"] = 0
            enabled = [v for v in rules["metrics"].values() if v.get("enabled")]
            total = sum(v["weight"] for v in enabled)
            for value in enabled:
                value["weight"] /= total
            rules_path = root / "rules.json"
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            report = evaluate_submission(str(source), str(tests), str(rules_path), str(root / "out"), timeout=1)
            self.assertTrue(report["first_pass"]["smoke_ok"], report["first_pass"])
            self.assertEqual(report["grade_status"], "complete")

    def test_output_limit_failure_is_capped(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "spam.c"
            source.write_text('#include <stdio.h>\nint main(void){while(1) puts("spam");}\n', encoding="utf-8")
            tests = root / "tests.json"
            tests.write_text(json.dumps([{"input":"", "expected_output":""}]), encoding="utf-8")
            rules = json.loads((project / "rules" / "rules.json").read_text())
            rules["time_limit_s"] = 1
            rules["grading_policy"]["first_pass_failure"]["trigger_statuses"].append("output_limit_exceeded")
            rules_path = root / "rules.json"
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            report = evaluate_submission(str(source), str(tests), str(rules_path), str(root / "out"), timeout=1)
            self.assertEqual(report["grade_status"], "execution_blocked")
            self.assertLessEqual(report["overall_score"], 20)


if __name__ == "__main__":
    unittest.main()
