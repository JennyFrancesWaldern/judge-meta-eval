# judge-meta-eval

How much can an LLM judge be trusted to score grounded-generation quality,
and which judge biases move the score enough to change a ranking, not just
shift a number?

**What makes this worth a look:** decision rules fixed before any result
exists (a 25% contamination threshold, set before the check ran); blind
pairwise human labeling with a hidden repeat subset for measuring
intra-rater agreement; a contamination check that runs before the main
experiment, not one that shows up in limitations after the fact.

**Status, as of 2026-09-11:** pre-registered design published, no results
yet. Two things are open:

- **Length/condition confound** -- unresolved. Response length may vary
  systematically by generation condition, which would confound the
  verbosity-bias measurement this project also plans to make. The main
  generation run is held until this is settled.
- **Contamination probe** -- generated, awaiting hand-scoring. The
  decision rule was fixed in advance: below 25% memorization, proceed as
  designed; at or above, the design changes before the main run, not
  after.

The full analysis plan -- dataset choice, cost, sample-size and power
reasoning, every confound found and how it was addressed, and a decisions
log tracking what changed and why as the design got checked against real
data -- is the detail for anyone who wants it:
**[ANALYSIS_PLAN.md](ANALYSIS_PLAN.md)**. No results exist yet; see
[RESULTS.md](RESULTS.md).

---

## How to run

    make setup      # install pinned dependencies
    make test       # run the cache + determinism tests
    make reproduce  # run the full pipeline end to end from cache (not yet implemented)

## How to label

ANALYSIS_PLAN.md is approved. Three pieces are built and tested; the last
step needs an API key and hasn't been run:

1. `data/raw/source_passages.json` -- done. 200 real MS MARCO QA items,
   fetched from RAGTruth's source data (src/prepare_dataset.py, no API key
   needed, just reads public data).
2. Response generation (src/generate_responses.py) -- written and tested
   against synthetic fixtures, not yet run for real. Records the full
   administration condition on every response, caches by that condition so
   a rerun costs nothing already-done, and is resumable if it dies partway.
   Check the cost first:

       python -m src.generate_responses --dry-run

   Dry run against the real 200 items: 800 calls (4 conditions x 200
   items), ~$2.70 (revised after the real contamination-probe calls showed
   output length was underestimated by 2.7x -- see ANALYSIS_PLAN.md's
   decisions log). **Held as of this writing** pending a length/condition
   confound check -- see ANALYSIS_PLAN.md's Open Questions. Needs
   `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` set (a
   `.env` file works) before running without `--dry-run` -- it fails loudly
   rather than falling back to anything if a key is missing, and only checks
   for a key right before a call it can't serve from cache.
3. The labeling tool (src/labeling.py, src/labeling_server.py) -- built and
   tested against synthetic fixtures. `make test` covers blinding (no model
   identity ever reaches the display payload) and resume-after-restart. It
   needs `data/generated/response_pairs.json` to exist, which step 2
   produces.

Once response_pairs.json exists:

    make label

Opens a local blind pairwise comparison UI at http://127.0.0.1:5000. Saves
incrementally to data/labels/labels.jsonl after every item; closing the tool
and reopening it resumes exactly where you left off, with the same queue
order and blinding it built the first time. A silent 10% repeat subset is
mixed in for later intra-rater agreement -- it is not marked as a repeat in
the UI.

## Layout

    CLAUDE.md          repo-specific context, imports shared rules
    ANALYSIS_PLAN.md   written and approved before any experiment code
    RESULTS.md         findings, kept separate from this file
    src/               pipeline code, cache layer, seeded-run helper
    data/raw/          unprocessed source data
    data/labels/       human labels -- append-only, never regenerated
    data/generated/    synthesized/model-generated data
    cache/             cached API responses so a rerun is cheap
    outputs/           pipeline outputs
    tests/             cache and determinism tests

## License scope

The MIT license in this repo covers the code only. It does not cover the
contents of data/labels/ or data/generated/ -- that data carries no license
grant here and should not be assumed reusable.
