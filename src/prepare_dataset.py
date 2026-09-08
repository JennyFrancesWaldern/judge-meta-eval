#!/usr/bin/env python3
"""Fetch and subset RAGTruth's QA source data. No API key needed -- this
reads public benchmark data over HTTP, it does not call an LLM. Writes
data/raw/source_passages.json: a deterministic sample of unique
(passages, question) pairs from RAGTruth's QA task (MS MARCO passages).

Source: https://github.com/ParticleMedia/RAGTruth (MIT, arXiv:2401.00396),
dataset/source_info.jsonl. One row per unique source instance -- much
smaller than response.jsonl (one row per generated response, ~6x larger),
so this is fetched in full rather than paged.

Schema of a QA row in source_info.jsonl:
    {"source_id": "...", "task_type": "QA", "source": "MARCO",
     "source_info": {"question": "...", "passages": "passage 1:...\\n\\npassage 2:..."}}
"passages" is 3 concatenated MS MARCO candidate passages per question, not
a single passage -- some of the 3 may not actually be relevant to the
question, which is itself part of MS MARCO's original QA design.
"""
import json
import sys
import urllib.request
from pathlib import Path

import random

from src.seeding import set_seed

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "raw" / "source_passages.json"

SOURCE_INFO_URL = (
    "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl"
)


def fetch_qa_items() -> dict[str, dict]:
    request = urllib.request.Request(
        SOURCE_INFO_URL, headers={"User-Agent": "judge-meta-eval-data-prep/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as resp:
        raw = resp.read().decode("utf-8")

    items_by_id: dict[str, dict] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("task_type") != "QA":
            continue
        items_by_id[row["source_id"]] = {
            "item_id": row["source_id"],
            "passage": row["source_info"]["passages"],
            "question": row["source_info"]["question"],
        }
    return items_by_id


def main() -> int:
    n_sample = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    print(f"Fetching {SOURCE_INFO_URL} ...", file=sys.stderr)
    items_by_id = fetch_qa_items()
    print(f"Found {len(items_by_id)} unique QA source instances.", file=sys.stderr)

    if len(items_by_id) < n_sample:
        print(
            f"Only {len(items_by_id)} unique QA items available, fewer than "
            f"the requested {n_sample}.",
            file=sys.stderr,
        )
        return 1

    set_seed(seed)
    sampled_ids = random.sample(sorted(items_by_id.keys()), n_sample)
    sampled = [items_by_id[i] for i in sampled_ids]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(sampled, indent=2), encoding="utf-8")
    print(f"Wrote {len(sampled)} sampled items to {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
