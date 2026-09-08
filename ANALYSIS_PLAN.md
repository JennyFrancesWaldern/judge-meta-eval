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
  "agreement specifically on the ungrounded-response pairs" cuts the
  relevant n to ~65-100 and widens the interval substantially). Any
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

- **Source-passage contamination.** The leading dataset candidate
  (RAGTruth) draws its QA passages from MS MARCO (~2016) and its
  summarization passages from CNN/DailyMail (~2015-16) -- both almost
  certainly present in frontier model pretraining data by now. A model
  could produce a "well-grounded-looking" answer from memorized knowledge
  rather than by actually using the provided passage, which would inflate
  apparent quality independent of real grounding behavior. Mitigation:
  before generating anything, run a verbatim-recall probe (ask the
  generation models to continue an unseen-to-them snippet of candidate
  source passages) and report what it finds, per METHODOLOGY.md's
  contamination-check requirement. If recall is high, scope the item pool
  toward the "Recent News" subset or flag the limitation explicitly rather
  than proceeding as if the passages were unseen.
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

For each of 200 sampled MS MARCO QA items (passage + question), generate
three responses -- fresh generations, not RAGTruth's bundled responses, so
the quality spread and the "deliberately weak" condition are under my
control:

- **(a) Strong, grounded** -- Claude Sonnet 5, given passage + question,
  prompted normally.
- **(b) Weaker model, grounded** -- Claude Haiku 4.5, same passage +
  question. A genuine capability-driven quality spread rather than a
  sabotaged prompt.
- **(c) Deliberately ungrounded** -- Claude Sonnet 5, given ONLY the
  question (passage withheld), forced to answer from parametric knowledge
  alone. Holds model capability constant and isolates the specific failure
  mode this project is about: did the response actually use the source.

To stay inside the 200-comparison labeling budget, each item is paired once
rather than all three ways: alternate items between an (a) vs (b) pair and
an (a) vs (c) pair, so both failure modes get labeled coverage without
exceeding 200 total comparisons.

**Cost estimate** (official per-million-token rates, checked directly
against claude.com/pricing on 2026-09-07): assuming ~300 input tokens
(passage + question + instructions) and ~150 output tokens per call,
200 calls each for (a), (b), (c):

| Condition | Model | Input cost | Output cost | Subtotal |
|---|---|---|---|---|
| (a) strong | Sonnet 5 ($2/$10 per M) | $0.12 | $0.30 | $0.42 |
| (b) weak | Haiku 4.5 ($1/$5 per M) | $0.06 | $0.15 | $0.21 |
| (c) ungrounded | Sonnet 5, no passage | $0.05 | $0.30 | $0.35 |

**Total: ~$1** for the full 600-generation response pool. Even with a 5-10x
buffer for prompt iteration, retries, and the contamination probe, this
stays under ~$10. Judge-scoring costs (Phase 3) are separate and will get
their own estimate before anything is spent there.

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
different generation administration. That's a real limitation, carried
into the Confounds section above rather than left implicit.
