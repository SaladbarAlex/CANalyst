# CANalyst final report

The [final report](../output/paper/CANalyst_Final_Report.pdf) uses the two-column ACM `sigconf` layout.

## Build

Use TeX Live with `acmart`, `pgfplots`, and `latexmk`.
From the repository root, run:

```sh
mkdir -p output/paper
latexmk -cd -pdf -outdir=../output/paper -jobname=CANalyst_Final_Report paper/final.tex
```

The build uses the installed ACM class and bibliography style without local edits. It follows the course metadata used in the midterm. The course archive `cpsc8580template.zip` was unavailable, so comparison with that archive remains pending.

## Reproduce the scores

1. Open [the detector results](../backend/out/final_2026-11-22/detection/results.md) for the November window metrics.
2. Open [the detector verification](../backend/out/final_2026-11-22/detection/verification.md) for the local rerun commands.
3. Run `python -m scripts.summarize_final_models --out /tmp/canalyst-paper-verification.json` from `backend/`.
4. Read the model scores and recomputed human agreement in the generated JSON.
5. Open [the human review results](../backend/out/claim_review/heldout/results.md) for the rating counts.

Choose a new output path if the verification JSON already exists.

The historical CTT freeze script has an unmatched source hash. The saved packets and replies support offline rescoring.
