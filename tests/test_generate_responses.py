"""Tests for the response-generation script. Never makes a real API call --
call_model is monkeypatched throughout. Uses small synthetic fixtures only.
"""
import json

import pytest

from src import cache, generate_responses as gr


def make_fixture_items(n=3):
    return [
        {
            "item_id": f"fixture_{i:03d}",
            "passage": f"Test passage {i}.",
            "question": f"Test question {i}?",
        }
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    yield


@pytest.fixture
def counting_call_model(monkeypatch):
    # Fake keys so ensure_key_present doesn't block these tests -- the
    # missing-key behavior itself is tested separately, below, by deleting
    # these back out.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    calls = []

    def fake_call_model(provider, model, prompt, temperature):
        calls.append({"provider": provider, "model": model, "prompt": prompt, "temperature": temperature})
        return f"fake response #{len(calls)} from {model}"

    monkeypatch.setattr(gr, "call_model", fake_call_model)
    return calls


# --- Dry run / cost estimate ---

def test_dry_run_counts_all_as_needed_when_cache_empty():
    items = make_fixture_items(3)
    stats = gr.estimate_cost(items, gr.CONDITIONS)
    assert stats["calls_cached"] == 0
    assert stats["calls_needed"] == 3 * len(gr.CONDITIONS)
    assert stats["estimated_cost_usd"] > 0


def test_dry_run_never_calls_the_model(counting_call_model):
    items = make_fixture_items(3)
    gr.generate_all(items, gr.CONDITIONS, dry_run=True)
    assert counting_call_model == []


def test_dry_run_reflects_partial_cache():
    items = make_fixture_items(2)
    cond = gr.CONDITIONS["a"]
    key = gr.build_cache_key(items[0]["item_id"], "a", cond)
    cache.set(key, {"text": "already generated"})

    stats = gr.estimate_cost(items, gr.CONDITIONS)
    assert stats["calls_cached"] == 1
    assert stats["calls_needed"] == 2 * len(gr.CONDITIONS) - 1


def test_dry_run_respects_seed_and_temperature_in_key():
    items = make_fixture_items(1)
    cond = gr.CONDITIONS["a"]
    # Cached under the default seed/temperature...
    key = gr.build_cache_key(items[0]["item_id"], "a", cond, seed=gr.SEED, temperature=gr.TEMPERATURE)
    cache.set(key, {"text": "cached at seed 0"})

    # ...should NOT be treated as cached under a different seed/temperature.
    stats = gr.estimate_cost(items, {"a": cond}, seed=gr.SECOND_SEED, temperature=gr.VARIANCE_SUBSET_TEMPERATURE)
    assert stats["calls_cached"] == 0
    assert stats["calls_needed"] == 1


# --- Caching and resume ---

def test_cache_hit_skips_the_call(counting_call_model):
    items = make_fixture_items(1)
    for condition_name, cond in gr.CONDITIONS.items():
        key = gr.build_cache_key(items[0]["item_id"], condition_name, cond)
        cache.set(key, {"text": "pre-cached", "condition": condition_name})

    result = gr.generate_all(items, gr.CONDITIONS, dry_run=False)

    assert counting_call_model == []
    assert result["made_calls"] == 0
    assert result["all_responses"][items[0]["item_id"]]["a"]["text"] == "pre-cached"


def test_resume_does_not_recall_or_double_charge(counting_call_model):
    items = make_fixture_items(2)

    first = gr.generate_all(items, gr.CONDITIONS, dry_run=False)
    assert first["made_calls"] == 2 * len(gr.CONDITIONS)
    calls_after_first_run = len(counting_call_model)

    # Simulate a restart: call generate_all again against the same cache.
    second = gr.generate_all(items, gr.CONDITIONS, dry_run=False)

    assert second["made_calls"] == 0
    assert len(counting_call_model) == calls_after_first_run  # no new calls at all


def test_partial_run_then_resume_completes_without_recalling(monkeypatch, counting_call_model):
    items = make_fixture_items(3)

    # Simulate dying partway through: only process the first item, as if the
    # process were killed after item 0.
    gr.generate_all(items[:1], gr.CONDITIONS, dry_run=False)
    calls_after_partial = len(counting_call_model)
    assert calls_after_partial == len(gr.CONDITIONS)

    # Resume against the full item list.
    result = gr.generate_all(items, gr.CONDITIONS, dry_run=False)

    # Only the two new items' conditions should have made fresh calls.
    assert result["made_calls"] == 2 * len(gr.CONDITIONS)
    assert len(counting_call_model) == calls_after_partial + 2 * len(gr.CONDITIONS)


# --- Condition metadata round-trip ---

def test_condition_metadata_round_trips_through_cache(counting_call_model):
    items = make_fixture_items(1)
    gr.generate_all(items, gr.CONDITIONS, dry_run=False)

    key = gr.build_cache_key(items[0]["item_id"], "a", gr.CONDITIONS["a"])
    record = cache.get(key)

    assert record["model"] == gr.CONDITIONS["a"]["model"]
    assert record["provider"] == gr.CONDITIONS["a"]["provider"]
    assert record["prompt_format"] == gr.PROMPT_FORMAT
    assert record["few_shot_draw"] == gr.FEW_SHOT_DRAW
    assert record["temperature"] == gr.TEMPERATURE
    assert record["seed"] == gr.SEED
    assert record["item_id"] == items[0]["item_id"]
    assert record["passage_included"] == gr.CONDITIONS["a"]["passage_included"]
    assert "generated_at_ms" in record


def test_variance_subset_record_carries_second_seed_and_temperature(counting_call_model):
    items = make_fixture_items(1)
    gr.generate_all(items, gr.CONDITIONS, dry_run=False, seed=gr.SECOND_SEED, temperature=gr.VARIANCE_SUBSET_TEMPERATURE)

    key = gr.build_cache_key(
        items[0]["item_id"], "a", gr.CONDITIONS["a"], seed=gr.SECOND_SEED, temperature=gr.VARIANCE_SUBSET_TEMPERATURE
    )
    record = cache.get(key)
    assert record["seed"] == gr.SECOND_SEED
    assert record["temperature"] == gr.VARIANCE_SUBSET_TEMPERATURE

    # And it must NOT collide with the main run's cache entry for the same item/condition.
    main_key = gr.build_cache_key(items[0]["item_id"], "a", gr.CONDITIONS["a"])
    assert cache.get(main_key) is None


def test_ungrounded_condition_prompt_excludes_passage():
    items = make_fixture_items(1)
    prompt = gr.build_prompt(items[0], gr.CONDITIONS["d"])
    assert items[0]["passage"] not in prompt


def test_grounded_condition_prompt_includes_passage():
    items = make_fixture_items(1)
    prompt = gr.build_prompt(items[0], gr.CONDITIONS["a"])
    assert items[0]["passage"] in prompt


# --- Fail loudly on missing key ---

def test_missing_key_fails_loudly(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        gr.ensure_key_present("anthropic")


def test_missing_key_check_happens_before_any_call(monkeypatch, counting_call_model):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    items = make_fixture_items(1)
    with pytest.raises(RuntimeError):
        gr.generate_all(items, gr.CONDITIONS, dry_run=False)
    assert counting_call_model == []


def test_present_key_does_not_raise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    gr.ensure_key_present("anthropic")  # should not raise


def test_fully_cached_run_needs_no_key(monkeypatch, counting_call_model):
    items = make_fixture_items(1)
    gr.generate_all(items, gr.CONDITIONS, dry_run=False)  # populate cache with fake keys present

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Fully served from cache now -- must succeed with no key at all.
    result = gr.generate_all(items, gr.CONDITIONS, dry_run=False)
    assert result["made_calls"] == 0


# --- Pairing schedule ---

def test_pair_schedule_cycles_through_four_types(counting_call_model):
    items = make_fixture_items(8)
    result = gr.generate_all(items, gr.CONDITIONS, dry_run=False)
    pairs = gr.build_response_pairs(items, result["all_responses"])

    pair_types = [p["pair_type"] for p in pairs]
    assert pair_types == ["a_b", "a_c", "a_d", "b_d"] * 2


def test_response_pairs_carry_full_condition_metadata_but_display_hides_it(counting_call_model):
    from src.labeling import entry_to_display

    items = make_fixture_items(1)
    result = gr.generate_all(items, gr.CONDITIONS, dry_run=False)
    pairs = gr.build_response_pairs(items, result["all_responses"])

    pair = pairs[0]
    assert "model" in pair["response_1"]  # full metadata present in the data file

    items_by_id = {pair["item_id"]: pair}
    entry = {"item_id": pair["item_id"], "left_is": "response_1"}
    display = entry_to_display(entry, items_by_id)
    assert "model" not in json.dumps(display)


def test_build_response_pairs_skips_incomplete_items():
    items = make_fixture_items(1)
    # Only condition "a" generated -- schedule for item 0 needs "a" and "b".
    all_responses = {items[0]["item_id"]: {"a": {"text": "only this one"}}}
    pairs = gr.build_response_pairs(items, all_responses)
    assert pairs == []


# --- Self-preference bracket selection ---

def test_select_cross_family_items_matches_a_b_and_b_d_slots():
    items = make_fixture_items(8)
    # PAIR_SCHEDULE = ["a_b", "a_c", "a_d", "b_d"], cross-family = a_b (idx 0), b_d (idx 3)
    cross_family = gr.select_cross_family_items(items)
    expected_ids = {items[i]["item_id"] for i in range(8) if i % 4 in (0, 3)}
    assert {item["item_id"] for item in cross_family} == expected_ids
    assert len(cross_family) == 4  # half of 8


def test_bracket_condition_is_a_different_model_than_core_b():
    assert gr.BRACKET_CONDITION["model"] != gr.CONDITIONS["b"]["model"]
    assert gr.BRACKET_CONDITION["provider"] == "openai"


# --- Variance subset selection ---

def test_variance_subset_is_stratified_across_pair_types():
    items = make_fixture_items(40)  # 10 per pair-type group
    subset = gr.select_variance_subset(items, n=20)  # 5 per group
    counts = {}
    for i, item in enumerate(items):
        if item in subset:
            pair_type = gr.PAIR_SCHEDULE[i % 4]
            counts[pair_type] = counts.get(pair_type, 0) + 1
    assert all(c == 5 for c in counts.values())
    assert set(counts.keys()) == set(gr.PAIR_SCHEDULE)


def test_variance_subset_uses_second_seed_distinct_from_main():
    assert gr.SECOND_SEED != gr.SEED
    assert gr.VARIANCE_SUBSET_TEMPERATURE != gr.TEMPERATURE  # must be nonzero to show any variation at all
