#!/usr/bin/env python3
"""Automated, code-only memorization flag for the main 200-item labeling pool.

The contamination probe (src/contamination_probe.py) gives an overall
memorization RATE from a disjoint sample -- it deliberately can't say which
of the 200 actual labeling-pool items are affected, because looking at
those items' withheld-passage answers herself would compromise blinding.

This script instead flags items MECHANICALLY, using only the already-
generated condition (d) responses from the core run (data/generated/
all_responses.json) -- no human ever looks at the withheld-passage text to
produce this flag, so it does not touch blinding at all.

What it catches: distinctive, hard-to-guess facts in the passage (phone
numbers, dollar amounts, percentages, large numbers, multi-word proper-noun
phrases) that also appear verbatim in the withheld-passage response. A
single such match is a strong signal the model already knew the specific
answer without the passage.

What it misses: memorization of diffuse, non-numeric passage content with
no distinctive extractable fact (e.g., a paraphrased description). This is
a supplement to the contamination-probe rate, not a replacement -- it will
under-count, not over-count.

Output: a flag per item (not an exclusion). The plan is to run the primary
analysis on the full 200-item pool and report a sensitivity check with
flagged items removed, rather than silently dropping items based on a
coarse heuristic.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PASSAGES_PATH = REPO_ROOT / "data" / "raw" / "source_passages.json"
ALL_RESPONSES_PATH = REPO_ROOT / "data" / "generated" / "all_responses.json"
FLAGS_OUTPUT_PATH = REPO_ROOT / "outputs" / "memorization_flags.json"

PHONE_RE = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
MONEY_RE = re.compile(r"\$\d[\d,]*(?:\.\d+)?")
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?%")
BIG_NUMBER_RE = re.compile(r"\b\d{4,}\b")  # 4+ digits -- short numbers are too common to be distinctive
PROPER_NOUN_RE = re.compile(r"\b(?:[A-Z][a-z]+\s){1,3}[A-Z][a-z]+\b")  # 2-4 word capitalized phrases


def extract_distinctive_facts(passage: str, question: str) -> set[str]:
    """Facts pulled from the passage that the question doesn't already give away."""
    question_lower = question.lower()
    facts = set()
    for pattern in (PHONE_RE, MONEY_RE, PERCENT_RE, BIG_NUMBER_RE, PROPER_NOUN_RE):
        for match in pattern.findall(passage):
            if match.lower() not in question_lower:
                facts.add(match)
    return facts


def flag_item(passage: str, question: str, withheld_response: str) -> dict:
    facts = extract_distinctive_facts(passage, question)
    matched = {f for f in facts if f in withheld_response}
    return {
        "distinctive_facts_found": len(facts),
        "matched_in_withheld_response": sorted(matched),
        "likely_memorized": len(matched) >= 1,
    }


def flag_all(items: list[dict], all_responses: dict) -> list[dict]:
    results = []
    for item in items:
        d_response = all_responses.get(item["item_id"], {}).get("d")
        if d_response is None:
            continue
        flag = flag_item(item["passage"], item["question"], d_response["text"])
        results.append({"item_id": item["item_id"], **flag})
    return results


def main() -> int:
    if not SOURCE_PASSAGES_PATH.exists():
        print(f"Missing {SOURCE_PASSAGES_PATH}. Run: python -m src.prepare_dataset", file=sys.stderr)
        return 1
    if not ALL_RESPONSES_PATH.exists():
        print(
            f"Missing {ALL_RESPONSES_PATH}. Run the core generation first: python -m src.generate_responses --component core",
            file=sys.stderr,
        )
        return 1

    items = json.loads(SOURCE_PASSAGES_PATH.read_text(encoding="utf-8"))
    all_responses = json.loads(ALL_RESPONSES_PATH.read_text(encoding="utf-8"))

    flags = flag_all(items, all_responses)
    n_flagged = sum(1 for f in flags if f["likely_memorized"])

    FLAGS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAGS_OUTPUT_PATH.write_text(json.dumps(flags, indent=2), encoding="utf-8")
    print(f"Flagged {n_flagged} of {len(flags)} items as likely memorized (mechanical check, no human review).")
    print(f"Wrote {FLAGS_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
