# Additional Clemson RCD models - October 30, 2026

The existing integration uses the Clemson RCD LLM Service. It does not launch a new Palmetto Slurm model server. Arbitrary exact chat-model selectors are already supported by `RCDExplainer`, the dashboard's configured model list, and the frozen-evidence benchmark runner.

## Access result

The evening live catalog request to `https://llm.rcd.clemson.edu/v1/models?full=true` returned HTTP 302 to `access.rcd.clemson.edu/`; following that redirect returned HTTP 403. The credential-free snapshot is `backend/out/rcd_catalog_access_check_2026-10-30.json` (UTC timestamp falls on October 31; local date is October 30). A subsequent catalog utility refuses redirects so it never forwards the authorization header to another host. This is a service/network access block, not an automatic tool-approval rejection. No additional model inference or comparative accuracy measurement was possible during this attempt.

The new `scripts.discover_rcd_models` utility records lifecycle, online-instance counts, features, and supported endpoints. It selects online active, active-LTS, or experimental chat models; retired/deprecated models and embeddings are excluded. It does not alter the dashboard configuration automatically. Regression tests cover filtering and credential-safe redirect handling.

## Candidate expansion and reproducible procedure

Clemson's documentation illustrates `gptoss-20b` and `qwen3-omni-30b-a3b`. These provide additional families beyond the existing GLM/Gemma comparison if the live catalog confirms current access. The documentation examples are not a live availability guarantee. Do not add an embedding model as an explanation model.

1. Restore Clemson/CUVPN access and run `python -m scripts.discover_rcd_models --out out/rcd_catalog_new.json` from `backend/`.
2. Select eligible models and append their exact names to `RCD_LLM_MODELS` in the ignored `backend/.env`. Preserve existing settings and restart the API. Presence of a credential alone does not prove readiness.
3. Use the unchanged v4 HCRL and ROAD corpora with an initial one-alert smoke test. Use a separate smoke directory, a 90-second timeout, the existing 1,800-token cap, and two workers. Record empty replies or unsupported parameters as failures. Do not tune on label accuracy.
4. Once request compatibility is established, use new full-run directories without `--limit`. Preserve all 69 HCRL and 31 ROAD alerts, failures, exact corpus identities, request settings, source hashes, token counts and latency. Archive changed adapter sources before further modifications.
5. Compare each completed run with `explanations_v4_2026-10-30_control_v5` using `scripts.compare_models`. Its output must report matching evidence/targets and all scored attempts. The saved Benchmark tab discovers new `out/explanations_*/*/explanations_*.json` runs automatically, separating smoke subsets.

Example only, after the catalog confirms the name:

```bash
python -m scripts.benchmark_models --corpus out/frozen_2026-10-30_v4/road.json \
  --model rcd:gptoss-20b --limit 1 --out out/explanations_new_gptoss_smoke/road
python -m scripts.benchmark_models --corpus out/frozen_2026-10-30_v4/road.json \
  --model rcd:gptoss-20b --out out/explanations_new_gptoss/road
```

Keep campus-hosted RCD models separate from the commercial OpenAI gateway in hosting, cost, and interpretation. Do not reuse the previous v2 commercial result as a v4 matched-input comparison. Extra calls were not sent through the commercial gateway to work around unavailable campus access.

Sources: [RCD available models](https://docs.rcd.clemson.edu/llm/models/) and [local model API](https://docs.rcd.clemson.edu/llm/usage/api/), checked October 30, 2026.
