
import json
from pathlib import Path
from datetime import datetime, timezone


def write_reports(report, output_dir="reports"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    json_path = out / "grade_report.json"
    text_path = out / "grade_report.txt"

    # Write the complete JSON report.
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "AUTOGRADER REPORT",
        "=" * 50,
        f"Source: {report.get('source_file')}",
        f"Overall score: {report.get('overall_score')}/100",
        f"Grade status: {report.get('grade_status', 'complete')}",
    ]

    # Include raw score and score-cap information when available.
    score_summary = report.get("score_summary")

    if score_summary:
        lines += [
            "",
            "SCORING SUMMARY",
            "-" * 50,
            (
                "Raw weighted score: "
                f"{score_summary.get('raw_weighted_score')}/100"
            ),
            f"Final score: {score_summary.get('final_score')}/100",
            f"Score cap: {score_summary.get('score_cap')}",
            f"Cap applied: {score_summary.get('cap_applied')}",
        ]

        cap_reason = score_summary.get("cap_reason")

        if cap_reason:
            lines.append(f"Cap reason: {cap_reason}")

    first_pass = report.get("first_pass")
    if first_pass:
        lines += ["", "FIRST-PASS CHECK", "-" * 50,
                  f"Compiled: {first_pass.get('compiled')}",
                  f"Smoke test: {first_pass.get('smoke_status')}",
                  f"Suspected infinite loop: {first_pass.get('suspected_infinite_loop')}"]
        sanity = first_pass.get("static_sanity") or {}
        for check, passed in sanity.items():
            lines.append(f"  {check}: {passed}")

    # Include individual metric results.
    lines += [
        "",
        "METRICS",
        "-" * 50,
    ]

    for name, metric in report.get("metrics", {}).items():
        lines += [
            (
                f"{name}: {metric.get('score')} "
                f"(weight={metric.get('weight')}, "
                f"effective_weight={metric.get('effective_weight')}, "
                f"contribution={metric.get('contribution')}, "
                f"threshold={metric.get('threshold')}, "
                f"threshold_met={metric.get('threshold_met')})"
            ),
            "  " + str(metric.get("feedback", "")),
        ]

        evidence = metric.get("evidence") or {}

        # Print correctness test evidence.
        if isinstance(evidence, dict):
            for case in evidence.get("cases", []):
                if not case.get("passed", True):
                    lines += [
                        f"  Failing case: {case.get('name')}",
                        f"    Status: {case.get('status')}",
                        f"    Input: {case.get('input')!r}",
                        (
                            "    Expected: "
                            f"{case.get('expected_output')!r}"
                        ),
                        (
                            "    Actual: "
                            f"{case.get('actual_output')!r}"
                        ),
                        (
                            "    Reason: "
                            f"{case.get('feedback', case.get('status'))}"
                        ),
                    ]

    flags = report.get("flags", [])
    if flags:
        lines += ["", "FLAGS FOR REVIEW", "-" * 50]
        for flag in flags:
            lines.append(str(flag))

    # Include compilation and general errors.
    errors = report.get("errors", [])

    if errors:
        lines += [
            "",
            "ERRORS",
            "-" * 50,
        ]

        for error in errors:
            lines.append(str(error))

    usefulness = report.get("usefulness_limitations", {})
    if usefulness:
        lines += ["", "USEFULNESS IN REAL-LIFE SETTINGS", "-" * 50]
        for item in usefulness.get("usefulness", []):
            lines += [f"- {item.get('use_case')}: {item.get('example')}",
                      f"  Benefit: {item.get('benefit')}"]
        lines += ["", "CONCRETE LIMITATIONS", "-" * 50]
        for item in usefulness.get("limitations", []):
            lines += [f"- {item.get('limitation')}: {item.get('example')}"]

    # Include documented limitations.
    lines += [
        "",
        "LIMITATIONS",
        "-" * 50,
    ]

    for limitation in report.get(
        "limitations",
        [
            "Heuristic metrics are not formal proofs.",
            "Timeout is not a secure sandbox.",
        ],
    ):
        lines.append(f"- {limitation}")

    text_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return {
        "json": str(json_path),
        "text": str(text_path),
    }
