#!/usr/bin/env python3
"""Local blind pairwise labeling tool. Single command, no deploy.

Run with: python -m src.labeling_server
Reads response pairs from data/generated/response_pairs.json (must exist --
see ANALYSIS_PLAN.md for the generation design). Fails loudly if that file
is missing rather than serving a broken page.

Labels are appended, one JSON line per submission, to data/labels/labels.jsonl.
That file is append-only: this server never rewrites or deletes a line in it.
"""
import sys
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request

from src.labeling import LabelStore, QueueStore, entry_to_display, make_label_record

REPO_ROOT = Path(__file__).resolve().parent.parent
RESPONSE_PAIRS_PATH = REPO_ROOT / "data" / "generated" / "response_pairs.json"
QUEUE_PATH = REPO_ROOT / "data" / "generated" / "label_queue.json"
LABELS_PATH = REPO_ROOT / "data" / "labels" / "labels.jsonl"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>judge-meta-eval labeling</title>
<style>
  body { max-width: 900px; margin: 2rem auto; padding: 0 1.5rem;
         font-family: -apple-system, "Segoe UI", sans-serif; line-height: 1.5; color: #1a1a1a; }
  h1 { font-size: 1.3rem; }
  #progress { color: #666; margin-bottom: 1.5rem; }
  #passage { background: #f6f6f6; padding: 1rem; border-radius: 6px; white-space: pre-wrap; }
  #question { font-weight: 600; margin: 1rem 0; }
  .responses { display: flex; gap: 1rem; margin: 1rem 0; }
  .response { flex: 1; border: 1px solid #ddd; border-radius: 6px; padding: 1rem; white-space: pre-wrap; }
  .response.selected { border-color: #1a1a1a; border-width: 2px; }
  .controls { margin-top: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
  button { padding: 0.5rem 1rem; cursor: pointer; }
  textarea { width: 100%; min-height: 4rem; margin-top: 0.75rem; font-family: inherit; }
  select { margin-top: 0.5rem; }
  #done { display: none; }
  label { display: block; margin-top: 0.5rem; }
</style>
</head>
<body>
<h1>judge-meta-eval -- blind pairwise labeling</h1>
<div id="progress">Loading...</div>
<div id="labeling">
  <div id="passage"></div>
  <div id="question"></div>
  <div class="responses">
    <div class="response" id="left"></div>
    <div class="response" id="right"></div>
  </div>
  <div class="controls">
    <button data-verdict="left">Left is better</button>
    <button data-verdict="right">Right is better</button>
    <button data-verdict="tie">Tie</button>
    <button data-verdict="unusable">Mark unusable</button>
  </div>
  <label>Rationale (why):
    <textarea id="rationale"></textarea>
  </label>
  <label>Confidence:
    <select id="confidence">
      <option value="low">Low</option>
      <option value="medium" selected>Medium</option>
      <option value="high">High</option>
    </select>
  </label>
  <div class="controls">
    <button id="submit">Submit</button>
  </div>
</div>
<div id="done"><h2>All items labeled.</h2></div>
<script>
let current = null;
let servedAt = null;
let verdict = null;

async function loadNext() {
  const res = await fetch('/api/next');
  const data = await res.json();
  document.getElementById('progress').textContent =
    `Item ${data.completed + (data.done ? 0 : 1)} of ${data.total}`;
  if (data.done) {
    document.getElementById('labeling').style.display = 'none';
    document.getElementById('done').style.display = 'block';
    return;
  }
  current = data;
  servedAt = data.served_at_ms;
  verdict = null;
  document.getElementById('passage').textContent = data.passage;
  document.getElementById('question').textContent = data.question;
  document.getElementById('left').textContent = data.left_text;
  document.getElementById('right').textContent = data.right_text;
  document.getElementById('left').className = 'response';
  document.getElementById('right').className = 'response';
  document.getElementById('rationale').value = '';
  document.getElementById('confidence').value = 'medium';
}

document.querySelectorAll('button[data-verdict]').forEach(btn => {
  btn.addEventListener('click', () => {
    verdict = btn.dataset.verdict;
    document.getElementById('left').className = 'response' + (verdict === 'left' ? ' selected' : '');
    document.getElementById('right').className = 'response' + (verdict === 'right' ? ' selected' : '');
  });
});

document.getElementById('submit').addEventListener('click', async () => {
  if (!verdict) { alert('Pick a verdict first.'); return; }
  const rationale = document.getElementById('rationale').value;
  if (!rationale.trim() && verdict !== 'unusable') {
    if (!confirm('No rationale written -- submit anyway?')) return;
  }
  const unusable_reason = verdict === 'unusable' ? rationale : null;
  await fetch('/api/submit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      queue_position: current.queue_position,
      served_at_ms: servedAt,
      verdict: verdict,
      rationale: rationale,
      confidence: document.getElementById('confidence').value,
      unusable_reason: unusable_reason,
    }),
  });
  loadNext();
});

loadNext();
</script>
</body>
</html>
"""


def create_app(response_pairs_path: Path, queue_path: Path, labels_path: Path) -> Flask:
    if not response_pairs_path.exists():
        raise FileNotFoundError(
            f"Missing {response_pairs_path}. Generate response pairs first -- "
            "see ANALYSIS_PLAN.md section 2 for the generation design."
        )
    import json

    items = json.loads(response_pairs_path.read_text(encoding="utf-8"))
    items_by_id = {item["item_id"]: item for item in items}

    queue_store = QueueStore(queue_path)
    queue = queue_store.load_or_build(items)
    label_store = LabelStore(labels_path)

    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/api/next")
    def next_item():
        completed = label_store.count()
        if completed >= len(queue):
            return jsonify({"done": True, "completed": completed, "total": len(queue)})
        entry = queue[completed]
        display = entry_to_display(entry, items_by_id)
        import time

        return jsonify({
            "done": False,
            "queue_position": completed,
            "completed": completed,
            "total": len(queue),
            "served_at_ms": int(time.time() * 1000),
            **display,
        })

    @app.post("/api/submit")
    def submit():
        body = request.get_json()
        expected_position = label_store.count()
        if body["queue_position"] != expected_position:
            return jsonify({"error": "stale queue position, reload"}), 409
        entry = queue[expected_position]
        record = make_label_record(
            queue_position=expected_position,
            entry=entry,
            verdict=body["verdict"],
            rationale=body.get("rationale", ""),
            confidence=body.get("confidence", ""),
            served_at_ms=body["served_at_ms"],
            unusable_reason=body.get("unusable_reason"),
        )
        label_store.append(record)
        return jsonify({"ok": True})

    return app


def main() -> int:
    try:
        app = create_app(RESPONSE_PAIRS_PATH, QUEUE_PATH, LABELS_PATH)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    webbrowser.open("http://127.0.0.1:5000/")
    app.run(port=5000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
