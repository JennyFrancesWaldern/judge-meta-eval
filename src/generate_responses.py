#!/usr/bin/env python3
"""Generate response pairs for judge-meta-eval labeling. See ANALYSIS_PLAN.md
section 2 for the design and cost estimate this implements.

Idempotent and resumable: every (item, condition, seed, temperature) call is
cached in cache/, keyed on the full administration condition that would
produce it. Rerunning after a crash re-reads whatever is already cached and
only pays for what is missing -- it never re-calls or double-charges for a
condition that already succeeded.

Use --dry-run to see the exact call count and cost estimate for every
component (core generation, the self-preference bracket, the variance
subset) without making any calls and without needing an API key. Real runs
fail loudly, lazily and per-call, if a required key is missing -- a run
fully satisfied by cache never needs a key at all.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src import cache
from src.seeding import set_seed

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PASSAGES_PATH = REPO_ROOT / "data" / "raw" / "source_passages.json"
ALL_RESPONSES_PATH = REPO_ROOT / "data" / "generated" / "all_responses.json"
RESPONSE_PAIRS_PATH = REPO_ROOT / "data" / "generated" / "response_pairs.json"
BRACKET_RESPONSES_PATH = REPO_ROOT / "data" / "generated" / "self_pref_bracket_responses.json"
VARIANCE_RESPONSES_PATH = REPO_ROOT / "data" / "generated" / "variance_subset_responses.json"

# Fixed per ANALYSIS_PLAN.md section 3 (administration conditions are
# deliberately NOT crossed during generation) -- recorded on every response
# anyway, per the requirement that a constant is still a condition value.
PROMPT_FORMAT = "plain_v1"
FEW_SHOT_DRAW = "zero_shot"
TEMPERATURE = 0.0
SEED = 0

# See ANALYSIS_PLAN.md section 2, "Revision 2026-09-07" for why this is
# 3 models / 4 conditions rather than the original 2/3.
CONDITIONS = {
    "a": {"provider": "anthropic", "model": "claude-sonnet-5", "passage_included": True, "label": "strong"},
    "b": {"provider": "openai", "model": "gpt-5.4-mini", "passage_included": True, "label": "moderate_cross_family"},
    "c": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "passage_included": True, "label": "weak"},
    "d": {"provider": "anthropic", "model": "claude-sonnet-5", "passage_included": False, "label": "ungrounded"},
}

# Item index % 4 selects which two conditions are paired for human labeling.
# Guarantees the cross-family pairs (a_b, b_d) get real coverage rather than
# being crowded out by same-family comparisons -- see ANALYSIS_PLAN.md.
PAIR_SCHEDULE = ["a_b", "a_c", "a_d", "b_d"]
CROSS_FAMILY_PAIR_TYPES = {"a_b", "b_d"}

# Self-preference bracket (ANALYSIS_PLAN.md section 2, "Revision 2026-09-08"):
# gpt-5.4-mini and Claude Sonnet 5 are not a capability-matched cross-family
# pair -- see that section for why price parity turned out not to mean
# capability parity here. This condition is generated ONLY for the items
# whose scheduled pair-type is cross-family, and is NOT added to human
# labeling (it would double that subset's labeling load). It exists purely
# so Phase 3 can compare the judge's family preference against a SECOND,
# differently-tiered cross-family model, bracketing Sonnet 5 from the other
# side of gpt-5.4-mini.
BRACKET_CONDITION = {
    "provider": "openai",
    "model": "gpt-5.6-sol",
    "passage_included": True,
    "label": "cross_family_flagship_bracket",
}

# Second-seed variance subset (ANALYSIS_PLAN.md section on variance
# components): a stratified 50-item subset, one item from every 4th
# position across all 4 pair-type groups, redrawn under SECOND_SEED. Uses a
# NONZERO temperature -- at TEMPERATURE = 0.0 a second seed would not
# actually produce different output, so it would measure nothing. This
# subset therefore measures sampling variance AT TEMPERATURE 0.7
# specifically, not the (near-zero-by-construction) variance of the main
# temperature-0.0 dataset. That distinction goes in ANALYSIS_PLAN.md, not
# just here.
SECOND_SEED = 1
VARIANCE_SUBSET_TEMPERATURE = 0.7
VARIANCE_SUBSET_SIZE = 50

ESTIMATED_OUTPUT_TOKENS = 150  # the response doesn't exist yet; this stays a flat assumption

# USD per million tokens (input, output). Checked directly against
# claude.com/pricing and developers.openai.com/api/docs/pricing on
# 2026-09-07/08 -- see ANALYSIS_PLAN.md section 2. Re-verify before relying
# on this if run much later; these rates change.
PRICING_PER_M = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.6-sol": (4.0, 20.0),
}


def build_cache_key(
    item_id: str, condition_name: str, cond: dict, seed: int = SEED, temperature: float = TEMPERATURE
) -> str:
    """The full administration condition, as a stable JSON string. This is
    the cache key -- if it isn't in here, it can't be recovered from cache."""
    return json.dumps(
        {
            "item_id": item_id,
            "condition_name": condition_name,
            "model": cond["model"],
            "provider": cond["provider"],
            "passage_included": cond["passage_included"],
            "prompt_format": PROMPT_FORMAT,
            "few_shot_draw": FEW_SHOT_DRAW,
            "temperature": temperature,
            "seed": seed,
        },
        sort_keys=True,
    )


def build_prompt(item: dict, cond: dict) -> str:
    if cond["passage_included"]:
        return (
            f"Passage:\n{item['passage']}\n\n"
            f"Question: {item['question']}\n\n"
            "Answer the question using only the passage above."
        )
    return f"Question: {item['question']}\n\nAnswer from your own knowledge."


def call_model(provider: str, model: str, prompt: str, temperature: float) -> str:
    """Make the actual API call. Imports are lazy so dry-run and tests never
    need network access or credentials just to load this module."""
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        resp = client.messages.create(
            model=model,
            max_tokens=400,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    if provider == "openai":
        import openai

        client = openai.OpenAI()  # reads OPENAI_API_KEY
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
    raise ValueError(f"unknown provider {provider!r}")


REQUIRED_ENV_VAR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def ensure_key_present(provider: str) -> None:
    """Checked lazily, right before a call that can't be served from cache
    -- NOT upfront for the whole run, so a run fully satisfied by cache
    never needs a key at all (a reader can reproduce from cache alone)."""
    env_var = REQUIRED_ENV_VAR[provider]
    if not os.environ.get(env_var):
        raise RuntimeError(
            f"Missing required environment variable: {env_var}. Set it "
            "(e.g. in a .env file) before this call can be made. This "
            "script refuses to fall back to a mock or a different provider."
        )


def estimate_tokens(text: str) -> int:
    """~4 chars/token, the standard rough heuristic absent a real tokenizer.
    Applied to the actual built prompt, not a flat assumption, whenever real
    source items are available."""
    return max(1, len(text) // 4)


def estimate_cost(items: list[dict], conditions: dict, seed: int = SEED, temperature: float = TEMPERATURE) -> dict:
    """Cost of whatever is NOT already cached, for the given items/conditions/
    seed/temperature. Never makes a call. Input tokens are estimated from the
    real prompt text; output tokens remain a flat assumption."""
    calls_needed = 0
    calls_cached = 0
    cost = 0.0
    for item in items:
        for condition_name, cond in conditions.items():
            key = build_cache_key(item["item_id"], condition_name, cond, seed=seed, temperature=temperature)
            if cache.get(key) is not None:
                calls_cached += 1
                continue
            calls_needed += 1
            input_tokens = estimate_tokens(build_prompt(item, cond))
            in_price, out_price = PRICING_PER_M[cond["model"]]
            cost += (input_tokens / 1_000_000) * in_price
            cost += (ESTIMATED_OUTPUT_TOKENS / 1_000_000) * out_price
    return {
        "calls_needed": calls_needed,
        "calls_cached": calls_cached,
        "estimated_cost_usd": round(cost, 4),
    }


def generate_all(
    items: list[dict], conditions: dict, dry_run: bool, seed: int = SEED, temperature: float = TEMPERATURE
) -> dict:
    all_responses: dict[str, dict] = {}
    made_calls = 0
    for item in items:
        all_responses[item["item_id"]] = {}
        for condition_name, cond in conditions.items():
            key = build_cache_key(item["item_id"], condition_name, cond, seed=seed, temperature=temperature)
            cached_record = cache.get(key)
            if cached_record is not None:
                all_responses[item["item_id"]][condition_name] = cached_record
                continue
            if dry_run:
                continue
            ensure_key_present(cond["provider"])
            prompt = build_prompt(item, cond)
            text = call_model(cond["provider"], cond["model"], prompt, temperature)
            record = {
                "text": text,
                "model": cond["model"],
                "provider": cond["provider"],
                "condition": condition_name,
                "label": cond["label"],
                "passage_included": cond["passage_included"],
                "prompt_format": PROMPT_FORMAT,
                "few_shot_draw": FEW_SHOT_DRAW,
                "temperature": temperature,
                "seed": seed,
                "item_id": item["item_id"],
                "generated_at_ms": int(time.time() * 1000),
            }
            cache.set(key, record)
            all_responses[item["item_id"]][condition_name] = record
            made_calls += 1
    return {"all_responses": all_responses, "made_calls": made_calls}


def build_response_pairs(items: list[dict], all_responses: dict) -> list[dict]:
    """One labeled pair per item, per PAIR_SCHEDULE. Skips items whose
    scheduled pair isn't fully generated yet (e.g. a partial resume)."""
    pairs = []
    for i, item in enumerate(items):
        pair_type = PAIR_SCHEDULE[i % len(PAIR_SCHEDULE)]
        cond_1, cond_2 = pair_type.split("_")
        responses = all_responses.get(item["item_id"], {})
        if cond_1 not in responses or cond_2 not in responses:
            continue
        pairs.append(
            {
                "item_id": item["item_id"],
                "pair_type": pair_type,
                "passage": item["passage"],
                "question": item["question"],
                "response_1": responses[cond_1],
                "response_2": responses[cond_2],
            }
        )
    return pairs


def select_cross_family_items(items: list[dict]) -> list[dict]:
    """The subset whose scheduled pair-type already involves the mini-tier
    cross-family model -- these are the items the self-preference bracket
    (gpt-5.6-sol) is generated for."""
    return [item for i, item in enumerate(items) if PAIR_SCHEDULE[i % len(PAIR_SCHEDULE)] in CROSS_FAMILY_PAIR_TYPES]


def select_variance_subset(items: list[dict], n: int = VARIANCE_SUBSET_SIZE) -> list[dict]:
    """A stratified subset covering all 4 pair-type groups roughly evenly,
    for the second-seed variance measurement."""
    groups: dict[str, list[dict]] = {p: [] for p in PAIR_SCHEDULE}
    for i, item in enumerate(items):
        groups[PAIR_SCHEDULE[i % len(PAIR_SCHEDULE)]].append(item)
    per_group = n // len(PAIR_SCHEDULE)
    subset = []
    for pair_type in PAIR_SCHEDULE:
        subset.extend(groups[pair_type][:per_group])
    return subset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print call count and cost, make no calls.")
    parser.add_argument(
        "--component",
        choices=["core", "bracket", "variance", "all"],
        default="all",
        help="Which piece to run/estimate.",
    )
    args = parser.parse_args()

    load_dotenv()

    if not SOURCE_PASSAGES_PATH.exists():
        print(
            f"Missing {SOURCE_PASSAGES_PATH}. Run: python -m src.prepare_dataset",
            file=sys.stderr,
        )
        return 1
    items = json.loads(SOURCE_PASSAGES_PATH.read_text(encoding="utf-8"))
    set_seed(SEED)

    cross_family_items = select_cross_family_items(items)
    variance_items = select_variance_subset(items)

    components = []
    if args.component in ("core", "all"):
        components.append(("core (4 conditions x 200 items)", items, CONDITIONS, SEED, TEMPERATURE))
    if args.component in ("bracket", "all"):
        components.append(
            (
                f"self-preference bracket (gpt-5.6-sol x {len(cross_family_items)} items)",
                cross_family_items,
                {"e": BRACKET_CONDITION},
                SEED,
                TEMPERATURE,
            )
        )
    if args.component in ("variance", "all"):
        components.append(
            (
                f"variance subset (4 conditions x {len(variance_items)} items, seed={SECOND_SEED}, temp={VARIANCE_SUBSET_TEMPERATURE})",
                variance_items,
                CONDITIONS,
                SECOND_SEED,
                VARIANCE_SUBSET_TEMPERATURE,
            )
        )

    if args.dry_run:
        grand_total = 0.0
        for label, comp_items, comp_conditions, seed, temperature in components:
            stats = estimate_cost(comp_items, comp_conditions, seed=seed, temperature=temperature)
            print(f"--- {label} ---")
            print(f"  Already cached: {stats['calls_cached']}")
            print(f"  Calls needed: {stats['calls_needed']}")
            print(f"  Estimated cost of remaining calls: ${stats['estimated_cost_usd']:.4f}")
            grand_total += stats["estimated_cost_usd"]
        print(f"=== Grand total across selected components: ${grand_total:.4f} ===")
        return 0

    for label, comp_items, comp_conditions, seed, temperature in components:
        result = generate_all(comp_items, comp_conditions, dry_run=False, seed=seed, temperature=temperature)
        print(f"{label}: made {result['made_calls']} new API calls this run.")

        if comp_conditions is CONDITIONS and seed == SEED and temperature == TEMPERATURE:
            pairs = build_response_pairs(items, result["all_responses"])
            ALL_RESPONSES_PATH.parent.mkdir(parents=True, exist_ok=True)
            ALL_RESPONSES_PATH.write_text(json.dumps(result["all_responses"], indent=2), encoding="utf-8")
            RESPONSE_PAIRS_PATH.write_text(json.dumps(pairs, indent=2), encoding="utf-8")
            print(f"  Wrote {len(pairs)} response pairs to {RESPONSE_PAIRS_PATH}")
        elif "e" in comp_conditions:
            BRACKET_RESPONSES_PATH.write_text(json.dumps(result["all_responses"], indent=2), encoding="utf-8")
            print(f"  Wrote bracket responses to {BRACKET_RESPONSES_PATH}")
        else:
            VARIANCE_RESPONSES_PATH.write_text(json.dumps(result["all_responses"], indent=2), encoding="utf-8")
            print(f"  Wrote variance-subset responses to {VARIANCE_RESPONSES_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
