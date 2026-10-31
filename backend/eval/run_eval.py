"""Measures how accurately an extractor turns criteria text into structured rules.

Usage:
    python eval/run_eval.py                 # rule-based extractor (offline)
    ANTHROPIC_API_KEY=... python eval/run_eval.py --extractor llm

Each labeled example is one criterion bullet with its expected category,
field, operator and value. Metrics:

- category accuracy: right kind of rule (lab, condition, medication, ...)
- exact match: category, field, operator and value(s) all correct
- unsafe rate: the extractor produced a checkable rule that is wrong.
  This is the number that matters most: a wrong rule can wrongly exclude
  (or include) a patient, while "other" only asks a human to review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trialmatch.criteria_rules import classify  # noqa: E402
from trialmatch.models import Criterion  # noqa: E402

HERE = Path(__file__).parent


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def values_equal(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return str(a).lower() == str(b).lower()


def is_exact(pred: Criterion, exp: dict) -> bool:
    if pred.category.value != exp["category"]:
        return False
    if exp["category"] == "other":
        return True
    if pred.field != exp["field"] or pred.operator != exp["operator"]:
        return False
    if exp["category"] == "pregnancy":
        return True  # the value is a free-text label
    return values_equal(pred.value, exp["value"]) and values_equal(pred.value_max, exp["value_max"])


def extract_with(name: str):
    if name == "rules":
        return lambda kind, text: classify(kind, text)
    import anthropic

    from trialmatch.criteria_llm import LLMExtractor

    llm = LLMExtractor(anthropic.Anthropic().messages, os.getenv("LLM_MODEL", "claude-haiku-5-5"))

    def run(kind: str, text: str) -> Criterion:
        header = "Inclusion Criteria:" if kind == "inclusion" else "Exclusion Criteria:"
        items = llm.extract(f"{header}\n\n* {text}")
        return items[0] if items else Criterion(kind=kind, category="other", text=text)

    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extractor", choices=["rules", "llm"], default="rules")
    parser.add_argument("--data", type=Path, default=HERE / "heldout_set.jsonl")
    parser.add_argument("--write", type=Path, default=None, help="Write a markdown report here.")
    args = parser.parse_args()

    examples = load(args.data)
    extract = extract_with(args.extractor)
    started = time.perf_counter()

    category_ok = exact_ok = unsafe = structured_expected = structured_found = 0
    misses: list[str] = []
    by_category: dict[str, list[int]] = {}
    for ex in examples:
        exp = ex["expected"]
        pred = extract(ex["kind"], ex["text"])
        cat_hit = pred.category.value == exp["category"]
        exact = is_exact(pred, exp)
        category_ok += cat_hit
        exact_ok += exact
        stats = by_category.setdefault(exp["category"], [0, 0])
        stats[0] += exact
        stats[1] += 1
        if exp["category"] != "other":
            structured_expected += 1
            structured_found += exact
        if pred.is_structured and not exact:
            unsafe += 1
        if not exact:
            got = f"{pred.category.value} {pred.field} {pred.operator} {pred.value} {pred.value_max or ''}".strip()
            misses.append(f"| {ex['text'][:70]} | {exp['category']} {exp['field'] or ''} {exp['operator'] or ''} {exp['value'] or ''} | {got} |")

    n = len(examples)
    elapsed = time.perf_counter() - started
    lines = [
        f"# Extraction eval: `{args.extractor}`",
        "",
        f"{n} labeled criteria · {elapsed:.1f}s",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Category accuracy | **{category_ok / n:.0%}** ({category_ok}/{n}) |",
        f"| Exact structured match | **{exact_ok / n:.0%}** ({exact_ok}/{n}) |",
        f"| Recall on checkable criteria | **{structured_found / structured_expected:.0%}** ({structured_found}/{structured_expected}) |",
        f"| Unsafe rate (wrong checkable rule) | **{unsafe / n:.0%}** ({unsafe}/{n}) |",
        "",
        "| Category | Exact |",
        "|---|---|",
        *[f"| {cat} | {ok}/{total} |" for cat, (ok, total) in sorted(by_category.items())],
    ]
    if misses:
        lines += ["", "## Misses", "", "| Criterion | Expected | Got |", "|---|---|---|", *misses]
    report = "\n".join(lines)
    print(report)
    if args.write:
        args.write.write_text(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
