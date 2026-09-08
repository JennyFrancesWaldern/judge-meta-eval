"""Tests for the blind pairwise labeling tool.

Uses small synthetic fixtures only (clearly-fake placeholder text) -- these
exercise plumbing, not any real experiment. No API calls.
"""
import json

import pytest

from src.labeling import (
    LabelStore,
    QueueStore,
    build_queue,
    entry_to_display,
    make_label_record,
)


def make_fixture_items(n=20):
    return [
        {
            "item_id": f"fixture_{i:03d}",
            "passage": f"Test passage {i} used only by the test suite.",
            "question": f"Test question {i}?",
            "response_1": {"text": f"Response A for item {i}", "source_model": "sonnet-5", "condition": "a"},
            "response_2": {"text": f"Response B for item {i}", "source_model": "haiku-4.5", "condition": "b"},
        }
        for i in range(n)
    ]


# --- Queue construction ---

def test_queue_length_includes_repeats():
    items = make_fixture_items(20)
    queue = build_queue(items, repeat_fraction=0.10, min_repeat_gap=3, seed=1)
    assert len(queue) == 22  # 20 base + 2 repeats (round(20 * 0.10))


def test_queue_build_is_deterministic_given_seed():
    items = make_fixture_items(20)
    q1 = build_queue(items, seed=42)
    q2 = build_queue(items, seed=42)
    assert q1 == q2


def test_queue_build_differs_across_seeds():
    items = make_fixture_items(20)
    q1 = build_queue(items, seed=1)
    q2 = build_queue(items, seed=2)
    assert q1 != q2


def test_repeats_are_spaced_apart():
    items = make_fixture_items(30)
    min_gap = 5
    queue = build_queue(items, repeat_fraction=0.20, min_repeat_gap=min_gap, seed=7)

    positions_by_item = {}
    for pos, entry in enumerate(queue):
        positions_by_item.setdefault(entry["item_id"], []).append(pos)

    repeated = {item_id: positions for item_id, positions in positions_by_item.items() if len(positions) > 1}
    assert repeated, "expected at least one repeated item in this fixture"
    for item_id, positions in repeated.items():
        positions.sort()
        for a, b in zip(positions, positions[1:]):
            assert b - a >= min_gap


# --- Blinding ---

def test_display_hides_model_identity():
    items = make_fixture_items(5)
    items_by_id = {item["item_id"]: item for item in items}
    entry = {"item_id": "fixture_000", "left_is": "response_1"}

    display = entry_to_display(entry, items_by_id)

    serialized = json.dumps(display).lower()
    for leaked in ("sonnet", "haiku", "source_model", "condition", '"a"', '"b"'):
        assert leaked not in serialized, f"display leaked identity via {leaked!r}"
    assert set(display.keys()) == {"passage", "question", "left_text", "right_text"}


def test_repeat_display_has_identical_shape_to_fresh():
    items = make_fixture_items(5)
    items_by_id = {item["item_id"]: item for item in items}
    fresh = entry_to_display({"item_id": "fixture_000", "left_is": "response_1"}, items_by_id)
    repeat = entry_to_display({"item_id": "fixture_000", "left_is": "response_2"}, items_by_id)
    assert set(fresh.keys()) == set(repeat.keys())


def test_both_orderings_occur_across_many_builds():
    items = make_fixture_items(2)
    orderings = set()
    for seed in range(50):
        queue = build_queue(items, repeat_fraction=0, seed=seed)
        orderings.add(queue[0]["left_is"])
    assert orderings == {"response_1", "response_2"}


# --- Storage and resume ---

def test_label_store_append_and_count(tmp_path):
    store = LabelStore(tmp_path / "labels.jsonl")
    assert store.count() == 0
    store.append({"a": 1})
    store.append({"a": 2})
    assert store.count() == 2
    assert store.read_all() == [{"a": 1}, {"a": 2}]


def test_label_store_never_rewrites_existing_lines(tmp_path):
    path = tmp_path / "labels.jsonl"
    store = LabelStore(path)
    store.append({"n": 1})
    first_write = path.read_text(encoding="utf-8")
    store.append({"n": 2})
    assert path.read_text(encoding="utf-8").startswith(first_write)


def test_queue_store_persists_across_instances(tmp_path):
    items = make_fixture_items(10)
    path = tmp_path / "queue.json"

    first = QueueStore(path).load_or_build(items, seed=99)
    # A second QueueStore instance, as if the tool were restarted, must load
    # the exact same queue rather than building a fresh random one.
    second = QueueStore(path).load_or_build(items, seed=123)  # different seed, should be ignored
    assert first == second


def test_resume_picks_up_at_label_count(tmp_path):
    items = make_fixture_items(10)
    queue = build_queue(items, repeat_fraction=0, seed=1)
    label_store = LabelStore(tmp_path / "labels.jsonl")

    def next_position():
        return label_store.count()

    assert next_position() == 0
    entry = queue[next_position()]
    label_store.append(make_label_record(0, entry, "left", "r", "medium", served_at_ms=0))
    assert next_position() == 1

    entry = queue[next_position()]
    label_store.append(make_label_record(1, entry, "tie", "r", "high", served_at_ms=0))
    assert next_position() == 2


def test_make_label_record_stores_unusable_reason():
    entry = {"item_id": "fixture_000", "left_is": "response_1"}
    record = make_label_record(
        0, entry, "unusable", "", "low", served_at_ms=0, unusable_reason="passage truncated"
    )
    assert record["unusable_reason"] == "passage truncated"
    assert record["item_id"] == "fixture_000"


# --- End-to-end resume through the Flask app ---

@pytest.fixture
def app_paths(tmp_path):
    items = make_fixture_items(10)
    response_pairs_path = tmp_path / "response_pairs.json"
    response_pairs_path.write_text(json.dumps(items), encoding="utf-8")
    return {
        "response_pairs": response_pairs_path,
        "queue": tmp_path / "label_queue.json",
        "labels": tmp_path / "labels.jsonl",
    }


def test_server_resumes_after_simulated_restart(app_paths):
    from src.labeling_server import create_app

    app1 = create_app(app_paths["response_pairs"], app_paths["queue"], app_paths["labels"])
    client1 = app1.test_client()

    first = client1.get("/api/next").get_json()
    assert first["queue_position"] == 0

    client1.post(
        "/api/submit",
        json={
            "queue_position": 0,
            "served_at_ms": first["served_at_ms"],
            "verdict": "left",
            "rationale": "test rationale",
            "confidence": "medium",
            "unusable_reason": None,
        },
    )

    # Simulate closing and reopening the tool: a brand new app instance
    # pointed at the same on-disk paths must resume at position 1, with the
    # identical persisted queue -- not a freshly shuffled one.
    app2 = create_app(app_paths["response_pairs"], app_paths["queue"], app_paths["labels"])
    client2 = app2.test_client()

    second = client2.get("/api/next").get_json()
    assert second["queue_position"] == 1
    assert second["done"] is False


def test_server_reports_done_when_queue_exhausted(app_paths):
    from src.labeling_server import create_app

    app = create_app(app_paths["response_pairs"], app_paths["queue"], app_paths["labels"])
    client = app.test_client()

    total = client.get("/api/next").get_json()["total"]
    for i in range(total):
        item = client.get("/api/next").get_json()
        client.post(
            "/api/submit",
            json={
                "queue_position": i,
                "served_at_ms": item["served_at_ms"],
                "verdict": "tie",
                "rationale": "",
                "confidence": "low",
                "unusable_reason": None,
            },
        )

    final = client.get("/api/next").get_json()
    assert final["done"] is True


def test_missing_response_pairs_file_fails_loudly(tmp_path):
    from src.labeling_server import create_app

    with pytest.raises(FileNotFoundError):
        create_app(
            tmp_path / "does_not_exist.json",
            tmp_path / "queue.json",
            tmp_path / "labels.jsonl",
        )
