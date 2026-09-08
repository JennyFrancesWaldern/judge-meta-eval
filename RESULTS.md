# Results

*No results exist yet. The analysis plan is published -- see ANALYSIS_PLAN.md
-- with two open questions still unresolved and the main generation run held
pending one of them. Nothing below has been run.*

<!-- status: plan published, results pending -->
<!-- headline: not yet available -->
<!-- repo_public: true -->

## Headline result

## Uncertainty

## What I expected and what actually happened

## Limitations

## What I'd do next

## Instrument validation

The labeling tool's repeat-injection logic (src/labeling.py) had a defect
during development, caught by its own test suite before any real labeling
happened.

**The defect:** a silent 10% subset of items is meant to be re-served later
in the queue, spaced at least `min_repeat_gap` positions from the original,
so intra-rater agreement can be measured without the repeat being
recognizable. The first implementation picked the repeat's source position
and insertion point using a snapshot of queue positions taken before any
insertions -- correct for the first repeat, but each later insertion shifts
everything after it, so a second repeat's source position could already be
stale by the time it was used. Two repeats could also both derive from the
same original item, letting a later repeat land *between* an existing
pair's two occurrences: each pair was individually spaced correctly against
the occurrence it was built from, but the adjacent gap between two
occurrences that were never directly compared was never validated at all.

**What it would have corrupted:** items meant to be spaced apart (e.g. by
15+ positions) could end up as few as 3 positions apart. A repeat served
that close to its original is much more likely to be recognized as the same
item rather than judged fresh -- which would inflate the measured
intra-rater agreement number, since a recognized repeat invites "be
consistent with myself" rather than an independent second judgment. Since
that number is the upper bound the whole project's judge-human agreement
claim is compared against, a silently inflated intra-rater estimate would
have made the judge look worse relative to a human ceiling that was never
actually real.

**Fix:** each item is now repeated at most once, so there is exactly one
gap per repeated item and it is always the gap that was validated at
insertion time. Caught by `tests/test_labeling.py::test_repeats_are_spaced_apart`
before the tool was ever run against real labels -- see the commit history
for judge-meta-eval.
