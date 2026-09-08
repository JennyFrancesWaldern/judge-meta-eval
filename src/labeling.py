"""Core logic for the blind pairwise labeling tool.

Kept separate from the Flask server (labeling_server.py) so the queue,
blinding, and storage logic can be unit tested without spinning up an HTTP
server. Nothing here makes a network or API call.
"""
import json
import random
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_queue(
    items: list[dict],
    repeat_fraction: float = 0.10,
    min_repeat_gap: int = 15,
    seed: int = 0,
) -> list[dict]:
    """Build a fixed labeling queue: one entry per item, plus silent repeats.

    Each entry independently randomizes which response is shown on the
    left, including repeats of the same item -- so a repeat cannot be
    spotted by its layout matching the original. Repeats are placed at
    least min_repeat_gap positions after their original occurrence.

    The queue is built once, deterministically from `seed`, and is meant to
    be persisted (see QueueStore) so a resumed session sees the exact same
    order rather than a freshly shuffled one.
    """
    rng = random.Random(seed)

    order = list(range(len(items)))
    rng.shuffle(order)
    queue = [
        {"item_id": items[i]["item_id"], "left_is": rng.choice(["response_1", "response_2"])}
        for i in order
    ]

    # Each source_pos/insert_pos below is resolved against the queue's
    # *current* length and contents, not a stale pre-insertion snapshot --
    # otherwise an earlier insertion shifts everything after it and the
    # gap constraint silently breaks for pairs decided before that shift.
    #
    # Each item is repeated at most once (used_item_ids below). Without
    # this, a second repeat could source from an item that already has a
    # pending repeat, land between the two existing occurrences, and create
    # an adjacent pair whose gap was never actually validated against
    # min_repeat_gap.
    n_repeats = int(round(len(items) * repeat_fraction))
    used_item_ids: set[str] = set()
    for _ in range(n_repeats):
        candidates = [
            pos for pos in range(len(queue))
            if pos + min_repeat_gap < len(queue) and queue[pos]["item_id"] not in used_item_ids
        ]
        if not candidates:
            break
        source_pos = rng.choice(candidates)
        source_item_id = queue[source_pos]["item_id"]
        used_item_ids.add(source_item_id)
        insert_pos = rng.randint(source_pos + min_repeat_gap, len(queue))
        repeat_entry = {
            "item_id": source_item_id,
            "left_is": rng.choice(["response_1", "response_2"]),
        }
        queue.insert(insert_pos, repeat_entry)

    return queue


def entry_to_display(entry: dict, items_by_id: dict[str, dict]) -> dict[str, Any]:
    """Build the labeler-facing payload for a queue entry. No identifying info."""
    item = items_by_id[entry["item_id"]]
    left_key = entry["left_is"]
    right_key = "response_2" if left_key == "response_1" else "response_1"
    return {
        "passage": item["passage"],
        "question": item["question"],
        "left_text": item[left_key]["text"],
        "right_text": item[right_key]["text"],
    }


class QueueStore:
    """Persists the once-built queue so repeated runs resume the same order."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict] | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, queue: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(queue, indent=2), encoding="utf-8")

    def load_or_build(
        self,
        items: list[dict],
        repeat_fraction: float = 0.10,
        min_repeat_gap: int = 15,
        seed: int = 0,
    ) -> list[dict]:
        existing = self.load()
        if existing is not None:
            return existing
        queue = build_queue(items, repeat_fraction, min_repeat_gap, seed)
        self.save(queue)
        return queue


class LabelStore:
    """Append-only JSONL store for completed labels. Never rewrites past lines."""

    def __init__(self, path: Path):
        self.path = path

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


def make_label_record(
    queue_position: int,
    entry: dict,
    verdict: str,
    rationale: str,
    confidence: str,
    served_at_ms: int,
    unusable_reason: str | None = None,
) -> dict:
    return {
        "queue_position": queue_position,
        "item_id": entry["item_id"],
        "left_is": entry["left_is"],
        "verdict": verdict,
        "rationale": rationale,
        "confidence": confidence,
        "unusable_reason": unusable_reason,
        "served_at_ms": served_at_ms,
        "submitted_at_ms": int(time.time() * 1000),
    }
