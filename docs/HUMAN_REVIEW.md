# Human claim review

## Current results

Both reviewers completed all 40 claims. Both files passed strict ID, label, claim, and evidence checks.
Original exports are preserved in `backend/out/claim_review/heldout/originals/`.

The reviewers agreed on 32 of 40 claims (80%). Cohen's kappa is 0.521.
Eight claims still need human adjudication: C001, C005, C007, C013, C024, C031, C032, and C035.
See the [comparison and disagreements](../backend/out/claim_review/heldout/results.md).

The reported per-model rates use agreed claims only. Final adjudicated support rates remain pending.
Record adjudication decisions separately. Keep both original rating files unchanged.

## Reviewer workflow

1. Open [the review page](../frontend/public/human-review.html) in a browser. With Vite running, use `http://localhost:5173/human-review.html`.
2. Choose your assigned reviewer slot, A or B. Read the rubric in the form.
3. Rate all 40 claims using only the cited evidence. Use **Next unrated** to find any skipped claims.
4. Select **Download CSV**. Return `rater_A.csv` or `rater_B.csv` to the coordinator.

The HTML file works offline and can be shared directly. Reviewers should work independently on separate devices or browser profiles. The page saves drafts in the current browser if storage is available. For a portable backup, download a CSV. Open that CSV in the same reviewer slot to resume on another device. The form keeps existing draft entries if a file conflicts with them.

## Coordinator

Use each complete CSV in its matching `backend/out/claim_review/heldout/` rater slot. Once you have both files, run `python -m scripts.claim_review score --set heldout` from `backend/`. Share the standalone HTML only. It contains the blinded review sheet and rubric.

From the repository root, run `node tools/build_human_review.mjs` to refresh the HTML from the saved `sheet.csv`.
