from collections.abc import Mapping

from app.core.enums import AttemptVerdict


def validate_evaluation_payload(payload: Mapping[str, object]) -> list[str]:
    """Dependency-free guard for the evaluator's persisted JSON contract."""
    required = {
        "verdict",
        "score",
        "what_is_correct",
        "what_is_wrong",
        "missing_points",
        "short_explanation",
    }
    issues = [f"Missing field: {field}" for field in sorted(required - set(payload))]
    if payload.get("verdict") not in {item.value for item in AttemptVerdict}:
        issues.append("Invalid verdict")
    score = payload.get("score")
    if not isinstance(score, int | float) or isinstance(score, bool) or not 0 <= score <= 1:
        issues.append("Score must be between 0 and 1")
    for field in ("what_is_correct", "what_is_wrong", "missing_points"):
        if field in payload and (
            not isinstance(payload[field], list)
            or not all(isinstance(item, str) for item in payload[field])
        ):
            issues.append(f"{field} must be a list of strings")
    if "short_explanation" in payload and not isinstance(payload["short_explanation"], str):
        issues.append("short_explanation must be a string")
    return issues
