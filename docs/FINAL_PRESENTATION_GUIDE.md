# Final presentation guide

**Use the [redesigned 20-minute deck](../output/presentation/CANalyst_Final_Presentation_20min_Class.pptx).**

Rehearse to 19:30. Keep 30 seconds for transitions, followed by three minutes for questions.
The deck has 20 main slides, six backup slides, and detailed speaker notes.
It extends the midterm and follows Nicholas's Clemson template.
Slide 6 contains the 45-second experiment animation, full screen.
The deck uses Avenir Next and Consolas. Present from a Mac, or install both fonts on the presentation computer.

Presenters: Nicholas DiGennaro and Alexander Salazar.
Confirm the assigned symposium date. The listed sessions are November 24, December 1, and December 3, 2026.
The rubric covers timing, structure, presentation quality, and content quality.
Source: Lecture Note 01, course-project slides, as supplied by Nicholas.

## Rehearsal schedule

Nicholas presents slides 1 through 8. Alexander starts slide 9 at 6:50.

| Slide | Time | Elapsed | Speaking cue |
| --- | ---: | ---: | --- |
| 1. CANalyst | 0:20 | 0:20 | Introduce the question and both presenters. |
| 2. An alert is not an explanation | 1:10 | 1:30 | State the CAN security problem and the research question. |
| 3. Where CANalyst fits | 0:45 | 2:15 | Contrast decoding, fingerprinting, detection, and CANalyst. |
| 4. Project timeline | 0:25 | 2:40 | Connect the midterm, corrections, and final evaluation. |
| 5. How CANalyst works | 1:00 | 3:40 | Trace one alert from capture to citation. |
| 6. Experiment in motion | 0:50 | 4:30 | Play and narrate the 45-second video. |
| 7. Four real-data test sets | 1:00 | 5:30 | Introduce four datasets and three evaluation units. |
| 8. Detection on ROAD | 1:20 | 6:50 | Report the v2 false-alarm drop and masquerade misses. |
| 9. HCRL: fewer alarms cost recall | 0:55 | 7:45 | Explain one fewer false alarm versus 56 more misses. |
| 10. How we scored explanations | 0:55 | 8:40 | Explain matched evidence and the three checks. |
| 11. Midterm vs. corrected evidence | 1:15 | 9:55 | Show midterm versus corrected scores on the same alerts. |
| 12. What we corrected | 1:00 | 10:55 | Explain the three corrections and why no single fix gets credit. |
| 13. November: four separate test sets | 0:40 | 11:35 | Give each test set its denominator. |
| 14. One instruction changed spoofing labels | 0:55 | 12:30 | Explain spoofing gains from the changed instruction. |
| 15. A valid citation can back a wrong claim | 1:00 | 13:30 | Show why a valid citation can back a wrong claim. |
| 16. Human review | 1:15 | 14:45 | Report 80% agreement, kappa 0.521, and eight open claims. |
| 17. Dashboard demo | 1:40 | 16:25 | Open an alert, its citation, and saved benchmarks. |
| 18. Results on six more vehicles | 1:20 | 17:45 | Contrast DTU results with the shared TU Eindhoven 2/44. |
| 19. What we learned | 1:20 | 19:05 | Answer the research question and name the next study. |
| 20. Questions | 0:25 | 19:30 | Close and invite questions. |

Suggested transition: "Alexander will explain how we evaluated the alerts that reached the explanation stage."

Backup slides cover ROAD detection, HCRL detection, provenance, model latency, human review, and references.

## Animation narration

The step bar at the top of the video names each stage. Each stage lasts about 8 seconds.

1. Data: public captures split into a clean reference and an evaluation capture.
2. Detect: windows that differ from the reference merge into an alert. Missed attacks stop here.
3. Package: each alert becomes an evidence packet. Ground-truth labels go to the scorer only.
4. Explain: the rule baseline and three models receive the same packet.
5. Score: labels, citations, and a human-rated sample of claims. 32 of 40 agree, and 8 are open.

The animation illustrates the experiment. It does not depict a live vehicle attack or real-time benchmark execution.

## Offline demo

Install dependencies and raw ROAD files before class. See [HANDOFF_11_23.md](../HANDOFF_11_23.md).

Start the API:

```sh
cd backend
EXPLAINER=mock .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the dashboard in another terminal:

```sh
cd frontend
npm run dev -- --host 127.0.0.1 --strictPort
```

1. Open <http://127.0.0.1:5173/> before the talk.
2. Wait for the ROAD capture's 41,829 frames to load.
3. Select its alert and test one evidence citation.
4. Open **Evaluation > Frozen benchmarks** and check the saved results.
5. Test slide 6 on the presentation computer and projector.
6. Keep the [MP4](../output/presentation/assets/experiment-flow.mp4) and [poster](../output/presentation/assets/experiment-flow.png) available.

| Time | Action |
| --- | --- |
| 0:00 to 0:15 | Show the ROAD capture and separate clean reference. |
| 0:15 to 1:00 | Open an alert, identify the offline control, and click one citation. |
| 1:00 to 1:30 | Open saved benchmarks. Identify the selected corpus and its denominator. |
| 1:30 to 1:40 | Show the review entry point and return to the slides. |

Use the [dashboard screenshot](../output/presentation/assets/road-dashboard.png) if the browser stalls.
Keep the [citation screenshot](../output/presentation/assets/citation-navigation.png) and [benchmark screenshot](../output/presentation/assets/frozen-benchmarks.png) ready.
Use <http://127.0.0.1:5173/?dataset=synthetic> only as an explicitly identified synthetic fallback.
Use saved hosted replies during class.

Native PowerPoint playback needs a presentation-computer check.
The earlier deck opened without a repair warning. That observation does not verify this revised deck's playback.

## Q&A facts

### Did the detector improve?

ROAD v2 reduces false positives from 1,461 to 50 of 9,598 normal windows.
Precision rises from 38.4% to 94.8%. Recall remains near 46.6%.
Masquerade detections fall from four to three of 971 windows.
See the [detector verification](../backend/out/final_2026-11-22/detection/verification.md).

### Why keep v1 as the default?

On HCRL, v2 saves one false alarm but misses 56 additional spoofing windows.
The whitelist plus interval baseline has the best HCRL F1 in this comparison, 0.996.
The tradeoff depends on the dataset.

### Does the model beat the rules?

October corrected GLM and control-v5 each score 86/89 attack labels.
CTT prompt-v2 Qwen scores 34/42, compared with control-v2 at 29/42.
Every TUE arm scores 2/44. These experiments do not support universal superiority.

### What did the prompt change do?

On 70 HCRL targets, Gemma improves 69 to 70, GLM 59 to 70, and Qwen 37 to 69.
All six runs already score 17/17 on DoS. Gains occur in spoofing labels.
Qwen also loses one fuzzing label in that comparison.
The midterm100 replication improves HCRL totals, but Qwen loses one DoS and two fuzzing labels.
CTT Qwen falls from 34/42 to 32/42 after the same wording change.

### Do citations prove faithful explanations?

No. Citation checks establish that an evidence item exists.
Both humans completed 40 claims and agreed on 32, giving 80% agreement and kappa 0.521.
The agreed subset contains 26 supported and six unsupported claims.
Eight disagreements remain unresolved. Do not report 26/32 as a full-sample support estimate.
See [human results](../backend/out/claim_review/heldout/results.md).

### What does the additional-vehicle evaluation establish?

CTT includes four additional vehicles with references from those vehicles.
TUE includes two cars with offline attack edits of one testing segment per car.
Both evaluate labels on selected detected alerts. Neither measures all attack windows or transfer without calibration.
Both TUE payload-fuzzing captures produce no alerts and therefore no explanation targets.

### Can we reproduce the results?

Saved replies, target IDs, source hashes, and scoring code are committed.
All 42 selected CTT sources and 14 TUE sources match their manifests.
The archived CTT freeze-script hash has no matching reachable source revision.
Keep those outputs as historical artifacts and disclose that source-reconstruction limit.
See the [current evidence summary](../backend/out/final_2026-11-23/model_results.md).

### Is inference fast enough?

October corrected GLM median times were 6.33 seconds on HCRL and 6.60 seconds on ROAD.
Those timings depend on the recorded settings and server conditions.
Detection runs locally. No study has established faster or more accurate human analysis.

## Report and final checks

Read the [final report](../output/paper/CANalyst_Final_Report.pdf) and [build notes](../paper/README.md).
The deadline is December 3, 2026, at 8:00 p.m. EST.
Compare its unchanged ACM class with Canvas's `cpsc8580template.zip` before submission.
The course ZIP was unavailable locally, and browser access was unavailable during this revision.

Before class, confirm the session date, rehearse together, and test the video.
Resolve disagreements only through documented human adjudication.
The deck reports pending decisions explicitly.
