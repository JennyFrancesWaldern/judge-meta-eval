# judge-meta-eval

How much can an LLM judge be trusted on grounded-generation quality, and which biases move the score?

**Status:** Scaffolded -- no experiments run yet.

## How to run

    make setup      # install pinned dependencies
    make test       # run the cache + determinism tests
    make reproduce  # run the full pipeline end to end from cache (not yet implemented)

## How to label

ANALYSIS_PLAN.md is approved. The labeling tool (src/labeling.py,
src/labeling_server.py) is built and tested against synthetic fixtures --
`make test` covers blinding (no model identity ever reaches the display
payload) and resume-after-restart. It has not been run against real data:
that needs `data/generated/response_pairs.json` to exist first, which in
turn needs the response-generation step from ANALYSIS_PLAN.md section 2 to
actually run (an approved ~$1 in API calls, not yet made -- see that file).

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
