import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const runtime = process.env.RUNTIME_NODE_MODULES
if (!runtime) throw new Error('Set RUNTIME_NODE_MODULES to the bundled runtime modules directory.')
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(runtime, '@oai/artifact-tool/dist/artifact_tool.mjs')))
const skill = '/Users/nickdigennaro/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11011/skills/presentations'
const { finalizePresentation, applyPresentationChartFont } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')))
const build = path.join(root, 'tmp/final_presentation')
const output = path.join(root, 'output/presentation')
const outputName = process.env.PRESENTATION_OUTPUT_NAME || 'CANalyst_Final_Presentation_15min.pptx'
const finalMode = process.argv.includes('--final')
const source = 'backend/out/final_2026-11-22/detection/results.json'
const detection = JSON.parse((await fs.readFile(path.join(root, source), 'utf8')).replace(/\bNaN\b/g, 'null'))
const modelResults = JSON.parse(await fs.readFile(path.join(root, 'backend/out/final_2026-11-22/model_results.json'), 'utf8'))
const ds = name => detection.datasets.find(row => row.dataset === name)
const metrics = name => ds(name).references.single.evaluation
const road = metrics('road')
const hcrl = metrics('hcrl')
const percent = value => value == null ? 'n/a' : `${(100 * value).toFixed(value > 0 && value < .001 ? 3 : value > .999 && value < 1 ? 2 : 1)}%`
const value = (rows, method, metric) => {
  const result = rows[method][metric]
  return result && typeof result === 'object' && 'value' in result ? result.value : result
}
const p = (rows, method, metric) => percent(value(rows, method, metric))
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } })
const colors = { paper: '#F6F3ED', ink: '#192E3A', muted: '#53636B', orange: '#C75B26', teal: '#18776D', blue: '#4E6C91', line: '#D5DAD8', white: '#FFFFFF' }
const font = 'Arial'
const slides = []
const pageNumbers = []
const chartOwners = []
const tableOwners = []

await fs.mkdir(build, { recursive: true })
await fs.mkdir(output, { recursive: true })

function text(slide, content, x, y, w, h, size = 29, color = colors.ink, bold = false) {
  const shape = slide.shapes.add({ geometry: 'textbox', name: content.slice(0, 65), position: { left: x, top: y, width: w, height: h }, fill: 'none', line: { fill: 'none', width: 0 } })
  shape.text = content
  shape.text.style = { fontFamily: font, fontSize: size, color, bold }
  shape.text.insets = 0
  return shape
}

function slide(title, notes, subtitle = '', dark = false) {
  const s = presentation.slides.add()
  s.background.fill = dark ? colors.ink : colors.paper
  text(s, title, 72, 48, 1136, 108, 44, dark ? colors.white : colors.ink, true)
  if (subtitle) text(s, subtitle, 74, 150, 1124, 52, 23, dark ? '#D6E1E2' : colors.muted)
  pageNumbers.push(text(s, String(slides.length + 1).padStart(2, '0'), 1170, 670, 48, 26, 18, dark ? '#D6E1E2' : colors.muted))
  s.speakerNotes.text = notes
  slides.push({ title, notes })
  return s
}

function statementRows(s, rows, y = 220, gap = 115, dark = false) {
  rows.forEach(([heading, body], i) => {
    text(s, heading, 76, y + i * gap, 360, 55, 29, dark ? '#F1AE7C' : colors.orange, true)
    text(s, body, 462, y + i * gap, 738, gap - 16, 28, dark ? colors.white : colors.ink)
  })
}

function caption(s, content) { text(s, content, 76, 622, 1124, 44, 20, colors.muted) }

function table(s, values, widths, { y = 210, height = 360, size = 25 } = {}) {
  const t = s.tables.add({ rows: values.length, columns: values[0].length, left: 76, top: y, width: 1124, height, values, columnWidths: widths })
  t.borders.assign({ fill: colors.line, width: 0.7 })
  values.forEach((row, r) => row.forEach((_, c) => {
    const cell = t.getCell(r, c)
    cell.fill = r === 0 ? colors.ink : (r % 2 ? colors.white : '#ECEEE9')
    cell.text.style = { fontFamily: font, fontSize: size, color: r === 0 ? colors.white : colors.ink, bold: r === 0 }
  }))
  tableOwners.push(slides.length)
  return t
}

function chart(s, categories, series, { x = 76, y = 210, w = 1124, h = 380, max = 1, format = '0%', legend = true } = {}) {
  const c = s.charts.add('bar', { position: { left: x, top: y, width: w, height: h }, categories,
    // Excel chart workbooks preserve 15 significant digits. Counts stay exact in notes.
    series: series.map((entry, i) => ({ ...entry, values: entry.values.map(n => Number(n.toPrecision(12))), fill: entry.fill || [colors.teal, colors.orange, colors.blue][i] })),
    barOptions: { direction: 'column', grouping: 'clustered', gapWidth: 80 }, hasLegend: legend,
    legend: { position: 'bottom', textStyle: { typeface: font, fontSize: 24, fill: colors.ink } },
    xAxis: { textStyle: { typeface: font, fontSize: 24, fill: colors.ink }, line: { fill: colors.line, width: 1 } },
    yAxis: { min: 0, max, numberFormatCode: format, textStyle: { typeface: font, fontSize: 22, fill: colors.muted }, majorGridlines: { fill: colors.line, width: 1 } },
    dataLabels: { showValue: true, position: 'outEnd', numberFormatCode: format === '0%' ? '0.0%' : format, textStyle: { typeface: font, fontSize: 24, fill: colors.ink, bold: true } },
    chartFill: colors.paper, plotAreaFill: colors.paper, chartLine: { fill: 'none', width: 0 }, plotAreaLine: { fill: 'none', width: 0 } })
  applyPresentationChartFont(c, { fontFamily: font })
  chartOwners.push(slides.length)
  return c
}

async function screenshot(s, name, position, crop) {
  const bytes = await fs.readFile(path.join(output, 'assets', name))
  s.images.add({ blob: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), contentType: 'image/png', alt: `CANalyst application: ${name}`, fit: crop ? 'cover' : 'contain', position, ...(crop ? { crop } : {}) })
}

// Author the complete story, then assign the requested 15-minute talk order below.
{
  const s = presentation.slides.add()
  s.background.fill = colors.ink
  text(s, 'CANalyst', 76, 158, 1124, 120, 80, colors.white, true)
  text(s, 'LLM-Assisted Analysis\nof CAN Bus Attacks', 80, 294, 1100, 130, 44, colors.white)
  text(s, 'Nicholas DiGennaro and Alexander Salazar', 80, 522, 1110, 45, 27, '#F1AE7C')
  text(s, 'CPSC 8580 Security Symposium · Clemson University · Fall 2026', 80, 588, 1110, 52, 23, '#D6E1E2')
  const notes = 'Timing: 0:25. Introduce both authors. Our research question is whether an LLM can turn measured CAN anomalies into useful, checkable explanations. Detection and explanation are separate in this project. We will cover the system, its evaluation, and the limits of the evidence. We analyze public research captures offline. We do not demonstrate an attack on a live vehicle. Sources: docs/CANalyst_CPSC8580_Project_Proposal.pptx; docs/Project_Proposal_Written_CPSC_8580.pdf. Course timing: lectures/Lecture_Note01.pdf, printed slides 25 and 28, specifies 20 minutes plus 3 minutes of questions.'
  s.speakerNotes.text = notes
  slides.push({ title: 'CANalyst', notes })
  pageNumbers.push(null)
}
{
  const s = slide('The analyst problem', 'Timing: 0:50. A CAN log gives us timestamps, identifiers, and payload bytes. A flag tells an analyst where behavior changed, but not whether the change is an attack or what measurement supports that conclusion. A numeric arbitration ID is not a verified vehicle function. Without a manufacturer database, assigning a real signal name can be wrong. CANalyst therefore explains measured rate, timing, entropy, and identifier changes. The prompt asks the model to leave vehicle function unknown without a verified mapping. The intended benefit is faster inspection; we have not measured analyst time or correctness. Sources: README.md; app/evidence.py; CAN-D paper https://arxiv.org/abs/2006.05993.', 'A suspicious window still needs an explanation')
  statementRows(s, [['Input', 'Timestamp, arbitration ID, payload bytes'], ['Detector output', 'An anomaly score and a flagged interval'], ['Analyst need', 'What changed, what supports it, and what remains unknown']])
}
{
  const s = slide('Where CANalyst fits', 'Timing: 0:45. Related work addresses several distinct problems. READ and LibreCAN recover signal structure or meaning from proprietary CAN data. CIDS uses clock behavior to fingerprint transmitting controllers. Our project combines statistical alerts with evidence-linked explanations and a review interface. We do not claim to replace those systems or to be the first explainable CAN detector. This distinction also sets our scope: an explanation about an anomaly is not a recovered DBC database or authenticated ECU identity. Sources: READ https://doi.org/10.1109/TIFS.2018.2870826; LibreCAN https://mpese.com/publication/pese-2019-librecan/ACM_CCS_LibreCAN_Paper.pdf; CIDS https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho.')
  table(s, [['Research direction', 'Representative work', 'Primary output'], ['Signal decoding', 'READ, LibreCAN', 'Structure or meaning of CAN data'], ['ECU fingerprinting', 'CIDS', 'Controller identity from clock behavior'], ['This project', 'CANalyst', 'Evidence-linked alert explanation']], [300, 300, 524], { height: 330 })
  caption(s, 'Scope: interpret detected anomalies. Signal decoding and ECU authentication remain separate tasks.')
}
{
  const s = slide('Datasets and attack labels', 'Timing: 1:00. Car-Hacking contains injection captures for denial of service, fuzzing, RPM spoofing, and gear spoofing, plus normal traffic. Its records provide injected-versus-normal flags; the capture identifies the attack type. ROAD provides varied ambient traffic and attacks with timing metadata. It includes real fabrication and fuzzing captures and simulated masquerade derivatives. A fabrication capture and its masquerade derivative share source traffic. Synthetic traffic is used for tests and demonstrations, not headline real-data results. Both public datasets represent limited vehicle coverage. Sources: https://ocslab.hksecurity.net/Datasets/CAN-intrusion-dataset; https://zenodo.org/records/10462796; app/datasets.py; app/loader.py.')
  table(s, [['Source', 'What we evaluate', 'Ground truth'], ['Car-Hacking / HCRL', 'DoS, fuzzing, RPM/gear spoofing', 'Per-frame injection flags'], ['ROAD', 'Fabrication, fuzzing, masquerade', 'Attack intervals and capture metadata'], ['Synthetic', 'Regression and demo scenarios', 'Generator-defined attack intervals']], [265, 465, 394], { height: 330 })
  caption(s, 'ROAD masquerade examples are derived captures. Synthetic results are kept separate from real-data claims.')
}
{
  const s = slide('System architecture', 'Timing: 1:00. The pipeline first validates and normalizes a capture. It learns normal behavior from a separate attack-free baseline or an explicitly clean prefix. It then computes rolling features and flags windows. Adjacent flags become an alert. The evidence builder packages measured deviations and a few sample frames. A rule control or a selected language model returns a structured explanation. The dashboard links each citation back to the measured item. Ingestion and detection run locally. Hosted explanations are requested explicitly, so opening a capture does not silently start model calls. Sources: app/loader.py, features.py, detector.py, evidence.py, llm.py, pipeline.py; README.md.')
  table(s, [['Stage', 'Operation', 'Output'], ['1', 'Validate capture and normal baseline', 'Normalized frames'], ['2', 'Measure windows and detect changes', 'Scored windows and merged alerts'], ['3', 'Build the evidence packet', 'Named measurements and samples'], ['4', 'Run control or selected model', 'Structured labels, claims, citations'], ['5', 'Inspect in the dashboard', 'Linked evidence and saved comparisons']], [100, 560, 464], { y: 190, height: 405, size: 25 })
  caption(s, 'The model explains an alert after detection. It does not scan the full raw capture.')
}
{
  const s = slide('Window features and detector profiles', 'Timing: 0:55. Defaults use half-second windows with a quarter-second stride. The rule detector maps measured deviations to component scores, then takes the maximum allowed component. Profile v1 includes all six components. Profile v2 allows only unknown IDs, per-ID rate inflation, and total bus load to raise alerts, while still retaining other measurements as evidence. The default threshold is 0.55. The learned comparison uses IsolationForest on the same feature family with explicit normal training and calibration. These profiles change detection, not prompt wording or control rules. Sources: app/detector.py, features.py, windowstats.py; scripts/benchmark.py.')
  table(s, [['Component', 'v1 raises alerts', 'v2 raises alerts'], ['Bus load, unknown IDs, per-ID rate', 'Yes', 'Yes'], ['Missing IDs, timing, payload entropy', 'Yes', 'No']], [650, 237, 237], { y: 225, height: 230, size: 28 })
  text(s, '0.5 s windows · 0.25 s stride · threshold 0.55', 78, 507, 1120, 58, 31, colors.teal, true)
  caption(s, 'All components remain available as evidence. The live application retains v1 as its default.')
}
{
  const s = slide('The evidence contract', 'Timing: 1:00. Every explanation must point to evidence items. E0 describes the alert interval and detector information. Per-ID items report counts, rates, timing, entropy, and whether a baseline exists. The corrected live packet distinguishes full-alert measurements from representative-window statistics. It also distinguishes the raw rate ratio from the detector ratio, which uses a minimum expected-count guard. Unknown baselines and single-frame timing are unavailable rather than false zeros. We omit ground-truth labels and identifying filenames from the model context. Up to six sampled frames provide context; they do not establish every payload value across the interval. Sources: app/evidence.py; app/llm.py; tests/test_explainer_integrity.py; out/semantic_audit_2026-10-30/numeric_validation_v4.json.')
  statementRows(s, [['Citable facts', 'Alert interval, counts, rates, timing, payload statistics'], ['Explicit scope', 'Full alert versus representative window; missing values stay missing'], ['Blinded prompts', 'Ground-truth labels and capture names stay outside the prompt']])
}
{
  const s = slide('Three evaluation questions', 'Timing: 1:00. Keep the units of analysis separate. Detection is evaluated on windows: how many attack windows are found, and how often normal windows are flagged? Classification is evaluated only on the alerts the detector produced. It cannot recover missed attack windows. Claim evaluation asks whether cited evidence actually supports the text. Citation membership is a mechanical check, not semantic verification. We also keep the October corrected evidence family separate from the November historical prompt and control family. They share many target alerts but have different packets and settings. Sources: docs/FINAL_RESULTS_2026-11-22.md; app/metrics.py; scripts/score_explanations.py.', '', true)
  statementRows(s, [['Detection', 'Precision, recall, and false-positive rate per window'], ['Classification', 'Attack-label accuracy per detected alert'], ['Claim support', 'Citation membership, numeric checks, and semantic review']], 225, 115, true)
}
{
  const s = slide('Evaluation protocol and data reuse', 'Timing: 0:55. The November protocol assigns reference, tuning, and evaluation roles. ROAD groups fabrication and masquerade twins into the same role. HCRL has one recording per attack type, so the protocol splits each recording in time and removes crossing windows. Thresholds and one-class models use tuning windows. However, the merged project had already evaluated these recordings during October development. The final rerun therefore verifies implementation under the saved protocol. It is not evidence from a new vehicle or a pristine project-level holdout. The appendix gives the exact role ledger. Sources: app/datasets.py; scripts/benchmark.py; docs/FINAL_RESULTS_2026-11-22.md; final detection verification.')
  table(s, [['Role', 'Use', 'Separation rule'], ['Reference', 'Learn normal measurements', 'Attack-free baseline'], ['Tuning', 'Choose thresholds and fit models', 'No evaluation windows used'], ['Evaluation', 'Report evaluation outcomes', 'ROAD capture groups; HCRL time slices']], [230, 430, 464], { height: 330 })
  caption(s, 'Prior project development touched these recordings. These are protocol evaluation results, not a new-vehicle test.')
}
{
  const s = slide('ROAD: fewer false alarms, limited recall', `Timing: 1:45. These values use the single-reference configuration and ROAD evaluation partition, rerun with the merged implementation. Profile v2 restricts which components may raise an alert. Compare false-positive rate and precision, then show recall. V1 finds 911 of 1,954 attack windows and flags 1,461 of 9,598 normal windows. V2 finds 910 attacks and flags 50 normal windows. Masquerade recall remains only 4/971 for v1 and 3/971 for v2. Its legitimate-looking timing or identifiers defeat coarse window statistics. Do not substitute ambient-only FPR for the all-normal-window denominator. Profile v2 is a candidate for this protocol, not a universally validated new default. Source: ${source}, ROAD single reference; detection/verification.md.`, 'Fresh merged-code run · single normal reference · protocol evaluation split')
  chart(s, ['Precision', 'Recall', 'False-positive rate'], [
    { name: 'Rule profile v1', values: ['precision', 'recall', 'fpr'].map(k => value(road, 'rule@0.55', k)), fill: colors.blue },
    { name: 'Rule profile v2', values: ['precision', 'recall', 'fpr'].map(k => value(road, 'rule_v2@0.55', k)), fill: colors.teal },
  ])
  caption(s, 'Masquerade detection: v1 4/971 windows; v2 3/971. Lower false alarms do not solve missed attacks.')
}
{
  const s = slide('HCRL: a simpler baseline remains competitive', `Timing: 0:40. HCRL has stronger injection signatures than the ROAD masquerade cases. Compare both rule profiles with the union of ID-whitelist and message-interval baselines. The simple baseline is competitive and can exceed the rule profiles on this protocol. That is why the project should not be presented as a best-in-class detection result. Profile v2 can trade some spoofing recall for fewer normal flags. We keep the live v1 default while reporting that tradeoff. Source: ${source}, HCRL single reference.`)
  table(s, [['Detector', 'Precision', 'Recall', 'F1'], ...['rule@0.55', 'rule_v2@0.55', 'whitelist_interval'].map((method, i) => [[ 'Rule profile v1', 'Rule profile v2', 'Whitelist + interval'][i], p(hcrl, method, 'precision'), p(hcrl, method, 'recall'), value(hcrl, method, 'f1').toFixed(3)])], [475, 220, 220, 209], { height: 310, size: 28 })
  caption(s, 'Corrected jitter handling reduces v1 false positives: 32 to 1. V2 misses 56 additional spoofing windows.')
}
{
  const s = slide('October: GLM matches control on attack labels', 'Timing: 1:05. These three arms use the exact same corrected v4 evidence and targets: 69 HCRL attack alerts, 20 ROAD attack alerts, and 11 ROAD false alarms. The local control-v5 and GLM-5.3 each classify all 69 HCRL attacks and 17 of 20 ROAD attacks correctly. They share the same three attack misses. Qwen3-30B-A3B Instruct FP8 is substantially lower on HCRL and also lower on ROAD. Both hosted arms completed all 100 requests without fallback. These are observed paired outcomes on development data, not statistical equivalence or evidence of general model superiority. Source: backend/out/final_2026-11-22/model_results.json and qwen_v4_hcrl.json, qwen_v4_road.json.', 'Exact matched evidence · 89 attack alerts; 11 false alarms scored separately')
  chart(s, ['HCRL attacks (n=69)', 'ROAD attacks (n=20)'], [{ name: 'Control-v5', values: [1, .85] }, { name: 'GLM-5.3', values: [1, .85] }, { name: 'Qwen3-30B-A3B', values: [24 / 69, .7] }])
  caption(s, 'Correct labels: control 69/69 and 17/20; GLM 69/69 and 17/20; Qwen 24/69 and 14/20.')
}
{
  const s = slide('November: explain the coverage before the score', 'Timing: 1:00. The set named heldout contains 77 alerts. Seventy are HCRL attacks from later time slices; seven are ROAD false alarms. There are no ROAD attack alerts in this set. The historical control-v2 classifies all 70 HCRL attacks correctly. With historical prompt v2, Gemma scores 69, GLM 59, and Qwen3.6 scores 37. Failed requests count as wrong when an attack alert has a recorded error. The table reports total request failures across all 77 alerts separately. This Qwen3.6-27B model is different from the October Qwen3-30B model. Sources: out/alerts/heldout/alerts.jsonl; out/explanations/heldout/scores.json; final model_results.json.', '77 detected alerts: 70 HCRL attacks + 7 ROAD false alarms')
  table(s, [['Historical arm', 'HCRL attack labels', 'No answer / 77'], ['Control rules v2', '70 / 70', '0'], ['Gemma-4-31B, prompt v2', '69 / 70', '0'], ['GLM-5.3, prompt v2', '59 / 70', '5'], ['Qwen3.6-27B, prompt v2', '37 / 70', '0']], [600, 300, 224], { y: 210, height: 350, size: 25 })
  caption(s, 'Zero ROAD attack alerts. This set cannot establish ROAD attack-label accuracy.')
}
{
  const s = slide('One prompt line changes many labels', 'Timing: 0:55. The historical ablation replaces only the DoS definition in prompt v2 with the earlier wording. The newer sentence allows a flood that displaces legitimate traffic. That is physically plausible but can also pull spoofing alerts toward DoS. Restoring the older wording greatly improves HCRL spoofing labels in these runs. Qwen rises from 37 to 69 correct attack labels, while GLM rises from 59 to 70. Gemma rises from 69 to 70. GLM also has fewer failed requests, so service-output variation contributes to the observed difference. These runs establish sensitivity to wording, not a universal prompt improvement. Sources: app/llm.py SYSTEM_PROMPT_V2_DOSV1; out/explanations/heldout/scores.json; docs/FINAL_RESULTS_2026-11-22.md.', 'Same 70 HCRL attack targets · historical prompt v2 versus the DoS-line ablation')
  chart(s, ['Gemma-4-31B', 'GLM-5.3', 'Qwen3.6-27B'], [{ name: 'Prompt v2', values: [69 / 70, 59 / 70, 37 / 70], fill: colors.blue }, { name: 'DoS-line ablation', values: [1, 1, 69 / 70], fill: colors.orange }])
  caption(s, 'Correct labels: 69→70, 59→70, 37→69. GLM total no-answer count also falls from 5 to 1.')
}
{
  const s = slide('Valid citations can accompany unsupported claims', 'Timing: 0:55. In one saved GLM response, the cited measurement reports zero payload entropy. The explanation infers all-zero bytes. Zero entropy supports constancy under the estimator, not the specific constant value. Separate sampled frames may show zeros, but the claim must cite them and stay within their scope. A second example names CAN ID 0x55 in the summary while the packet and cited claim name 0x655. The identifier validator flags the mismatch without rewriting model output. The selected October semantic audit reviewed 18 claims: 13 supported, five unsupported, and none numerically contradicted. It was purposive and AI-assisted, not an independent population estimate. Sources: claims_v4_followup.csv, claim V4-03; validation_2026-10-30_v4/road_glm.json.')
  text(s, 'Measured: payload entropy = 0', 78, 220, 1100, 65, 36, colors.teal, true)
  text(s, 'Unsupported leap: therefore every byte is 0x00', 78, 320, 1110, 80, 33, colors.orange, true)
  text(s, 'Citation membership checks the reference.\nSemantic review checks what the reference proves.', 78, 447, 1100, 120, 31)
  caption(s, 'Selected audit: 13 supported and 5 unsupported claims out of 18. Independent human ratings remain incomplete.')
}
{
  const s = slide('Deployment and latency', 'Timing: 0:40. Python ingestion, feature extraction, and detection run locally. The React dashboard calls the local API. The implementation uses Clemson RCD for hosted explanation experiments rather than the originally proposed self-hosted Palmetto Slurm server. On October v4, median GLM response time is about 6.3 to 6.6 seconds and Qwen about 4.2 seconds. The deterministic control has negligible request latency. These are observed run timings, not a service guarantee or controlled hardware comparison. All 100 requests completed for both hosted arms in that comparison. Saved November runs used different prompts, models, token budgets, and service conditions. Sources: README.md; model_results.json; docs/CANalyst_Palmetto_Implementation_Guide.md.')
  table(s, [['October v4 arm', 'HCRL median', 'ROAD median', 'Failed / 100'], ['Control-v5', '<1 ms', '<1 ms', '0'], ['GLM-5.3', '6.33 s', '6.60 s', '0'], ['Qwen3-30B-A3B', '4.27 s', '4.19 s', '0']], [490, 215, 215, 204], { height: 315, size: 27 })
  caption(s, 'Capture processing is local. Hosted explanations are explicit requests with measured latency and failure accounting.')
}
{
  const s = slide('Dashboard demonstration', 'Timing: 2:20. Prewarm the installed ROAD example before class. Use the offline control for the live path and say that it is deterministic. First show the capture source, 41,829 frames, separate normal baseline, and detected alert. Select the alert and jump from a claim citation to its measured evidence. Explain one rate or timing change without assigning an unverified signal function. Next open Evaluation, then Frozen benchmarks, and show the detection versus explanation denominators. If time permits, open Benchmark for a saved GLM example and its identifier warning. Do not start a hosted request during the timed talk. If the browser fails, narrate this screenshot and the appendix screenshots. Source: verified real-road-default-startup screenshot and 19-check browser QA.', 'Capture → alert → cited measurement → saved comparison')
  text(s, '1. Select a flagged interval', 76, 212, 540, 45, 27, colors.teal, true)
  text(s, '2. Inspect the cited measurement', 660, 212, 540, 45, 27, colors.teal, true)
  await screenshot(s, 'road-dashboard.png', { left: 76, top: 272, width: 540, height: 230 }, { left: 338 / 1440, top: 424 / 2372, right: 20 / 1440, bottom: 1488 / 2372 })
  await screenshot(s, 'road-dashboard.png', { left: 660, top: 272, width: 540, height: 280 }, { left: 730 / 1440, top: 930 / 2372, right: 20 / 1440, bottom: 1084 / 2372 })
  caption(s, 'Live path uses the offline control. Saved GLM results demonstrate actual hosted-model output.')
}
{
  const s = slide('Limits of the current evidence', 'Timing: 1:10. First, the datasets cover a narrow set of vehicles and conditions. Earlier development touched the recordings later assigned evaluation roles. Second, the explanation experiment conditions on detected alerts, so strong label accuracy says nothing about attacks the detector misses. Third, the November explainer set contains no ROAD attack alerts. Fourth, valid citations do not prove semantic support. Both independent human review sheets still have 40 unanswered rows. We have not measured analyst task time, correctness, or trust. These are substantive research limits, not just implementation issues. A next study should reserve new data, include stealthy ROAD-like attacks, and use independent human raters. Sources: FINAL_RESULTS_2026-11-22.md; claim_review/heldout/rater_A.csv and rater_B.csv.')
  statementRows(s, [['Generalization', 'Prior data reuse and limited vehicle coverage'], ['Missed attacks', 'Alert-label accuracy does not measure detector recall'], ['Human benefit', 'Independent claim ratings and analyst task study are not complete']])
}
{
  const s = slide('What the project demonstrates', 'Timing: 0:50. Return to the research question. We built an end-to-end workflow that validates CAN data, detects anomalies, produces compact evidence, and makes explanations inspectable. The experiments show a useful engineering outcome: explicit scopes, versioned inputs, failure accounting, and linked citations make mistakes visible. The corrected GLM arm matches the control on the observed attack labels, but does not improve that accuracy. Detector behavior still limits coverage, especially masquerade. Our research conclusion is therefore a measured prototype and a reproducible evaluation framework. The next step is to test whether this evidence-linked workflow improves human analysis on genuinely new data. Sources: final model results; fresh detector verification; source tests and browser QA.', '', true)
  statementRows(s, [['Built', 'A working CAN analysis and evidence-review workflow'], ['Measured', 'Detection tradeoffs, model labels, failures, and latency'], ['Still unproven', 'Generalization and improved human analyst performance']], 225, 115, true)
}
{
  const s = slide('Questions', 'Timing: 0:20 transition, then 3:00 Q&A. Invite questions about detector coverage, data reuse, prompt sensitivity, and citation support. Keep the appendix available for detailed denominators and baseline comparisons. Do not describe the rule control as an LLM, the November set as project-level untouched data, or citation validity as semantic correctness. If asked whether deployment is production-ready, state that this is a local research prototype. Hosted infrastructure is Clemson RCD; production scaling and vehicle deployment were not evaluated.')
  text(s, 'Can measured evidence make\nmodel explanations easier to verify?', 78, 246, 1110, 160, 47, colors.teal, true)
  text(s, 'Technical details and backup screens follow.', 80, 515, 1100, 50, 28, colors.muted)
}

// Appendix: keep detailed protocol and evidence available for questions.
{
  const s = slide('Appendix: split and provenance ledger', 'Use during questions about independence. ROAD uses a separate normal reference, alternating ambient capture roles, and grouped attack families. Fabrication/masquerade twins stay together. HCRL uses normal [0,120) as reference, [120,300) as tuning, and later normal traffic as evaluation. Attack recordings are split at the median nonempty window. Prior October work touched all four HCRL attack recordings and all 25 November ROAD evaluation capture sources. The final model-results summary records exact overlap. Source: app/datasets.py; FINAL_RESULTS_2026-11-22.md; final detection verification.')
  table(s, [['Protocol', 'Assigned separation', 'Project-level caveat'], ['ROAD detection', 'Capture/family grouping', 'All 25 evaluation sources previously used'], ['HCRL detection', 'Disjoint time windows', 'All four attack recordings previously scored'], ['October vs November midterm100', 'Different evidence and prompt versions', 'All 100 alert targets overlap'], ['November explainer heldout', 'Later HCRL slices; ROAD false alarms', 'No ROAD attack alerts; no new vehicle']], [330, 380, 414], { y: 200, height: 390, size: 24 })
}
function fullDetectorSlide(name, rows) {
  const names = { 'rule@0.55': 'Rule v1', 'rule_v2@0.55': 'Rule v2', 'rule@tuned': 'Rule v1, tuned', id_whitelist: 'ID whitelist', interval: 'Message interval', whitelist_interval: 'Whitelist + interval', id_entropy: 'ID entropy', iforest: 'IsolationForest', ocsvm: 'One-class SVM' }
  const s = slide(`Appendix: ${name.toUpperCase()} detector comparison`, `Single-reference configuration. These values are drawn programmatically from ${source}. Thresholds marked tuned target at most 1% false positives on attack-free tuning windows. Evaluation windows overlap, so the benchmark uses 20-window block bootstrap intervals with 2,000 draws. Do not interpret a single dataset's ranking as general superiority. Undefined precision occurs when no windows are flagged; display it as n/a, not zero.`)
  table(s, [['Method', 'Precision', 'Recall', 'F1', 'FPR'], ...Object.entries(names).map(([key, label]) => [label, p(rows, key, 'precision'), p(rows, key, 'recall'), value(rows, key, 'f1')?.toFixed(3) ?? 'n/a', p(rows, key, 'fpr')])], [380, 186, 186, 186, 186], { y: 180, height: 440, size: 23 })
  caption(s, 'Fresh merged-code run · single reference · full intervals and thresholds remain in the result JSON.')
}
fullDetectorSlide('road', road)
fullDetectorSlide('hcrl', hcrl)
{
  const s = slide('Appendix: version names describe different layers', 'Use this slide to prevent version confusion. Live evidence-v4 uses corrected missingness and raw-versus-guarded ratio semantics. The local rule control is control-v5 and its hosted prompt is can-evidence-v3. November historical experiments explicitly select alert/window scopes, control rules v1/v2, and prompts v1/v2/v2-dosv1. Detector profile v2 changes eligible alert components; it is not a prompt or control-rule version. Preserve saved packets instead of regenerating them silently under new code. Sources: app/evidence.py, app/llm.py, app/detector.py; FINAL_RESULTS_2026-11-22.md.')
  table(s, [['Layer', 'Live corrected path', 'Historical experiment path'], ['Detector profile', 'v1 default', 'v1 or v2'], ['Evidence', 'evidence-v4', 'Explicit alert or window scope'], ['Rule control', 'control-v5', 'rules v1 or v2'], ['Hosted prompt', 'can-evidence-v3', 'v1, v2, v2-dosv1']], [300, 380, 444], { height: 370, size: 26 })
}
{
  const s = slide('Appendix: failures and false-alarm denominators', 'The October paired corpus has 89 attack alerts and 11 false alarms. GLM calls one false alarm benign; the local control and Qwen call none benign. The November heldout set has only HCRL attacks. GLM no-answer counts are across all 77 alerts, so do not subtract all five from HCRL accuracy without inspecting IDs. In the midterm ROAD-only DoS-line ablation, GLM has 30 of 31 replies. The missing target is A0093, an ambient_dyno_drive_extended_short false alarm over [0,23) seconds. Both GLM prompts call 6 of the 10 shared false alarms benign. On all 11 targets, ablation benign classification ranges from 6/11 to 7/11 depending on the missing answer; original v2 is 7/11. Source: final model_results.json.')
  table(s, [['Comparison', 'Attack denominator', 'False-alarm denominator'], ['October corrected v4', '69 HCRL + 20 ROAD', '11 ROAD'], ['November heldout', '70 HCRL; 0 ROAD', '7 ROAD'], ['November ROAD ablation', '20 ROAD', '11 ROAD; one GLM answer missing']], [420, 360, 344], { height: 310, size: 26 })
  caption(s, 'Missing predictions and failed requests must remain visible. Matched-subset and full-set rates answer different questions.')
}
{
  const s = slide('Appendix: claim-review protocol', 'Human ratings are not complete. The existing blinded packet contains 40 sampled claims with evidence and two empty rater files. Ask two independent human raters to label each claim supported, unsupported, or contradicted using the saved rubric. Keep model identities and the answer key hidden until ratings are complete. The score command computes agreement and Cohen kappa, then lists disagreements for adjudication. Preserve both original rating sheets. The current automated identifier and citation checks are useful quality controls, but cannot replace those judgments. Source: backend/out/claim_review/heldout/rubric.md; scripts/claim_review.py; claim_review/heldout/sheet.csv.')
  statementRows(s, [['Supported', 'The cited evidence supports the claim within its stated scope'], ['Unsupported', 'The evidence does not justify the conclusion'], ['Contradicted', 'The evidence conflicts with the claim']])
  caption(s, '40 claims × 2 human raters planned. Both rating sheets remain blank; no human agreement result is reported.')
}
{
  const s = slide('Appendix: saved benchmark screen', 'Backup for the live demo. The Evaluation view contains November detection and frozen explainer benchmarks. The historical Benchmark tab retains October corrected experiments. Explain that these are saved results, not recomputed detector runs or live model calls. Show the dataset and denominator before interpreting a score. Screenshot source: output/presentation/assets/frozen-benchmarks.png, captured during the 19-check browser QA on 2026-11-22.')
  await screenshot(s, 'frozen-benchmarks.png', { left: 76, top: 195, width: 1124, height: 332 }, { left: 60 / 1440, top: 580 / 3928, right: 60 / 1440, bottom: 2958 / 3928 })
  caption(s, 'Saved November comparisons: 70 HCRL attack alerts, 7 ROAD false alarms, and zero ROAD attack alerts.')
}
{
  const s = slide('Appendix: sources and reproducibility', 'Primary sources: Car-Hacking dataset, https://ocslab.hksecurity.net/Datasets/CAN-intrusion-dataset. ROAD dataset, https://zenodo.org/records/10462796; dataset paper https://arxiv.org/abs/2012.14600. CIDS, Cho and Shin, USENIX Security 2016, https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho. READ, https://doi.org/10.1109/TIFS.2018.2870826. LibreCAN, https://mpese.com/publication/pese-2019-librecan/ACM_CCS_LibreCAN_Paper.pdf. CAN-D, https://arxiv.org/abs/2006.05993. Project results: backend/out/final_2026-11-22/model_results.json; backend/out/final_2026-11-22/detection/results.json; docs/FINAL_RESULTS_2026-11-22.md. Exact inputs and source hashes remain in manifests. All speaker notes identify their supporting artifacts.')
  statementRows(s, [['Dataset sources', 'HCRL Car-Hacking; ORNL ROAD'], ['Related research', 'READ; LibreCAN; CIDS; CAN-D'], ['Project evidence', 'Frozen packets, raw replies, scoring scripts, and source hashes']])
  caption(s, 'Full source links are in speaker notes. Rehearsal and demo instructions are in FINAL_PRESENTATION_GUIDE.md.')
}

if (slides.length !== 28) throw new Error(`Expected 28 slides; got ${slides.length}`)
const order = [1, 2, 4, 5, 7, 8, 10, 12, 13, 14, 15, 17, 18, 19, 20, 3, 6, 9, 11, 16, 21, 22, 23, 24, 25, 26, 27, 28]
const timings = ['0:25', '0:50', '1:00', '1:00', '1:00', '1:00', '1:30', '1:05', '0:45', '0:55', '0:55', '1:45', '1:10', '0:50', '0:20']
const duration = timings.reduce((total, time) => {
  const [minutes, seconds] = time.split(':').map(Number)
  return total + minutes * 60 + seconds
}, 0)
if (duration !== 870) throw new Error(`Expected a 14:30 talk plus buffer; got ${duration} seconds`)
const originals = [...slides]
const slideFacades = [...presentation.slides.items]
const inspected = await presentation.inspect({ select: '$.slides[*]', include: ['id'] })
order.forEach((original, index) => {
  const record = originals[original - 1]
  record.notes = index < timings.length
    ? record.notes.replace(/^Timing: [^.]+\./, `Timing: ${timings[index]}.`)
    : `Backup slide. ${record.notes.replace(/^Timing: [^.]+\.\s*/, '')}`
  if (original === 1) record.notes += ' Requested talk length: 15 minutes. Main content totals 14:30 with a 30-second buffer.'
  if (original === 13) record.notes += ' Focus on the corpus coverage and the score ordering. The following slide explains the prompt ablation.'
  if (original === 17) record.notes = 'Timing: 1:45. Prewarm the installed ROAD capture. Say the live path uses the offline rule control. Spend 20 seconds showing the capture and separate baseline. Spend 40 seconds selecting the alert and clicking a citation. Spend 35 seconds showing Evaluation > Frozen benchmarks and its 70 HCRL attacks plus seven ROAD false alarms. Use the final ten seconds to return to the deck. If the browser stalls, narrate the two screenshot details and skip the live actions. Do not start a hosted request. Source: verified browser QA and saved screenshots.'
  if (original === 20) record.notes += ' The course allows three minutes for questions after the presentation.'
  slideFacades[original - 1].speakerNotes.text = record.notes
  if (pageNumbers[original - 1]) pageNumbers[original - 1].text = String(index + 1).padStart(2, '0')
})
presentation.slides.reorder(order.map(original => inspected.records[original - 1].id))
slides.splice(0, slides.length, ...order.map(original => originals[original - 1]))
chartOwners.splice(0, chartOwners.length, ...chartOwners.map(original => order.indexOf(original) + 1).sort((a, b) => a - b))
tableOwners.splice(0, tableOwners.length, ...tableOwners.map(original => order.indexOf(original) + 1).sort((a, b) => a - b))
await fs.writeFile(path.join(build, 'slide-content.json'), JSON.stringify(slides, null, 2))
await fs.writeFile(path.join(build, 'build-inputs.json'), JSON.stringify({ detectionSource: source, finalMode, slides: slides.length, tables: tableOwners, charts: chartOwners, modelCorpus: Object.keys(modelResults) }, null, 2))
const candidatePath = path.join(build, finalMode ? `candidate-${outputName}` : 'candidate-preview.pptx')
await (await PresentationFile.exportPptx(presentation)).save(candidatePath)
const previewDir = path.join(build, finalMode ? 'final-slides' : 'preview-slides')
await fs.mkdir(previewDir, { recursive: true })
for (const [index, s] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide: s, format: 'png', scale: 1 })
  await fs.writeFile(path.join(previewDir, `slide-${String(index + 1).padStart(2, '0')}.png`), new Uint8Array(await png.arrayBuffer()))
}
console.log(JSON.stringify({ candidatePath, previewDir, slides: slides.length }))
if (finalMode) {
  const result = await finalizePresentation({ workspaceDir: root, candidatePath, finalPath: path.join(output, outputName),
    explicitTotalSlideCount: 28, requiredNativeTableOwnerSlides: tableOwners, requiredNativeChartOwnerSlides: chartOwners,
    materializeLiteralChartWorkbooks: true, fontPolicy: { basis: 'design', families: [font] },
    pythonExecutable: '/Users/nickdigennaro/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
    integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
    layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
    layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit', ...tableOwners.flatMap(i => ['--require-native-table-slide', String(i)])],
    verifyArtifactToolImport: true, receiptPath: path.join(build, `${outputName}.validation.json`) })
  console.log(JSON.stringify(result))
}
