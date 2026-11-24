# Claim-support review: heldout

40 claims, two raters. Cohen's kappa 0.521 (observed agreement 80.0%). Rates below use the 32 claims both raters labeled the same; disagreements are listed for adjudication.

| run | supported | unsupported | contradicted | claims |
|---|---|---|---|---|
| control-v2_alert | 6 (75%) | 2 (25%) | 0 (0%) | 8 |
| gemma-4-31b_v2_alert | 9 (100%) | 0 (0%) | 0 (0%) | 9 |
| glm-5.3_v2_alert | 4 (57%) | 3 (43%) | 0 (0%) | 7 |
| qwen3.6-27b-fp8_v2_alert | 7 (88%) | 1 (12%) | 0 (0%) | 8 |

## Disagreements

| claim | run | A | B |
|---|---|---|---|
| C001 | control-v2_alert | S | C |
| C005 | qwen3.6-27b-fp8_v2_alert | S | U |
| C007 | qwen3.6-27b-fp8_v2_alert | S | U |
| C013 | glm-5.3_v2_alert | S | U |
| C024 | gemma-4-31b_v2_alert | C | U |
| C031 | glm-5.3_v2_alert | S | U |
| C032 | glm-5.3_v2_alert | S | U |
| C035 | control-v2_alert | S | C |
