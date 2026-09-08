#!/usr/bin/env python3
"""Contamination probe for the passage-withheld ("ungrounded") condition.

METHODOLOGY.md requires a contamination check on any borrowed benchmark.
MS MARCO (the QA source) is from 2016 and has almost certainly been in
frontier pretraining data for years. The specific risk this probe targets:
condition (d) withholds the passage to force a genuinely ungrounded
response -- but if the model already knows the answer from pretraining, the
withheld-passage response comes back correct anyway, and (d) silently stops
being "ungrounded" for that item. A weak condition that's secretly fine for
some unknown fraction of items is a design problem, not a footnote.

This probe:
- Draws a sample DISJOINT from the 200-item labeling pool (so nothing here
  is later shown to the same person during blind labeling -- reusing an
  item would mean she's no longer blind to it).
- Generates ONLY the passage-withheld condition for that sample.
- Writes a review file with the passage alongside the withheld-passage
  answer, for a human (not an unvalidated automated judge -- we don't have
  one yet, and using one here would be circular) to mark correct/incorrect.
- A separate scoring step (see main's --score) computes the memorization
  rate once every item is marked.

Usage:
    python -m src.contamination_probe --dry-run     # count and cost, no calls, no key
    python -m src.contamination_probe               # generate, needs ANTHROPIC_API_KEY
    python -m src.contamination_probe --score        # after you've filled in judgments
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src import cache
from src.generate_responses import (
    CONDITIONS,
    build_cache_key,
    build_prompt,
    ensure_key_present,
    estimate_cost,
    estimate_tokens,
    call_model,
)
from src.prepare_dataset import fetch_qa_items
from src.seeding import set_seed
import random

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PASSAGES_PATH = REPO_ROOT / "data" / "raw" / "source_passages.json"
PROBE_OUTPUT_PATH = REPO_ROOT / "outputs" / "contamination_probe.json"

PROBE_SIZE = 40
PROBE_SEED = 2  # distinct from the main run's SEED (0), so probe sampling never collides
UNGROUNDED_CONDITION = CONDITIONS["d"]

# Decision rule, stated in advance per METHODOLOGY.md ("state the decision
# the number supports before looking at the number"): below this rate, the
# ungrounded condition proceeds as designed and the rate itself gets
# reported in Limitations. At or above it, the condition changes before the
# full run -- see ANALYSIS_PLAN.md for what "changes" means in that case.
HIGH_CONTAMINATION_THRESHOLD = 0.25


def select_probe_items() -> list[dict]:
    """40 items disjoint from the 200-item labeling pool."""
    if not SOURCE_PASSAGES_PATH.exists():
        raise FileNotFoundError(f"Missing {SOURCE_PASSAGES_PATH}. Run: python -m src.prepare_dataset")
    labeling_pool = json.loads(SOURCE_PASSAGES_PATH.read_text(encoding="utf-8"))
    used_ids = {item["item_id"] for item in labeling_pool}

    print("Fetching RAGTruth QA pool to sample a disjoint probe set...", file=sys.stderr)
    all_qa_items = fetch_qa_items()
    candidates = {i: item for i, item in all_qa_items.items() if i not in used_ids}

    set_seed(PROBE_SEED)
    sampled_ids = random.sample(sorted(candidates.keys()), PROBE_SIZE)
    return [candidates[i] for i in sampled_ids]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--score", action="store_true", help="Compute the memorization rate from a filled-in review file.")
    args = parser.parse_args()

    load_dotenv()

    if args.score:
        if not PROBE_OUTPUT_PATH.exists():
            print(f"Missing {PROBE_OUTPUT_PATH}. Run the probe first.", file=sys.stderr)
            return 1
        items = json.loads(PROBE_OUTPUT_PATH.read_text(encoding="utf-8"))
        unscored = [i for i in items if i["human_judged_correct"] is None]
        if unscored:
            print(
                f"{len(unscored)} of {len(items)} items still have human_judged_correct: null. "
                "Score every item before computing a rate.",
                file=sys.stderr,
            )
            return 1
        n_correct = sum(1 for i in items if i["human_judged_correct"])
        rate = n_correct / len(items)
        print(f"Memorization rate: {n_correct}/{len(items)} = {rate:.1%}")
        if rate >= HIGH_CONTAMINATION_THRESHOLD:
            print(
                f"At or above the {HIGH_CONTAMINATION_THRESHOLD:.0%} threshold set in advance -- "
                "the ungrounded condition should change before the full run, not proceed with a note."
            )
        else:
            print(f"Below the {HIGH_CONTAMINATION_THRESHOLD:.0%} threshold -- proceed, and report this rate in Limitations.")
        return 0

    probe_items = select_probe_items()
    conditions = {"d": UNGROUNDED_CONDITION}

    if args.dry_run:
        stats = estimate_cost(probe_items, conditions)
        print(f"Probe items (disjoint from the 200-item labeling pool): {len(probe_items)}")
        print(f"Already cached: {stats['calls_cached']}")
        print(f"Calls needed: {stats['calls_needed']}")
        print(f"Estimated cost: ${stats['estimated_cost_usd']:.4f}")
        return 0

    from src.generate_responses import generate_all

    result = generate_all(probe_items, conditions, dry_run=False)

    review = []
    for item in probe_items:
        record = result["all_responses"][item["item_id"]]["d"]
        review.append(
            {
                "item_id": item["item_id"],
                "question": item["question"],
                "passage": item["passage"],
                "withheld_answer": record["text"],
                "human_judged_correct": None,
            }
        )
    PROBE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROBE_OUTPUT_PATH.write_text(json.dumps(review, indent=2), encoding="utf-8")
    print(f"Made {result['made_calls']} new API calls.")
    print(f"Wrote {len(review)} items to {PROBE_OUTPUT_PATH} for review.")
    print("Fill in human_judged_correct (true/false) for each, then run --score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
