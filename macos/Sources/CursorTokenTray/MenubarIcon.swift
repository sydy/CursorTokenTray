import AppKit
import CursorTokenCore

enum MenubarIcon {
    static func image(remaining: Double?, error: Bool, mode: String, pointSize: CGFloat = 22) -> NSImage {
        let scales: [CGFloat] = [2, 3]
        let img = NSImage(size: NSSize(width: pointSize, height: pointSize))
        img.isTemplate = true
        for scale in scales {
            let px = Int(round(pointSize * scale))
            guard let rep = NSBitmapImageRep(
                bitmapDataPlanes: nil,
                pixelsWide: px,
                pixelsHigh: px,
                bitsPerSample: 8,
                samplesPerPixel: 4,
                hasAlpha: true,
                isPlanar: false,
                colorSpaceName: .deviceRGB,
                bytesPerRow: 0,
                bitsPerPixel: 0
            ) else { continue }
            rep.size = NSSize(width: pointSize, height: pointSize)
            NSGraphicsContext.saveGraphicsState()
            if let ctx = NSGraphicsContext(bitmapImageRep: rep) {
                NSGraphicsContext.current = ctx
                draw(in: NSRect(x: 0, y: 0, width: pointSize, height: pointSize), remaining: remaining, error: error, mode: mode)
            }
            NSGraphicsContext.restoreGraphicsState()
            img.addRepresentation(rep)
        }
        return img
    }

    static func remainingColor(_ remaining: Double) -> NSColor {
        if remaining > 50 { return NSColor(calibratedRed: 46 / 255, green: 204 / 255, blue: 113 / 255, alpha: 1) }
        if remaining >= 20 { return NSColor(calibratedRed: 241 / 255, green: 196 / 255, blue: 15 / 255, alpha: 1) }
        return NSColor(calibratedRed: 231 / 255, green: 76 / 255, blue: 60 / 255, alpha: 1)
    }

    static func draw(in rect: NSRect, remaining: Double?, error: Bool, mode: String) {
        let box = min(rect.width, rect.height)
        let cx = rect.midX
        let cy = rect.midY
        NSColor.black.set()
        if mode == "dot" {
            let r = box * 0.18
            NSBezierPath(ovalIn: NSRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2)).fill()
            return
        }
        if mode == "number" {
            let label = error ? "!" : (remaining.map { String(format: "%.0f", $0) } ?? "–")
            drawCentered(label, cx: cx, cy: cy, size: box * 0.42)
            return
        }
        let ringW = max(1.85, min(2.4, box * 0.095))
        let outer = box * 0.42
        let midR = max(ringW, outer - ringW / 2)
        let track = NSBezierPath()
        track.appendArc(withCenter: NSPoint(x: cx, y: cy), radius: midR, startAngle: 0, endAngle: 360)
        track.lineWidth = ringW
        NSColor.black.withAlphaComponent(0.22).setStroke()
        track.stroke()
        if error {
            strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 0, to: 360)
            drawCentered("!", cx: cx, cy: cy, size: box * 0.36)
            return
        }
        if let remaining {
            let pct = min(100, max(0, remaining))
            if pct <= 0 {
                strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 0, to: 360)
            } else {
                strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 90, to: 90 - pct / 100 * 360)
            }
            drawCentered(String(format: "%.0f", pct), cx: cx, cy: cy, size: box * 0.34)
        } else {
            strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 90, to: 90 - 40)
            drawCentered("–", cx: cx, cy: cy, size: box * 0.34)
        }
    }

    static func strokeArc(cx: CGFloat, cy: CGFloat, r: CGFloat, w: CGFloat, from: CGFloat, to: CGFloat) {
        let path = NSBezierPath()
        path.appendArc(withCenter: NSPoint(x: cx, y: cy), radius: r, startAngle: from, endAngle: to, clockwise: true)
        path.lineWidth = w
        path.lineCapStyle = .round
        NSColor.black.setStroke()
        path.stroke()
    }

    static func drawCentered(_ text: String, cx: CGFloat, cy: CGFloat, size: CGFloat) {
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: size, weight: .semibold),
            .foregroundColor: NSColor.black,
        ]
        let s = NSAttributedString(string: text, attributes: attrs)
        let sz = s.size()
        s.draw(at: NSPoint(x: cx - sz.width / 2, y: cy - sz.height / 2))
    }
}
