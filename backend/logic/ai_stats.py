"""What the ai_generations log says about quality, speed and cost, per call kind and prompt version."""
import json
import re
from collections import Counter
from statistics import median

from core import db


def _p95(values: list[int]) -> int | None:
    values = sorted(v for v in values if v is not None)
    return values[min(len(values) - 1, round(0.95 * (len(values) - 1)))] if values else None


def violation_key(error: str) -> str:
    """'Week 7: days sum to 455 TSS' and 'Week 3: days sum to 210 TSS' count as the same problem."""
    return re.sub(r"\d+(\.\d+)?", "N", error)


def report(days: int = 30) -> list[dict]:
    rows = db.query(
        "SELECT kind, prompt_version, attempt, ok, errors, latency_ms, input_tokens, output_tokens"
        " FROM ai_generations WHERE created_at >= datetime('now', ?) ORDER BY id",
        [f"-{days} days"],
    )
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["kind"], row["prompt_version"]), []).append(row)

    result = []
    for (kind, version), calls in sorted(groups.items()):
        starts = [c for c in calls if c["attempt"] == 1]  # every generation begins with attempt 1
        violations = Counter(violation_key(e) for c in calls for e in json.loads(c["errors"]))
        latencies = [c["latency_ms"] for c in calls if c["latency_ms"] is not None]
        result.append({
            "kind": kind,
            "prompt_version": version,
            "generations": len(starts),
            "calls": len(calls),
            "first_try": sum(c["ok"] for c in starts),
            "succeeded": sum(c["ok"] for c in calls),
            "latency_p50_ms": round(median(latencies)) if latencies else None,
            "latency_p95_ms": _p95(latencies),
            "input_tokens": sum(c["input_tokens"] or 0 for c in calls),
            "output_tokens": sum(c["output_tokens"] or 0 for c in calls),
            "top_violations": violations.most_common(3),
        })
    return result
