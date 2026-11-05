"""Generate representative, reproducible sample reports for the project deliverable."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "sample_outputs"
OUT.mkdir(parents=True, exist_ok=True)
cases = ROOT / "tests" / "sample_cases.json"
rules = ROOT / "rules" / "rules.json"
samples = {
    "correct_submission": ROOT / "tests" / "inputs" / "assignment_sample_add.c",
    "wrong_answer": ROOT / "tests" / "inputs" / "wrong_sum.c",
    "compile_failure": ROOT / "tests" / "inputs" / "compile_error.c",
    "infinite_loop": ROOT / "tests" / "inputs" / "infinite_loop.c",
    "memory_error": ROOT / "tests" / "inputs" / "memory_error.c",
}
for label, source in samples.items():
    destination = OUT / label
    command = [
        sys.executable, "-m", "src.main", "--source", str(source),
        "--tests", str(cases), "--rules", str(rules),
        "--output-dir", str(destination),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
    (destination / "generation.log").write_text(
        "COMMAND: " + " ".join(command) + "\nEXIT: " + str(completed.returncode)
        + "\nSTDOUT:\n" + completed.stdout + "\nSTDERR:\n" + completed.stderr,
        encoding="utf-8",
    )
    print(label, "report generated" if (destination / "grade_report.json").exists() else "FAILED")
