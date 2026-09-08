#!/usr/bin/env python3
"""Generate response pairs for judge-meta-eval labeling. See ANALYSIS_PLAN.md
section 2 for the design and cost estimate this implements.

Idempotent and resumable: every (item, condition, prompt_format, seed,
temperature) call is cached in cache/, keyed on the full administration
condition that would produce it. Rerunning after a crash re-reads whatever
is already cached and only pays for what is missing -- it never re-calls or
double-charges for a condition that already succeeded.

Use --dry-run to see the exact call count and cost estimate for every
component (core generation, the self-preference bracket, the format-
variance subset) without making any calls and without needing an API key.
Real runs fail loudly, lazily and per-call, if a required key is missing --
a run fully satisfied by cache never needs a key at all.
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
FORMAT_VARIANCE_RESPONSES_PATH = REPO_ROOT / "data" / "generated" / "format_variance_responses.json"

# Few-shot draw is fixed per ANALYSIS_PLAN.md section 3 (zero-shot generation
# is standard for this model tier) -- recorded on every response anyway,
# since a constant is still a condition value. Prompt FORMAT is no longer
# fixed -- see FORMAT_VARIANTS below and ANALYSIS_PLAN.md's 2026-09-09
# revision.
FEW_SHOT_DRAW = "zero_shot"
TEMPERATURE = 0.0
SEED = 0
DEFAULT_PROMPT_FORMAT = "plain_v1"

# See ANALYSIS_PLAN.md section 2, "Revision 2026-09-07" for why this is
# 3 models / 4 conditions rather than the original 2/3.
CONDITIONS = {
    "a": {"provider": "anthropic", "model": "claude-sonnet-5", "passage_included": True, "label": "strong"},
    "b": {"provider": "openai", "model": "gpt-5.4-mini", "passage_included": True, "label": "moderate_cross_family"},
    "c": {"provider": "anthropic", "model": "claude-haiku-4-5", "passage_included": True, "label": "weak"},
    "d": {"provider": "anthropic", "model": "claude-sonnet-5", "passage_included": False, "label": "ungrounded"},
}

# Item index % 5 selects which two conditions are paired for human labeling.
# b_c added 2026-09-09: GPT-5.4 mini vs. Haiku 4.5 -- two small models on
# opposite families, the closest thing to a capability-matched cross-family
# comparison in this design (see ANALYSIS_PLAN.md). 200 items / 5 types = 40
# each (was 50 each across 4 types) -- no change to total labeling time.
PAIR_SCHEDULE = ["a_b", "a_c", "a_d", "b_d", "b_c"]

# Pair-types eligible for the self-preference bracket (condition e). Deliberately
# NOT the same set as "cross-family pairs" in general -- b_c is cross-family
# too (b=OpenAI, c=Anthropic) but doesn't involve condition (a), so it isn't
# part of the Sonnet-5-bracketing logic below. It's a separate, matched-tier
# self-preference test in its own right.
BRACKET_ELIGIBLE_PAIR_TYPES = {"a_b", "b_d"}

# Self-preference bracket (ANALYSIS_PLAN.md section 2, "Revision 2026-09-08"):
# gpt-5.4-mini and Claude Sonnet 5 are not a capability-matched cross-family
# pair -- see that section for why price parity turned out not to mean
# capability parity here. This condition is generated ONLY for the items
# whose scheduled pair-type is bracket-eligible, and is NOT added to human
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

# Format-variance subset (ANALYSIS_PLAN.md, "Revision 2026-09-09" -- replaces
# the original seed/temperature variance subset). METHODOLOGY.md's top-ranked
# failure mode (per Unit 1 notes) is format/harness sensitivity, which can
# exceed between-model variance -- and prompt format is exactly the thing
# fixed at generation time in this design for labeling-budget reasons. A
# second seed at nonzero temperature would have measured sampling variance,
# not that. This measures the thing actually named in METHODOLOGY.md:
# regenerate a stratified subset under alternate, semantically equivalent
# prompt formats, same seed and temperature as the main run, and see how
# much the responses move.
FORMAT_VARIANCE_SUBSET_SIZE = 50


def _plain_v1(item: dict, passage_included: bool) -> str:
    if passage_included:
        return (
            f"Passage:\n{item['passage']}\n\n"
            f"Question: {item['question']}\n\n"
            "Answer the question using only the passage above."
        )
    return f"Question: {item['question']}\n\nAnswer from your own knowledge."


def _instruction_first_v1(item: dict, passage_included: bool) -> str:
    if passage_included:
        return (
            "Answer the following question using only the passage provided below.\n\n"
            f"Question: {item['question']}\n\n"
            f"Passage:\n{item['passage']}"
        )
    return f"Answer the following question using your own knowledge.\n\nQuestion: {item['question']}"


def _qa_style_v1(item: dict, passage_included: bool) -> str:
    if passage_included:
        return f"{item['passage']}\n\nQ: {item['question']}\nA:"
    return f"Q: {item['question']}\nA:"


# Three semantically equivalent formats: differ in instruction wording,
# ordering (passage-first vs. question-first), and verbosity -- the same
# axes Sclar et al. vary. All ask for the same thing.
FORMAT_VARIANTS = {
    "plain_v1": _plain_v1,
    "instruction_first_v1": _instruction_first_v1,
    "qa_style_v1": _qa_style_v1,
}

# Was 150 (a guess). Measured 2026-09-10 from the 40 real contamination-probe
# calls (condition d, Sonnet 5): avg 409 est. tokens, range 210-594 -- Sonnet 5
# writes full markdown-formatted answers by default, not terse extractive
# ones, even on an open "answer from your own knowledge" prompt. Grounded
# conditions (a, b, c) haven't been measured for real yet and may differ
# (the "use only the passage" instruction is more constraining), but 150 is
# now known to be the wrong order of magnitude for at least one condition,
# so this uses the measured value everywhere pending real data on the rest.
ESTIMATED_OUTPUT_TOKENS = 410

# USD per million tokens (input, output). Checked directly against
# claude.com/pricing and developers.openai.com/api/docs/pricing on
# 2026-09-07/08 -- see ANALYSIS_PLAN.md section 2. Re-verify before relying
# on this if run much later; these rates change.
PRICING_PER_M = {
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.6-sol": (4.0, 20.0),
}


def build_cache_key(
    item_id: str,
    condition_name: str,
    cond: dict,
    seed: int = SEED,
    temperature: float = TEMPERATURE,
    prompt_format: str = DEFAULT_PROMPT_FORMAT,
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
            "prompt_format": prompt_format,
            "few_shot_draw": FEW_SHOT_DRAW,
            "temperature": temperature,
            "seed": seed,
        },
        sort_keys=True,
    )


def build_prompt(item: dict, cond: dict, prompt_format: str = DEFAULT_PROMPT_FORMAT) -> str:
    return FORMAT_VARIANTS[prompt_format](item, cond["passage_included"])


# Sonnet 5 (and Opus 5 / Fable 5) reject `temperature` outright (400) --
# removed from the API, not just defaulted. Haiku 4.5 still accepts it.
# Checked against the current Claude API reference on 2026-09-10.
ANTHROPIC_NO_TEMPERATURE_MODELS = {"claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-fable-5-1"}


def call_model(provider: str, model: str, prompt: str, temperature: float) -> str:
    """Make the actual API call. Imports are lazy so dry-run and tests never
    need network access or credentials just to load this module."""
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        kwargs = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if model in ANTHROPIC_NO_TEMPERATURE_MODELS:
            # No temperature knob on this model -- adaptive thinking runs by
            # default regardless; keep it shallow since this is a plain
            # extractive-QA task, not something that benefits from deep
            # reasoning, and thinking tokens are billed as output either way.
            kwargs["output_config"] = {"effort": "low"}
        else:
            kwargs["temperature"] = temperature
        resp = client.messages.create(**kwargs)
        # content[0] is not reliably the answer once thinking is active --
        # a ThinkingBlock can come first. Take only text blocks.
        return "".join(block.text for block in resp.content if block.type == "text")
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


def estimate_cost(
    items: list[dict],
    conditions: dict,
    seed: int = SEED,
    temperature: float = TEMPERATURE,
    prompt_format: str = DEFAULT_PROMPT_FORMAT,
) -> dict:
    """Cost of whatever is NOT already cached, for the given items/conditions/
    seed/temperature/prompt_format. Never makes a call. Input tokens are
    estimated from the real prompt text; output tokens remain a flat
    assumption."""
    calls_needed = 0
    calls_cached = 0
    cost = 0.0
    for item in items:
        for condition_name, cond in conditions.items():
            key = build_cache_key(
                item["item_id"], condition_name, cond, seed=seed, temperature=temperature, prompt_format=prompt_format
            )
            if cache.get(key) is not None:
                calls_cached += 1
                continue
            calls_needed += 1
            input_tokens = estimate_tokens(build_prompt(item, cond, prompt_format=prompt_format))
            in_price, out_price = PRICING_PER_M[cond["model"]]
            cost += (input_tokens / 1_000_000) * in_price
            cost += (ESTIMATED_OUTPUT_TOKENS / 1_000_000) * out_price
    return {
        "calls_needed": calls_needed,
        "calls_cached": calls_cached,
        "estimated_cost_usd": round(cost, 4),
    }


def generate_all(
    items: list[dict],
    conditions: dict,
    dry_run: bool,
    seed: int = SEED,
    temperature: float = TEMPERATURE,
    prompt_format: str = DEFAULT_PROMPT_FORMAT,
) -> dict:
    all_responses: dict[str, dict] = {}
    made_calls = 0
    for item in items:
        all_responses[item["item_id"]] = {}
        for condition_name, cond in conditions.items():
            key = build_cache_key(
                item["item_id"], condition_name, cond, seed=seed, temperature=temperature, prompt_format=prompt_format
            )
            cached_record = cache.get(key)
            if cached_record is not None:
                all_responses[item["item_id"]][condition_name] = cached_record
                continue
            if dry_run:
                continue
            ensure_key_present(cond["provider"])
            prompt = build_prompt(item, cond, prompt_format=prompt_format)
            text = call_model(cond["provider"], cond["model"], prompt, temperature)
            record = {
                "text": text,
                "model": cond["model"],
                "provider": cond["provider"],
                "condition": condition_name,
                "label": cond["label"],
                "passage_included": cond["passage_included"],
                "prompt_format": prompt_format,
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


def select_bracket_items(items: list[dict]) -> list[dict]:
    """The subset whose scheduled pair-type is bracket-eligible (involves
    condition (a) against the mini-tier cross-family model) -- these are the
    items the self-preference bracket (gpt-5.6-sol) is generated for."""
    return [
        item for i, item in enumerate(items) if PAIR_SCHEDULE[i % len(PAIR_SCHEDULE)] in BRACKET_ELIGIBLE_PAIR_TYPES
    ]


def select_stratified_subset(items: list[dict], n: int) -> list[dict]:
    """A subset covering all pair-type groups as evenly as possible."""
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
        choices=["core", "bracket", "format_variance", "all"],
        default="all",
        help="Which piece to run/estimate.",
    )
    parser.add_argument(
        "--format-variants",
        type=int,
        choices=[1, 2],
        default=2,
        help="How many ALTERNATE formats (beyond the main plain_v1) to test in the format-variance subset.",
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

    bracket_items = select_bracket_items(items)
    format_variance_items = select_stratified_subset(items, FORMAT_VARIANCE_SUBSET_SIZE)
    alternate_formats = list(FORMAT_VARIANTS.keys())[1 : 1 + args.format_variants]

    components = []
    if args.component in ("core", "all"):
        components.append(("core (4 conditions x 200 items)", items, CONDITIONS, SEED, TEMPERATURE, DEFAULT_PROMPT_FORMAT))
    if args.component in ("bracket", "all"):
        components.append(
            (
                f"self-preference bracket (gpt-5.6-sol x {len(bracket_items)} items)",
                bracket_items,
                {"e": BRACKET_CONDITION},
                SEED,
                TEMPERATURE,
                DEFAULT_PROMPT_FORMAT,
            )
        )
    if args.component in ("format_variance", "all"):
        for fmt in alternate_formats:
            components.append(
                (
                    f"format variance ({fmt}, 4 conditions x {len(format_variance_items)} items)",
                    format_variance_items,
                    CONDITIONS,
                    SEED,
                    TEMPERATURE,
                    fmt,
                )
            )

    if args.dry_run:
        grand_total = 0.0
        for label, comp_items, comp_conditions, seed, temperature, prompt_format in components:
            stats = estimate_cost(comp_items, comp_conditions, seed=seed, temperature=temperature, prompt_format=prompt_format)
            print(f"--- {label} ---")
            print(f"  Already cached: {stats['calls_cached']}")
            print(f"  Calls needed: {stats['calls_needed']}")
            print(f"  Estimated cost of remaining calls: ${stats['estimated_cost_usd']:.4f}")
            grand_total += stats["estimated_cost_usd"]
        print(f"=== Grand total across selected components: ${grand_total:.4f} ===")
        return 0

    for label, comp_items, comp_conditions, seed, temperature, prompt_format in components:
        result = generate_all(
            comp_items, comp_conditions, dry_run=False, seed=seed, temperature=temperature, prompt_format=prompt_format
        )
        print(f"{label}: made {result['made_calls']} new API calls this run.")

        if comp_conditions is CONDITIONS and prompt_format == DEFAULT_PROMPT_FORMAT:
            pairs = build_response_pairs(items, result["all_responses"])
            ALL_RESPONSES_PATH.parent.mkdir(parents=True, exist_ok=True)
            ALL_RESPONSES_PATH.write_text(json.dumps(result["all_responses"], indent=2), encoding="utf-8")
            RESPONSE_PAIRS_PATH.write_text(json.dumps(pairs, indent=2), encoding="utf-8")
            print(f"  Wrote {len(pairs)} response pairs to {RESPONSE_PAIRS_PATH}")
        elif "e" in comp_conditions:
            BRACKET_RESPONSES_PATH.write_text(json.dumps(result["all_responses"], indent=2), encoding="utf-8")
            print(f"  Wrote bracket responses to {BRACKET_RESPONSES_PATH}")
        else:
            existing = {}
            if FORMAT_VARIANCE_RESPONSES_PATH.exists():
                existing = json.loads(FORMAT_VARIANCE_RESPONSES_PATH.read_text(encoding="utf-8"))
            existing[prompt_format] = result["all_responses"]
            FORMAT_VARIANCE_RESPONSES_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            print(f"  Wrote format-variance responses ({prompt_format}) to {FORMAT_VARIANCE_RESPONSES_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
