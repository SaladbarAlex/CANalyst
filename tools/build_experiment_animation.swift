import AppKit
import AVFoundation
import CoreText

let width = 1920
let height = 1080
let frameRate: Int32 = 30
let sectionSeconds: CGFloat = 8.4
let outroSeconds: CGFloat = 3
let totalSeconds = 5 * sectionSeconds + outroSeconds
let W = CGFloat(width)

let white = CGColor(gray: 1, alpha: 1)
let orange = color(0xF56600)
let purple = color(0x522D80)
let ink = color(0x2E1A47)
let body = color(0x3D3546)
let muted = color(0x7A7184)
let faint = color(0xA8A0B3)
let lavender = color(0xD9D0E6)
let tile = color(0xF7F5F9)
let line = color(0xE7E3EC)
let paleOrange = color(0xFFF1E5)
let regular = "AvenirNext-Regular" as CFString
let demi = "AvenirNext-DemiBold" as CFString
let monoFont = "Menlo-Regular" as CFString
let monoBold = "Menlo-Bold" as CFString

// Stage name, heading, narration line.
let sections = [
    ("Data", "Public CAN captures", "Recorded traffic splits into a clean reference and an evaluation capture."),
    ("Detect", "Flag abnormal windows", "Windows that differ from the reference merge into an alert. Missed attacks stop here."),
    ("Package", "Build a blinded evidence packet", "Each alert becomes measurements with evidence IDs. Labels stay with the scorer."),
    ("Explain", "Same packet, four explainers", "The rule baseline and three hosted models get identical evidence."),
    ("Score", "Check labels, citations, and claims", "Two people rated 40 claims: 32 agree, 8 still need a final decision.")
]

func color(_ hex: UInt32) -> CGColor {
    CGColor(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: 1)
}

func clamp(_ v: CGFloat) -> CGFloat { min(max(v, 0), 1) }
func easeOut(_ v: CGFloat) -> CGFloat { 1 - pow(1 - clamp(v), 3) }
func easeInOut(_ v: CGFloat) -> CGFloat {
    let x = clamp(v)
    return x < 0.5 ? 4 * x * x * x : 1 - pow(-2 * x + 2, 3) / 2
}
// Overshoot for pop-in elements.
func pop(_ v: CGFloat) -> CGFloat {
    let x = clamp(v)
    let c: CGFloat = 1.70158
    return 1 + (c + 1) * pow(x - 1, 3) + c * pow(x - 1, 2)
}
func progress(_ t: CGFloat, _ start: CGFloat, _ duration: CGFloat) -> CGFloat { clamp((t - start) / duration) }
func mix(_ a: CGFloat, _ b: CGFloat, _ p: CGFloat) -> CGFloat { a + (b - a) * p }

// Top-left origin drawing helpers. The context is flipped once in draw().
struct Canvas {
    let context: CGContext

    func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ fill: CGColor, outline: CGColor? = nil, radius: CGFloat = 0, lineWidth: CGFloat = 2) {
        let path = CGPath(roundedRect: CGRect(x: x, y: y, width: w, height: h), cornerWidth: min(radius, w / 2, h / 2), cornerHeight: min(radius, w / 2, h / 2), transform: nil)
        context.addPath(path)
        context.setFillColor(fill)
        guard let outline else { return context.fillPath() }
        context.setStrokeColor(outline)
        context.setLineWidth(lineWidth)
        context.drawPath(using: .fillStroke)
    }

    func measure(_ value: String, _ size: CGFloat, font: CFString) -> CGFloat {
        let line = CTLineCreateWithAttributedString(attributed(value, size, white, font))
        return CGFloat(CTLineGetTypographicBounds(line, nil, nil, nil))
    }

    func attributed(_ value: String, _ size: CGFloat, _ fill: CGColor, _ font: CFString) -> NSAttributedString {
        NSAttributedString(string: value, attributes: [
            NSAttributedString.Key(rawValue: kCTFontAttributeName as String): CTFontCreateWithName(font, size, nil),
            NSAttributedString.Key(rawValue: kCTForegroundColorAttributeName as String): fill
        ])
    }

    func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ fill: CGColor = ink, font: CFString = regular, center: Bool = false) {
        let ctFont = CTFontCreateWithName(font, size, nil)
        let offset = center ? measure(value, size, font: font) / 2 : 0
        context.textMatrix = CGAffineTransform(scaleX: 1, y: -1)
        context.textPosition = CGPoint(x: x - offset, y: y + CTFontGetAscent(ctFont))
        CTLineDraw(CTLineCreateWithAttributedString(attributed(value, size, fill, font)), context)
    }

    func path(_ points: [CGPoint], _ stroke: CGColor, width: CGFloat = 4, dashed: Bool = false) {
        context.saveGState()
        context.setStrokeColor(stroke)
        context.setLineWidth(width)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        if dashed { context.setLineDash(phase: 0, lengths: [10, 12]) }
        context.addLines(between: points)
        context.strokePath()
        context.restoreGState()
    }

    func circle(_ x: CGFloat, _ y: CGFloat, _ r: CGFloat, _ fill: CGColor) {
        context.setFillColor(fill)
        context.fillEllipse(in: CGRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r))
    }

    func check(_ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ fill: CGColor) {
        circle(x, y, size, fill)
        path([CGPoint(x: x - size * 0.42, y: y + size * 0.02), CGPoint(x: x - size * 0.1, y: y + size * 0.34), CGPoint(x: x + size * 0.45, y: y - size * 0.3)], white, width: size * 0.18)
    }

    // Draws content scaled and faded around its center.
    func group(alpha: CGFloat, scale: CGFloat = 1, center: CGPoint = .zero, dx: CGFloat = 0, dy: CGFloat = 0, _ content: () -> Void) {
        guard alpha > 0.001 else { return }
        context.saveGState()
        context.setAlpha(alpha)
        context.translateBy(x: center.x + dx, y: center.y + dy)
        context.scaleBy(x: scale, y: scale)
        context.translateBy(x: -center.x, y: -center.y)
        content()
        context.restoreGState()
    }

    // Pops an element in at a start time with a slight overshoot.
    func popIn(_ t: CGFloat, at start: CGFloat, center: CGPoint, _ content: () -> Void) {
        let p = progress(t, start, 0.45)
        group(alpha: easeOut(p * 1.6), scale: mix(0.6, 1, pop(p)), center: center, content)
    }

    func card(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ title: String, _ detail: String? = nil, highlighted: Bool = false, accent: CGColor = purple) {
        box(x, y, w, h, highlighted ? tile : white, outline: highlighted ? accent : line, radius: 16)
        box(x, y + 18, 7, h - 36, accent, radius: 3)
        let titleY = detail == nil ? y + h / 2 - 22 : y + h / 2 - 42
        text(title, x + 34, titleY, 36, ink, font: demi)
        if let detail { text(detail, x + 34, titleY + 50, 26, muted) }
    }

    // A small packet travelling along a polyline.
    func traveller(_ points: [CGPoint], _ p: CGFloat, fill: CGColor = orange) {
        guard p > 0 && p < 1 else { return }
        let segments = zip(points, points.dropFirst()).map { ($0, $1, hypot($1.x - $0.x, $1.y - $0.y)) }
        var remaining = segments.reduce(0) { $0 + $1.2 } * easeInOut(p)
        for (a, b, d) in segments {
            if remaining <= d && d > 0 {
                let q = remaining / d
                box(mix(a.x, b.x, q) - 16, mix(a.y, b.y, q) - 11, 32, 22, fill, radius: 6)
                return
            }
            remaining -= d
        }
    }
}

func draw(_ context: CGContext, at second: CGFloat) {
    context.translateBy(x: 0, y: CGFloat(height))
    context.scaleBy(x: 1, y: -1)
    let c = Canvas(context: context)
    c.box(0, 0, W, CGFloat(height), white)

    let outro = second >= 5 * sectionSeconds
    let index = min(Int(second / sectionSeconds), 4)
    let t = second - CGFloat(index) * sectionSeconds
    drawStepper(c, index: index, t: t, outro: outro)
    if outro { return drawOutro(c, t: second - 5 * sectionSeconds) }

    // Slide-and-fade between stages.
    let enter = easeOut(progress(t, 0, 0.6))
    let exit = easeInOut(progress(t, sectionSeconds - 0.45, 0.45))
    c.group(alpha: enter * (1 - exit), dx: (1 - enter) * 140 - exit * 140) {
        c.text("STEP \(index + 1)", 120, 150, 26, orange, font: monoBold)
        c.text(sections[index].1, 120, 186, 64, ink, font: demi)
        switch index {
        case 0: drawData(c, t)
        case 1: drawDetect(c, t)
        case 2: drawPackage(c, t)
        case 3: drawExplain(c, t)
        default: drawScore(c, t)
        }
        let captionIn = easeOut(progress(t, 0.8, 0.5))
        c.group(alpha: captionIn, dy: (1 - captionIn) * 20) {
            c.box(120, 960, 1680, 76, tile, radius: 10)
            c.box(120, 960, 7, 76, orange, radius: 3)
            c.text(sections[index].2, 150, 980, 30, body)
        }
    }
}

func drawStepper(_ c: Canvas, index: Int, t: CGFloat, outro: Bool) {
    for i in 0..<5 {
        let x = 120 + CGFloat(i) * 340
        let active = i == index && !outro
        let done = i < index || outro
        c.box(x, 84, 320, 8, lavender, radius: 4)
        if done { c.box(x, 84, 320, 8, purple, radius: 4) }
        if active { c.box(x, 84, max(8, 320 * clamp(t / sectionSeconds)), 8, orange, radius: 4) }
        let label = "\(i + 1)  \(sections[i].0)"
        c.text(label, x, 36, 28, active ? ink : (done ? purple : faint), font: active || done ? demi : regular)
    }
}

func drawData(_ c: Canvas, _ t: CGFloat) {
    c.popIn(t, at: 0.6, center: CGPoint(x: 310, y: 385)) { c.card(120, 330, 380, 110, "HCRL") }
    c.popIn(t, at: 0.9, center: CGPoint(x: 310, y: 545)) { c.card(120, 490, 380, 110, "ROAD") }
    c.path([CGPoint(x: 500, y: 385), CGPoint(x: 600, y: 470)], lavender)
    c.path([CGPoint(x: 500, y: 545), CGPoint(x: 600, y: 500)], lavender)

    // Scrolling CAN log.
    let panelIn = easeOut(progress(t, 1.1, 0.5))
    c.group(alpha: panelIn) {
        c.box(600, 300, 600, 520, tile, radius: 18)
        c.text("TIME      ID     DATA BYTES", 630, 322, 22, muted, font: monoBold)
        c.context.saveGState()
        c.context.clip(to: CGRect(x: 600, y: 360, width: 600, height: 445))
        let ids = ["0x316", "0x2A0", "0x18F", "0x43F", "0x316", "0x260", "0x545", "0x316"]
        let scroll = max(0, t - 1.2) * 58
        for row in 0..<30 {
            let y = 370 + CGFloat(row) * 40 - scroll.truncatingRemainder(dividingBy: 40) - 40 * 0
            let n = row + Int(scroll / 40)
            let id = ids[n % ids.count]
            let bytes = (0..<8).map { String(format: "%02X", (n * 37 + $0 * 53 + 11) % 256) }.joined(separator: " ")
            let time = String(format: "%7.4f", 12.4 + Double(n) * 0.0004)
            c.text("\(time)  \(id)  \(bytes)", 630, y, 22, n % 7 == 3 ? orange : body, font: monoFont)
        }
        c.context.restoreGState()
    }

    c.popIn(t, at: 3.0, center: CGPoint(x: 1560, y: 395)) { c.card(1330, 330, 460, 130, "Clean reference", "Normal traffic only", highlighted: true) }
    c.popIn(t, at: 3.5, center: CGPoint(x: 1560, y: 625)) { c.card(1330, 560, 460, 130, "Evaluation capture", "Normal and attack traffic", highlighted: true, accent: orange) }
    let top = [CGPoint(x: 1200, y: 520), CGPoint(x: 1265, y: 520), CGPoint(x: 1265, y: 395), CGPoint(x: 1330, y: 395)]
    let bottom = [CGPoint(x: 1200, y: 600), CGPoint(x: 1265, y: 600), CGPoint(x: 1265, y: 625), CGPoint(x: 1330, y: 625)]
    c.group(alpha: easeOut(progress(t, 3.0, 0.4))) {
        c.path(top, lavender)
        c.path(bottom, lavender)
    }
    for k in 0..<6 {
        let start = 3.9 + CGFloat(k) * 0.65
        c.traveller(top, progress(t, start, 1.0), fill: purple)
        c.traveller(bottom, progress(t, start + 0.3, 1.0))
    }
}

let barHeights: [CGFloat] = (0..<40).map { i in
    let base: CGFloat = 120 + CGFloat((i * 47) % 50)
    return (17...24).contains(i) ? base + 170 + CGFloat((i * 13) % 40) : base
}

func drawDetect(_ c: Canvas, _ t: CGFloat) {
    let left: CGFloat = 120, baseline: CGFloat = 760, step: CGFloat = 34
    c.text("Messages per window", left, 340, 26, muted, font: demi)
    c.text("0.5 s windows  ·  0.25 s stride", left, 790, 24, muted)
    let sweep = easeInOut(progress(t, 1.9, 4.0)) * 40
    for i in 0..<40 {
        let grow = easeOut(progress(t, 0.5 + CGFloat(i) * 0.03, 0.5))
        let h = barHeights[i] * grow
        let flagged = (17...24).contains(i) && CGFloat(i) < sweep
        let missed = (31...34).contains(i)
        c.box(left + CGFloat(i) * step, baseline - h, step - 10, h, flagged ? orange : (missed && t > 6.2 ? faint : purple), radius: 5)
    }
    // Sliding window bracket.
    if t > 1.8 && t < 6.2 {
        let x = left + min(sweep, 38) * step - 6
        c.box(x, 400, 2 * step + 2, 380, CGColor(gray: 0, alpha: 0), outline: orange, radius: 8, lineWidth: 4)
    }
    // Missed attack region.
    let missIn = easeOut(progress(t, 6.1, 0.5))
    c.group(alpha: missIn) {
        c.box(left + 31 * step - 8, 560, 4 * step + 6, 214, CGColor(gray: 0, alpha: 0), outline: muted, radius: 8, lineWidth: 3)
        c.text("Missed attack", left + 31 * step - 6, 515, 24, muted, font: demi)
        c.text("stops here", left + 31 * step - 6, 820, 24, muted)
    }
    // Merge flagged windows into an alert.
    let mergeIn = easeOut(progress(t, 5.6, 0.5))
    c.group(alpha: mergeIn) {
        c.path([CGPoint(x: left + 17 * step, y: 830), CGPoint(x: left + 17 * step, y: 845), CGPoint(x: left + 25 * step - 10, y: 845), CGPoint(x: left + 25 * step - 10, y: 830)], orange, width: 4)
    }
    c.popIn(t, at: 6.3, center: CGPoint(x: 1660, y: 470)) {
        c.card(1520, 400, 280, 140, "Alert", "8 windows merged", highlighted: true, accent: orange)
    }
}

func drawPackage(_ c: Canvas, _ t: CGFloat) {
    let slide = easeInOut(progress(t, 0.4, 0.8))
    c.group(alpha: 1, dx: mix(-60, 0, slide)) {
        c.card(120, 420, 360, 140, "Alert", "from the detector", highlighted: true, accent: orange)
    }
    c.path([CGPoint(x: 480, y: 490), CGPoint(x: 640, y: 490)], lavender)
    c.traveller([CGPoint(x: 480, y: 490), CGPoint(x: 640, y: 490)], progress(t, 0.9, 0.7))

    let packetIn = easeOut(progress(t, 0.8, 0.5))
    c.group(alpha: packetIn, scale: mix(0.92, 1, packetIn), center: CGPoint(x: 940, y: 560)) {
        c.box(640, 290, 600, 540, tile, outline: purple, radius: 20)
        c.text("Evidence packet", 680, 316, 36, ink, font: demi)
    }
    let items = [("E1", "Message rate vs. reference"), ("E2", "Data-byte variation"), ("E3", "Unknown or missing IDs"), ("E4", "Time between messages"), ("E5", "Sample frames")]
    for (i, item) in items.enumerated() {
        let y = 390 + CGFloat(i) * 84
        c.popIn(t, at: 1.4 + CGFloat(i) * 0.45, center: CGPoint(x: 940, y: y + 30)) {
            c.box(680, y, 520, 64, white, outline: line, radius: 12)
            c.text(item.0, 704, y + 15, 28, orange, font: monoBold)
            c.text(item.1, 780, y + 15, 28, body)
        }
    }
    // Ground-truth label diverts to the scorer.
    let drop = easeInOut(progress(t, 5.0, 1.2))
    c.popIn(t, at: 4.0, center: CGPoint(x: 1560, y: 380)) {
        c.box(1420, mix(330, 650, drop), 300, 90, paleOrange, outline: orange, radius: 14)
        c.text("Ground-truth label", 1570, mix(358, 678, drop), 28, ink, font: demi, center: true)
    }
    c.group(alpha: easeOut(progress(t, 4.4, 0.5))) {
        c.path([CGPoint(x: 1300, y: 290), CGPoint(x: 1300, y: 830)], faint, width: 3, dashed: true)
        c.box(1400, 620, 340, 210, CGColor(gray: 0, alpha: 0), outline: faint, radius: 18, lineWidth: 3)
        c.text("Scorer only", 1570, 770, 28, muted, font: demi, center: true)
    }
}

let arms = ["Rule baseline", "GLM-5.3", "Gemma 4 31B", "Qwen 3.6 27B"]

func drawExplain(_ c: Canvas, _ t: CGFloat) {
    c.card(120, 450, 400, 150, "Evidence packet", "E1 to E5", highlighted: true)
    for (i, arm) in arms.enumerated() {
        let y = 290 + CGFloat(i) * 150
        let route = [CGPoint(x: 520, y: 525), CGPoint(x: 700, y: 525), CGPoint(x: 700, y: y + 55), CGPoint(x: 880, y: y + 55)]
        c.group(alpha: easeOut(progress(t, 0.6 + CGFloat(i) * 0.15, 0.4))) { c.path(route, lavender) }
        c.popIn(t, at: 0.7 + CGFloat(i) * 0.2, center: CGPoint(x: 1080, y: y + 55)) {
            c.card(880, y, 400, 110, arm, accent: i == 0 ? muted : purple)
        }
        c.traveller(route, progress(t, 1.9 + CGFloat(i) * 0.25, 1.1))
        c.group(alpha: easeOut(progress(t, 3.6 + CGFloat(i) * 0.35, 0.4))) {
            c.path([CGPoint(x: 1280, y: y + 55), CGPoint(x: 1380, y: y + 55)], lavender)
        }
        c.popIn(t, at: 3.8 + CGFloat(i) * 0.35, center: CGPoint(x: 1600, y: y + 55)) {
            c.box(1380, y + 10, 420, 90, white, outline: line, radius: 14)
            c.text("label", 1404, y + 36, 24, muted)
            c.text(i == 3 ? "replay" : "spoofing", 1474, y + 32, 30, ink, font: demi)
            c.box(1640, y + 34, 64, 40, tile, radius: 8)
            c.text("E1", 1672, y + 40, 22, orange, font: monoBold, center: true)
            c.box(1712, y + 34, 64, 40, tile, radius: 8)
            c.text("E2", 1744, y + 40, 22, orange, font: monoBold, center: true)
        }
    }
}

func drawScore(_ c: Canvas, _ t: CGFloat) {
    for (i, arm) in arms.enumerated() {
        let y = 300 + CGFloat(i) * 130
        c.popIn(t, at: 0.4 + CGFloat(i) * 0.12, center: CGPoint(x: 330, y: y + 50)) {
            c.box(120, y, 420, 100, white, outline: line, radius: 14)
            c.text(arm, 148, y + 30, 30, ink, font: demi)
        }
    }
    let checks = [("Label", "Matches the ground truth?"), ("Citation", "Does each evidence ID exist?"), ("Human review", "Does the evidence support the claim?")]
    for (i, check) in checks.enumerated() {
        let y = 290 + CGFloat(i) * 200
        let start = 1.0 + CGFloat(i) * 1.3
        c.group(alpha: easeOut(progress(t, start - 0.4, 0.4))) {
            c.path([CGPoint(x: 540, y: 520), CGPoint(x: 680, y: 520), CGPoint(x: 680, y: y + 80), CGPoint(x: 780, y: y + 80)], lavender)
        }
        for k in 0..<2 { c.traveller([CGPoint(x: 540, y: 520), CGPoint(x: 680, y: 520), CGPoint(x: 680, y: y + 80), CGPoint(x: 780, y: y + 80)], progress(t, start - 0.3 + CGFloat(k) * 0.35, 0.8), fill: purple) }
        c.popIn(t, at: start, center: CGPoint(x: 1280, y: y + 80)) {
            c.box(780, y, 1020, 160, i == 2 ? tile : white, outline: i == 2 ? purple : line, radius: 18)
            c.text(check.0, 820, y + 32, 38, ink, font: demi)
            c.text(check.1, 820, y + 90, 28, muted)
        }
        c.popIn(t, at: start + 0.6, center: CGPoint(x: 1720, y: y + 80)) {
            c.check(1720, y + 80, 34, i == 2 ? orange : purple)
        }
    }
    // Human review counter.
    let count = Int((easeOut(progress(t, 4.4, 1.6)) * 32).rounded())
    c.group(alpha: easeOut(progress(t, 4.3, 0.4))) {
        c.text("\(count) / 40 agree", 1410, 718, 34, purple, font: demi)
        c.text("8 still open", 1410, 768, 26, orange, font: demi)
    }
}

func drawOutro(_ c: Canvas, t: CGFloat) {
    let words = ["Detect", "Package", "Explain", "Check"]
    let total = words.enumerated().reduce(CGFloat(0)) { $0 + c.measure($1.element, 72, font: demi) + ($1.offset < 3 ? 120 : 0) }
    var x = (W - total) / 2
    for (i, word) in words.enumerated() {
        let p = easeOut(progress(t, 0.1 + CGFloat(i) * 0.25, 0.5))
        let w = c.measure(word, 72, font: demi)
        c.group(alpha: p, dy: (1 - p) * 30) {
            c.text(word, x, 420, 72, i == 3 ? orange : ink, font: demi)
            if i < 3 { c.text("→", x + w + 60, 420, 72, faint, center: true) }
        }
        x += w + 120
    }
    let sub = easeOut(progress(t, 1.2, 0.6))
    c.group(alpha: sub) {
        c.text("Every claim cites a measurement you can open.", W / 2, 580, 40, muted, center: true)
    }
}

func writeAnimation(to url: URL) throws {
    let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
    writer.shouldOptimizeForNetworkUse = true
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
        AVVideoCodecKey: AVVideoCodecType.h264,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: [
            AVVideoAverageBitRateKey: 6_000_000,
            AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
            AVVideoMaxKeyFrameIntervalKey: Int(frameRate) * 2
        ]
    ])
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height,
        kCVPixelBufferCGImageCompatibilityKey as String: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey as String: true
    ])
    writer.add(input)
    guard writer.startWriting() else { throw writer.error ?? CocoaError(.fileWriteUnknown) }
    writer.startSession(atSourceTime: .zero)
    guard let pool = adaptor.pixelBufferPool else { throw CocoaError(.fileWriteUnknown) }
    let bitmapInfo = CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedFirst.rawValue
    let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
    let frameCount = Int((totalSeconds * CGFloat(frameRate)).rounded())

    for frame in 0..<frameCount {
        while !input.isReadyForMoreMediaData {
            guard writer.status == .writing else { throw writer.error ?? CocoaError(.fileWriteUnknown) }
            Thread.sleep(forTimeInterval: 0.003)
        }
        try autoreleasepool {
            var pixelBuffer: CVPixelBuffer?
            guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pixelBuffer) == kCVReturnSuccess,
                  let pixelBuffer else { throw CocoaError(.fileWriteUnknown) }
            CVPixelBufferLockBaseAddress(pixelBuffer, [])
            let context = CGContext(data: CVPixelBufferGetBaseAddress(pixelBuffer), width: width, height: height,
                                    bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(pixelBuffer),
                                    space: colorSpace, bitmapInfo: bitmapInfo)
            guard let context else { throw CocoaError(.fileWriteUnknown) }
            draw(context, at: CGFloat(frame) / CGFloat(frameRate))
            CVPixelBufferUnlockBaseAddress(pixelBuffer, [])
            let time = CMTime(value: Int64(frame), timescale: frameRate)
            guard adaptor.append(pixelBuffer, withPresentationTime: time) else {
                throw writer.error ?? CocoaError(.fileWriteUnknown)
            }
        }
    }

    input.markAsFinished()
    let finished = DispatchSemaphore(value: 0)
    writer.finishWriting { finished.signal() }
    finished.wait()
    guard writer.status == .completed else { throw writer.error ?? CocoaError(.fileWriteUnknown) }
}

func writePNG(_ image: CGImage, to url: URL) throws {
    let bitmap = NSBitmapImageRep(cgImage: image)
    guard let png = bitmap.representation(using: .png, properties: [:]) else { throw CocoaError(.fileWriteUnknown) }
    try png.write(to: url, options: .atomic)
}

let arguments = CommandLine.arguments.dropFirst()
let output = URL(fileURLWithPath: arguments.first ?? "output/presentation/assets/experiment-flow.mp4")
let directory = output.deletingLastPathComponent()
let scratch = directory.appendingPathComponent(".experiment-flow-\(UUID().uuidString).mp4")
let files = FileManager.default
try files.createDirectory(at: directory, withIntermediateDirectories: true)
defer { try? files.removeItem(at: scratch) }
try writeAnimation(to: scratch)

let movie = AVURLAsset(url: scratch)
let generator = AVAssetImageGenerator(asset: movie)
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero
// Poster: the first stage once its content has built in.
let poster = try await generator.image(at: CMTime(seconds: 5.5, preferredTimescale: 600)).image
try writePNG(poster, to: output.deletingPathExtension().appendingPathExtension("png"))

if let qaPath = arguments.dropFirst().first {
    let qaDirectory = URL(fileURLWithPath: qaPath, isDirectory: true)
    try files.createDirectory(at: qaDirectory, withIntermediateDirectories: true)
    let stamps: [Double] = stride(from: 0.5, to: Double(totalSeconds), by: 1.5).map { $0 }
    for second in stamps {
        let frame = try await generator.image(at: CMTime(seconds: second, preferredTimescale: 600)).image
        try writePNG(frame, to: qaDirectory.appendingPathComponent(String(format: "t%04.1f.png", second)))
    }
}

let video = try await movie.loadTracks(withMediaType: .video)[0]
let duration = try await movie.load(.duration)
let format = try await video.load(.formatDescriptions)[0]
let dimensions = CMVideoFormatDescriptionGetDimensions(format)
let fourCC = CMFormatDescriptionGetMediaSubType(format)
let codec = String(decoding: [24, 16, 8, 0].map { UInt8(truncatingIfNeeded: fourCC >> $0) }, as: UTF8.self)
let audioTracks = try await movie.loadTracks(withMediaType: .audio)
guard abs(duration.seconds - Double(totalSeconds)) < 0.05, codec == "avc1", audioTracks.isEmpty,
      dimensions.width == width, dimensions.height == height else { throw CocoaError(.fileReadCorruptFile) }

if files.fileExists(atPath: output.path) {
    _ = try files.replaceItemAt(output, withItemAt: scratch)
} else {
    try files.moveItem(at: scratch, to: output)
}
print("\(duration.seconds) seconds, \(dimensions.width) x \(dimensions.height), \(codec), silent")
