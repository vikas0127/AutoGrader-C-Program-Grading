from analyzers.interface import AnalyzerResult
from src.runner import run_compiled_program
from pathlib import Path
import tempfile


def normalize_output(text):
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def compare_outputs(actual, expected):
    return normalize_output(actual) == normalize_output(expected)


def evaluate_correctness(executable, cases, timeout=2.0, memory_limit_mb=None,
                         reference_executable=None, comparison_policy=None, sandbox_mode='off'):
    if not cases:
        return AnalyzerResult("correctness", "skipped", None, evidence=[], feedback="No test cases supplied.")
    evidence = []
    for i, case in enumerate(cases):
        if "expected_output" not in case and reference_executable is None:
            return AnalyzerResult("correctness", "error", None, evidence={"case": i + 1},
                                  feedback="Each test needs expected_output unless a reference executable is configured.")
        item = {"name": case.get("name", f"case_{i+1}"), "input": case.get("input", ""),
                "args": case.get("args", []), "expected_output": case.get("expected_output"),
                "actual_output": None, "stderr": "", "passed": False,
                "status": "execution_error", "feedback": ""}
        if not isinstance(item["args"], list) or any(not isinstance(x, (str, int, float)) for x in item["args"]):
            item["status"] = "invalid_test_case"; item["feedback"] = "args must be an array of scalar values."; evidence.append(item); continue
        try:
            with tempfile.TemporaryDirectory(prefix="autograder_case_") as case_dir:
                for rel, content in (case.get("files") or {}).items():
                    target = (Path(case_dir) / rel).resolve()
                    if not target.is_relative_to(Path(case_dir).resolve()):
                        raise ValueError(f"Unsafe test file path: {rel}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(str(content), encoding="utf-8")
                run = run_compiled_program(executable, stdin=item["input"], timeout=timeout,
                    memory_limit_mb=memory_limit_mb, args=item["args"], cwd=case_dir, sandbox_mode=sandbox_mode)
                item["actual_output"] = run.get("stdout", ""); item["stderr"] = run.get("stderr", "")
                if run["status"] == "timeout":
                    item["status"] = "timeout"; item["feedback"] = f"Exceeded {timeout}s wall-clock limit."
                elif run["status"] != "ok":
                    item["status"] = "crash" if run.get("error") == "runtime_error" else "execution_error"
                    item["feedback"] = f"Execution failed ({run.get('error')}); exit={run.get('returncode')}. {item['stderr']}".strip()
                else:
                    expected_output = item["expected_output"]
                    if reference_executable is not None:
                        with tempfile.TemporaryDirectory(prefix="autograder_reference_") as ref_dir:
                            for rel, content in (case.get("files") or {}).items():
                                target = (Path(ref_dir) / rel).resolve()
                                if not target.is_relative_to(Path(ref_dir).resolve()):
                                    raise ValueError(f"Unsafe reference input file path: {rel}")
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(str(content), encoding="utf-8")
                            reference_run = run_compiled_program(
                                reference_executable, stdin=item["input"], timeout=timeout,
                                memory_limit_mb=memory_limit_mb, args=item["args"], cwd=ref_dir, sandbox_mode=sandbox_mode)
                        item["reference_output"] = reference_run.get("stdout", "")
                        item["reference_stderr"] = reference_run.get("stderr", "")
                        if reference_run.get("status") != "ok":
                            item["status"] = "reference_oracle_error"
                            item["feedback"] = "Trusted reference program did not complete successfully."
                            evidence.append(item)
                            continue
                        expected_output = item["reference_output"]
                    item["expected_output"] = expected_output
                    stdout_ok = compare_outputs(item["actual_output"], expected_output)
                    expected_files = case.get("expected_files") or {}
                    file_errors = []
                    for rel, expected in expected_files.items():
                        target = (Path(case_dir) / rel).resolve()
                        if not target.is_relative_to(Path(case_dir).resolve()):
                            file_errors.append(f"Unsafe expected file path: {rel}"); continue
                        actual = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
                        if actual is None or not compare_outputs(actual, str(expected)):
                            file_errors.append(f"File output mismatch: {rel}")
                    item["passed"] = stdout_ok and not file_errors
                    item["status"] = "passed" if item["passed"] else "wrong_answer"
                    item["feedback"] = "Output matched." if item["passed"] else ("Standard output differs." if not stdout_ok else "; ".join(file_errors))
                    item["file_output_feedback"] = file_errors
                item["returncode"] = run.get("returncode"); item["duration_seconds"] = run.get("duration_seconds")
        except (OSError, ValueError) as exc:
            item["status"] = "invalid_test_case"; item["feedback"] = str(exc)
        evidence.append(item)
    passed = sum(x["passed"] for x in evidence); total = len(evidence)
    return AnalyzerResult("correctness", "ok", round(100 * passed / total, 2),
        evidence={"passed": passed, "total": total, "cases": evidence},
        feedback=f"Passed {passed}/{total} test cases.")
