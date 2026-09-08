# Analysis plan

*Written before any experiment code, per CLAUDE.md. Needs approval before the
pipeline is built. No API calls, no dataset downloads, and no results exist
yet -- everything below is a proposal.*

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
  they don't consume more of my labeling time. So: human-agreement estimate
  is the tightly-constrained number; bias-flip-rate estimates can be much
  better powered.

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

**Priced both ways:**
- 1 alternate format: 200 calls, **$0.29** (real dry run against the
  actual 50-item subset).
- 2 alternate formats: 400 calls, **$0.58**.
- (For reference, the original seed/temperature version priced at $0.28 for
  a similar-sized subset -- comparable cost, wrong target.)

Going with **2 alternate formats ($0.58)**: one comparison point can't
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
  secretly-fine responses labeled as one thing. Concrete check, run before
  the full spend (src/contamination_probe.py, not yet executed): generate
  condition (d) only, on 40 items disjoint from the 200-item labeling pool
  (so nothing here is later shown to me during blind labeling), and I score
  each by hand for whether the withheld-passage answer is still correct --
  not with an automated scorer, since we don't have a validated one yet and
  using one here would be circular. Decision rule, fixed in advance: below
  25% memorization, proceed and report the rate in Limitations; at or above
  25%, the ungrounded condition changes before the full run rather than
  proceeding with a footnote. Cost: 40 calls, ~$0.06.

  A second, distinct contamination question -- can the generation models
  recite the passages verbatim, which would inflate the *grounded*
  conditions (a, b, c) rather than invalidate the ungrounded one -- remains
  open and is not covered by this probe. Worth a similar cheap check before
  trusting any "grounded" framing, but is not gating the current spend
  decision the way the (d)-condition check is.

  **The rate-vs-flags gap, addressed 2026-09-09.** The probe runs on items
  disjoint from the 200-item labeling pool specifically to protect
  blinding -- but that means it produces an overall RATE with no way to
  say which of the 200 actual labeling items are contaminated. At, say,
  15% (below the 25% threshold), the honest position was going to be
  "proceed knowing roughly 15% of condition (d) isn't really ungrounded,
  with no way to tell which items." That's not good enough on its own.

  There is a way to do better without compromising blinding: a mechanical,
  code-only check (src/memorization_flagging.py) run against the MAIN
  pool's own condition-(d) responses -- already generated as part of the
  800-call core run, so this costs nothing extra. It extracts distinctive,
  hard-to-guess facts from each passage (phone numbers, dollar amounts,
  percentages, 4+ digit numbers, multi-word proper-noun phrases) and checks
  whether they appear verbatim in that item's own withheld-passage
  response. No human ever looks at the withheld-passage text to produce
  this flag -- it's regex-based text matching, not a judgment call -- so it
  never touches what I see during labeling. This is different in kind from
  the earlier rejection of an automated judge for the *general* research
  question (that would be circular, since we have no validated judge);
  checking for a literal phone number leaking through has no such
  circularity problem.

  Honest limits: this catches the easy, distinctive cases and will miss
  memorization of diffuse, non-numeric content -- it under-counts, it
  doesn't over-count, and it is a supplement to the disjoint-sample rate,
  not a replacement for it.

  **Revised plan below 25%:** proceed with the full run, AND run the
  mechanical flag against the real 200-item pool once condition (d) exists,
  AND report both the primary analysis (full 200 items) and a sensitivity
  check with flagged items removed. That is a real answer with a number
  attached, not a footnote saying contamination might be a problem.
  Flagged items are never silently excluded pre-labeling -- excluding
  based on an imperfect heuristic before seeing the data risks a selection
  bias of its own, and it would shrink the labeling investment below the
  n the sample-size section already sized carefully.
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

**Cost estimate** (official per-million-token rates, checked directly
against claude.com/pricing and the OpenAI API pricing docs on 2026-09-07):
assuming ~300 input tokens (passage + question + instructions) and ~150
output tokens per call, 200 calls each for (a), (b), (c), (d):

| Condition | Model | Input cost | Output cost | Subtotal |
|---|---|---|---|---|
| (a) strong | Sonnet 5 ($2/$10 per M) | $0.12 | $0.30 | $0.42 |
| (b) moderate, cross-family | GPT-5.4 mini ($0.75/$4.50 per M) | $0.045 | $0.135 | $0.18 |
| (c) weak | Haiku 4.5 ($1/$5 per M) | $0.06 | $0.15 | $0.21 |
| (d) ungrounded | Sonnet 5, no passage | $0.05 | $0.30 | $0.35 |

**Total: ~$1.20** for the full 800-generation response pool. Confirmed by an
actual dry run against the real 200-item RAGTruth sample (not the flat
token assumption above): **$1.17**, using real prompt text. Even with a
5-10x buffer for prompt iteration and retries, this stays under ~$12.
Judge-scoring costs (Phase 3) are separate -- see the total-cost section
near the end of this file.

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

2. **~$0.35, bracketing from the other side.** Added condition (e) =
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
   real dry run against the actual 80 items: **80 calls, $0.35.**

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

| Component | Calls | Est. cost |
|---|---|---|
| Core generation (4 conditions x 200 items, 5 pair types incl. b_c) | 800 | $1.17 |
| Contamination probe (condition d x 40 disjoint items) | 40 | $0.06 |
| Memorization flagging (mechanical, code-only, reuses core-run data) | 0 | $0.00 |
| Format-variance subset (2 alternate formats x 4 conditions x 50 items) | 400 | $0.58 |
| Self-preference bracket generation (gpt-5.6-sol x 80 items) | 80 | $0.35 |
| **Phase 1/2 subtotal** | **1,320** | **$2.16** |
| Judge v1 baseline (Sonnet-5 judge x 200 pairs) | 200 | $0.72 |
| Position-swap bias experiment | 200 | $0.72 |
| Verbosity bias experiment (200 padding generations + 200 judge calls) | 400 | $1.42 |
| Self-preference judge scoring (a_b/b_d + a_e/e_d bracket + b_c, 2 judges) | 400 | ~$2.16 |
| Swap-averaging mitigation | 0 | $0.00 (reuses position-swap data) |
| Rubric-decomposition mitigation | 200 | $1.32 |
| Reference-guided grading mitigation | 200 | $0.78 |
| **Phase 3 subtotal (rough order of magnitude)** | **1,600** | **~$7.12** |
| **Total through Phase 3** | **~2,920** | **~$9.28** |

Call it **under $12 all-in** with a buffer, and I will still ask before
Phase 3 spending starts, with real numbers checked the same way these were
-- this table is a planning estimate, not a pre-authorization.
