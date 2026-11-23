import AppKit
import AVFoundation
import CoreText

let width = 1280
let height = 720
let frameRate: Int32 = 24
let sceneSeconds = 6

let white = CGColor(gray: 1, alpha: 1)
let orange = color(0xF56600)
let purple = color(0x522D80)
let ink = color(0x2E1A47)
let muted = color(0x5E5469)
let border = color(0xDFD8E7)
let palePurple = color(0xF5F1F9)
let paleOrange = color(0xFFF1E5)
let regular = "ArialMT" as CFString
let bold = "Arial-BoldMT" as CFString

let scenes = [
    ("Source", "Public CAN captures", "Both datasets contain recorded CAN traffic with normal and attack examples."),
    ("Split", "Reference and evaluation split", "Use normal traffic to build the reference. Run the detector on the evaluation captures."),
    ("Window", "Window features and detection", "The detector compares each window’s features with the normal reference."),
    ("Alert", "Alert selection", "Merge adjacent flagged windows. Missed attacks stay outside the explanation benchmark."),
    ("Freeze", "Frozen evidence", "Each explainer gets the same evidence. Only the scorer gets the ground-truth labels."),
    ("Explain", "Explanation arms", "The rule control and three hosted models process the same frozen packets."),
    ("Score", "Scoring and claim review", "Score labels, failures and latency. Independent human claim review is pending.")
]

func color(_ hex: UInt32) -> CGColor {
    let red = CGFloat((hex >> 16) & 255) / 255
    let green = CGFloat((hex >> 8) & 255) / 255
    let blue = CGFloat(hex & 255) / 255
    return CGColor(red: red, green: green, blue: blue, alpha: 1)
}

struct Canvas {
    let context: CGContext

    func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ fill: CGColor,
             outline: CGColor? = nil, radius: CGFloat = 0) {
        let rect = CGRect(x: x, y: CGFloat(height) - y - h, width: w, height: h)
        let path = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)
        context.addPath(path)
        context.setFillColor(fill)
        if let outline {
            context.setStrokeColor(outline)
            context.setLineWidth(2)
            context.drawPath(using: .fillStroke)
            return
        }
        context.fillPath()
    }

    func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat,
              _ fill: CGColor = ink, strong: Bool = false) {
        let font = CTFontCreateWithName(strong ? bold : regular, size, nil)
        let string = NSAttributedString(string: value, attributes: [
            NSAttributedString.Key(rawValue: kCTFontAttributeName as String): font,
            NSAttributedString.Key(rawValue: kCTForegroundColorAttributeName as String): fill
        ])
        context.textPosition = CGPoint(x: x, y: CGFloat(height) - y - CTFontGetAscent(font))
        CTLineDraw(CTLineCreateWithAttributedString(string), context)
    }

    func path(_ points: [CGPoint], _ lineColor: CGColor, width: CGFloat = 4, dashed: Bool = false) {
        context.saveGState()
        context.setStrokeColor(lineColor)
        context.setLineWidth(width)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        if dashed {
            context.setLineDash(phase: 0, lengths: [7, 9])
        }
        context.addLines(between: points.map { CGPoint(x: $0.x, y: CGFloat(height) - $0.y) })
        context.strokePath()
        context.restoreGState()
    }

    func circle(_ x: CGFloat, _ y: CGFloat, _ radius: CGFloat, _ fill: CGColor) {
        context.setFillColor(fill)
        context.fillEllipse(in: CGRect(x: x - radius, y: CGFloat(height) - y - radius,
                                       width: 2 * radius, height: 2 * radius))
    }

    func arrow(_ coordinates: [(CGFloat, CGFloat)], phase: CGFloat, scoring: Bool = false) {
        let points = coordinates.map { CGPoint(x: $0.0, y: $0.1) }
        let lineColor = scoring ? muted : purple
        path(points, lineColor, dashed: scoring)

        let end = points[points.count - 1]
        let previous = points[points.count - 2]
        let angle = atan2(end.y - previous.y, end.x - previous.x)
        let wings = [-CGFloat.pi / 4, CGFloat.pi / 4].map {
            CGPoint(x: end.x - 10 * cos(angle + $0), y: end.y - 10 * sin(angle + $0))
        }
        path([wings[0], end, wings[1]], lineColor)

        let segments = zip(points, points.dropFirst()).map { (start: $0, end: $1, distance: hypot($1.x - $0.x, $1.y - $0.y)) }
        var remaining = segments.reduce(0) { $0 + $1.distance } * phase
        for segment in segments {
            if remaining <= segment.distance && segment.distance > 0 {
                let portion = remaining / segment.distance
                let x = segment.start.x + portion * (segment.end.x - segment.start.x)
                let y = segment.start.y + portion * (segment.end.y - segment.start.y)
                circle(x, y, 8, white)
                circle(x, y, 5.5, scoring ? muted : orange)
                break
            }
            remaining -= segment.distance
        }
    }

    func card(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat,
              _ title: String, _ detail: String? = nil, highlighted: Bool = false) {
        box(x, y, w, h, highlighted ? palePurple : white, outline: highlighted ? purple : border, radius: 12)
        box(x + 1, y + 13, 5, h - 26, highlighted ? orange : purple, radius: 2)
        let textY = detail == nil ? y + h / 2 - 15 : y + h / 2 - 30
        text(title, x + 24, textY, 27, ink, strong: true)
        if let detail {
            text(detail, x + 24, textY + 34, 20, muted)
        }
    }
}

func draw(_ context: CGContext, at second: CGFloat) {
    let canvas = Canvas(context: context)
    let scene = min(Int(second) / sceneSeconds, scenes.count - 1)
    let localTime = second - CGFloat(scene * sceneSeconds)
    let phase = (localTime / 2.0).truncatingRemainder(dividingBy: 1)

    canvas.box(0, 0, CGFloat(width), CGFloat(height), white)
    canvas.box(72, 45, 43, 5, orange)
    canvas.text("CANalyst experiment workflow", 72, 62, 21, purple, strong: true)
    canvas.text(scenes[scene].1, 72, 98, 55, strong: true)
    canvas.box(72, 192, 1136, 339, color(0xFBF9FC), outline: border, radius: 16)

    switch scene {
    case 0:
        canvas.arrow([(430, 306), (591, 306), (591, 357), (749, 357)], phase: phase)
        canvas.arrow([(430, 413), (591, 413), (591, 380), (749, 380)], phase: phase)
        canvas.card(128, 266, 302, 80, "HCRL")
        canvas.card(128, 373, 302, 80, "ROAD")
        canvas.card(755, 310, 378, 113, "CAN recordings", "Normal and attack traffic", highlighted: true)

    case 1:
        canvas.arrow([(388, 351), (558, 351), (558, 305), (700, 305)], phase: phase)
        canvas.arrow([(388, 373), (558, 373), (558, 420), (700, 420)], phase: phase)
        canvas.card(128, 309, 260, 109, "CAN recordings", "HCRL and ROAD")
        canvas.card(706, 251, 426, 108, "Clean reference", "Normal traffic only", highlighted: true)
        canvas.card(706, 366, 426, 108, "Evaluation captures", "Normal and attack traffic", highlighted: true)

    case 2:
        canvas.text("Overlapping windows", 128, 245, 25, ink, strong: true)
        for index in 0..<15 {
            let x = 129 + CGFloat(index) * 30
            let barHeight = CGFloat([18, 31, 22, 44, 31, 25, 42, 20, 34, 28, 47, 25, 20, 29, 36][index])
            canvas.box(x, 345 - barHeight, 14, barHeight, purple, radius: 3)
        }
        let activeWindow = min(Int(localTime / 1.45), 3)
        for index in 0..<4 {
            let selected = index == activeWindow
            canvas.box(128 + CGFloat(index) * 85, 363 + CGFloat(index % 2) * 35, 170, 29,
                       selected ? paleOrange : palePurple, outline: selected ? orange : border, radius: 5)
        }
        canvas.text("0.5 s window  ·  0.25 s stride", 128, 462, 23, muted)
        canvas.arrow([(572, 364), (671, 364)], phase: phase)
        canvas.card(678, 307, 450, 113, "Detector", "Frame counts, timing and payload changes", highlighted: true)

    case 3:
        canvas.text("Detector windows", 128, 255, 25, ink, strong: true)
        for index in 0..<7 {
            let flagged = 2...4 ~= index
            let fill = flagged ? paleOrange : white
            let outline = flagged ? orange : border
            canvas.box(128 + CGFloat(index) * 56, 331, 48, 55, fill, outline: outline, radius: 5)
            canvas.circle(152 + CGFloat(index) * 56, 359, 5, flagged ? orange : border)
        }
        canvas.path([CGPoint(x: 240, y: 404), CGPoint(x: 240, y: 414), CGPoint(x: 400, y: 414), CGPoint(x: 400, y: 404)], orange)
        canvas.text("Flagged windows", 239, 439, 21, muted)
        canvas.arrow([(521, 359), (696, 359)], phase: phase)
        canvas.card(702, 306, 428, 106, "Detected alert", "Continues to explanation", highlighted: true)

    case 4:
        canvas.arrow([(439, 303), (705, 303)], phase: phase)
        canvas.arrow([(439, 430), (705, 430)], phase: phase, scoring: true)
        canvas.card(128, 252, 311, 102, "Detected alert", "Frames and rule signals")
        canvas.card(711, 252, 419, 102, "Frozen evidence packet", "Features and evidence citations", highlighted: true)
        canvas.card(128, 379, 311, 102, "Ground-truth labels", "Dataset annotations")
        canvas.card(711, 379, 419, 102, "Scorer only", "Compare with predicted labels")

    case 5:
        for y: CGFloat in [249, 325, 401, 477] {
            canvas.arrow([(485, 363), (600, 363), (600, y), (728, y)], phase: phase)
        }
        canvas.card(128, 307, 357, 112, "Frozen evidence packet", "Same input for every arm", highlighted: true)
        canvas.card(734, 221, 394, 56, "Rule control")
        canvas.card(734, 297, 394, 56, "GLM-5.3")
        canvas.card(734, 373, 394, 56, "Gemma-4-31B")
        canvas.card(734, 449, 394, 56, "Qwen3.6-27B-FP8")

    default:
        canvas.arrow([(442, 303), (579, 303), (579, 315), (693, 315)], phase: phase)
        canvas.arrow([(442, 431), (579, 431), (579, 346), (693, 346)], phase: phase, scoring: true)
        canvas.card(128, 252, 314, 102, "Explainer outputs", "Predictions and claims")
        canvas.card(128, 380, 314, 102, "Ground-truth labels", "Dataset annotations")
        canvas.card(699, 256, 431, 137, "Benchmark scoring", "Label accuracy, failures and latency", highlighted: true)
        canvas.card(699, 407, 431, 75, "Human claim review pending")
    }

    canvas.box(72, 555, 1136, 56, palePurple, radius: 7)
    canvas.box(72, 555, 5, 56, orange, radius: 2)
    canvas.text(scenes[scene].2, 91, 570, 23, ink)

    for index in scenes.indices {
        let x = 72 + CGFloat(index) * 164
        canvas.box(x, 648, 152, 5, index < scene ? purple : border, radius: 2)
        if index == scene {
            canvas.box(x, 648, max(8, 152 * localTime / CGFloat(sceneSeconds)), 5, orange, radius: 2)
        }
        canvas.text(scenes[index].0, x, 663, 18, index == scene ? ink : muted, strong: index == scene)
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
            AVVideoAverageBitRateKey: 2_500_000,
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
    let frameCount = scenes.count * sceneSeconds * Int(frameRate)

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
let firstFrame = try await generator.image(at: .zero).image
try writePNG(firstFrame, to: output.deletingPathExtension().appendingPathExtension("png"))

if let qaPath = arguments.dropFirst().first {
    let qaDirectory = URL(fileURLWithPath: qaPath, isDirectory: true)
    try files.createDirectory(at: qaDirectory, withIntermediateDirectories: true)
    for index in scenes.indices {
        let second = index * sceneSeconds + sceneSeconds / 2
        let frame = try await generator.image(at: CMTime(value: Int64(second), timescale: 1)).image
        try writePNG(frame, to: qaDirectory.appendingPathComponent("\(index + 1)-\(scenes[index].0).png"))
    }
}

let video = try await movie.loadTracks(withMediaType: .video)[0]
let duration = try await movie.load(.duration)
let format = try await video.load(.formatDescriptions)[0]
let dimensions = CMVideoFormatDescriptionGetDimensions(format)
let fourCC = CMFormatDescriptionGetMediaSubType(format)
let codec = String(decoding: [24, 16, 8, 0].map { UInt8(truncatingIfNeeded: fourCC >> $0) }, as: UTF8.self)
let audioTracks = try await movie.loadTracks(withMediaType: .audio)
guard duration.seconds == Double(scenes.count * sceneSeconds), codec == "avc1", audioTracks.isEmpty,
      dimensions.width == width, dimensions.height == height else { throw CocoaError(.fileReadCorruptFile) }

if files.fileExists(atPath: output.path) {
    _ = try files.replaceItemAt(output, withItemAt: scratch)
} else {
    try files.moveItem(at: scratch, to: output)
}
print("\(duration.seconds) seconds, \(dimensions.width) x \(dimensions.height), \(codec), silent")
