import fs from 'node:fs/promises'
import path from 'node:path'
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
presentation.theme.defaultFont = 'Avenir Next'
const copies = presentation.slides.items.map(s => s.copy())
presentation.slides.keep([])

// Low-key Clemson light: purple ink, orange only for small markers and key numbers.
const color = { orange: '#F56600', purple: '#522D80', dark: '#2E1A47', body: '#3D3546', muted: '#7A7184', faint: '#A8A0B3', lavender: '#D9D0E6', tile: '#F7F5F9', line: '#E7E3EC', white: '#FFFFFF' }
const font = 'Avenir Next'
const mono = 'Consolas'
const videoSlide = 6
const videoSeconds = 45
const source = 'backend/out/final_2026-11-22/detection/results.json'
const detection = JSON.parse((await fs.readFile(path.join(root, source), 'utf8')).replace(/\bNaN\b/g, 'null'))
const metrics = name => detection.datasets.find(d => d.dataset === name).references.single.evaluation
const road = metrics('road')
const hcrl = metrics('hcrl')
const value = (rows, method, metric) => {
  const v = rows[method][metric]
  return v && typeof v === 'object' && 'value' in v ? v.value : v
}
const pct = (n, digits = 1) => n == null ? 'n/a' : `${(n * 100).toFixed(n > 0 && n < .001 ? 3 : digits)}%`
const slides = []
const chartOwners = []
const tableOwners = []
const seconds = [20,70,45,25,60,50,60,80,55,55,75,60,40,55,60,75,100,80,80,25]
const X = 57.6
const W = 1166.4

// Entrance builds. Shapes drawn after anim(order, kind) get a name that
// tools/add_slide_animations.py turns into a PowerPoint entrance effect.
// Kinds: drop (falls into place), rise, grow, fade. Groups play in order on slide start.
let entrance = null
const anim = (order, kind = 'drop') => { entrance = order == null ? null : { order, kind } }
const animName = (name, kind = entrance?.kind) => entrance ? `anim:${entrance.order}:${kind}:${name}` : name

function text(s, content, x, y, width, height, size = 26, fill = color.body, bold = false, { align = 'left', valign = 'top', family = font, bg, kind } = {}) {
  const t = s.shapes.add({ geometry: 'textbox', name: animName(content.slice(0, 60), kind), position: { left: x, top: y, width, height }, fill: bg || 'none', line: { fill: 'none', width: 0 } })
  t.text = content
  // Sizes are pixels (0.75 pt each). Keep everything at 16 pt or larger for the back row.
  t.text.style = { typeface: family, fontSize: Math.max(size, 21.4), color: fill, bold, alignment: align, verticalAlignment: valign }
  t.text.insets = 0
  return t
}

function box(s, x, y, width, height, fill, { line, radius, geometry = 'rect' } = {}) {
  return s.shapes.add({ geometry, name: animName(geometry), position: { left: x, top: y, width, height }, fill,
    line: line ? { style: 'solid', fill: line, width: 1.25 } : { fill: 'none', width: 0 }, ...(radius ? { borderRadius: radius } : {}) })
}

// Big number with label. With count, stacked opaque frames tick the first number up from zero.
// The final frame sits on top, so static views show only the real value.
function stat(s, number, label, x, y, width, fill = color.purple, size = 88, { count, bg = color.white } = {}) {
  if (count) {
    const token = number.match(/[\d,]+(\.\d+)?/)[0]
    const target = Number(token.replace(/,/g, ''))
    const decimals = token.split('.')[1]?.length ?? 0
    ;[0, .15, .35, .55, .75, .9].forEach(f => {
      const v = (target * f).toFixed(decimals)
      text(s, number.replace(token, decimals ? v : Number(v).toLocaleString('en-US')), x, y, width, size * 1.15, size, fill, true, { bg, kind: 'count' })
    })
  }
  text(s, number, x, y, width, size * 1.15, size, fill, true, count ? { bg, kind: 'count' } : {})
  text(s, label, x, y + size * 1.2, width, 80, 24, color.muted)
}

function replace(e, content) {
  const shape = presentation.resolve(e.id)
  shape.text = content
  shape.text.style = { typeface: font, fontSize: e.style.fontSize, color: e.style.color, bold: e.style.bold || false, alignment: e.style.alignment || 'left' }
  return shape
}

// Template elements: title at top 43, footer at 672, slide number at 669. Footer and number are removed.
async function slide(title, notes, { base = 6, retain = () => false, keepTitle = true } = {}) {
  anim(null)
  const s = presentation.slides.addCopy(copies[base - 1])
  const inspected = await presentation.inspect({ select: '$.slides[*]', include: ['id', 'elements.id', 'elements.kind', 'elements.text', 'elements.position', 'elements.style'] })
  const elements = inspected.records.at(-1).elements
  if (base !== 1 && base !== 15) {
    for (const e of elements) {
      if (e.position.top === 43 && keepTitle) replace(e, title)
      else if (!retain(e)) presentation.delete(e.id)
    }
  }
  const timing = seconds[slides.length]
  const timingText = timing ? `Timing: ${Math.floor(timing / 60)}:${String(timing % 60).padStart(2, '0')}. ` : 'Backup slide. '
  s.speakerNotes.text = timingText + notes
  slides.push({ title, notes: timingText + notes, templateSlide: base, seconds: timing || 0 })
  return { s, elements }
}

function table(s, values, widths, { y = 170, height = 365, size = 26 } = {}) {
  const t = s.tables.add({ rows: values.length, columns: values[0].length, left: X, top: y, width: W, height, values, columnWidths: widths })
  t.borders.assign({ fill: color.line, width: .7 })
  values.forEach((row, r) => row.forEach((_, c) => {
    const cell = t.getCell(r, c)
    cell.fill = r === 0 ? color.tile : color.white
    cell.text.style = { typeface: font, fontSize: size, color: r === 0 ? color.dark : color.body, bold: r === 0 }
  }))
  tableOwners.push(slides.length)
}

function chart(s, categories, series, { max = 1, format = '0%', x = X, y = 155, width = W, height = 430, legend = true } = {}) {
  const c = s.charts.add('bar', { position: { left: x, top: y, width, height }, categories,
    series: series.map((entry, i) => ({ ...entry, values: entry.values.map(n => Number(n.toPrecision(12))), fill: entry.fill || [color.purple, color.orange, color.lavender][i] })),
    barOptions: { direction: 'column', grouping: 'clustered', gapWidth: 85 }, hasLegend: legend,
    legend: { position: 'bottom', textStyle: { typeface: font, fontSize: 24, fill: color.body } },
    xAxis: { textStyle: { typeface: font, fontSize: 24, fill: color.body }, line: { fill: color.line, width: 1 } },
    yAxis: { min: 0, max, numberFormatCode: format, textStyle: { typeface: font, fontSize: 22, fill: color.muted }, majorGridlines: { fill: color.line, width: 1 } },
    dataLabels: { showValue: true, position: 'outEnd', numberFormatCode: format === '0%' ? '0.0%' : format, textStyle: { typeface: font, fontSize: 24, fill: color.body, bold: true } },
    chartFill: color.white, plotAreaFill: color.white, chartLine: { fill: 'none', width: 0 }, plotAreaLine: { fill: 'none', width: 0 } })
  applyPresentationChartFont(c, { fontFamily: font })
  chartOwners.push(slides.length)
}

function caption(s, content, y = 640) { text(s, content, X, y, W, 40, 24, color.muted) }

async function picture(s, name, position, alt, crop) {
  const bytes = await fs.readFile(path.join(output, 'assets', name))
  s.images.add({ blob: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), contentType: 'image/png', alt, fit: crop ? 'cover' : 'contain', position, ...(crop ? { crop } : {}) })
}

// 1. Title
{
  const { elements } = await slide('CANalyst', 'Introduce both authors. Our question: can a language model turn a CAN alert into an explanation that an analyst can check against measurements? This talk covers the problem, how CANalyst works, what we measured, and what we learned. The talk totals 19:30, leaving 30 seconds before the three-minute question period. Sources: docs/midterm/paper/midterm.tex; docs/FINAL_RESULTS_2026-11-23.md.', { base: 1 })
  const replacements = [null, null, 'CANalyst', 'LLM-Assisted CAN Attack Analysis', 'Nicholas DiGennaro\nAlexander Salazar', 'Annual CPSC 8580 Security Symposium\nClemson University, Fall 2026']
  elements.forEach((e, i) => replacements[i] === null ? presentation.delete(e.id) : replace(e, replacements[i]))
}

// 2. Problem and CAN primer
{
  const { s } = await slide('An alert is not an explanation', 'Start with the security problem. A car has dozens of controllers that share one network, the CAN bus. Every message carries an ID, a timestamp, and up to eight data bytes. The ID says what the message is about, not who sent it, and nothing authenticates the sender. Anyone with bus access, through a compromised controller or a diagnostic port, can inject, flood, or imitate messages. An intrusion detector can flag when traffic looks abnormal. An analyst still has to decide what kind of attack it was and why. That step is slow and needs expertise. Our research question: can a language model explain an alert using measurements the analyst can verify? Scope: offline analysis of recorded captures, not live vehicles. The log rows are illustrative. Sources: docs/midterm/paper/midterm.tex lines 51 to 63; paper/final.tex lines 56 to 76.')
  anim(1, 'drop')
  box(s, X, 160, 620, 250, color.tile, { radius: 14 })
  text(s, 'TIME      ID     DATA BYTES', X + 28, 182, 570, 30, 21.4, color.muted, true, { family: mono })
  const rows = ['12.4031  0x316  05 21 68 09 21 21 00 6F', '12.4035  0x2A0  00 00 00 00 00 00 00 00', '12.4039  0x316  05 21 68 09 21 21 00 6F', '12.4040  0x316  05 21 68 09 21 21 00 6F']
  rows.forEach((row, i) => text(s, row, X + 28, 226 + i * 42, 570, 34, 22, color.body, false, { family: mono }))
  anim(2, 'fade')
  rows.slice(2).forEach((row, i) => text(s, row, X + 28, 310 + i * 42, 570, 34, 22, color.orange, true, { family: mono, bg: color.tile }))
  anim(3, 'drop')
  text(s, 'Detector', 740, 180, 480, 30, 22, color.muted, true)
  text(s, '"Something changed here."', 740, 214, 480, 44, 30, color.body)
  anim(4, 'drop')
  text(s, 'Analyst', 740, 300, 480, 30, 22, color.muted, true)
  text(s, '"Which attack? Why?"', 740, 334, 480, 44, 30, color.dark, true)
  anim(5, 'rise')
  text(s, 'OUR QUESTION', X, 470, W, 30, 22, color.orange, true, { family: mono })
  text(s, 'Can a language model explain a CAN alert using measurements an analyst can check?', X, 510, W, 110, 40, color.purple, true)
}

// 3. Related work positioning
{
  const { s } = await slide('Where CANalyst fits', 'Prior work answers different questions about CAN traffic. READ and LibreCAN decode signals: they recover what the bytes mean. CIDS fingerprints senders from clock skew: it asks who sent a message. Intrusion detectors, including our own detector stage, ask when traffic is abnormal. CANalyst starts after detection. It asks why an alert looks like a particular attack, and it requires every claim to cite a measurement the analyst can open. We also compare every model against a hand-written rule baseline that sees the same evidence. Sources: paper/final.tex lines 78 to 87; READ doi 10.1109/TIFS.2018.2870826; LibreCAN ACM CCS 2019; CIDS USENIX Security 2016.')
  const rows = [
    ['What do the bytes mean?', 'Signal decoding', 'READ, LibreCAN'],
    ['Who sent this message?', 'Sender fingerprinting', 'CIDS'],
    ['When is traffic abnormal?', 'Intrusion detection', 'Rule and ML detectors'],
    ['Why this attack, and can I check it?', 'Evidence-linked explanation', 'CANalyst'],
  ]
  text(s, 'QUESTION', X + 24, 152, 500, 24, 16, color.muted, true)
  text(s, 'APPROACH', 640, 152, 300, 24, 16, color.muted, true)
  text(s, 'EXAMPLES', 960, 152, 260, 24, 16, color.muted, true)
  rows.forEach(([q, kind, who], i) => {
    const y = 186 + i * 104
    const ours = i === 3
    anim(i + 1, ours ? 'grow' : 'drop')
    box(s, X, y, W, 88, ours ? color.tile : color.white, { line: ours ? color.purple : color.line, radius: 10 })
    if (ours) box(s, X, y, 8, 88, color.orange)
    text(s, q, X + 24, y + 26, 560, 40, 25, ours ? color.purple : color.dark, true)
    text(s, kind, 640, y + 28, 300, 36, 22, color.body)
    text(s, who, 960, y + 28, 250, 36, 22, ours ? color.purple : color.muted, ours)
  })
  anim(5, 'fade')
  caption(s, 'Every CANalyst claim must cite a measurement. A rule baseline sees the same evidence.', 620)
}

// 4. Timeline
{
  const { s } = await slide('Project timeline', 'Thirty seconds of context. September: proposal and an offline prototype with an evidence-linked interface. October: real HCRL and ROAD captures replaced synthetic data in the main evaluation. Midterm: GLM and a rule baseline explained the same 100 detected alerts. After the midterm we corrected the evidence: whole-alert counts, explicit missing values, and clearer attack definitions. November added detector reruns, a prompt change, six more vehicles, and two human raters per claim. Sources: docs/PROGRESS_2026-10-30.md; docs/midterm/paper/midterm.tex; backend/out/final_2026-11-23/model_results.json.')
  const steps = [
    ['SEP', 'Proposal and\nprototype', 'Offline analysis\nwith citations'],
    ['OCT', 'Real CAN\ncaptures', 'HCRL and ROAD\nreplace synthetic'],
    ['OCT 22', 'Midterm\ncomparison', 'GLM vs rules on\n100 alerts'],
    ['NOV', 'Corrected\nevidence', 'Whole-alert counts,\nclear definitions'],
    ['NOV', 'Expanded\nevaluation', '6 more vehicles,\n2 human raters'],
  ]
  const xs = steps.map((_, i) => 150 + i * 245)
  const y = 330
  anim(1, 'fade')
  box(s, xs[0], y - 2, xs[4] - xs[0], 4, color.lavender)
  anim(2, 'wipe')
  box(s, xs[0], y - 2, xs[3] - xs[0], 4, color.orange)
  steps.forEach(([month, head, body], i) => {
    anim(3 + i, 'drop')
    const r = i === 4 ? 17 : 12
    box(s, xs[i] - r, y - r, 2 * r, 2 * r, i === 4 ? color.white : color.orange, { geometry: 'ellipse', line: color.orange })
    text(s, month, xs[i] - 110, y - 70, 220, 28, 18, color.purple, true, { align: 'center', family: mono })
    text(s, head, xs[i] - 115, y + 40, 230, 72, 23, color.dark, true, { align: 'center' })
    text(s, body, xs[i] - 115, y + 120, 230, 64, 18, color.muted, false, { align: 'center' })
  })
  anim(8, 'rise')
  text(s, 'Today: 4 datasets, 6 vehicles, 2 human raters', X, 600, W, 40, 24, color.body)
}

// 5. Pipeline
{
  const { s } = await slide('How CANalyst works', 'Trace one alert left to right. Load a capture and a separate clean reference. Half-second windows advance every quarter second. The detector measures rates, timing, data-byte variation, and unknown or missing IDs, then merges flagged windows into alerts. Missed attacks never reach the explanation stage. For each alert we build an evidence packet: whole-alert counts plus a few sample frames, each with an evidence ID. Ground-truth labels and capture names stay out of the packet. A rule baseline or a language model returns a label, an explanation, and citations. The dashboard opens each citation so an analyst can check it. Vehicle function stays unknown without a verified signal map. Sources: app/loader.py, features.py, detector.py, evidence.py, llm.py, pipeline.py.')
  const steps = [
    ['Load', 'Capture plus a\nclean reference'],
    ['Detect', 'Flag abnormal\nhalf-second windows'],
    ['Package', 'Evidence packet\nwith evidence IDs'],
    ['Explain', 'Rules or LLM:\nlabel + citations'],
    ['Check', 'Open each citation\nin the dashboard'],
  ]
  steps.forEach(([head, body], i) => {
    anim(i + 1, 'drop')
    const x = X + i * 238
    const ours = i >= 2
    box(s, x, 200, 200, 200, ours ? color.tile : color.white, { line: ours ? color.purple : color.line, radius: 14 })
    text(s, String(i + 1).padStart(2, '0'), x + 22, 220, 60, 26, 18, color.orange, true, { family: mono })
    text(s, head, x + 22, 256, 170, 40, 30, color.dark, true)
    text(s, body, x + 22, 310, 170, 80, 20, color.body)
    if (i < 4) text(s, '→', x + 202, 278, 34, 40, 28, color.faint, false, { align: 'center' })
  })
  anim(6, 'wipe')
  box(s, X, 430, 438, 3, color.lavender)
  text(s, 'Detection', X, 444, 438, 30, 20, color.muted, true, { align: 'center' })
  box(s, X + 476, 430, 690, 3, color.orange)
  text(s, 'Explanation: what we evaluate', X + 476, 444, 690, 30, 20, color.purple, true, { align: 'center' })
  anim(7, 'rise')
  text(s, 'Labels and capture names never enter the packet. Detector misses never reach the explainer.', X, 560, W, 70, 24, color.body)
}

// 6. Full-bleed video
{
  const { s } = await slide('Experiment in motion', `Click to play the ${videoSeconds}-second animation. The bar at the top names each stage as it plays. Narrate in five beats. One: public captures and a clean reference. Two: windows feed the detector, and missed attacks stop here. Three: each alert becomes a blinded evidence packet. Four: the rule baseline and three models get the same packet. Five: saved replies are scored for labels and citations, and two people rated a sample of claims. This is a process animation, not a live attack or a real-time run. Source: tools/build_experiment_animation.swift.`, { keepTitle: false })
  await picture(s, 'experiment-flow.png', { left: 0, top: 0, width: 1280, height: 720 }, 'Experiment flow video')
}

// 7. Datasets
{
  const { s } = await slide('Four real-data test sets', 'HCRL provides frame injection flags. ROAD adds fabrication, fuzzing, and simulated masquerade, with interval metadata. Their detector protocol separates reference, tuning, and evaluation roles, though earlier development used these recordings. DTU can-train-and-test v2 adds four vehicles with a clean reference per vehicle. TU Eindhoven adds an Opel Astra and a Renault Clio; its attack traces are offline edits of one recorded drive per car. The final results today use recorded traffic and traces derived from it. The midterm also evaluated synthetic traffic. Three separate units: detector windows, explained alerts, and reviewed claims. Sources: app/datasets.py; backend/out/final_2026-11-23/model_results.json; docs/ADDITIONAL_DATASETS.md.')
  const sets = [
    ['HCRL Car-Hacking', '1 vehicle', 'Injection flags on each frame', 'Detection + explanation'],
    ['ORNL ROAD', '1 vehicle', 'Attack intervals and metadata', 'Detection + explanation'],
    ['DTU can-train-and-test', '4 vehicles', 'Attack flags, clean reference per car', 'Explanation transfer'],
    ['TU Eindhoven', '2 cars', 'Offline edits of one recorded drive', 'Explanation transfer'],
  ]
  sets.forEach(([name, cars, truth, use], i) => {
    anim(i + 1, 'drop')
    const x = X + (i % 2) * 593
    const y = 160 + Math.floor(i / 2) * 190
    box(s, x, y, 573, 170, color.white, { line: color.line, radius: 14 })
    text(s, name, x + 26, y + 22, 380, 36, 26, color.dark, true)
    text(s, cars, x + 400, y + 26, 150, 30, 20, color.orange, true, { align: 'right' })
    text(s, truth, x + 26, y + 72, 520, 30, 20, color.body)
    text(s, use, x + 26, y + 112, 520, 30, 20, color.purple, true)
  })
  anim(5, 'rise')
  text(s, 'We score three different things: detector windows, explained alerts, and reviewed claims.', X, 560, W, 40, 24, color.body)
}

// 8. ROAD detection with detector change
{
  const { s } = await slide('Detection on ROAD', 'Fresh merged-code run with one clean reference: 1,954 attack windows and 9,598 normal windows. Detector v1 is the live default. Detector v2 only lets three signals raise an alert: bus load, unknown IDs, and per-ID rate. The others stay as evidence. A timing guard also stops near-zero timing variation from producing extreme scores. On ROAD, false-positive windows fall from 1,461 to 50. Precision rises from 38.4 to 94.8 percent. Recall stays near 46.6 percent. Masquerade is the gap: forged traffic that imitates a real sender. V1 catches 4 of 971 masquerade windows and v2 catches 3. Cleaner alerts do not mean better coverage. Threshold 0.55, half-second windows, quarter-second stride. Sources: backend/out/final_2026-11-22/detection/results.json; verification.md; app/detector.py.')
  chart(s, ['Precision', 'Recall', 'False-positive rate'], [
    { name: 'Detector v1', values: ['precision','recall','fpr'].map(k => value(road,'rule@0.55',k)) },
    { name: 'Detector v2', values: ['precision','recall','fpr'].map(k => value(road,'rule_v2@0.55',k)) },
  ], { width: 720, height: 470 })
  anim(2, 'drop')
  stat(s, '1,461 → 50', 'false-alarm windows out of 9,598 normal', 820, 170, 400, color.purple, 50)
  anim(3, 'drop')
  stat(s, '3 / 971', 'masquerade windows caught by v2', 820, 340, 400, color.orange, 50, { count: true })
  anim(4, 'fade')
  text(s, 'V2 lets only bus load, unknown IDs, and per-ID rate raise alerts.', 820, 500, 400, 100, 20, color.body)
}

// 9. HCRL tradeoff
{
  const { s } = await slide('HCRL: fewer alarms cost recall', 'HCRL has 8,616 attack windows and 13,458 normal windows. V1 detects 8,450 attacks with one false-positive window. V2 detects 8,394 with zero. So v2 removes one false-positive window and misses 56 more spoofing windows at the fixed threshold. A simple baseline, unknown IDs plus message spacing, detects 8,581 attacks with 27 false positives and has the best F1 here, 0.996. That supports testing simple baselines before crediting a complex detector, and keeping v1 as the default. Full tables are in the appendix. Source: backend/out/final_2026-11-22/detection/results.json and verification.md.')
  anim(1, 'drop')
  box(s, X, 170, 560, 300, color.tile, { radius: 16 })
  stat(s, '−1', 'false-positive window\n(1 → 0 of 13,458 normal)', X + 36, 200, 500, color.purple, 120)
  anim(2, 'drop')
  box(s, X + 606, 170, 560, 300, color.tile, { radius: 16 })
  stat(s, '+56', 'missed spoofing windows\n(of 8,616 attack windows)', X + 642, 200, 500, color.orange, 120, { count: true, bg: color.tile })
  anim(3, 'rise')
  text(s, `Simple baseline (unknown IDs + message spacing): F1 ${value(hcrl,'whitelist_interval','f1').toFixed(3)}, best in this comparison.`, X, 530, W, 70, 26, color.body, true)
}

// 10. How explanations were scored
{
  const { s } = await slide('How we scored explanations', 'Clemson RCD hosts the models. Every system in a comparison gets the same alerts, boundaries, and evidence packet version. Labels and identifying filenames are hidden. Replies are saved before scoring, and invalid or failed replies stay in the denominator. We score three things. Is the attack label right? Does each cited evidence ID exist? And, for a sample, does the evidence actually support the sentence? That last check needs people. The rule baseline is deterministic and is not a language model. October and November are separate experiment families and are not pooled. Sources: scripts/score_explanations.py; app/llm.py; backend/out/final_2026-11-22/model_results.json.')
  anim(1, 'drop')
  box(s, X, 230, 290, 200, color.tile, { line: color.purple, radius: 14 })
  text(s, 'Same alert\nsame evidence', X + 24, 270, 250, 80, 28, color.dark, true)
  text(s, 'Labels and filenames hidden', X + 24, 370, 250, 40, 18, color.muted)
  anim(2, 'fade')
  text(s, '→', 360, 310, 50, 40, 30, color.faint, false, { align: 'center' })
  const arms = ['Rule baseline', 'GLM-5.3', 'Gemma 4 31B', 'Qwen 3.6 27B']
  arms.forEach((a, i) => {
    anim(3 + i, 'drop')
    text(s, a, 430, 196 + i * 66, 280, 36, 26, color.dark, true)
    box(s, 430, 244 + i * 66, 260, 1.5, color.line)
  })
  anim(7, 'fade')
  text(s, '→', 720, 310, 50, 40, 30, color.faint, false, { align: 'center' })
  const checks = [['Label', 'Is the attack type right?'], ['Citation', 'Does the evidence ID exist?'], ['Support', 'Do people agree it backs the claim?']]
  checks.forEach(([head, body], i) => {
    anim(8 + i, 'drop')
    const y = 190 + i * 96
    box(s, 780, y, 6, 70, i === 2 ? color.orange : color.purple)
    text(s, head, 802, y, 420, 34, 24, color.dark, true)
    text(s, body, 802, y + 36, 420, 30, 19, color.body)
  })
  anim(11, 'fade')
  caption(s, 'Failed or invalid replies stay in the denominator. Detector misses are outside this score.', 560)
}

// 11. Midterm to corrected
{
  const { s } = await slide('Midterm vs. corrected evidence', 'Same 100 alerts and boundaries: 69 HCRL attacks, 20 ROAD attacks, and 11 ROAD false alarms. At the midterm, GLM labeled 54 of 69 HCRL and 7 of 20 ROAD attacks, 61 of 89. The rule baseline scored 70 of 89. GLM called 10 of 13 ROAD fabrication alerts replay: it read an ambiguous rate-and-payload pattern as replay. After we rebuilt the packets, GLM and the rule baseline each score 86 of 89, and they mislabel the same three detected masquerade alerts. Qwen3-30B scores 38 of 89. On the 11 false alarms, the rule baseline calls 0 benign and GLM 1. Matching the rules is not beating them, and several things changed at once. Sources: docs/midterm/paper/midterm.tex; backend/out/final_2026-11-22/model_results.json, October paired v4.')
  anim(1, 'drop')
  text(s, 'MIDTERM', X, 160, 520, 28, 18, color.muted, true, { family: mono })
  stat(s, '61 / 89', 'GLM attack labels', X, 200, 520, color.faint, 76)
  stat(s, '70 / 89', 'Rule baseline', X, 360, 520, color.faint, 76)
  anim(2, 'fade')
  text(s, '→', 560, 300, 100, 80, 60, color.lavender, false, { align: 'center' })
  anim(3, 'drop')
  text(s, 'CORRECTED', 700, 160, 520, 28, 18, color.orange, true, { family: mono })
  stat(s, '86 / 89', 'GLM attack labels', 700, 200, 520, color.purple, 76, { count: true })
  stat(s, '86 / 89', 'Rule baseline', 700, 360, 520, color.purple, 76, { count: true })
  anim(4, 'fade')
  caption(s, 'Same 100 alerts. GLM now matches the rules. Both mislabel the same three masquerade alerts.', 600)
}

// 12. What we corrected
{
  const { s } = await slide('What we corrected', 'The first packet used representative-window counts where the model needed whole-alert scope. In one inspected case it showed 176 unknown-ID frames while the whole alert had 2,806. That likely explains part of the model error. We also changed the replay definition, ratio handling, missing values, control rules, and inference settings. Each improves the evidence, but the rerun is not a one-fix-at-a-time ablation, so we cannot credit the gain to one change. Sources: docs/PROGRESS_2026-10-30.md; app/evidence.py; app/llm.py; midterm.tex.')
  const fixes = [
    ['Measurement scope', '176 frames', '2,806 frames', 'Unknown-ID count: one window vs. the whole alert'],
    ['Replay definition', 'Repetition', 'Out-of-context sequence', 'Periodic traffic alone no longer means replay'],
    ['Missing values', 'Silent', 'Explicit "unknown"', 'Unavailable timing and baselines are labeled'],
  ]
  fixes.forEach(([head, before, after, why], i) => {
    const y = 165 + i * 128
    anim(1 + i * 2, 'drop')
    text(s, head, X, y + 4, 330, 36, 25, color.dark, true)
    text(s, why, X, y + 46, 330, 60, 17, color.muted)
    box(s, 420, y, 330, 96, color.white, { line: color.line, radius: 12 })
    text(s, before, 420, y + 30, 330, 40, 26, color.faint, true, { align: 'center' })
    anim(2 + i * 2, 'grow')
    text(s, '→', 760, y + 26, 60, 40, 30, color.faint, false, { align: 'center' })
    box(s, 830, y, 394, 96, color.tile, { line: color.purple, radius: 12 })
    text(s, after, 830, y + 30, 394, 40, 26, color.purple, true, { align: 'center' })
  })
  anim(7, 'fade')
  caption(s, 'All three changed together, so no single fix gets the credit.', 570)
}

// 13. November test sets
{
  const { s } = await slide('November: four separate test sets', 'Give the denominators, then the caveat. Later slices of HCRL and ROAD: 70 HCRL attacks and 7 ROAD false alarms, with zero ROAD attacks. These are later slices of recordings we used during development, not untouched data. The midterm replication reuses the original 89 attacks and 11 false alarms. DTU contributes 42 attacks; its detector emitted 154 false alarms, and we sampled 59, at most three per capture. TU Eindhoven contributes 44 attacks and no false alarms. Each row has its own packets. Do not pool them. All 42 selected DTU raw captures and 14 TU Eindhoven captures match their saved hashes. Sources: backend/out/final_2026-11-23/model_results.json and manifest audit.')
  table(s, [['Test set','Attack alerts','False alarms'],['Later slices of HCRL / ROAD','70 HCRL, 0 ROAD','7 ROAD'],['Same 100 midterm alerts','69 HCRL, 20 ROAD','11 ROAD'],['DTU (4 vehicles)','42','59 sampled of 154'],['TU Eindhoven (2 cars)','44','0']], [520,330,316.4], { height: 360, size: 25 })
  anim(2, 'fade')
  caption(s, 'Each row has its own fixed alert list. We never pool them into one score.', 580)
}

// 14. Prompt change
{
  const { s } = await slide('One instruction changed spoofing labels', 'We changed one instruction about bus flooding and kept the same 70 HCRL attack alerts. Gemma moves 69 to 70, GLM 59 to 70, and Qwen 37 to 69. All six runs already labeled all 17 flooding alerts correctly, so the gains are spoofing labels. Qwen also lost one fuzzing label. GLM failures across all 77 targets drop from five to one. The same-100 replication also improves HCRL, but Qwen loses one flooding and two fuzzing labels there. On DTU, Qwen falls from 34 to 32, so the change does not help everywhere. Source: backend/out/final_2026-11-23/model_results.json.')
  chart(s, ['Gemma 4 31B','GLM-5.3','Qwen 3.6 27B'], [{ name: 'Original instructions', values: [69,59,37], fill: color.lavender },{ name: 'Changed flooding instruction', values: [70,70,69], fill: color.purple }], { max: 75, format: '0', height: 400 })
  anim(2, 'fade')
  caption(s, 'Correct labels out of 70 HCRL attacks. All runs were already 17/17 on flooding. Qwen lost one fuzzing label.', 580)
}

// 15. Claims and citations
{
  const { s } = await slide('A valid citation can back a wrong claim', 'For one message ID, 0x000, the data bytes showed no variation across the alert. That is evidence E2. The model inferred that every byte was 0x00. Zero entropy says the bytes never changed. It cannot say what value they held. The citation is real, and the claim still goes too far. In an earlier purposive audit of 18 claims, all 18 citations resolved, 13 claims were supported, and 5 were not. A GLM summary also wrote 0x55 for ID 0x655. That is why we added human review. We have not measured analyst correctness or task time. Sources: backend/out/semantic_audit_2026-10-30/claims_v4_followup.json; docs/FINAL_RESULTS_2026-11-22.md.')
  anim(1, 'drop')
  box(s, X, 170, 500, 230, color.tile, { radius: 14 })
  text(s, 'EVIDENCE E2', X + 28, 196, 440, 26, 17, color.muted, true, { family: mono })
  text(s, 'ID 0x000\ndata-byte entropy = 0\nacross the whole alert', X + 28, 236, 450, 130, 25, color.dark, true, { family: mono })
  anim(2, 'drop')
  box(s, 724, 170, 500, 230, color.white, { line: color.orange, radius: 14 })
  text(s, 'MODEL CLAIM', 752, 196, 440, 26, 17, color.orange, true, { family: mono })
  text(s, '"Every data byte\nis 0x00."', 752, 236, 450, 130, 32, color.dark, true)
  anim(3, 'grow')
  text(s, '≠', 570, 240, 120, 90, 72, color.orange, true, { align: 'center' })
  anim(4, 'rise')
  text(s, 'Entropy says the bytes never changed. It cannot say what they were.', X, 440, W, 50, 26, color.purple, true)
  text(s, 'Earlier audit: 18 of 18 citations valid, but only 13 of 18 claims supported.', X, 510, W, 40, 22, color.body)
}

// 16. Human review
{
  const { s } = await slide('Human review', 'Two people rated all 40 blinded claims: a project author and an independent volunteer. They agreed on 32 of 40, 80 percent. Cohen kappa, agreement adjusted for chance, is 0.521. Among agreed claims, 26 are supported and 6 unsupported. Eight claims still need a final decision. Do not read 26 of 32 as a full-sample support rate. The sample has ten claims per system across 27 alerts. It excludes ROAD attacks, summaries, uncited claims, the new datasets, and the changed-instruction runs. Original rating files are unchanged. Sources: backend/out/claim_review/heldout/results.json; docs/HUMAN_REVIEW.md.')
  anim(1, 'drop')
  stat(s, '80%', 'agreement\n32 of 40 claims', X, 190, 360, color.purple, 110, { count: true })
  anim(2, 'drop')
  stat(s, '0.521', "Cohen's kappa\nagreement beyond chance", X + 400, 190, 360, color.purple, 110, { count: true })
  anim(3, 'drop')
  stat(s, '8', 'claims still need\na final decision', X + 800, 190, 360, color.orange, 110, { count: true })
  anim(4, 'rise')
  box(s, X, 470, W, 1.5, color.line)
  text(s, 'Of the 32 agreed claims: 26 supported, 6 unsupported. Not a full-sample rate.', X, 500, W, 40, 24, color.body)
}

// 17. Demo
{
  const { s } = await slide('Dashboard demo', 'Prewarm the ROAD capture before class and use the offline rule baseline. Fifteen seconds: name the capture and clean reference. Forty-five seconds: select the alert, read one measurement, and click its evidence citation. Separate measured facts from interpretation. The confidence shown is a rule score, not a probability. Thirty seconds: open Evaluation and the saved November results, and state the denominator: 70 HCRL attacks, 7 ROAD false alarms, zero ROAD attacks. Ten seconds: show the review entry point, then return. If the browser stalls, switch to these screenshots at the first stall. Do not run hosted inference live. Sources: output/presentation/assets/road-dashboard.png; docs/FINAL_PRESENTATION_GUIDE.md.')
  text(s, 'Detected interval', X, 150, 550, 40, 24, color.purple, true)
  text(s, 'Explanation and citation', 674, 150, 550, 40, 24, color.purple, true)
  await picture(s, 'road-dashboard.png', { left: X, top: 200, width: 576, height: 245 }, 'ROAD timeline', { left: 338/1440, top: 424/2372, right: 20/1440, bottom: 1488/2372 })
  await picture(s, 'road-dashboard.png', { left: 674, top: 200, width: 550, height: 288 }, 'ROAD alert explanation and evidence citation', { left: 730/1440, top: 930/2372, right: 20/1440, bottom: 1084/2372 })
  caption(s, 'ROAD capture correlated_signal_attack_3.log, offline rule baseline. Confidence is a rule score, not a probability.', 560)
}

// 18. Additional vehicles
{
  const { s } = await slide('Results on six more vehicles', 'DTU uses four vehicles with a clean reference per vehicle. Its 42 attack alerts are 14 flooding, 15 fuzzing, and 13 spoofing. The rule baseline scores 29 of 42. The changed instruction moves Gemma from 23 to 24, leaves GLM at 31, and lowers Qwen from 34 to 32. TU Eindhoven has two cars and 44 attack alerts: 2 flooding, 40 fuzzing or diagnostic, and 2 replay. Every system gets only the two flooding alerts right, with either prompt. One GLM reply is missing in the changed-prompt run, so it is scored 2 of 44 with 43 replies. Payload-fuzzing captures produced no alerts, so those misses are not in the table. Labels do not transfer well to new vehicles. Sources: backend/out/final_2026-11-23/model_results.json; DTU and TU Eindhoven manifests.')
  text(s, 'DTU: correct labels of 42', X, 150, 700, 34, 22, color.dark, true)
  chart(s, ['Gemma 4 31B','GLM-5.3','Qwen 3.6 27B'], [{ name: 'Original instructions', values: [23,31,34], fill: color.lavender },{ name: 'Changed flooding instruction', values: [24,31,32], fill: color.purple }], { max: 42, format: '0', y: 190, width: 700, height: 380 })
  anim(2, 'fade')
  text(s, 'Rule baseline: 29 / 42', X, 590, 700, 34, 22, color.body, true)
  anim(3, 'drop')
  box(s, 800, 170, 424, 400, color.tile, { radius: 16 })
  text(s, 'TU EINDHOVEN', 836, 200, 360, 26, 17, color.muted, true, { family: mono })
  stat(s, '2 / 44', 'for every system,\nwith either prompt', 836, 240, 360, color.orange, 88, { count: true, bg: color.tile })
  anim(4, 'fade')
  text(s, 'Only the two flooding alerts are right. All 40 fuzzing and 2 replay labels miss.', 836, 440, 360, 110, 19, color.body)
}

// 19. What we learned
{
  const { s } = await slide('What we learned', 'Answer the opening question. Partly. CANalyst makes model explanations checkable: every claim cites a measurement, and we can score labels and citations. Checking also shows the limits. Corrected GLM matched the rule baseline on the October alerts but did not beat it. Labels transfer poorly to new vehicles, with 2 of 44 on TU Eindhoven. A real citation can still back an unsupported claim. Detection is a ceiling: masquerade stays mostly undetected. Next: resolve the eight open ratings, and run a timed study to see whether analysts are faster or more accurate with CANalyst on new recordings. One archived DTU freeze-script hash has no reachable source revision, so we keep those outputs and disclose that limit. Sources: final model summary, adapter audit, human review.')
  anim(1, 'drop')
  text(s, 'Model explanations can be checked. Checking shows they match rules, not beat them.', X, 160, W, 100, 34, color.purple, true)
  const findings = [
    ['86 / 89', 'Corrected GLM ties the rule baseline on October alerts.'],
    ['2 / 44', 'Labels do not transfer to new vehicles (TU Eindhoven).'],
    ['13 / 18', 'Valid citations, but not every claim is supported.'],
    ['3 / 971', 'Masquerade mostly undetected, so never explained.'],
  ]
  findings.forEach(([n, body], i) => {
    anim(2 + i, 'drop')
    const y = 290 + i * 66
    text(s, n, X, y, 190, 44, 30, i === 0 ? color.purple : color.orange, true, { family: mono })
    text(s, body, X + 210, y + 4, 950, 44, 24, color.body)
  })
  anim(6, 'rise')
  text(s, 'Next: a timed analyst study on new recordings.', X, 580, W, 40, 24, color.dark, true)
}

// 20. Questions
{
  const { elements } = await slide('Questions', 'Close the 20-minute talk, then take three minutes of questions. The appendix covers detector metrics, data reuse, model latency, and review scope. CANalyst is a local research prototype. No live-vehicle deployment or analyst benefit has been established.', { base: 15 })
  replace(elements[0], 'Thank you')
  replace(elements[1], 'Questions?')
}

async function fullDetector(name, rows) {
  const labels = { 'rule@0.55':'Detector v1', 'rule_v2@0.55':'Detector v2', 'rule@tuned':'Detector v1, tuned', id_whitelist:'Unknown-ID check', interval:'Message spacing', whitelist_interval:'Unknown ID + spacing', id_entropy:'ID entropy', iforest:'IsolationForest', ocsvm:'One-class SVM' }
  const { s } = await slide(`Appendix: ${name} detector results`, `Single-reference results from ${source}. Evaluation windows overlap. The benchmark reports 20-window block bootstrap intervals with 2,000 draws. Tuned thresholds target at most 1% false positives on clean tuning windows. These tables show point estimates. Undefined precision appears as n/a. Precision shows two decimals so a single false positive stays visible. Cross-dataset rankings do not establish universal superiority.`)
  table(s, [['Method','Precision','Recall','F1','FPR'],...Object.entries(labels).map(([key,label]) => [label,pct(value(rows,key,'precision'),2),pct(value(rows,key,'recall')),value(rows,key,'f1')?.toFixed(3) ?? 'n/a',pct(value(rows,key,'fpr'))])], [390,194,194,194,194.4], { y: 150, height: 470, size: 22 })
}
await fullDetector('ROAD', road)
await fullDetector('HCRL', hcrl)
{
  const { s } = await slide('Appendix: data provenance', 'ROAD groups fabrication and masquerade twins. HCRL assigns reference, tuning, and evaluation to disjoint time slices. Earlier development touched all four HCRL attack recordings and all 25 ROAD evaluation capture sources. October and November midterm100 share 100 targets with different packets. All 42 selected DTU source hashes and all 14 TU Eindhoven hashes match the raw downloads. No whole-file duplicates occur within either selected manifest. Matching hashes do not establish independence of trips. The archived DTU freeze-script hash does not match reachable source history. Preserve those historical targets and disclose the limitation. Sources: app/datasets.py; backend/out/final_2026-11-23/model_results.json; adapter audit.')
  table(s, [['Comparison','Separation','Limit'],['ROAD / HCRL','Capture groups or time slices','Evaluation sources used earlier'],['October / November','Versioned packets and prompts','100 midterm targets overlap'],['DTU (4 vehicles)','Clean reference per vehicle','Known-vehicle calibration'],['TU Eindhoven (2 cars)','Reference and testing slices','Attack edits share a testing session']], [310,390,466.4], { height: 420, size: 24 })
}
{
  const { s } = await slide('Appendix: models and latency', 'The October corrected run uses evidence-v4, control-v5, and hosted prompt can-evidence-v3. GLM-5.3 and Qwen3-30B-A3B Instruct FP8 each complete all 100 requests without fallback. Median latency is 6.331 seconds on HCRL and 6.599 on ROAD for GLM, and 4.272 and 4.192 for Qwen. The original midterm GLM medians were 24 and 33 seconds, with a maximum of 825 seconds. Multiple settings changed, so those latency differences are observational. November uses historical prompt v2 and v2-dosv1 with Gemma 4-31B, GLM-5.3, and Qwen3.6-27B FP8. Source: model_results.json and midterm.tex.')
  table(s, [['October system','HCRL median','ROAD median','Replies'],['GLM-5.3','6.331 s','6.599 s','100 / 100'],['Qwen3-30B-A3B FP8','4.272 s','4.192 s','100 / 100']], [440,240,240,246.4], { height: 285, size: 26 })
  caption(s, 'November models and prompts belong to a separate experiment family.', 500)
}
{
  const { s } = await slide('Appendix: human-review coverage', 'Rater A labels 33 supported, six unsupported, and one contradicted. Rater B labels 26 supported, 12 unsupported, and two contradicted. They agree on 32 of 40, with kappa 0.521. Agreed-only counts appear here and must not be presented as full ten-claim rates. Eight disagreements remain: C001, C005, C007, C013, C024, C031, C032, and C035. Preserve original ratings and record human adjudication separately. Each system contributes three flooding, three fuzzing, two spoofing, and two ROAD false-alarm claims. Sources: backend/out/claim_review/heldout/results.json and original CSVs.')
  table(s, [['System','Supported','Unsupported','Agreed / sampled'],['Rule baseline','6','2','8 / 10'],['Gemma 4 31B','9','0','9 / 10'],['GLM-5.3','4','3','7 / 10'],['Qwen 3.6 27B','7','1','8 / 10']], [440,220,220,286.4], { height: 365, size: 25 })
  caption(s, '40 claims across 27 alerts. Agreed claims only. Excludes summaries, uncited claims, and new datasets.', 580)
}
{
  const { s } = await slide('Appendix: references', 'Datasets: HCRL Car-Hacking, https://ocslab.hksecurity.net/Datasets/CAN-intrusion-dataset. ORNL ROAD, https://zenodo.org/records/10462796 and https://arxiv.org/abs/2012.14600. DTU can-train-and-test v2, https://doi.org/10.11583/DTU.24805533.v2. TU Eindhoven CAN v2, https://data.4tu.nl/datasets/efb320d8-c189-4e54-98af-3a79cc14f421/2. Related work: READ, https://doi.org/10.1109/TIFS.2018.2870826. LibreCAN, https://mpese.com/publication/pese-2019-librecan/ACM_CCS_LibreCAN_Paper.pdf. CIDS, https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho. CAN-D, https://arxiv.org/abs/2006.05993. Project: backend/out/final_2026-11-22/detection/results.json; backend/out/final_2026-11-23/model_results.json; docs/FINAL_RESULTS_2026-11-23.md. Original history: docs/midterm/paper/midterm.tex. Dataset archives and hashes: docs/ADDITIONAL_DATASETS.md.')
  const refs = [['Datasets', 'HCRL Car-Hacking, ORNL ROAD\nDTU can-train-and-test, TU Eindhoven CAN'], ['Related work', 'READ, LibreCAN, CIDS, CAN-D'], ['Project evidence', 'Frozen inputs, raw replies, manifests,\nscoring scripts, and source hashes']]
  refs.forEach(([head, body], i) => {
    text(s, head, X, 170 + i * 140, 300, 40, 26, color.purple, true)
    text(s, body, 390, 170 + i * 140, 834, 100, 26)
  })
  caption(s, 'Full links and per-slide sources are in the speaker notes.', 620)
}

if (slides.length !== 26 || seconds.reduce((a,b) => a+b,0) !== 1170) throw new Error('Slide count or timing changed unexpectedly.')
await fs.writeFile(path.join(build,'slide-content.json'), JSON.stringify(slides,null,2))
const candidatePath = path.join(build,'candidate-clemson.pptx')
await (await PresentationFile.exportPptx(presentation)).save(candidatePath)
const previewDir = path.join(build,'preview')
await fs.rm(previewDir,{ recursive:true, force:true })
await fs.mkdir(previewDir,{ recursive:true })
for (const [index,s] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide:s,format:'png',scale:1 })
  await fs.writeFile(path.join(previewDir,`slide-${String(index+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()))
}
console.log(JSON.stringify({ candidatePath, previewDir, slides: slides.length, tables:tableOwners, charts:chartOwners }))
if (process.argv.includes('--final')) {
  const withBuilds = path.join(build,'candidate-clemson-builds.pptx')
  execFileSync(python,[path.join(root,'tools/add_slide_animations.py'),candidatePath,withBuilds])
  const withVideo = path.join(build,'candidate-clemson-video.pptx')
  execFileSync(python,[path.join(root,'tools/embed_experiment_video.py'),withBuilds,withVideo,template,path.join(output,'assets/experiment-flow.mp4'),String(videoSlide),'--duration-ms',String(videoSeconds * 1000)])
  const result = await finalizePresentation({ workspaceDir:root,candidatePath:withVideo,finalPath:path.join(output,outputName),explicitTotalSlideCount:26,
    requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:chartOwners,materializeLiteralChartWorkbooks:true,
    fontPolicy:{basis:'user_request',families:[font,mono]},
    pythonExecutable:python,
    integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
    layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableOwners.flatMap(i=>['--require-native-table-slide',String(i)])],
    verifyArtifactToolImport:true,receiptPath:path.join(build,`${outputName}.validation.json`) })
  console.log(JSON.stringify(result))
}
