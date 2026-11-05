
import json
import math
from pathlib import Path


def load_rules(path="rules/rules.json"):
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_rules(rules)
    return rules


def validate_rules(rules):
    if rules.get("score_scale") != 100:
        raise ValueError("Unsupported score scale")

    policy = rules.get("missing_metric_policy")
    if policy not in ("error", "renormalize_skipped"):
        raise ValueError(
            "missing_metric_policy must be 'error' or "
            "'renormalize_skipped'"
        )

    metrics = rules.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("metrics must be a non-empty object")

    enabled = {
        name: config
        for name, config in metrics.items()
        if isinstance(config, dict) and config.get("enabled") is True
    }

    if not enabled:
        raise ValueError("At least one metric must be enabled")

    weights = []

    for name, config in enabled.items():
        weight = config.get("weight")
        threshold = config.get("threshold", 0)
        if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                or not math.isfinite(threshold) or not 0 <= threshold <= 100):
            raise ValueError(f"Invalid threshold: {name}; expected 0..100")

        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(weight)
            or weight < 0
        ):
            raise ValueError(f"Invalid weight: {name}")

        weights.append(weight)

    if not math.isclose(sum(weights), 1.0, abs_tol=1e-9):
        raise ValueError("Enabled weights must sum to 1.0")

    validate_grading_policy(rules)


def validate_grading_policy(rules):
    """
    Validate the optional grading policy.

    If the policy is not supplied, score capping remains disabled.
    """

    grading_policy = rules.get("grading_policy", {})

    if not isinstance(grading_policy, dict):
        raise ValueError("grading_policy must be an object")

    cap_rule = grading_policy.get("all_correctness_tests_fail", {})

    if not isinstance(cap_rule, dict):
        raise ValueError(
            "grading_policy.all_correctness_tests_fail must be an object"
        )

    enabled = cap_rule.get("enabled", False)

    if not isinstance(enabled, bool):
        raise ValueError(
            "grading_policy.all_correctness_tests_fail.enabled "
            "must be a boolean"
        )

    if not enabled:
        return

    score_cap = cap_rule.get("score_cap")

    if (
        isinstance(score_cap, bool)
        or not isinstance(score_cap, (int, float))
        or not math.isfinite(score_cap)
        or not 0 <= score_cap <= 100
    ):
        raise ValueError(
            "score_cap must be a finite number between 0 and 100"
        )

    trigger_statuses = cap_rule.get("trigger_statuses")

    if (
        not isinstance(trigger_statuses, list)
        or not trigger_statuses
        or any(
            not isinstance(status, str) or not status.strip()
            for status in trigger_statuses
        )
    ):
        raise ValueError(
            "trigger_statuses must be a non-empty list of strings"
        )


def should_apply_score_cap(rules, by_name):
    """
    Determine whether the all-correctness-tests-fail cap should apply.

    The cap applies only when:
    - The rule is enabled.
    - Correctness is enabled.
    - Correctness has been evaluated.
    - At least one test case exists.
    - Every test case failed.
    - Every failed case has a triggering status.
    """

    grading_policy = rules.get("grading_policy", {})
    cap_rule = grading_policy.get("all_correctness_tests_fail", {})

    if not cap_rule.get("enabled", False):
        return False, None, None

    correctness_config = rules["metrics"].get("correctness", {})

    if not correctness_config.get("enabled", False):
        return False, None, None

    correctness_result = by_name.get("correctness")

    if correctness_result is None:
        return False, None, None

    if correctness_result.get("status") != "ok":
        return False, None, None

    evidence = correctness_result.get("evidence")

    if not isinstance(evidence, dict):
        return False, None, None

    cases = evidence.get("cases")

    if not isinstance(cases, list) or not cases:
        return False, None, None

    trigger_statuses = set(cap_rule["trigger_statuses"])

    # Every case must have failed.
    if any(case.get("passed") is True for case in cases):
        return False, None, None

    # Every case must have a recognized timeout/runtime failure status.
    if any(
        case.get("status") not in trigger_statuses
        for case in cases
    ):
        return False, None, None

    score_cap = cap_rule["score_cap"]

    reason = (
        "All correctness test cases failed due to timeout "
        "or runtime failure."
    )

    return True, score_cap, reason


def calculate_score(rules, results):
    validate_rules(rules)

    by_name = {}

    for result in results:
        name = result["name"]

        if name in by_name:
            raise ValueError(f"Duplicate result: {name}")

        by_name[name] = result

    policy = rules["missing_metric_policy"]
    scoreable = []
    skipped = []

    for name, config in rules["metrics"].items():
        if not config.get("enabled", False):
            continue

        result = by_name.get(name)

        if result is None:
            raise ValueError(f"Metric {name} is missing")

        if result.get("status") in ("skipped", "error"):
            if policy == "renormalize_skipped":
                skipped.append({
                    "name": name,
                    "weight": config["weight"],
                    "reason": result.get("feedback", f"Metric status: {result.get('status')}"),
                    "status": result.get("status"),
                })
                continue
            raise ValueError(f"Metric {name} was {result.get('status')}")

        if result.get("status") != "ok":
            raise ValueError(f"Metric {name} is not scoreable: {result.get('status')}")

        score = result.get("score")

        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 100
        ):
            raise ValueError(f"Invalid score: {name}")

        scoreable.append((name, config, result, score))

    active_weight = sum(
        config["weight"]
        for _, config, _, _ in scoreable
    )

    if active_weight <= 0:
        raise ValueError("No positive weight remains for scoreable metrics")

    total = 0.0
    metric_details = {}

    for name, config, result, score in scoreable:
        original_weight = config["weight"]
        effective_weight = original_weight / active_weight
        contribution = score * effective_weight
        total += contribution

        threshold = config.get("threshold", 0)
        metric_details[name] = {
            "score": score,
            "threshold": threshold,
            "threshold_met": score >= threshold,
            "weight": original_weight,
            "effective_weight": round(effective_weight, 6),
            "contribution": round(contribution, 2),
            "evidence": result.get("evidence"),
            "feedback": result.get("feedback", ""),
        }

    # Preserve the original weighted score before applying any cap.
    raw_weighted_score = round(total, 2)

    # Apply the configurable grading policy.
    cap_applied, score_cap, cap_reason = should_apply_score_cap(
        rules,
        by_name,
    )

    final_score = raw_weighted_score

    if cap_applied:
        final_score = min(raw_weighted_score, score_cap)

    score_calculation = {
        "overall_score": round(final_score, 2),
        "raw_weighted_score": raw_weighted_score,
        "score_scale": 100,
        "missing_metric_policy": policy,
        "metrics": metric_details,
        "skipped_metrics": skipped,
        "original_active_weight": 1.0,
        "scoreable_weight": round(active_weight, 6),
        "score_cap": score_cap,
        "cap_applied": cap_applied,
        "cap_reason": cap_reason,
    }

    return score_calculation
