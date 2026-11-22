# CANalyst

<!-- impeccable:product-schema 1 -->

## Platform

web

## Product Purpose

CANalyst supports CAN traffic analysis for the CPSC 8580 course project at Clemson University.
Statistical detectors identify suspicious traffic. Explanations classify alerts and cite measured evidence.

## Users

Assumption from the repository and task: students and cybersecurity researchers inspect captures and compare detection and explanation results.

## Operating Context

The React dashboard uses a local FastAPI service.
Users can analyze installed ROAD traffic, upload captures with a separate normal baseline, or generate synthetic traffic.
Hosted explanations require an explicit user action.

## Capabilities and Constraints

- Preserve model selection, cached responses, upload validation, and evidence inspection.
- Keep live capture metrics separate from saved experiment results.
- Distinguish historical experiments from frozen held-out benchmark sets.
- Show failed model requests and incomplete submissions in scoring.
- Treat citation validity as a reference check, not proof of a claim.
- Preserve existing Original and Pastel appearances, including light and dark themes.

## Evidence on Hand

README.md describes the implemented workflow.
Saved experiment inputs and results live in backend/out.
The heldout explainer set contains 70 Car-Hacking attack alerts and seven ROAD false alarms.
It contains no ROAD attack alerts.

## Open Decisions

Deployment, analyst-study design, and production user roles are not established by this merge task.
No future image-generation workflow preference has been selected.
