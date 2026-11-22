---
title: "CANalyst on Clemson Palmetto 2"
subtitle: "Feasibility Assessment and Implementation Guide"
author: "Nicholas DiGennaro & Alexander Salazar — CPSC 8580"
date: "September 16, 2026"
geometry: margin=1in
fontsize: 11pt
toc: true
toc-depth: 2
colorlinks: true
---

# 1. Feasibility Verdict

**Yes — CANalyst is a good fit for Palmetto 2.** Every stage of the proposed pipeline (ingest, feature extraction, detection, LLM analysis, dashboard) maps cleanly onto resources Palmetto already provides for free to Clemson researchers:

| Pipeline stage | Palmetto resource | Verdict |
|---|---|---|
| Ingest CAN logs (Car-Hacking, ROAD) | `/scratch` or `/project` storage (SSD, 10 TB/user scratch) | Trivial — datasets are a few GB each |
| Feature extraction (sliding-window stats, entropy, bit-flips) | CPU nodes via Slurm batch/array jobs (54k+ cores cluster-wide) | Embarrassingly parallel, ideal Slurm workload |
| Detector (timing/frequency baseline + lightweight learned model) | 1 CPU node or 1 shared GPU | Cheap — no need for a full GPU allocation |
| LLM analysis — **open-weight model run locally** | A100 80GB / H100 80GB GPU nodes via `--gpus-per-node` | A 7–14B model (Llama 3.1 8B, Qwen2.5-14B, Mistral 7B) fits on a single GPU with room to spare |
| LLM analysis — **hosted model** | Outbound HTTPS from a compute node to a provider API | Works like any `pip install` (outbound egress); no inbound exposure needed |
| Dashboard (web UI) | Interactive job + SSH port forwarding, or Open OnDemand | Fine for dev/demo use; **not** meant to be a public always-on service |

The one genuinely non-technical prerequisite is **allocation access**: Palmetto requires a faculty PI to sponsor a ColdFront allocation (General Queue) before you can log in and submit jobs. Confirm with your course instructor whether CPSC 8580 already has a class allocation, or whether you need your advisor to request one — do this first, since it gates everything else.

---

# 2. Palmetto 2 at a Glance

Palmetto 2 is Clemson's primary HPC cluster, free for Clemson researchers, students, and staff, managed via the Slurm scheduler.

- **Compute:** ~1,206 nodes, ~54,500 CPU cores, ~343 TB aggregate RAM, ~1,615 GPUs cluster-wide; 729 nodes have 2+ GPUs; benchmarked at ~3.0 PFlop/s.
- **GPU generations:** A100 (40GB and 80GB variants) and H100 (80GB) GPUs are present; the Slurm GRES name for an A100 is `a100` (e.g. `--gpus-per-node a100:1`). AI-focused phases (`ai03`, `ai04`) have the fastest 400 Gbps NDR InfiniBand interconnect for multi-GPU work.
- **Storage:** 250 GB backed-up `/home`, 10 TB (not backed up) `/scratch`, and PI-allocated backed-up `/project` space — all on the same underlying filesystem, so there's no performance difference between them. Each compute node also has fast local `$TMPDIR` scratch (99GB–2.7TB) that is purged when the job ends.
- **Access:** SSH to `slogin.palmetto.clemson.edu`, or the browser-based **Open OnDemand** (OpenOD) at `https://openod.palmetto.clemson.edu`, which offers Jupyter, RStudio, VS Code Server, and a VNC desktop as point-and-click "interactive apps," plus a file browser and in-browser shell.
- **Scheduler:** Slurm. Default batch partition is `work1`. Interactive OpenOD sessions have short, tightened walltime caps by design (to keep the interactive queue responsive) — use `sbatch` batch jobs, not interactive sessions, for anything long-running like full-dataset feature extraction or LLM serving.

Sources: [Palmetto 2 Documentation](https://docs.rcd.clemson.edu/palmetto/), [About the Cluster](https://docs.rcd.clemson.edu/palmetto/about/), [Storage](https://docs.rcd.clemson.edu/palmetto/storage/store/), [Job Submission](https://docs.rcd.clemson.edu/palmetto/job_management/submit/), [FAQ](https://docs.rcd.clemson.edu/palmetto/faq/), [Open OnDemand access](https://clemsonciti.github.io/rcde_workshops/intro_palmetto/07-open-od.html).

---

# 3. Account Setup and Access

1. **Get an allocation.** Only faculty can request a ColdFront allocation directly. As a grad student, ask your advisor/course instructor to either (a) add you to an existing lab allocation, or (b) confirm a class allocation exists for CPSC 8580. See [Account Setup](https://docs.rcd.clemson.edu/palmetto/accounts/setup/) and [General Queue](https://docs.rcd.clemson.edu/coldfront/allocations/palmetto2_general_partition/).
2. **Complete onboarding training** (async, via Tiger Training) — required before your account is activated.
3. **Connect:**
   ```bash
   ssh <username>@slogin.palmetto.clemson.edu
   ```
   Requires Clemson credentials + Duo.
4. **Or use the browser:** `https://openod.palmetto.clemson.edu` — good for early exploration, Jupyter-based prototyping, and file management without touching SSH.

---

# 4. Environment Setup

Palmetto uses **Lmod** for software modules. Load `anaconda3`, then build a project-specific conda environment rather than using the base environment.

```bash
module purge
module load anaconda3/2023.09-0
module load cuda/12.2.0      # match to your torch build; check `module spider cuda`

conda create -n canalyst python=3.11 -y
source activate canalyst
```

> **Known gotcha:** if you `conda init` in `~/.bashrc`, Jupyter-through-OpenOD sessions can hang on a password prompt. Load the module and `source activate <env>` per-session instead of auto-activating conda at login ([FAQ](https://docs.rcd.clemson.edu/palmetto/faq/)).

Suggested `requirements.txt` (install inside the conda env with `pip install -r requirements.txt`):

```text
torch --index-url https://download.pytorch.org/whl/cu121
transformers
accelerate
vllm                # OpenAI-compatible local LLM serving on GPU
pandas
numpy
scikit-learn
scipy
pyarrow
streamlit           # or fastapi+uvicorn if you prefer an API-backed dashboard
plotly
anthropic           # or openai — for the hosted-model comparison arm
python-dotenv
```

Since modules don't persist across sessions, put the `module load` + `source activate` lines at the top of **every** Slurm script and every new shell.

---

# 5. Data Plan

- Store raw and processed datasets under `/scratch/<username>/canalyst/` (10 TB quota, fast, but **not backed up** — keep a copy of anything irreplaceable, e.g. your trained checkpoints and processed features, under `/project` or push to your own git/DVC remote).
- Car-Hacking and ROAD are both a few GB — well within `/home`'s 250 GB too, but prefer `/scratch` for I/O-heavy feature extraction and reserve `/home` for code and small config.
- Transfer datasets with `scp`/`rsync` over SSH, or drag-and-drop through the OpenOD file browser for small files. For larger pulls, download directly on a compute/login node with `wget`/`curl` from the dataset source rather than routing through your laptop.
- Use node-local `$TMPDIR` inside a job for the hottest intermediate I/O (e.g., temporary shuffled windows during feature extraction), then copy final outputs back to `/scratch` before the job ends — `$TMPDIR` is wiped at job completion.

---

# 6. Stage-by-Stage Implementation on Palmetto

## 6.1 Ingest + Feature Extraction (CPU, batch/array job)

This stage (parsing frames, computing per-ID frequency, inter-arrival stats, payload entropy, bit-flip rates) is CPU-bound and parallelizes trivially across CAN IDs, time windows, or dataset files — a good fit for a **Slurm job array**.

`feature_extraction.sbatch`:
```bash
#!/bin/bash
#SBATCH --job-name canalyst-features
#SBATCH --nodes 1
#SBATCH --cpus-per-task 16
#SBATCH --mem 32gb
#SBATCH --time 04:00:00
#SBATCH --array=0-9                 # one task per dataset shard/file
#SBATCH --output logs/features_%A_%a.out

module purge
module load anaconda3/2023.09-0
source activate canalyst

srun python3 src/features/extract.py \
    --input /scratch/$USER/canalyst/raw/shard_${SLURM_ARRAY_TASK_ID}.csv \
    --output /scratch/$USER/canalyst/features/shard_${SLURM_ARRAY_TASK_ID}.parquet
```
Submit with `sbatch feature_extraction.sbatch`; check status with `squeue -u $USER`.

## 6.2 Detector Training/Evaluation

The proposal's baseline+lightweight-model detector (timing/frequency thresholds plus something like an isolation forest or small MLP) doesn't need a full GPU. Run it CPU-only for the baseline, and request a single shared GPU only if you train a neural model:

```bash
#SBATCH --cpus-per-task 8
#SBATCH --mem 16gb
#SBATCH --time 02:00:00
#SBATCH --gpus-per-node a100:1      # omit this line entirely for the CPU-only baseline
```

Report precision/recall/F1 against the ground-truth labels in Car-Hacking and ROAD as described in the proposal's evaluation section.

## 6.3 LLM Analysis — Open-Weight Model (local, on-cluster)

This is the arm Palmetto is best suited for. For each flagged window, you send a **compact structured summary** (affected IDs, feature deviations, representative frames) — not raw traffic — to a locally-served open-weight model.

Pick a model that fits a single GPU comfortably: **Llama 3.1 8B-Instruct**, **Qwen2.5-14B-Instruct**, or **Mistral-7B-Instruct** all fit well under 80GB even unquantized, leaving headroom for KV-cache. Avoid 70B-class models unless you explicitly want to spend the multi-GPU allocation — a 70B model in bf16 needs ~140GB, i.e. 2× 80GB GPUs.

`llm_serve.sbatch` (vLLM, OpenAI-compatible server):
```bash
#!/bin/bash
#SBATCH --job-name canalyst-llm
#SBATCH --nodes 1
#SBATCH --cpus-per-task 8
#SBATCH --mem 64gb
#SBATCH --time 04:00:00
#SBATCH --gpus-per-node a100:1
#SBATCH --output logs/llm_%j.out

module purge
module load anaconda3/2023.09-0
module load cuda/12.2.0
source activate canalyst

echo "LLM server node: $(hostname)"
python3 -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Llama-3.1-8B-Instruct \
    --port 8001 --host 0.0.0.0
```
While it's running, tunnel in from your laptop (see §6.5) and point your analysis script's OpenAI-compatible client at `http://localhost:<local-port>/v1`. For quick interactive prototyping instead of a batch job, request a GPU through an **Open OnDemand Jupyter or VS Code Server** session and run the same `vllm serve` command (or `ollama serve` if you prefer Ollama's simpler model management) from a terminal inside that session.

## 6.4 LLM Analysis — Hosted Model

Compute nodes have the same outbound internet access used for `pip`/`conda` installs, so calling a hosted API (e.g., the Anthropic API) from inside a Slurm job works the same as it would locally:

```python
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": evidence_summary_prompt}],
)
```
Practical notes:
- **Verify egress once** before building around it — run a trivial `curl https://api.anthropic.com` (or your chosen provider) from a compute node in an interactive job; some clusters throttle or block outbound traffic on compute (vs. login) nodes, Palmetto generally does not, but confirm early.
- Store the API key in a `.env` file excluded from git (`python-dotenv`), never hard-code it or commit it.
- Track token spend — hosted-API costs are the one part of this pipeline Palmetto doesn't subsidize. Budget for it (Anthropic/OpenAI education credits are worth checking).

## 6.5 Dashboard

Palmetto compute nodes aren't publicly routable, so the dashboard is a **dev/demo** deployment, not a production one — which matches a course project's needs fine.

Run it as you would any other service, then reach it via SSH port forwarding:

```bash
#!/bin/bash
#SBATCH --job-name canalyst-dashboard
#SBATCH --cpus-per-task 4
#SBATCH --mem 8gb
#SBATCH --time 02:00:00

module purge
module load anaconda3/2023.09-0
source activate canalyst
echo "Dashboard node: $(hostname)"
streamlit run src/dashboard/app.py --server.port 8501 --server.address 0.0.0.0
```

From your laptop, once you know the node from the job's `.out` file (`hostname`):

```bash
ssh -L 127.0.0.1:8080:<node-hostname>:8501 <username>@slogin.palmetto.clemson.edu
```

Then open `http://localhost:8080` locally. Never bind a service to a public interface without authentication — other Palmetto users share the same network namespace and there's no per-user firewalling between compute nodes ([SSH Port Forwarding docs](https://docs.rcd.clemson.edu/palmetto/connect/ssh_port_forwarding/)).

For live demos/presentations, it's often simpler to pre-compute results (detections + LLM explanations) into a static export (JSON/Parquet) and have the dashboard read that, rather than depending on a live tunnel and a live GPU allocation being up at demo time.

---

# 7. Suggested Repository Layout

```
canalyst/
  data/                     # gitignored; pointers to /scratch paths
  slurm/
    feature_extraction.sbatch
    train_detector.sbatch
    llm_serve.sbatch
    dashboard.sbatch
  src/
    ingest/
    features/
    detect/
    llm/                    # prompt templates, evidence-linking logic, client wrappers
    dashboard/
  notebooks/                # OpenOD Jupyter prototyping
  environment.yml / requirements.txt
  README.md
```

---

# 8. Timeline Mapping (from the proposal)

| Milestone | Palmetto-specific tasks |
|---|---|
| **By midterm (10/22)** | Allocation + onboarding done; datasets loaded to `/scratch`; feature-extraction array jobs producing per-window stats for both datasets; baseline detector running with first precision/recall/F1 numbers; first dashboard cut (timeline + per-ID view) reading static exported features |
| **By end of semester** | vLLM-served open-weight model integrated with evidence-linked prompts; hosted-model arm wired in and egress-tested; full evaluation (detection, classification accuracy vs. non-LLM baseline, explanation faithfulness sampling, latency/cost comparison); dashboard demo path finalized (tunnel or pre-computed export); optional user study |

---

# 9. Risks and Mitigations Specific to Palmetto

| Risk | Mitigation |
|---|---|
| No allocation yet / advisor approval delay | Request access in week 1 — this blocks everything else |
| Interactive OpenOD sessions time out mid-experiment | Use `sbatch` batch jobs for anything beyond quick prototyping; interactive apps are meant for dev, not full runs |
| `/scratch` isn't backed up | Mirror processed features, checkpoints, and results to `/project` or an external git/DVC remote regularly |
| GPU queue wait times during high-demand periods | Request the smallest GPU footprint that fits your model (single A100, not multi-GPU) and submit batch jobs ahead of deadlines rather than relying on last-minute interactive access |
| Hosted-API egress blocked or rate-limited from compute nodes | Test with a trivial `curl`/SDK call early, not the week of the deadline |
| Dashboard exposed without auth | Only ever access via SSH tunnel; never bind to a public interface |
| LLM hallucination / ungrounded claims (proposal's own stated risk) | Keep the structured-evidence-summary design from the proposal — never hand the model raw traffic, always require evidence citations, and sample-check faithfulness manually as planned |

---

# 10. Quick Reference

```bash
# Connect
ssh <username>@slogin.palmetto.clemson.edu

# Load environment
module purge && module load anaconda3/2023.09-0 && source activate canalyst

# Submit / monitor / cancel jobs
sbatch slurm/feature_extraction.sbatch
squeue -u $USER
scancel <jobid>

# Tunnel to a service running on a compute node
ssh -L 127.0.0.1:8080:<node>:<remote-port> <username>@slogin.palmetto.clemson.edu
```

---

# 11. Sources

- [Palmetto 2 Documentation (RCD)](https://docs.rcd.clemson.edu/palmetto/)
- [About the Palmetto 2 Cluster](https://docs.rcd.clemson.edu/palmetto/about/)
- [Palmetto 2 Account Setup](https://docs.rcd.clemson.edu/palmetto/accounts/setup/)
- [Palmetto 2 General Queue (ColdFront)](https://docs.rcd.clemson.edu/coldfront/allocations/palmetto2_general_partition/)
- [Job Submission in Slurm](https://docs.rcd.clemson.edu/palmetto/job_management/submit/)
- [About the Job Scheduler](https://docs.rcd.clemson.edu/palmetto/job_management/sched/)
- [Storage on Palmetto 2](https://docs.rcd.clemson.edu/palmetto/storage/store/)
- [Software / Module System](https://docs.rcd.clemson.edu/software/modules/)
- [SSH Port Forwarding](https://docs.rcd.clemson.edu/palmetto/connect/ssh_port_forwarding/)
- [Open OnDemand — Web-based Access (RCD workshop)](https://clemsonciti.github.io/rcde_workshops/intro_palmetto/07-open-od.html)
- [Palmetto 2 FAQ](https://docs.rcd.clemson.edu/palmetto/faq/)
