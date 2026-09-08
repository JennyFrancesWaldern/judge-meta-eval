# judge-meta-eval

How much can an LLM judge be trusted on grounded-generation quality, and which biases move the score?

**Status:** Analysis plan published, results pending. See
[ANALYSIS_PLAN.md](ANALYSIS_PLAN.md) for the full pre-registered design,
including two open questions still unresolved and the decisions log
tracking what changed as the design was checked against real data. No
results exist yet -- see [RESULTS.md](RESULTS.md).

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
