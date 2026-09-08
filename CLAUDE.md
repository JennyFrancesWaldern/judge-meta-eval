@../CLAUDE.md

# judge-meta-eval specifics

- Measures how much an LLM judge can be trusted on grounded-generation
  quality, and which biases (position, verbosity, self-preference, etc.)
  move the score.
- Human labels live in data/labels/ -- append-only, never regenerated.
- data/raw/ source transcripts are never regenerated once collected.
