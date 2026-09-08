# Analysis plan: judge-meta-eval

**Status: pre-registered design. Published 2026-09-11. No results exist yet.**

## What this is

This is the analysis plan for a small study on LLM-as-judge trustworthiness,
published before any experiment has produced a result. The question:

> How much can an LLM judge be trusted to score grounded-generation quality,
> and which judge biases actually move the score enough to change a ranking
> between two responses -- not just detectably shift a number?

This matters because LLM judges are increasingly used as a cheap substitute
for human review at scale, and "the judge mostly agrees with humans on
average" is a different claim from "the judge is safe to trust on the
comparisons that matter." A bias that never flips a ranking is a footnote;
one that does changes which model or response actually gets shipped.

**Why this is published now, not after results.** Every design decision
below -- the dataset, the models, the sample size, the pairing scheme, the
cost -- was made and revised before a single result existed to shape it.
Publishing the plan at this stage is the only way a reader can verify that
rather than take it on faith. Two open questions are called out explicitly
below, with the concrete mechanism that resolves (or will resolve) each --
they are not buried in Limitations where a bad number could be quietly
absorbed after the fact. The decisions log at the end records what changed
and why, as it happened, rather than smoothing the history into a clean
story in hindsight.

No results exist yet. RESULTS.md says so explicitly and will continue to
until there's something real to report.

## The four conditions and five pair types, briefly

Everything from here on uses this shorthand. The full generation design and
the reasoning behind each choice is in "Response generation design," much
further down -- this is just enough to follow the Open Questions and
everything after without flipping back and forth.

Every one of 200 source items gets four generated responses:

- **(a) Strong, grounded** -- Claude Sonnet 5, given the source passage.
- **(b) Moderate, grounded, cross-family** -- GPT-5.4 mini, given the
  source passage.
- **(c) Weaker model, grounded** -- Claude Haiku 4.5, given the source
  passage.
- **(d) Deliberately ungrounded** -- Claude Sonnet 5, source passage
  withheld.

Each item is shown to the human labeler as exactly one pair, cycling
through five pair types: **a_b, a_c, a_d, b_d, b_c**. "Self-preference,"
used throughout, means: does the judge favor Claude-family responses over
GPT-family ones, tested on the three pair types that cross that line
(a_b, b_d, b_c).

## Open questions right now

Two things are unresolved as of this publish.

### 1. Length/condition confound -- unresolved, main generation run held

The 40 real contamination-probe calls (condition (d), Sonnet 5) came back
averaging 409 output tokens -- far more than assumed, and enough to raise a
real question: does response length vary systematically BY CONDITION (for
instance, if the "strong" condition happens to share a model with the
"ungrounded" condition, is it also systematically the longest one)? If so,
a judge preferring longer responses becomes hard to distinguish from a
judge tracking the intended quality signal -- the same confound structure
already found and addressed for self-preference (see the decisions log),
now possibly present for verbosity too, one of the three biases this study
measures.

This is genuinely open, not resolved-but-unwritten. Real output-length data
exists for only one of the four generation conditions so far (the disjoint
contamination-probe items, not the 200-item labeling pool). Settling it
requires measuring length across all four conditions on real data, then
choosing between an analysis-side correction -- length as a covariate in
the judge-agreement analysis, or a matched-length subsample specifically
for the verbosity experiment -- each with a real cost in interpretability
that hasn't been picked yet. The fix will not be a length constraint added
to the generation prompts: the point of this study is to evaluate what
these models actually produce, not a constrained version of them.

**The main 800-call generation run is held until this is settled** -- not
because the answer is known to be bad, but because it isn't known at all
yet, and this project does not spend on the strength of an unchecked
assumption twice in the same week.

### 2. Contamination probe -- generated, not yet hand-scored

40 items, disjoint from the 200-item labeling pool, generated under the
passage-withheld condition and awaiting hand-scoring for whether the model
already knew the answer without the passage (src/contamination_probe.py;
full design and why it has to be hand-scored rather than automated is in
Confounds, below).

**The decision rule, fixed before any score exists:** below 25%
memorization, the design proceeds as-is and the rate gets reported in
Limitations; at or above 25%, the ungrounded condition changes before the
main run, not after. That threshold was set when the probe was designed,
before a single item was scored. This is the part of this document doing
the most work -- it's the one place a bad number can't be quietly absorbed
into a footnote after the fact. It either passes or it changes the design,
decided in advance of seeing which.

## Question

How much can an LLM judge be trusted to score grounded-generation quality,
and which judge biases actually move the score enough to change a ranking
between two responses (not just detectably shift a number)?

## What decision this informs

Whether an LLM judge can replace (or supplement) human review when scoring
grounded QA responses at scale, and if so, under what administration
safeguards (position randomization, verbosity control, model-family
blinding). A "yes, trustworthy" finding would support using an LLM judge as
a cheap first-pass filter; a "no, biased enough to flip rankings" finding
would argue for keeping a human in the loop on close calls specifically.

## What I'm measuring and what I'm claiming it measures

Two related but distinct things:

1. **Judge-human agreement** on pairwise "which response is better grounded"
   verdicts. This measures how often an automated judge's preference matches
   a human's preference on the same pair -- it does NOT measure "ground
   truth correctness," since there is no ground truth beyond a human
   judgment call here. I am claiming agreement-with-a-labeler, not
   agreement-with-truth.

2. **Bias effect on ranking**, not just on raw score. Per the prompt that
   started this: a bias that shifts a score by a few points but never
   changes which response the judge prefers is a footnote. I'm measuring
   flip rate -- how often position swap, verbosity padding, or
   response-model identity changes the judge's preferred response -- against
   the human-labeled baseline preference for that pair.

**Self-preference scope limit, stated plainly (2026-09-08):** with one
cross-family model pair in the core design, this project **detects a
difference but can't attribute it**. If the judge prefers Sonnet 5 over
GPT-5.4 mini responses, that is equally consistent with "the judge favors
its own family" and "GPT-5.4 mini is genuinely the weaker response," and
the four-condition design on its own cannot separate those two
explanations. See "Self-preference confound" below for what does and
doesn't fix this, and at what cost.

**Important scope limit:** there is one labeler (me). "Judge-human
agreement" in this project means judge-agreement-with-a-single-labeler,
bounded above by that labeler's own intra-rater consistency (measured via a
blind repeat subset). This is not inter-rater reliability, and the writeup
must never describe it as if multiple independent human raters were
involved.

## How the scorer gets validated

The judge (built in a later phase) is validated against my own blind
pairwise labels, collected before any judge exists, via:
- Raw agreement rate and Cohen's kappa against my verdicts.
- Rank correlation between judge-implied and human-implied response
  rankings.
- My own intra-rater agreement on a silently-repeated 10% subset, which
  upper-bounds how good judge-human agreement could possibly look --
  reported and compared to the judge's number, not treated as a separate
  footnote.

## Sample size and why that number

**Bottleneck is my own labeling time**, not API cost (see cost estimate
below -- generation is roughly $1). Available time is 8-15 hours across
sittings. A pairwise item with blind presentation, a free-text rationale, a
confidence flag, and time tracking realistically takes ~3 minutes once past
the first few practice items.

- 200 base items, each labeled once, pairwise -> ~10 hours at 3 min/item.
- +20 items (10%) silently re-served as blind repeats, spaced apart, for
  intra-rater agreement -> ~1 hour.
- Total ~220 labeling instances, ~11 hours -- fits the budget with slack for
  slower items and breaks.

**What this size can and cannot detect, honestly:**
- At n=200 and an assumed true kappa around 0.5-0.6 (typical for
  judge-vs-human agreement reported in the literature), the 95% CI on kappa
  is roughly +/-0.08 to 0.12. Adequate for a headline "moderate agreement,
  here's the interval" statement.
- It is NOT adequate to stratify that agreement by subcondition (e.g.
  "agreement specifically on the ungrounded-response pairs," meaning a_d
  and b_d together, is ~80 of the 200 -- updated from the original 4-pair-type
  design's ~100 now that a 5th pair type (b_c) is in the mix -- and widens
  the interval further still). Any
  subgroup breakdown in the writeup will carry a visibly wider interval or
  get flagged as underpowered rather than reported as if it were as precise
  as the headline number.
- Bias-effect-on-ranking experiments (Phase 3) are judge-only after this
  point -- they replay the same items through the judge under manipulated
  conditions (position swapped, verbosity padded) and compare the judge to
  itself, only anchoring to the human labels to say which direction is
  "toward" or "away from" the human-preferred response. Those can run at
  much larger n (hundreds to low thousands of judge calls) cheaply, since
  they don't consume more of my labeling time -- **but only when POOLED
  across all 200 items.** The moment a comparison is scoped to a single
  pair type (self-preference is inherently scoped this way -- there's no
  pair without a cross-family model to test it on), it's back down to
  n=40-80 regardless of how cheap judge calls are, because that's how many
  human-anchored items exist for that specific pair type. See "Power at
  n=40 per pair type," below, for exact numbers -- some of these
  comparisons are meaningfully underpowered, and that's decided now, before
  labeling, not discovered in the writeup.

**Variance subset, revised 2026-09-09 -- format, not seed.** The original
version of this note (2026-09-08) proposed a second seed at temperature 0.7
on a 48-item subset, $0.28, flagged honestly as measuring "sampling
variance at temperature 0.7," not the variance of the actual
temperature-0.0 labeled dataset. Correct, but flagging a mismatch doesn't
fix it: that subset would have sat in RESULTS.md looking like the
METHODOLOGY.md variance commitment was satisfied when it wasn't. The
committed concern is specifically that **administration conditions are a
random effect and format/harness variance can exceed between-model
variance** -- and prompt format is exactly the thing fixed at generation
time in this design (see the administration-conditions section below),
which is the top-ranked failure mode in the Unit-1 notes this project is
built on, not a secondary one. A seed/temperature subset doesn't touch
that gap at all.

Replaced with a genuine format-variance subset: a stratified 50-item
subset (10 from each of the 5 pair-type groups), all 4 core conditions,
regenerated under 1-2 ALTERNATE prompt formats -- same items, same seed,
same temperature as the main run, only the wording/ordering/verbosity of
the instruction changes (passage-first vs. question-first, terse vs.
explicit -- the same axes Sclar et al. vary). This directly measures
whether format moves the responses, which is the thing actually named in
METHODOLOGY.md.

**Priced both ways** (revised 2026-09-10 with the corrected 410-token
output assumption -- see section 2 above):
- 1 alternate format: 200 calls, **$0.68** (real dry run against the
  actual 50-item subset).
- 2 alternate formats: 400 calls, **$1.35**.
- (For reference, the original seed/temperature version priced at $0.28 for
  a similar-sized subset, before the output-token correction -- comparable
  cost at the time, wrong target regardless.)

Going with **2 alternate formats ($1.35)**: one comparison point can't
distinguish "this particular reformulation happens to be similar" from
"format doesn't matter here" -- two independent reformulations give at
least a minimal spread to look at. If format variance turns out large
relative to the model differences this project is trying to detect, that
changes what the whole study can claim, and it needs to be known before
labeling starts, not discovered after. If it turns out small, that itself
is worth reporting -- it's evidence the fixed-format decision didn't cost
much, which the original plan could only assert, not show.

## What result would tell me I'm wrong

- If judge-human kappa looks reasonable but is statistically
  indistinguishable from my own intra-rater kappa on the repeat subset, that
  is not evidence the judge is good -- it's evidence the task is noisy
  enough that anything clears that bar. I would need to say so, not round it
  up to "judge matches human performance."
- If bias manipulations (position, verbosity, self-preference) produce large
  flip rates against the human-anchored preference, that would falsify the
  premise that average-case agreement is a sufficient trust signal, even
  where the headline kappa looks fine.
- If the contamination check (below) shows the response-generation models
  can reproduce source passages near-verbatim from memory, any "grounded"
  framing is compromised for that subset and needs to be reported as such,
  not quietly excluded after the fact.

## Confounds

- **Source-passage contamination on the weak condition, specifically.**
  MS MARCO is from 2016 and has almost certainly been in frontier
  pretraining data for years. This isn't just a general contamination
  caveat -- it's a design problem for condition (d): withholding the
  passage is only a valid "ungrounded" manipulation if the model doesn't
  already know the answer. For a memorized item, (d) silently stops being
  ungrounded and the condition becomes a mix of genuinely-degraded and
  secretly-fine responses labeled as one thing.

  **Two signals exist for this, and they are not interchangeable. Ordered
  here by which one actually gets trusted, not by which is cheaper.**

  **Primary measure: the 40-item hand-scored probe.** src/contamination_probe.py
  generates condition (d) only, on 40 items disjoint from the 200-item
  labeling pool (so nothing here is later shown to me during blind
  labeling), and I score each by hand for whether the withheld-passage
  answer is still substantively correct -- restated in the model's own
  words counts, not just verbatim recall. This is the only signal in this
  project that can catch paraphrased memorization, which is the more
  likely form it takes: a model that "knows" a fact from pretraining
  answers with it in its own words far more often than by reciting the
  source passage verbatim. Not scored by an automated judge, since we have
  no validated one yet and using one here would be circular. Decision
  rule, fixed in advance: below 25% memorization, proceed and report the
  rate in Limitations; at or above 25%, the ungrounded condition changes
  before the full run rather than proceeding with a footnote. Cost: 40
  calls, ~$0.06. **This is the number that decides whether the full run
  happens as designed.**

  **Secondary, supplementary signal: the mechanical flagger.** After the
  probe clears (or the design is revised), src/memorization_flagging.py
  runs a regex check against the MAIN 200-item pool's own condition-(d)
  responses -- already generated as part of the 800-call core run, so this
  costs nothing extra, and no human ever looks at the withheld-passage
  text to produce it, so it never touches blinding. **What it can and
  cannot detect, stated together with its result, not separately:** it
  only catches VERBATIM leakage of distinctive tokens -- a phone number, a
  dollar figure, a proper-noun phrase reproduced exactly. A model that
  memorized a fact and restated it in its own words -- the more common
  failure mode, per the primary probe's design above -- produces no
  matching token and the flagger sees nothing. **A low flag rate is
  therefore close to uninformative on its own** and must never be reported
  as "contamination is low" -- only as "verbatim leakage is low," with the
  paraphrase blind spot named in the same sentence. Its only legitimate
  use in this project is a per-item sensitivity check (does excluding the
  handful of verbatim-leak items change the headline result), never as a
  substitute for, or a more reassuring restatement of, the hand-scored
  rate above.

  **Revised plan below 25% (from the hand-scored probe):** proceed with
  the full run, AND run the mechanical flagger against the real 200-item
  pool once condition (d) exists, AND report the primary analysis (full
  200 items) alongside a sensitivity check with flagged items removed --
  clearly labeled as catching only the verbatim-leak subset, not a
  complete accounting of memorization. Flagged items are never silently
  excluded pre-labeling -- excluding based on an imperfect heuristic
  before seeing the data risks a selection bias of its own, and it would
  shrink the labeling investment below the n the sample-size section
  already sized carefully.

  A second, distinct contamination question -- can the generation models
  recite the passages verbatim, which would inflate the *grounded*
  conditions (a, b, c) rather than invalidate the ungrounded one -- remains
  open and is not covered by either signal above. Worth a similar cheap
  check before trusting any "grounded" framing, but is not gating the
  current spend decision the way the (d)-condition check is.
- **Single labeler.** See scope limit above -- no inter-rater reliability is
  possible here, only intra-rater.
- **Quality vs. groundedness conflation.** A genuinely weaker model's
  response may read as "worse" to a human labeler for reasons unrelated to
  grounding fidelity (worse prose, awkward phrasing). The rationale
  free-text field exists specifically to let me distinguish "ungrounded"
  from "poorly written" after the fact -- but if I don't use it
  consistently, the two will be conflated in the label itself.
- **Administration conditions fixed at generation time.** See design note
  below -- prompt format and few-shot draw are NOT crossed during response
  generation, for labeling-budget reasons. That means this dataset cannot
  speak to whether the human-labeled ground truth itself would look
  different under a different generation administration. Format/position
  sensitivity is deliberately pushed to the judge side (Phase 3), where
  it's cheap to test without new human labels.

---

## Supporting detail (for the record; not part of the template above)

### 1. Dataset choice: RAGTruth (MIT license), QA subset

Three candidates considered:

- **RAGTruth** (arXiv:2401.00396, MIT license). ~18,000 human-annotated
  responses across QA (MS MARCO passages), summarization (CNN/DailyMail +
  a "Recent News" subset), and data-to-text (Yelp), generated by 6 models.
  Source passages are bundled directly in the release -- no live fetch
  required, which matters for the "one command reproduces this" goal.
  Recommended, scoped to the QA subset (MS MARCO passages + questions) to
  match the "grounded QA" framing of the research question and keep the
  passage domain consistent.
  Weakness: passage contamination risk (see Confounds), and MS MARCO
  passages are short web snippets, which somewhat compresses how rich a
  "deliberately weak" grounding failure can look compared to longer
  documents.

- **ExpertQA** (arXiv:2309.07852, MIT license). 2,177 expert-curated
  long-form questions across 32 fields. Rejected for this project: it does
  not bundle source documents, only URLs/passage fragments cited within
  answers. Re-fetching external pages at labeling or reproduction time
  risks link rot and inconsistent formatting -- a direct conflict with the
  "clone and run one command" reproducibility bar in CLAUDE.md.

- **CRAG / Meta Comprehensive RAG Benchmark** (facebookresearch/CRAG,
  KDD Cup 2024). Domain-diverse QA (finance, sports, music, movies, open
  domain), but retrieval is served through a mock knowledge-graph/web-search
  API rather than bundled static passages, and redistribution terms for the
  underlying data aren't clearly established. Rejected on infrastructure
  complexity (mock API dependency disproportionate to a solo scaffold
  project) and license-clarity grounds.

### 2. Response generation design and cost estimate

**Revision, 2026-09-07:** the original version of this section used 2
models (Sonnet 5, Haiku 4.5) across 3 conditions -- flagged during review as
not a real spread, and worse, both models are Anthropic. That leaves no
cross-family response for Phase 3's self-preference bias experiment ("does
the judge favor its own family") to test against. Revised to 3 models
across 4 conditions below. Recorded here rather than silently edited so the
plan's history is visible.

For each of 200 sampled MS MARCO QA items (passage + question), generate
four responses -- fresh generations, not RAGTruth's bundled responses, so
the quality spread and the "deliberately weak" condition are under my
control:

- **(a) Strong, grounded** -- Claude Sonnet 5, given passage + question,
  prompted normally. Anthropic.
- **(b) Moderate, grounded, cross-family** -- GPT-5.4 mini, same passage +
  question. Exists specifically so a human-labeled pair with a non-Anthropic
  response exists at all -- without it, Phase 3's self-preference test has
  nothing to anchor to.
- **(c) Weaker model, grounded** -- Claude Haiku 4.5, same passage +
  question. A genuine capability-driven quality spread rather than a
  sabotaged prompt. Anthropic.
- **(d) Deliberately ungrounded** -- Claude Sonnet 5, given ONLY the
  question (passage withheld), forced to answer from parametric knowledge
  alone. Holds model capability constant and isolates the specific failure
  mode this project is about: did the response actually use the source.
  Not a smaller model and not a truncated passage -- see the note on why
  those two mechanisms are kept distinct, below.

**Why not a degraded prompt or a truncated passage for the weak condition:**
asking a capable model to deliberately answer worse produces stylistic
tells (hedging, artificial simplicity) that no real deployment failure
looks like, which would make the judge's job unrealistically easy. Cutting
part of the passage muddies whether a resulting failure came from missing
information or from the model handling what remained poorly. (c) and (d)
are each a single, clean manipulation targeting a different failure mode:
(c) is genuine capability-driven weakness, confounded with general fluency
(this is exactly the "quality vs. groundedness conflation" confound below,
which the rationale field exists to help separate); (d) is condition-driven
ungroundedness with capability held constant. They are deliberately not
interchangeable.

**Pairing, to stay inside the 200-comparison labeling budget:** each item
gets exactly one pair, not all six possible combinations. Items are split
into five equal groups (40 each, assigned by item index mod 5) cycling
through: (a vs b), (a vs c), (a vs d), (b vs d), (b vs c). This guarantees
the cross-family pairs (a vs b, b vs d, and now b vs c) get real labeled
coverage rather than being crowded out by same-family comparisons.

**b vs c, added 2026-09-09.** Originally listed as a missing pair and
correctly called out as the sharper self-preference test: GPT-5.4 mini
against Haiku 4.5 -- two small, cheap models on opposite families, closer
to capability-matched than anything else in this design (unlike a vs b,
where Sonnet 5 is presumably the stronger model regardless of family).
**This costs nothing extra in generation spend.** Conditions (b) and (c)
are already generated for all 200 items regardless of which pair a given
item is scheduled for -- adding a 5th pair type only changes which
already-generated responses get shown to the labeler, not what gets
generated. The actual cost is a labeling-design tradeoff, not a dollar
one: 5 pair types over the same 200 items means 40 per type instead of 50,
which is what changed in the sample-size section's per-subgroup CI
discussion. Total labeling time is unaffected -- still ~200 items, ~11
hours -- because this redistributes the existing 200, it does not add to
them.

**Which 5 of the 6 possible pairs, and the one that's still missing.**
With b_c added, only **c vs d** (weak-grounded vs. ungrounded) remains
uncovered. That means I still can't say which failure mode -- a weaker
model trying its best, or a strong model guessing without the source --
looks worse to a human; I only know how each compares to the strong
condition (a) individually. Adding a 6th pair type would mean either more
labeling time (not authorized) or thinning every group to 33-34 items
(widening every subgroup CI further); left out for now on that basis.

**Cost estimate, revised 2026-09-10 with real measured output length.**
The original estimate (below, struck through in spirit not in markdown)
assumed ~150 output tokens per call, official per-million-token rates
checked against claude.com/pricing and the OpenAI API pricing docs on
2026-09-07. The 40 real contamination-probe calls (condition d, Sonnet 5)
came back averaging **409 estimated tokens, range 210-594** -- Sonnet 5
writes full markdown-formatted answers by default, even on an open-ended
prompt with no length instruction. 150 was the wrong order of magnitude,
not just imprecise. `ESTIMATED_OUTPUT_TOKENS` is now 410 everywhere in
src/generate_responses.py. Grounded conditions (a, b, c) haven't produced
real data yet -- their "use only the passage above" instruction may or may
not be more constraining than condition (d)'s open prompt -- so 410 is
applied to them too, pending real evidence, rather than assuming they're
shorter with no basis.

| Condition | Model | Input cost | Output cost (@410 tok) | Subtotal |
|---|---|---|---|---|
| (a) strong | Sonnet 5 ($2/$10 per M) | $0.12 | $0.82 | $0.94 |
| (b) moderate, cross-family | GPT-5.4 mini ($0.75/$4.50 per M) | $0.045 | $0.369 | $0.41 |
| (c) weak | Haiku 4.5 ($1/$5 per M) | $0.06 | $0.41 | $0.47 |
| (d) ungrounded | Sonnet 5, no passage | $0.05 | $0.82 | $0.87 |

**Total: ~$2.70** for the full 800-generation response pool -- confirmed by
an actual dry run against the real 200-item data with the corrected
constant. Up from the original $1.17 estimate; still small in absolute
terms, but a 2.3x miss on a number already presented as "checked," not
guessed, which is itself worth sitting with -- the input-token side was
real (measured from actual passages), the output-token side was not
(a flat assumption dressed up next to a measured number), and that
asymmetry wasn't flagged clearly enough the first time. Even with a 3-5x
buffer for prompt iteration and retries, this stays under ~$12-13. Judge-
scoring costs (Phase 3) are separate and carry the same open question --
see the total-cost section near the end of this file.

### 2b. Self-preference confound: investigation and what it costs to reduce

Raised in review: with a single cross-family model (b), family and
capability are confounded. If GPT-5.4 mini is weaker than Sonnet 5, a judge
preferring Claude responses is indistinguishable from a judge preferring
better responses. Confirmed -- see the scope-limit note near the top of
this document, in the requested words: **this design detects a difference
but can't attribute it.**

**What "buy a capability-matched cross-family model" turned out to mean, on
checking OpenAI's actual docs (not memory) on 2026-09-08:** price parity is
not capability parity. `gpt-5.6-terra` is priced almost identically to
Sonnet 5 ($2/$12 vs. $2/$10 per million tokens), which looks like an
obvious fix -- but OpenAI's own model page describes Terra as roughly
corresponding to "the mini model tier used in earlier GPT-5 families."
Their actual flagship is `gpt-5.6-sol` ($4/$20), described as "a flagship
model ... corresponds to the unsuffixed model tier." Meanwhile Sonnet 5 is
Anthropic's mid tier, not their flagship (Opus 5 and Fable 5.1 sit above
it). There is no benchmark I can point to that establishes Sonnet 5 and any
specific OpenAI model as equivalently capable -- vendor tier names and
prices are not a reliable cross-vendor capability scale. So no single model
swap "buys" a confirmed clean comparison; it only trades one guess for
another.

**What this project does about it, at two different costs:**

1. **Free, using data already being collected.** The 200-item human-labeled
   set already includes 100 a_b and b_d pairs. Once labeled, the human
   win-rate on those pairs is itself an empirical estimate of how
   comparable (a) and (b) actually look to a person -- not a vendor
   tier-name assumption. If it comes back near 50%, the existing
   cross-family pair is validated as roughly matched after the fact; if
   skewed, that skew itself becomes the capability-gap estimate the
   self-preference number needs to be interpreted against. This costs
   nothing beyond the already-approved labeling.

2. **~$0.77 (revised 2026-09-10 with the 410-token correction), bracketing
   from the other side.** Added condition (e) =
   `gpt-5.6-sol` (confirmed model ID, OpenAI's actual flagship, per the docs
   check above), generated for the items whose scheduled pair is
   bracket-eligible -- a vs b or b vs d (src/generate_responses.py,
   BRACKET_CONDITION, BRACKET_ELIGIBLE_PAIR_TYPES). With 5 pair types now
   (see b_c below), that's 80 items, not 100. Not human-labeled -- that
   would add to those items' labeling load, which wasn't authorized -- but
   available in Phase 3 for the judge to score automatically against (a)
   and (d). Logic: gpt-5.4-mini is presumably weaker than Sonnet 5, and
   gpt-5.6-sol is presumably stronger. If the judge prefers Claude
   responses regardless of which side of Sonnet 5 the OpenAI competitor
   sits on, that consistency is real evidence for family preference over
   capability-tracking -- a capability-tracking judge should flip which
   family it prefers when the capability gap reverses direction. Cost,
   real dry run against the actual 80 items: **80 calls, $0.77.**

3. **Free, a genuinely matched pair.** b_c (GPT-5.4 mini vs. Haiku 4.5, see
   the pairing note below) is the confound-lighter version of this same
   test -- two small models, opposite families, without needing to guess
   at a "flagship" bracket at all. It costs nothing beyond the labeling
   already planned, since it's a redistribution of the existing 200 items
   across one more pair type, not new items or new generation.

All three are additive, not redundant: option 1 sizes the gap for the mini
comparison; option 2 checks whether judge preference direction tracks a
capability gap that reverses sign; option 3 is the same question asked
with the least capability confound of any pair in the design.

### 3. Administration conditions: sampled, not fully crossed

METHODOLOGY.md requires treating administration conditions (prompt format,
position, few-shot draw) as a random effect, not folding their variance
into a single pooled estimate. Fully crossing them during response
GENERATION (e.g., 2 formats x 2 few-shot draws x 200 items) would multiply
the human-labeling burden past the 8-15 hour budget for no proportionate
gain, since format/position sensitivity is primarily a property of interest
for the JUDGE, not the generator, in this project's question.

Decision: fix a single generation format for the 200-item human-labeled
corpus (keeps labeling tractable and keeps the ground-truth comparison
clean). Push prompt-format and position sensitivity entirely to the judge
side in the next phase, where it's automatable against the existing 200
human labels without consuming any more labeling time. Few-shot draw
variance is scoped to the judge's prompt as well, not the generator's,
since zero-shot generation is standard for the model tier being used here.

**Cost of this choice, stated plainly:** this dataset cannot say whether
the human-labeled ground truth itself would look different under a
different generation administration. That's a real limitation -- but as of
2026-09-09 it is no longer an unmeasured one: see the format-variance
subset in the Sample-size section above, which directly tests how much
responses move under 2 alternate, semantically equivalent formats, and the
Confounds section, where this limitation lives alongside that result.

### 4. Total project cost estimate through Phase 3

Revised 2026-09-09: format-variance subset replaces the seed/temperature
subset (same rough cost, different and now-relevant target); b_c pairing
added at no generation cost; self-preference bracket recomputed at 80
items (not 100) now that there are 5 pair types instead of 4.

Requested as one number, not per-phase. Phase 3 itself has not been
formally planned or approved yet -- only sketched (judge v1, position
swap, verbosity padding, self-preference, three mitigations) -- so the
judge-side figures below are a rough order of magnitude, not a committed
budget, built the same way as everything else here: real per-token pricing,
input-token estimates from the real 200-item data where the object being
priced already exists (the judge prompt includes the real passage, whose
average length I already have: ~343 tokens), and stated assumptions where
it doesn't yet (response length ~150 tokens, judge output ~200 tokens,
rubric output ~500 tokens -- all flat assumptions, labeled as such).

**Correction, 2026-09-10: the Phase 1/2 rows below are real measurements;
the Phase 3 rows are still the original, now-suspect flat assumptions.**
The contamination probe's 40 real Sonnet-5 calls came back averaging 409
output tokens against a 150-token assumption -- a 2.7x miss, not a
rounding error, because Sonnet 5 writes full markdown-formatted answers by
default even on a plain, unconstrained prompt. Every Phase 3 row below
also assumes a Sonnet-5-family judge producing a SHORT verdict (200-500
tokens) on an equally unconstrained prompt. That assumption has not been
tested and, on the evidence above, has a real chance of being similarly
wrong -- an unconstrained judge prompt could just as easily come back
verbose. **Design lesson to carry into Phase 3, not yet applied here:**
judge prompts should force brevity explicitly (a word/token limit stated
in the prompt, or structured output via `output_config.format`) rather
than assume a judge task is naturally terse. Until Phase 3 is actually
built and priced against real judge calls the same way, treat the Phase 3
subtotal as having the same order-of-magnitude uncertainty the Phase 1/2
numbers just turned out to have -- plausibly 1-3x higher, not a number to
budget against precisely.

| Component | Calls | Est. cost |
|---|---|---|
| Core generation (4 conditions x 200 items, 5 pair types incl. b_c) | 800 | $2.70 |
| Contamination probe (condition d x 40 disjoint items) -- actually spent | 40 | $0.06* |
| Memorization flagging (mechanical, code-only, reuses core-run data) | 0 | $0.00 |
| Format-variance subset (2 alternate formats x 4 conditions x 50 items) | 400 | $1.35 |
| Self-preference bracket generation (gpt-5.6-sol x 80 items) | 80 | $0.77 |
| **Phase 1/2 subtotal (real, measured)** | **1,320** | **$4.88** |
| Judge v1 baseline (Sonnet-5 judge x 200 pairs) | 200 | $0.72 |
| Position-swap bias experiment | 200 | $0.72 |
| Verbosity bias experiment (200 padding generations + 200 judge calls) | 400 | $1.42 |
| Self-preference judge scoring (a_b/b_d + a_e/e_d bracket + b_c, 2 judges) | 400 | ~$2.16 |
| Swap-averaging mitigation | 0 | $0.00 (reuses position-swap data) |
| Rubric-decomposition mitigation | 200 | $1.32 |
| Reference-guided grading mitigation | 200 | $0.78 |
| **Phase 3 subtotal (rough order of magnitude, unverified output-length risk above)** | **1,600** | **~$7.12** |
| **Total through Phase 3** | **~2,920** | **~$11.99 nominal (plausibly $14-20 if Phase 3 judge output runs as verbose as Phase 1/2 generation did)** |

Call it **under $15-20 all-in** with the correction above folded in, not
the earlier "under $12." I will price Phase 3 against real judge calls the
same way Phase 1/2 is now priced -- measured, not assumed -- before any of
that spending starts, and will apply the brevity-forcing design lesson
above when writing the judge prompt rather than repeat the mistake.
*Contamination-probe cost is the one line above already actually spent,
not estimated -- $0.06 was accurate, since a 40-call, low-value spend was
worth just watching directly rather than re-estimating.

### 5. Power at n=40 per pair type (added 2026-09-09)

Computed directly (normal-approximation proportion tests, alpha=0.05
two-sided, 80% power -- standard formulas, not simulated, verified by
script), not estimated by feel. Two kinds of comparison need to be told
apart: a **one-sample test** (is this cell's rate different from a fixed
reference, e.g. "is judge preference different from a fair 50/50 coin")
and a **two-sample test** (is cell A's rate different from cell B's rate).
Phase 3's per-pair-type comparisons are almost all the first kind.

**Self-preference (one-sample vs. a 50/50 null) -- the sharpest case:**

| n | Minimum detectable skew | Practical meaning |
|---|---|---|
| 40 (one pair type: b_c alone, or a_b alone, or b_d alone) | 22.1pp | Only a ~72/28 split or worse is detectable. A real-but-moderate 60/40 skew will NOT reach significance. |
| 80 (bracket-eligible items, a vs {b,e} pooled) | 15.7pp | Still needs ~66/34 or worse. |
| 120 (a_b + b_d + b_c pooled, ignoring which specific pairing) | 12.8pp | Needs ~63/37 or worse. |
| 200 (hypothetical, if every item were cross-family) | 9.9pp | Not achievable here -- only 120 of 200 items touch a cross-family comparison at all. |

**This is the underpowered comparison, named plainly: self-preference at
the per-pair-type level (b_c alone, or a_b alone) cannot detect anything
short of a dramatic, ~70/30-or-worse split.** A moderate but still
practically concerning skew -- 60/40, say -- reads as statistically null
at n=40, not because there's no effect, but because the design can't see
it at that grain. b_c specifically, the pair added this round precisely
*because* it's the sharpest self-preference test, inherits this limit like
every other single-pair-type cell.

**Flip rate / verbosity effect (one-sample vs. a small baseline, ~10%):**

| n | Minimum detectable rate above baseline | 
|---|---|
| 40 (single pair type) | 13.3pp (detect >= ~23%) |
| 80 | 9.4pp (detect >= ~19%) |
| 200 (pooled, ignoring pair type) | 5.9pp (detect >= ~16%) |

Pooled at n=200, these are reasonably powered for a "does this bias exist
at a rate that would change a ranking decision" question -- which is the
question this project actually cares about (see "What I'm measuring,"
above: a bias that never flips anything is a footnote). Broken down by
pair type, they fall into the same 40-80 range as self-preference above.

**Between-cell comparisons (two-sample, e.g. "is pair-type A's flip rate
different from pair-type B's"):** 28.7pp at n=40 per arm, 20.3pp at n=80.
Coarser than either one-sample case above -- this project cannot make
fine-grained claims about which specific pair type is most bias-prone.

**Mitigation deltas** (swap-averaging, rubric decomposition,
reference-guided grading): evaluated the same way as judge-human
agreement -- kappa against the 200 human labels. Pooled at n=200, the
existing +/-0.08-0.12 kappa CI (see Sample size, above) applies; a
mitigation's improvement needs to move kappa by roughly that much to be
distinguishable from noise. Per-pair-type mitigation effects inherit the
same n=40-80 limits as above and are not separately powered.

**What's underpowered, stated plainly:** every PER-PAIR-TYPE breakdown
(self-preference in b_c alone, or a_b alone; flip rate specifically within
one pair type; a mitigation's effect measured only on one pair type) is
underpowered for anything but a large effect. Every POOLED measure (flip
rate and verbosity effect across all 200; mitigation deltas against the
full kappa) is reasonably powered for effects in the 6-10pp / kappa-CI
range, which is closer to the size of effect this project would actually
act on.

**Options, and the call:**

1. *More items* -- doesn't fix the sharpest case. Going from 40 to 50 per
   cell (the original 4-pair-type design) only moves the self-preference
   MDE from 22.1pp to 19.8pp -- still requires a ~70/30 split. Getting to a
   genuinely well-powered single-pair-type self-preference test (say,
   MDE ~10pp) would need n≈200 for that ONE pair type alone, which is the
   entire labeling budget spent on one comparison. Not worth it.
2. *Fewer pair types* -- dropping b_c and returning to 4 types at 50 each
   has the same problem: it doesn't rescue per-cell power (above), so it
   trades away a free, genuinely matched comparison for a power gain that
   doesn't materialize. **Recommendation: don't drop b_c.**
3. *Accept descriptive status where it's actually true, and pool where
   pooling is honest* -- this is the plan going forward:
   - **Inferential claims** (adequately powered): flip rate and verbosity
     effect POOLED across all 200 items; a POOLED self-preference estimate
     across all cross-family-touching comparisons (a_b + b_d + b_c, n=120,
     MDE 12.8pp) that asks "does the judge show a family preference at
     all," without asking which specific pairing drives it; mitigation
     deltas against the full-sample kappa.
   - **Descriptive only, stated as such wherever reported**: any
     per-pair-type breakdown, including b_c alone, a_b alone, and b_d
     alone. These get reported as observed rates with their (wide) CIs
     shown, explicitly labeled as not powered to distinguish from chance
     at this n, not quietly presented alongside the pooled inferential
     numbers as if they carried the same weight.

This is written down now so it constrains the eventual write-up rather
than getting discovered while drafting RESULTS.md: a per-pair-type
self-preference number that isn't statistically distinguishable from 50/50
must be reported as "not detectable at this n," never as "no
self-preference found."

---

## Decisions log

Chronological. Each entry is a design that changed because something got
checked, not because of taste -- that's the point of keeping this log
instead of quietly editing history.

**2026-09-07 -- Dataset and generation design first written.** RAGTruth
(MIT) chosen over ExpertQA (no bundled source passages) and CRAG (mock-API
dependency, unclear redistribution terms). Original response-generation
design: 2 models (Sonnet 5, Haiku 4.5), 3 conditions.

**2026-09-07 -- 2 models flagged as not a real spread, and worse, both
Anthropic.** Revised to 3 models / 4 conditions, adding GPT-5.4 mini,
specifically so Phase 3's self-preference test would have a cross-family
response to work with at all.

**2026-09-08 -- Self-preference confound found: GPT-5.4 mini is plausibly
just the weaker model, not evidence of family bias.** Investigated what a
"capability-matched" fix would cost. Checking OpenAI's docs directly rather
than trusting price as a proxy: a same-priced model (gpt-5.6-terra) is
documented by OpenAI itself as mini-tier, not matched at all -- price
turned out not to be a reliable cross-vendor capability scale. Added a
gpt-5.6-sol flagship bracket ($0.77) to test whether judge preference
reverses when the capability gap reverses, plus a free check using the
human win-rate on the existing pairs. The scope limit is stated in this
plan in these exact words: **"this design detects a difference but can't
attribute it."**

**2026-09-08 -- Variance subset added: a second seed at temperature 0.7.**
Priced at $0.28. Flagged honestly at the time as measuring "sampling
variance at temperature 0.7," not the variance of the actual temperature-0
labeled dataset.

**2026-09-09 -- That variance subset replaced, not just re-flagged.**
An honest caveat doesn't fix a subset measuring the wrong thing --
METHODOLOGY.md's top-ranked risk (format/harness sensitivity, per this
project's own Unit 1 notes) was the actual unmeasured gap. Replaced with a
format-variance subset: the same items regenerated under 2 alternate,
semantically equivalent prompt formats. Pair b_c (GPT-5.4 mini vs. Haiku
4.5) added the same day at zero extra generation cost -- both models are
already generated for every item regardless of pairing, so a 5th pair type
only redistributes which existing responses get labeled. A power analysis
was added: self-preference at n=40 per pair type needs a ~72/28 split to
detect at 80% power, computed directly, not estimated by feel.

**2026-09-09 -- Contamination check restructured: the hand-scored probe
made explicitly primary, the mechanical regex flagger made explicitly
secondary.** The flagger only catches verbatim token leakage; a model that
memorized a fact more often restates it in its own words. A low flag rate
is close to uninformative on its own and is never allowed to be reported
as if it meant low contamination.

**2026-09-10 -- Contamination probe run for real. Three SDK bugs found by
actually executing it, not by review.** contamination_probe.py never
called load_dotenv() itself; Sonnet 5 rejects the `temperature` parameter
outright (removed from the current API, not defaulted); the pinned Haiku
model ID carried a stale date suffix. All three had passed code review and
every test written so far -- none of that surfaces a bug that only a real
API call exposes. Fixed, with a regression test added for the
load_dotenv gap specifically.

**2026-09-10 -- 2.7x cost miss found in the same real run.** The 40 real
calls averaged 409 output tokens against a 150-token flat assumption used
everywhere in the cost model. Not a rounding error -- Sonnet 5 writes full
markdown-formatted answers by default even on a plain, unconstrained
prompt. Every cost figure in this document that depends on output length
was recomputed against the measured value. Phase 3's judge-call estimates
are flagged as carrying the same unverified assumption, with a plan to
verify them the same way -- a minimal real judge call -- before that
spending starts, and to force brevity explicitly in the judge prompt
(fine for a judge; not fine for the responses under study).

**2026-09-10 -- Length/condition confound noticed, unresolved.** The same
409-token measurement raised the question of whether response length
varies systematically by generation condition, which would confound the
verbosity-bias measurement -- and possibly compound the self-preference
confound above, if the same model family is both the "strong" condition
and the longest one. Open as of this publish; see Open Questions, above.
The main 800-call generation run is held pending resolution.
