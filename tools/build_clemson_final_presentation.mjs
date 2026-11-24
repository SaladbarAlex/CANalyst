import fs from 'node:fs/promises'
import path from 'node:path'
import crypto from 'node:crypto'
import { homedir } from 'node:os'
import { execFileSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const runtime = process.env.RUNTIME_NODE_MODULES
if (!runtime) throw new Error('Set RUNTIME_NODE_MODULES to the bundled runtime modules directory.')
const { FileBlob, PresentationFile } = await import(pathToFileURL(path.join(runtime, '@oai/artifact-tool/dist/artifact_tool.mjs')))
const skill = process.env.PRESENTATION_SKILL_DIR || path.join(homedir(), '.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11011/skills/presentations')
const python = process.env.RUNTIME_PYTHON || path.join(homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
const { finalizePresentation, applyPresentationChartFont } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')))
const build = path.join(root, 'tmp/clemson_final')
const output = path.join(root, 'output/presentation')
const template = path.join(root, 'docs/presentation_template/LibreCAN_Presentation_Clemson_Final.pptx')
const outputName = process.env.PRESENTATION_OUTPUT_NAME || 'CANalyst_Final_Presentation_20min_Class.pptx'
await fs.mkdir(build, { recursive: true })
execFileSync(python, [path.join(root, 'tools/prepare_clemson_template.py'), template, path.join(build, 'template-normalized.pptx')])
const presentation = await PresentationFile.importPptx(await FileBlob.load(path.join(build, 'template-normalized.pptx')))
const copies = presentation.slides.items.map(s => s.copy())
presentation.slides.keep([])
const color = { orange: '#F56600', purple: '#522D80', dark: '#2E1A47', body: '#2B1E3B', muted: '#5E5469', light: '#CFC3E0', line: '#E8E8E8', white: '#FFFFFF' }
const font = 'Arial'
const source = 'backend/out/final_2026-11-22/detection/results.json'
const detection = JSON.parse((await fs.readFile(path.join(root, source), 'utf8')).replace(/\bNaN\b/g, 'null'))
const metrics = name => detection.datasets.find(d => d.dataset === name).references.single.evaluation
const road = metrics('road')
const hcrl = metrics('hcrl')
const value = (rows, method, metric) => {
  const v = rows[method][metric]
  return v && typeof v === 'object' && 'value' in v ? v.value : v
}
const pct = n => n == null ? 'n/a' : `${(n * 100).toFixed(n > 0 && n < .001 ? 3 : 1)}%`
const slides = []
const chartOwners = []
const tableOwners = []
const seconds = [25,25,60,55,75,55,80,45,45,55,75,60,45,55,65,70,100,80,70,30]

function text(s, content, x, y, width, height, size = 28, fill = color.body, bold = false) {
  const t = s.shapes.add({ geometry: 'textbox', name: content.slice(0, 60), position: { left: x, top: y, width, height }, fill: 'none', line: { fill: 'none', width: 0 } })
  t.text = content
  t.text.style = { fontFamily: font, fontSize: size, color: fill, bold }
  t.text.insets = 0
  return t
}

function replace(e, content) {
  const shape = presentation.resolve(e.id)
  shape.text = content
  shape.text.style = { fontFamily: font, fontSize: e.style.fontSize, color: e.style.color, bold: e.style.bold || false, alignment: e.style.alignment || 'left' }
  return shape
}

async function slide(title, notes, footer, sourceNumber = 6, retain = () => false) {
  const s = presentation.slides.addCopy(copies[sourceNumber - 1])
  const inspected = await presentation.inspect({ select: '$.slides[*]', include: ['id', 'elements.id', 'elements.kind', 'elements.text', 'elements.position', 'elements.style'] })
  const elements = inspected.records.at(-1).elements
  if (sourceNumber !== 1 && sourceNumber !== 15) {
    for (const e of elements) {
      if (e.position.top === 43) replace(e, title)
      else if (e.position.top === 672) replace(e, footer)
      else if (e.position.top === 669) replace(e, String(slides.length + 1))
      else if (!retain(e)) presentation.delete(e.id)
    }
  }
  const timing = seconds[slides.length]
  const timingText = timing ? `Timing: ${Math.floor(timing / 60)}:${String(timing % 60).padStart(2, '0')}. ` : 'Backup slide. '
  s.speakerNotes.text = timingText + notes
  slides.push({ title, notes: timingText + notes, templateSlide: sourceNumber, seconds: timing || 0 })
  return { s, elements }
}

async function numbered(title, rows, notes, footer) {
  const { s } = await slide(title, notes, footer, 3, e => e.position.left === 57.6)
  rows.forEach(([heading, body], i) => {
    text(s, heading, 144, 134.4 + i * 105.6, 1075.2, 38, 28, color.dark, true)
    text(s, body, 144, 176 + i * 105.6, 1075.2, 43, 24)
  })
  return s
}

async function columns(title, rows, takeaway, notes, footer) {
  const { s } = await slide(title, notes, footer, 14, e => e.kind === 'shape')
  rows.forEach(([heading, body], i) => {
    const x = [57.6,459.2,860.8][i]
    text(s, heading, x, 182.4, 363.2, 76, 31, i === 1 ? color.purple : color.orange, true)
    text(s, body, x, 280, 363.2, 213, 27)
  })
  text(s, takeaway, 57.6, 548, 1166.4, 76.8, 28, color.purple, true)
  return s
}

function table(s, values, widths, { y = 170, height = 365, size = 27 } = {}) {
  const t = s.tables.add({ rows: values.length, columns: values[0].length, left: 57.6, top: y, width: 1166.4, height, values, columnWidths: widths })
  t.borders.assign({ fill: color.line, width: .7 })
  values.forEach((row, r) => row.forEach((_, c) => {
    const cell = t.getCell(r, c)
    cell.fill = r === 0 ? color.purple : color.white
    cell.text.style = { fontFamily: font, fontSize: size, color: r === 0 ? color.white : color.body, bold: r === 0 }
  }))
  tableOwners.push(slides.length)
}

function chart(s, categories, series, { max = 1, format = '0%', y = 155, height = 430 } = {}) {
  const c = s.charts.add('bar', { position: { left: 57.6, top: y, width: 1166.4, height }, categories,
    series: series.map((entry, i) => ({ ...entry, values: entry.values.map(n => Number(n.toPrecision(12))), fill: entry.fill || [color.orange, color.purple, color.light][i] })),
    barOptions: { direction: 'column', grouping: 'clustered', gapWidth: 85 }, hasLegend: true,
    legend: { position: 'bottom', textStyle: { typeface: font, fontSize: 24, fill: color.body } },
    xAxis: { textStyle: { typeface: font, fontSize: 24, fill: color.body }, line: { fill: color.line, width: 1 } },
    yAxis: { min: 0, max, numberFormatCode: format, textStyle: { typeface: font, fontSize: 22, fill: color.muted }, majorGridlines: { fill: color.line, width: 1 } },
    dataLabels: { showValue: true, position: 'outEnd', numberFormatCode: format === '0%' ? '0.0%' : format, textStyle: { typeface: font, fontSize: 24, fill: color.body, bold: true } },
    chartFill: color.white, plotAreaFill: color.white, chartLine: { fill: 'none', width: 0 }, plotAreaLine: { fill: 'none', width: 0 } })
  applyPresentationChartFont(c, { fontFamily: font })
  chartOwners.push(slides.length)
}

function caption(s, content) { text(s, content, 57.6, 605, 1166.4, 49, 24, color.muted) }

async function picture(s, name, position, alt, crop) {
  const bytes = await fs.readFile(path.join(output, 'assets', name))
  s.images.add({ blob: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), contentType: 'image/png', alt, fit: crop ? 'cover' : 'contain', position, ...(crop ? { crop } : {}) })
}

{
  const { elements } = await slide('CANalyst', 'Introduce both authors. CANalyst asks whether a language model can turn CAN anomalies into explanations that an analyst can verify. CAN traffic exposes timestamps, identifiers, and bytes. Those fields do not explain an attack by themselves. Our system detects changes, packages measurements, and links each model claim to evidence. This talk extends the midterm with corrected experiments, added datasets, and completed human ratings. The talk totals 19:30, leaving 30 seconds before the three-minute question period. Sources: docs/midterm/paper/midterm.tex; docs/FINAL_RESULTS_2026-11-23.md.', '', 1)
  const replacements = ['CPSC 8580 Security Symposium', '1', 'CANalyst', 'LLM-Assisted CAN Attack Analysis', 'Nicholas DiGennaro\nAlexander Salazar', 'Clemson University\nFall 2026']
  elements.forEach((e, i) => replace(e, replacements[i]))
}
await numbered('Project timeline', [
  ['September: proposal and prototype', 'Offline CAN analysis with an evidence-linked explanation interface.'],
  ['October: real captures and detection', 'HCRL and ROAD replace synthetic data in the main evaluation.'],
  ['Midterm: first model comparison', 'GLM and a rule control explain the same 100 detected alerts.'],
  ['After midterm: corrected evidence', 'Full-alert counts, explicit missing values, and clearer attack definitions.'],
  ['November: expanded evaluation', 'Detector reruns, prompt ablation, six additional vehicles, and two human ratings per claim.'],
], 'The proposal became a working prototype in September. Real-data ingestion followed in October, then detector and RCD model experiments. The first comparison exposed partial counts and weak attack definitions. We corrected those inputs and repeated the paired experiment. November added detector comparisons, prompt ablations, two additional datasets, and completed human ratings. Eight rating disagreements remain unresolved. Sources: docs/PROGRESS_2026-10-30.md; docs/midterm/paper/midterm.tex; backend/out/final_2026-11-23/model_results.json.', 'Source: project history and saved experiment artifacts')
await numbered('How CANalyst works', [
  ['Load a capture and clean reference', 'Normalize timestamps, CAN identifiers, and payload bytes.'],
  ['Detect anomalous windows', 'Measure rates, timing, entropy, missing IDs, and unknown IDs.'],
  ['Build a compact evidence packet', 'Separate full-alert measurements from representative-window statistics.'],
  ['Run a control or language model', 'Return a structured label, explanation, and evidence citations.'],
  ['Inspect the result', 'Open each citation in the dashboard and check the underlying measurement.'],
], 'The local pipeline starts with a capture and an explicitly clean reference. Half-second windows advance every quarter second. The detector flags windows, then merges adjacent flags into alerts. The evidence builder includes counts, rate changes, timing, entropy, and a few sample frames. A deterministic rule control or a selected model interprets that packet. The model does not scan the entire raw log. Detection misses remain outside this explanation stage. Ground-truth labels and identifying capture names stay out of model prompts. The dashboard makes the evidence accessible. Vehicle function remains unknown without a verified signal mapping. Sources: app/loader.py, features.py, detector.py, evidence.py, llm.py, pipeline.py.', 'Source: CANalyst pipeline and evidence contract')
{
  const { s } = await slide('Experiment in motion', 'Play the 42-second animation and narrate its flow. Public captures enter the loader. A clean reference supplies expected behavior. Window features feed the detector. The detector produces alerts, while missed attacks stay outside the explanation benchmark. Each selected alert becomes a blinded evidence packet. The control and models receive matched inputs. Saved replies then feed label scoring, citation checks, and claim review. Pause on the final stage to distinguish three outcomes: detection recall, label accuracy on detected alerts, and whether evidence supports each claim. This is a process animation, not a real-time recording or a depiction of a live vehicle attack. Source: tools/build_experiment_animation.swift and current experiment manifests.', '42-second experiment flow. Click the video to play.', 7)
  await picture(s, 'experiment-flow.png', { left: 180.3, top: 139, width: 919.4, height: 517.16 }, 'Experiment flow video')
}
{
  const { s } = await slide('Real-data evaluation setup', 'HCRL provides frame injection flags. ROAD adds fabrication, fuzzing, and simulated masquerade. Their detector protocol separates reference, tuning, and evaluation roles. Earlier development already used these recordings. DTU can-train-and-test v2 adds four vehicles with a clean reference per vehicle. TU Eindhoven adds Opel Astra and Renault Clio. Its attack traces edit the benign testing session offline. The new experiments score detected alerts. They do not estimate window-level recall or unseen-vehicle performance without calibration. TUE payload-fuzzing captures produce no alerts and no explanation targets. Synthetic examples support regression tests and demos only. Sources: app/datasets.py; backend/out/final_2026-11-23/model_results.json; docs/ADDITIONAL_DATASETS.md.', 'Sources: official dataset releases and frozen capture manifests')
  table(s, [['Dataset', 'Evaluation scope', 'Ground truth'], ['HCRL / Car-Hacking', 'Detection and alert explanations', 'Frame injection flags'], ['ROAD', 'Detection and alert explanations', 'Intervals and metadata'], ['DTU / CTT v2', 'Four vehicles, calibrated per vehicle', 'Frame attack flags'], ['TU Eindhoven v2', 'Two cars, offline-edited test traces', 'Frame differences']], [300, 515, 351.4], { height: 370, size: 25 })
  caption(s, 'Separate units: detector windows, classified alerts, and reviewed claims.')
}
await columns('Detector changes', [
  ['Clean reference', 'Learn expected behavior from attack-free traffic. Keep reference and evaluation roles explicit.'],
  ['Timing guard', 'Prevent jitter-collapse alerts when baseline timing variation is at or below 10 microseconds.'],
  ['Profile v2', 'Allow bus load, unknown IDs, and per-ID rate to raise alerts. Retain other features as evidence.'],
], 'Live default: v1. Profile v2 has a dataset-dependent recall tradeoff.', 'The merged detector preserves the existing v1 default. Its corrected timing guard avoids turning near-zero timing variance into extreme anomaly scores. That correction explains the HCRL v1 false-positive count changing from 32 in saved November results to one in the fresh run. Profile v2 is a separate comparison. It limits alerting to three injection-oriented components. Missing IDs, timing, and entropy remain visible as evidence but do not raise v2 alerts. The threshold is 0.55, with half-second windows and a quarter-second stride. These detector profiles are different from evidence versions, control-rule versions, and prompt versions. Sources: app/detector.py; backend/out/final_2026-11-22/detection/verification.md.', 'Source: detector implementation and fresh verification')
{
  const { s } = await slide('Detection on ROAD', 'This is the fresh merged-code run with a single normal reference. The denominator is 1,954 attack windows and 9,598 normal windows. V1 detects 911 attacks and flags 1,461 normal windows. V2 detects 910 attacks and flags 50 normal windows. Precision rises from 38.4% to 94.8%, while recall stays near 46.6%. The false-positive rate falls from 15.2% to 0.52%. The limitation is masquerade: v1 detects only four of 971 windows and v2 only three. Cleaner alerts therefore do not mean the detector covers all attacks. These windows overlap, and the saved benchmark includes block-bootstrap intervals. Source: backend/out/final_2026-11-22/detection/results.json, ROAD single reference.', 'Source: fresh merged-code run, ROAD single reference')
  chart(s, ['Precision', 'Recall', 'FPR'], [
    { name: 'Rule v1', values: ['precision','recall','fpr'].map(k => value(road,'rule@0.55',k)) },
    { name: 'Rule v2', values: ['precision','recall','fpr'].map(k => value(road,'rule_v2@0.55',k)) },
  ])
  caption(s, 'FPR: false-positive rate. Masquerade detection: v1 4/971 windows, v2 3/971.')
}
{
  const { s } = await slide('HCRL detector comparison', 'HCRL has stronger injection signatures. The single-reference evaluation contains 8,616 attack windows and 13,458 normal windows. V1 detects 8,450 attacks with one false positive. V2 detects 8,394 with zero false positives. Saving one false alarm costs 56 additional spoofing misses. A simple union of ID-whitelist and interval checks detects 8,581 attacks with 27 false positives. This baseline has better recall and F1 here. The result supports evaluating simple controls before crediting a more complicated detector. It also supports keeping the current v1 live default while documenting the tradeoff. Source: backend/out/final_2026-11-22/detection/results.json, HCRL single reference.', 'Source: fresh merged-code run, HCRL single reference')
  table(s, [['Method','Precision','Recall','F1'], ...['rule@0.55','rule_v2@0.55','whitelist_interval'].map((method,i) => [['Rule v1','Rule v2','Whitelist + interval'][i],`${(100*value(hcrl,method,'precision')).toFixed(2)}%`,pct(value(hcrl,method,'recall')),value(hcrl,method,'f1').toFixed(3)])], [460,235,235,236.4], { height: 330, size: 28 })
  caption(s, 'V2 saves one false alarm but misses 56 more spoofing windows.')
}
await columns('LLM evaluation on Clemson RCD', [
  ['Matched alerts', 'Freeze target IDs, boundaries, and evidence packets within each comparison.'],
  ['Blinded inputs', 'Exclude labels and identifying filenames. Require structured output and evidence IDs.'],
  ['Saved replies', 'Score labels, citations, failures, and latency. Preserve raw output for inspection.'],
], 'Classification measures detected alerts. Detector misses remain outside this score.', 'Clemson RCD provides the model infrastructure. The local control is deterministic and is not a language model. Within a paired comparison, every arm receives the same target alerts and packet version. We save replies before scoring. Invalid responses and failed calls stay visible rather than disappearing from denominators. Citation membership checks whether an evidence ID exists. It does not establish that the evidence justifies the sentence. We therefore distinguish label accuracy, output validity, and semantic support. October and November use different experiment versions and should not be pooled. Sources: scripts/score_explanations.py; app/llm.py; backend/out/final_2026-11-22/model_results.json.', 'Sources: saved RCD replies, manifests, and scorer')
{
  const { s } = await slide('First LLM results', 'These are the original midterm results, preserved as historical evidence. The matched corpus contains 69 HCRL attack alerts, 20 ROAD attack alerts, and 11 ROAD false alarms. GLM correctly labels 54 of 69 HCRL attacks and seven of 20 ROAD attacks. The original rule control scores 53 of 69 and 17 of 20. DoS is a shared weakness: GLM gets one of 16 and the control zero of 16. GLM calls ten of 13 ROAD fabrication alerts replay. Several normal periodic patterns therefore trigger a misleading attack interpretation. These results motivated inspection of the evidence and definitions. Source: docs/midterm/paper/midterm.tex, tables and discussion.', 'Historical midterm comparison. Same 89 attack alerts plus 11 false alarms.')
  table(s, [['Original arm','HCRL attack labels','ROAD attack labels'],['Rule control','53 / 69','17 / 20'],['GLM','54 / 69','7 / 20']], [460,353,353.4], { height: 295, size: 30 })
  text(s, 'GLM mislabeled 10 of 13 ROAD fabrication alerts as replay.', 57.6, 530, 1166.4, 66, 32, color.purple, true)
}
{
  const { s } = await slide('Corrected v4 results', 'We preserved all 100 targets and their boundaries, then rebuilt the packets under the corrected v4 contract. The control-v5 and GLM-5.3 each label 69 of 69 HCRL attacks and 17 of 20 ROAD attacks correctly. Qwen3-30B-A3B Instruct FP8 scores 24 of 69 and 14 of 20. Control and GLM share the same three ROAD masquerade misses. Both hosted arms return all 100 replies without fallback. The corrected GLM result matches the control on observed attack labels. It does not improve that score, establish statistical equivalence, or measure missed detector windows. Several inputs and settings changed since the midterm, so this comparison does not isolate one causal fix. Source: backend/out/final_2026-11-22/model_results.json, October paired v4.', 'October corrected v4. Matched targets and evidence across these three arms.')
  chart(s, ['HCRL attacks (69)', 'ROAD attacks (20)'], [
    { name: 'Control-v5', values: [1,17/20] },
    { name: 'GLM-5.3', values: [1,17/20] },
    { name: 'Qwen3-30B', values: [24/69,14/20] },
  ])
  caption(s, 'Control and GLM: 86/89 attack labels. Both miss the same three ROAD masquerade alerts.')
}
await columns('Corrections since midterm', [
  ['Measurement scope', 'One packet showed 176 unknown-ID frames. The full alert contained 2,806.'],
  ['Replay definition', 'Periodic repetition alone does not establish replay. Require evidence of an out-of-context sequence.'],
  ['Missing values', 'Keep unknown baselines and unavailable timing explicit. Separate raw and guarded rate ratios.'],
], 'Multiple changes occurred together. The gain cannot be assigned to one correction.', 'The first packet used representative-window counts where the model needed full-alert scope. In one inspected case, it showed 176 unknown-ID frames while the entire alert contained 2,806. That mismatch may explain part of the model error. It does not explain every original control error: the old control used separate bus-load and priority conditions. The corrected system also changes replay wording, ratio handling, missing values, control rules, and inference settings. Each improves the evidence contract, but the combined rerun is not a controlled ablation of each fix. Keep that distinction clear when describing the gain. Sources: docs/PROGRESS_2026-10-30.md; app/evidence.py; app/llm.py; midterm.tex.', 'Sources: semantic audit, corrected evidence contract, and saved midterm packets')
{
  const { s } = await slide('November coverage', 'The heldout-named corpus contains 70 HCRL attacks and seven ROAD false alarms, with zero ROAD attacks. It reuses recordings seen during development. The midterm100 replication uses the original 89 attack alerts and 11 false alarms. CTT contributes 42 attacks and 59 selected false alarms. Its detector emits 154 false alarms in total, capped to at most three per capture for scoring. TUE contributes 44 attacks and zero false alarms. These are separate experiment families with different packets. Do not pool them into one accuracy score. All 42 selected CTT raw captures and 14 TUE captures match their saved hashes. Sources: backend/out/final_2026-11-23/model_results.json and manifest audit.', 'Source: frozen manifests. Counts describe explanation targets.')
  table(s, [['Corpus','Attack alerts','False alarms'],['Later slices (heldout)','70 HCRL, 0 ROAD','7 ROAD'],['Midterm100 replication','69 HCRL, 20 ROAD','11 ROAD'],['DTU / CTT v2','42','59 of 154 selected'],['TU Eindhoven v2','44','0']], [510,350,306.4], { height: 370, size: 27 })
  caption(s, 'Each row has its own frozen targets and interpretation limits.')
}
{
  const { s } = await slide('DoS-line ablation', 'This experiment changes one DoS instruction while retaining the saved corpus. HCRL accuracy moves from 69 to 70 for Gemma, 59 to 70 for GLM, and 37 to 69 for Qwen3.6. All six runs already classify all 17 DoS alerts correctly. Gains occur in spoofing labels. GLM failures across all 77 targets drop from five to one. A midterm100 replication also improves HCRL: Gemma 66 to 69, GLM 61 to 68, and Qwen 36 to 65, each out of 69. ROAD changes are smaller: 16 to 16, 16 to 16, and 14 to 15, each out of 20. This is a separate experiment from October corrected v4. Gains do not extend uniformly to the additional datasets. Source: backend/out/final_2026-11-23/model_results.json.', 'November HCRL attacks. Same 70 targets, one changed DoS instruction.')
  chart(s, ['Gemma 4-31B','GLM-5.3','Qwen3.6-27B FP8'], [{ name: 'Prompt v2', values: [69,59,37] },{ name: 'Changed DoS line', values: [70,70,69] }], { max: 75, format: '0' })
  caption(s, 'All six runs already scored 17/17 on DoS. Improvements came from spoofing labels.')
}
await columns('Claims and citations', [
  ['Measured evidence', 'Payload entropy is zero for the observed interval.'],
  ['Unsupported leap', 'The model concludes that every payload byte is 0x00. Entropy alone cannot establish the byte value.'],
  ['Review question', 'Does the cited item support the exact sentence, within the stated interval and scope?'],
], 'A valid evidence ID does not prove that a claim is supported.', 'Zero entropy indicates no variation in the measured representation. It does not identify a particular byte value. An explanation can cite a real item and still make an unsupported claim. A prior AI-assisted purposive audit found 13 supported and five unsupported claims among 18. All citations resolved. That diagnostic audit is separate from the completed two-rater review on the next slide. A GLM summary also used identifier 0x55 instead of 0x655, outside that 18-claim audit. These examples motivate mechanical checks and semantic review. We have not measured analyst correctness or task time. Sources: docs/FINAL_RESULTS_2026-11-22.md; claim-review rubric.', 'Source: saved semantic audit examples. Human ratings follow.')
{
  const { s } = await slide('Human review results', 'Both human raters completed all 40 blinded claims. A project author and an independent volunteer submitted separate judgments. They agreed on 32 of 40, or 80 percent. Cohen kappa is 0.521. Among the agreed claims, 26 are supported and six unsupported. Eight disagreements remain unresolved. No claim receives contradicted from both raters, but each rater uses that label individually. Do not interpret 26 of 32 as a full-sample support rate. The sample has ten claims per arm across 27 unique alerts. It excludes ROAD attacks, summaries, uncited claims, new datasets, and the DoS ablation. Original CSVs remain unchanged. Sources: backend/out/claim_review/heldout/results.json; docs/HUMAN_REVIEW.md.', 'Source: 40 paired human judgments. Original exports preserved.')
  table(s, [['Measure','Result'],['Agreement','32 / 40 claims (80%)'],["Cohen’s kappa",'0.521'],['Agreed labels','26 supported, 6 unsupported'],['Unresolved','8 disagreements']], [430,736.4], { height: 370, size: 29 })
  caption(s, 'Agreement is complete. Full-sample adjudicated support rates remain pending.')
}
{
  const { s } = await slide('Dashboard demo', 'Prewarm the installed ROAD capture before class. Use the offline rule control. Spend 15 seconds identifying the capture and clean reference. Spend 45 seconds selecting an alert, reading a measurement, and clicking its evidence citation. Separate measured facts from model interpretation. Spend 30 seconds opening Evaluation and frozen November results. State the denominator: 70 HCRL attacks, seven ROAD false alarms, and zero ROAD attacks. Spend ten seconds showing the review entry point, then return to the deck. If the browser stalls, narrate these saved screens. Do not launch hosted inference during the demo. Sources: verified browser QA and output/presentation/assets/road-dashboard.png.', 'Demo: capture, alert, evidence citation, then saved evaluation')
  text(s, 'Detected interval', 57.6, 148, 550, 55, 31, color.purple, true)
  text(s, 'Explanation and citation', 674, 148, 550, 55, 31, color.orange, true)
  await picture(s, 'road-dashboard.png', { left: 57.6, top: 230, width: 550, height: 234 }, 'ROAD timeline', { left: 338/1440, top: 424/2372, right: 20/1440, bottom: 1488/2372 })
  await picture(s, 'road-dashboard.png', { left: 674, top: 230, width: 550, height: 288 }, 'ROAD alert explanation and evidence citation', { left: 730/1440, top: 930/2372, right: 20/1440, bottom: 1084/2372 })
  caption(s, 'ROAD capture: correlated_signal_attack_3.log. Offline rule control.')
}
{
  const { s } = await slide('Results on additional vehicles', 'CTT uses four vehicles with per-vehicle clean references. The 42 attack targets contain 14 DoS, 15 fuzzing, and 13 spoofing alerts. Control-v2 scores 29 of 42. The prompt change moves Gemma from 23 to 24, leaves GLM at 31, and lowers Qwen from 34 to 32. TUE uses two vehicles and 44 attack alerts: two DoS, 40 fuzzing or diagnostic alerts, and two replay alerts. Every arm scores only the two DoS alerts correctly. One GLM ablation reply is missing, so its full-target score remains two of 44, with 43 replies. The same-drive edited traces, label mapping, and compact evidence limit interpretation. Payload-fuzzing captures emit zero alerts, so the table excludes those misses. These results expose poor transfer of attack labels and no universal benefit from the DoS wording change. Sources: backend/out/final_2026-11-23/model_results.json; CTT and TUE manifests.', 'Correct labels / all attack targets. TUE scores are identical under both prompts.')
  table(s, [['Arm','CTT: v2','CTT: DoS line','TUE: both'],['Rule control-v2','29 / 42','n/a','2 / 44'],['Gemma 4-31B','23 / 42','24 / 42','2 / 44'],['GLM-5.3','31 / 42','31 / 42','2 / 44'],['Qwen3.6-27B FP8','34 / 42','32 / 42','2 / 44']], [400,240,270,256.4], { height: 365, size: 26 })
  caption(s, 'TUE: all arms miss 40 fuzzing / diagnostic labels and both replay labels.')
}
await columns('Limits and next steps', [
  ['Coverage', 'ROAD masquerade remains mostly undetected. Alert-label scores exclude these misses.'],
  ['Generalization', 'Additional vehicles expose label-transfer failures. Calibrated references and edited traces limit the claim.'],
  ['Human benefit', 'Resolve eight disagreements. A separate study must measure analyst correctness and task time.'],
], 'Contribution: a working, measurable workflow for inspecting CAN anomaly explanations.', 'Explicit evidence makes model errors inspectable. Corrected GLM matches the rule control on the October attack targets. The added datasets show that the same success does not transfer uniformly. TUE is a clear negative result. Detector misses and alert selection constrain explanation scores. Human agreement is measured, but eight disagreements remain open and no analyst task benefit is established. Future work should address semantic labels, missed low-rate payload changes, and a timed analyst task. One archived CTT freeze-script hash has no reachable matching source revision, so we preserve its historical outputs and disclose that reproducibility limit. Related work such as READ and LibreCAN addresses decoding, while CIDS addresses ECU fingerprinting. Sources: final model summary, adapter audit, human review, and related work references.', 'Sources: final results, source audit, and human-review protocol')
{
  const { elements } = await slide('Questions', 'Close the 20-minute talk, then allow three minutes for questions. Keep the appendix available for detector metrics, data reuse, model identity, latency, and review scope. Describe CANalyst as a local research prototype. The expanded dataset results reveal transfer limits. No live-vehicle deployment or analyst benefit has been established. Source: final results and implementation status.', '', 15)
  replace(elements[0], 'Thank you')
  replace(elements[1], 'Questions?')
}

async function fullDetector(name, rows) {
  const labels = { 'rule@0.55':'Rule v1', 'rule_v2@0.55':'Rule v2', 'rule@tuned':'Rule v1, tuned', id_whitelist:'ID whitelist', interval:'Message interval', whitelist_interval:'Whitelist + interval', id_entropy:'ID entropy', iforest:'IsolationForest', ocsvm:'One-class SVM' }
  const { s } = await slide(`Appendix: ${name} detector results`, `Single-reference results from ${source}. Evaluation windows overlap. The benchmark reports 20-window block bootstrap intervals with 2,000 draws. Tuned thresholds target at most 1% false positives on clean tuning windows. These tables show point estimates. Full intervals, thresholds, and source hashes remain in the result files. Undefined precision appears as n/a. Cross-dataset rankings do not establish universal superiority.`, 'Source: fresh detector results. Single-reference evaluation.')
  table(s, [['Method','Precision','Recall','F1','FPR'],...Object.entries(labels).map(([key,label]) => [label,pct(value(rows,key,'precision')),pct(value(rows,key,'recall')),value(rows,key,'f1')?.toFixed(3) ?? 'n/a',pct(value(rows,key,'fpr'))])], [390,194,194,194,194.4], { y: 150, height: 470, size: 24 })
}
await fullDetector('ROAD', road)
await fullDetector('HCRL', hcrl)
{
  const { s } = await slide('Appendix: data provenance', 'ROAD groups fabrication and masquerade twins. HCRL assigns reference, tuning, and evaluation to disjoint time slices. Earlier development touched all four HCRL attack recordings and all 25 ROAD evaluation capture sources. October and November midterm100 share 100 targets with different packets. All 42 selected CTT source hashes and all 14 TUE hashes match the raw downloads. No whole-file duplicates occur within either selected manifest. CTT uses vehicle-specific reference traffic. TUE uses attack edits of one testing session per vehicle. The archived CTT freeze-script hash does not match reachable source history. Preserve those historical targets and disclose the limitation. Sources: app/datasets.py; backend/out/final_2026-11-23/model_results.json; adapter audit.', 'Source: dataset roles, manifest hashes, and overlap audit')
  table(s, [['Comparison','Separation','Limit'],['ROAD / HCRL','Capture groups or time slices','Evaluation sources used earlier'],['October / November','Versioned packets and prompts','100 midterm targets overlap'],['DTU / CTT v2','Clean reference per vehicle','Known-vehicle calibration'],['TU Eindhoven v2','Reference and testing slices','Attack edits share a testing session']], [310,390,466.4], { height: 420, size: 25 })
}
{
  const { s } = await slide('Appendix: models and latency', 'The October corrected run uses evidence-v4, control-v5, and hosted prompt can-evidence-v3. GLM-5.3 and Qwen3-30B-A3B Instruct FP8 each complete all 100 requests without fallback. Median latency is 6.331 seconds on HCRL and 6.599 on ROAD for GLM, and 4.272 and 4.192 for Qwen. The original midterm GLM medians were 24 and 33 seconds, with a maximum of 825 seconds. Multiple settings changed, so those latency differences are observational. November uses historical prompt v2 and v2-dosv1 with Gemma 4-31B, GLM-5.3, and Qwen3.6-27B FP8. Source: model_results.json and midterm.tex.', 'Source: October corrected v4 saved request timings')
  table(s, [['October arm','HCRL median','ROAD median','Replies'],['GLM-5.3','6.331 s','6.599 s','100 / 100'],['Qwen3-30B-A3B FP8','4.272 s','4.192 s','100 / 100']], [440,240,240,246.4], { height: 285, size: 27 })
  caption(s, 'November models and prompts belong to a separate experiment family.')
}
{
  const { s } = await slide('Appendix: human-review coverage', 'Rater A labels 33 supported, six unsupported, and one contradicted. Rater B labels 26 supported, 12 unsupported, and two contradicted. They agree on 32 of 40, with kappa 0.521. Agreed-only counts appear here and must not be presented as full ten-claim rates. Control has six supported and two unsupported, Gemma nine supported, GLM four supported and three unsupported, and Qwen seven supported and one unsupported. Eight disagreements remain: C001, C005, C007, C013, C024, C031, C032, and C035. Preserve original ratings and record human adjudication separately. Each arm contributes three DoS, three fuzzing, two spoofing, and two ROAD false-alarm claims. Sources: backend/out/claim_review/heldout/results.json and original CSVs.', 'Source: paired human ratings. Table includes agreed claims only.')
  table(s, [['Arm','Supported','Unsupported','Agreed / sampled'],['Rule control-v2','6','2','8 / 10'],['Gemma 4-31B','9','0','9 / 10'],['GLM-5.3','4','3','7 / 10'],['Qwen3.6-27B FP8','7','1','8 / 10']], [440,220,220,286.4], { height: 365, size: 26 })
  caption(s, '40 claims across 27 alerts. Excludes summaries, uncited claims, and new datasets.')
}
{
  const { s } = await slide('Appendix: references', 'Datasets: HCRL Car-Hacking, https://ocslab.hksecurity.net/Datasets/CAN-intrusion-dataset. ORNL ROAD, https://zenodo.org/records/10462796 and https://arxiv.org/abs/2012.14600. DTU can-train-and-test v2, https://doi.org/10.11583/DTU.24805533.v2. TU Eindhoven CAN v2, https://data.4tu.nl/datasets/efb320d8-c189-4e54-98af-3a79cc14f421/2. Related work: READ, https://doi.org/10.1109/TIFS.2018.2870826. LibreCAN, https://mpese.com/publication/pese-2019-librecan/ACM_CCS_LibreCAN_Paper.pdf. CIDS, https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho. CAN-D, https://arxiv.org/abs/2006.05993. Project: backend/out/final_2026-11-22/detection/results.json; backend/out/final_2026-11-23/model_results.json; docs/FINAL_RESULTS_2026-11-23.md. Original history: docs/midterm/paper/midterm.tex. Dataset archives and hashes: docs/ADDITIONAL_DATASETS.md.', 'Full links and per-slide sources appear in speaker notes.')
  text(s, 'Datasets', 57.6, 160, 300, 50, 31, color.orange, true)
  text(s, 'HCRL Car-Hacking, ORNL ROAD\nDTU can-train-and-test, TU Eindhoven CAN', 390, 160, 834, 110, 29)
  text(s, 'Related work', 57.6, 315, 300, 50, 31, color.purple, true)
  text(s, 'READ, LibreCAN, CIDS, CAN-D', 390, 315, 834, 70, 29)
  text(s, 'Project evidence', 57.6, 460, 320, 50, 31, color.orange, true)
  text(s, 'Frozen inputs, raw replies, manifests,\nscoring scripts, and source hashes', 390, 460, 834, 110, 29)
}

if (slides.length !== 26 || seconds.reduce((a,b) => a+b,0) !== 1170) throw new Error('Slide count or timing changed unexpectedly.')
await fs.writeFile(path.join(build,'slide-content.json'), JSON.stringify(slides,null,2))
const candidatePath = path.join(build,'candidate-clemson.pptx')
await (await PresentationFile.exportPptx(presentation)).save(candidatePath)
const previewDir = path.join(build,'preview')
await fs.mkdir(previewDir,{ recursive:true })
for (const [index,s] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide:s,format:'png',scale:1 })
  await fs.writeFile(path.join(previewDir,`slide-${String(index+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()))
}
console.log(JSON.stringify({ candidatePath, previewDir, slides: slides.length, tables:tableOwners, charts:chartOwners }))
if (process.argv.includes('--final')) {
  const withVideo = path.join(build,'candidate-clemson-video.pptx')
  execFileSync(python,[path.join(root,'tools/embed_experiment_video.py'),candidatePath,withVideo,template,path.join(output,'assets/experiment-flow.mp4'),'4'])
  const result = await finalizePresentation({ workspaceDir:root,candidatePath:withVideo,finalPath:path.join(output,outputName),explicitTotalSlideCount:26,
    requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:chartOwners,materializeLiteralChartWorkbooks:true,
    fontPolicy:{basis:'reference',families:[font],referencePath:template,referenceSha256:crypto.createHash('sha256').update(await fs.readFile(template)).digest('hex')},
    pythonExecutable:python,
    integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
    layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableOwners.flatMap(i=>['--require-native-table-slide',String(i)])],
    verifyArtifactToolImport:true,receiptPath:path.join(build,`${outputName}.validation.json`) })
  console.log(JSON.stringify(result))
}
