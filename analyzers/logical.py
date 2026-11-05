"""Optional instructor-authored logical edge-case checks.

This analyzer deliberately does not guess a problem type or reuse another
assignment's hard-coded tests. Assignment-aware generated cases are evaluated
by the correctness analyzer using the independent oracle's expected outputs.
"""
from analyzers.interface import AnalyzerResult
from src.runner import run_compiled_program


def analyze_logical(executable, cases, timeout=2.0, memory_limit_mb=None, params=None):
    params = params or {}
    selected = params.get("test_cases", [])
    if not isinstance(selected, list) or not selected:
        return AnalyzerResult(
            "logical", "skipped", None, evidence={"cases": []},
            feedback=("No separate instructor-authored logical cases configured. "
                      "Generated boundary/corner cases are already evaluated under correctness; "
                      "no unrelated problem-specific tests are applied."),
        )

    invalid = [i for i, case in enumerate(selected) if not isinstance(case, dict)
               or "input" not in case or "expected_output" not in case]
    if invalid:
        return AnalyzerResult("logical", "error", None,
                              feedback=f"Invalid logical test case entries at indexes: {invalid}",
                              error="invalid_logical_cases")

    results = []
    for i, case in enumerate(selected):
        run = run_compiled_program(executable, str(case["input"]), timeout, memory_limit_mb)
        passed = (run.get("status") == "ok" and run.get("returncode") == 0
                  and run.get("stdout", "").strip() == str(case["expected_output"]).strip())
        results.append({"name": case.get("name", f"logical_{i+1}"),
                        "input": str(case["input"]),
                        "expected_output": str(case["expected_output"]),
                        "actual_output": run.get("stdout", ""),
                        "status": "passed" if passed else run.get("status", "wrong_answer"),
                        "passed": passed, "stderr": run.get("stderr", "")})
    passed_count = sum(case["passed"] for case in results)
    score = round(100 * passed_count / len(results), 2)
    return AnalyzerResult("logical", "ok", score,
                          evidence={"passed": passed_count, "total": len(results), "cases": results},
                          feedback=f"Instructor-authored logical cases passed: {passed_count}/{len(results)}.")
