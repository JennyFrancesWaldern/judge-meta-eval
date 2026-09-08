# judge-meta-eval

How much can an LLM judge be trusted on grounded-generation quality, and which biases move the score?

**Status:** Scaffolded -- no experiments run yet.

## How to run

    make setup      # install pinned dependencies
    make test       # run the cache + determinism tests
    make reproduce  # run the full pipeline end to end from cache (not yet implemented)

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
