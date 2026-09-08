#!/usr/bin/env python3
"""Generate response pairs for judge-meta-eval labeling. See ANALYSIS_PLAN.md
section 2 for the design and cost estimate this implements.

Idempotent and resumable: every (item, condition) call is cached in cache/,
keyed on the full administration condition that would produce it (model,
prompt format, few-shot draw, temperature, seed, passage-inclusion, item
id). Rerunning after a crash re-reads whatever is already cached and only
pays for what is missing -- it never re-calls or double-charges for a
condition that already succeeded.

Use --dry-run to see the exact call count and cost estimate without making
any calls and without needing an API key. Real runs fail loudly if a
required key is missing, rather than falling back to anything.
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

ESTIMATED_OUTPUT_TOKENS = 150  # the response doesn't exist yet; this stays a flat assumption

# USD per million tokens (input, output). Checked directly against
# claude.com/pricing and platform.openai.com/docs on 2026-09-07 -- see
# ANALYSIS_PLAN.md section 2. Re-verify before relying on this if run much
# later; these rates change.
PRICING_PER_M = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "gpt-5.4-mini": (0.75, 4.50),
}


def build_cache_key(item_id: str, condition_name: str, cond: dict) -> str:
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
            "temperature": TEMPERATURE,
            "seed": SEED,
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


def check_required_keys(conditions: dict) -> None:
    """Checked by the CLI's --dry-run summary only, to warn what a real run
    would need. NOT called unconditionally by generate_all -- see
    ensure_key_present, which checks lazily, per call, so a run that's
    fully satisfied by cache never needs a key at all."""
    providers = {c["provider"] for c in conditions.values()}
    missing = [REQUIRED_ENV_VAR[p] for p in providers if not os.environ.get(REQUIRED_ENV_VAR[p])]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them (e.g. in a .env file) before running for real. This "
            "script refuses to fall back to a mock or a different provider."
        )


def ensure_key_present(provider: str) -> None:
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


def estimate_cost(items: list[dict]) -> dict:
    """Cost of whatever is NOT already cached. Never makes a call. Input
    tokens are estimated from the real prompt text for each item; output
    tokens remain a flat assumption since the response doesn't exist yet."""
    calls_needed = 0
    calls_cached = 0
    cost = 0.0
    for item in items:
        for condition_name, cond in CONDITIONS.items():
            key = build_cache_key(item["item_id"], condition_name, cond)
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


def generate_all(items: list[dict], dry_run: bool) -> dict:
    all_responses: dict[str, dict] = {}
    made_calls = 0
    for item in items:
        all_responses[item["item_id"]] = {}
        for condition_name, cond in CONDITIONS.items():
            key = build_cache_key(item["item_id"], condition_name, cond)
            cached_record = cache.get(key)
            if cached_record is not None:
                all_responses[item["item_id"]][condition_name] = cached_record
                continue
            if dry_run:
                continue
            ensure_key_present(cond["provider"])
            prompt = build_prompt(item, cond)
            text = call_model(cond["provider"], cond["model"], prompt, TEMPERATURE)
            record = {
                "text": text,
                "model": cond["model"],
                "provider": cond["provider"],
                "condition": condition_name,
                "label": cond["label"],
                "passage_included": cond["passage_included"],
                "prompt_format": PROMPT_FORMAT,
                "few_shot_draw": FEW_SHOT_DRAW,
                "temperature": TEMPERATURE,
                "seed": SEED,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print call count and cost, make no calls.")
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

    if args.dry_run:
        stats = estimate_cost(items)
        print(f"Items: {len(items)}")
        print(f"Conditions per item: {len(CONDITIONS)}")
        print(f"Total (item, condition) pairs: {len(items) * len(CONDITIONS)}")
        print(f"Already cached: {stats['calls_cached']}")
        print(f"Calls needed: {stats['calls_needed']}")
        print(f"Estimated cost of remaining calls: ${stats['estimated_cost_usd']:.4f}")
        return 0

    result = generate_all(items, dry_run=False)
    pairs = build_response_pairs(items, result["all_responses"])

    ALL_RESPONSES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALL_RESPONSES_PATH.write_text(json.dumps(result["all_responses"], indent=2), encoding="utf-8")
    RESPONSE_PAIRS_PATH.write_text(json.dumps(pairs, indent=2), encoding="utf-8")

    print(f"Made {result['made_calls']} new API calls this run.")
    print(f"Wrote {len(pairs)} response pairs to {RESPONSE_PAIRS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
