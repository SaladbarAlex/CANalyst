# Claim-support review rubric

You will see one claim at a time, with the full text of every evidence item
the claim cites. Judge the claim **only against those cited items**. Do not
use what you know about CAN attacks, other items, or other claims.

You will not see which model wrote the claim or what the alert really was.
Please do not try to find out, and do not compare notes with the other rater
until both sheets are complete.

Put exactly one letter in the `label` column:

| label | meaning | example |
|---|---|---|
| **S** supported | Every factual statement in the claim follows from the cited items. Rounding and paraphrase are fine. | Claim: "0x000 sent 3,724 frames." Cited item says 0x000 sent 3724 frames. |
| **U** unsupported | The cited items do not establish the claim, though they do not contradict it either. This includes interpretations the numbers do not force. | Claim: "This targets the brakes." Cited item gives only rates and gaps, no function. |
| **C** contradicted | A cited item says something incompatible with the claim. | Claim: "Bus load more than doubled." Cited item says load was 0.79x baseline. |

Rules for hard cases:

1. **Mixed claims.** If any part of the claim is contradicted, label C. Otherwise,
   if any part is unsupported, label U. Label S only when every part is supported.
2. **Inference.** A claim may draw a conclusion ("consistent with a flood") if the
   cited numbers make it reasonable on their face. A conclusion that needs facts
   not in the cited items is U.
3. **Arithmetic.** Check it. "Twice the baseline" for 1.5x is C. "About 2x" for 1.9x is S.
4. **Hedged claims.** "May indicate" or "could be" still needs the cited numbers to
   point that way. A hedge does not turn an unsupported claim into a supported one.
5. **Every claim here cites something.** Claims with no citation are counted
   separately and are not part of this review.

Use the `note` column for anything that made a label hard. Notes help adjudication.
