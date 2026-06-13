# research/prototypes -- UNVALIDATED experiments

Nothing here is production code. Scripts in this directory:

- do NOT import from `engine/`, `core/`, or any DeckGen package;
- are NOT part of the pytest suite;
- have NOT been cross-checked against SPICE.

They exist only to show that the math in `docs/research/findings.md` runs and
produces self-consistent numbers. A prototype that runs and prints numbers
proves nothing about physical correctness. Every printed value is UNVERIFIED.

## Contents

- `charge_resolve_demo.py` -- pure-stdlib (no numpy) demonstration of the
  Pillar 3 charge-resolve math from `findings.md`:
  - D1: an LPE parser that retains `C` lines and aggregates them to logical nets
    (the half `engine/stages/stage0_parse.py` currently drops);
  - D2: the scalar charge-share formula and its matrix-solve equivalent;
  - D3: a free-free coupling case where the scalar formula is provably wrong;
  - D4: a degenerate floating-coupling island that is correctly reported as X
    (singular system) rather than a fabricated voltage.

Run:

```
python3 research/prototypes/charge_resolve_demo.py
```

The numbers it prints were hand-checked for ARITHMETIC consistency only. None of
the physical modeling assumptions (ON=short / OFF=open, lumped LPE caps, the
floating = trapped-charge reframe) has been validated against a SPICE run. See
`docs/research/open_questions.md` for what a SPICE pass must confirm.
