import AppKit
import CursorTokenCore

enum MenubarIcon {
    /// Template image for the menu bar extra: black + alpha, tinted by the system.
    static func image(remaining: Double?, error: Bool, mode: String, pointSize: CGFloat? = nil) -> NSImage {
        let size = pointSize ?? Self.pointSize()
        let scale = max(NSScreen.main?.backingScaleFactor ?? 2, 2)
        let px = max(32, Int((size * scale).rounded()))
        let img = NSImage(size: NSSize(width: size, height: size))
        if let rep = NSBitmapImageRep(
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
        ) {
            rep.size = NSSize(width: size, height: size)
            NSGraphicsContext.saveGraphicsState()
            if let ctx = NSGraphicsContext(bitmapImageRep: rep) {
                ctx.imageInterpolation = .high
                ctx.shouldAntialias = true
                NSGraphicsContext.current = ctx
                draw(in: NSRect(x: 0, y: 0, width: size, height: size), remaining: remaining, error: error, mode: mode)
                ctx.flushGraphics()
            }
            NSGraphicsContext.restoreGraphicsState()
            img.addRepresentation(rep)
        }
        img.isTemplate = true
        return img
    }

    static func pointSize() -> CGFloat {
        let thickness = NSStatusBar.system.thickness
        return thickness > 0 ? thickness : 22
    }

    static func remainingColor(_ remaining: Double) -> NSColor {
        if remaining > 50 { return NSColor(calibratedRed: 46 / 255, green: 204 / 255, blue: 113 / 255, alpha: 1) }
        if remaining >= 20 { return NSColor(calibratedRed: 241 / 255, green: 196 / 255, blue: 15 / 255, alpha: 1) }
        return NSColor(calibratedRed: 231 / 255, green: 76 / 255, blue: 60 / 255, alpha: 1)
    }

    static func percentLabel(_ remaining: Double?, error: Bool) -> String {
        StatusText.trayPercentLabel(remaining, error: error)
    }

    static func draw(in rect: NSRect, remaining: Double?, error: Bool, mode: String) {
        let box = min(rect.width, rect.height)
        let cx = rect.midX
        let cy = rect.midY
        if mode == "dot" {
            let r = box * 0.22
            NSColor.black.withAlphaComponent(remaining == nil && !error ? 0.35 : 1).setFill()
            NSBezierPath(ovalIn: NSRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2)).fill()
            return
        }
        if mode == "number" {
            let label = percentLabel(remaining, error: error)
            let size = box * (label == "100" ? 0.42 : label.count >= 2 ? 0.56 : 0.64)
            drawCentered(label, cx: cx, cy: cy, size: size)
            return
        }
        let inset = max(1.5, box * 0.13)
        let outer = box / 2 - inset
        let ringW = max(1.85, min(2.4, box * 0.095))
        let midR = max(ringW, outer - ringW / 2)
        let innerR = max(1, midR - ringW / 2)
        let track = NSBezierPath()
        track.appendArc(withCenter: NSPoint(x: cx, y: cy), radius: midR, startAngle: 0, endAngle: 360)
        track.lineWidth = ringW
        NSColor.black.withAlphaComponent(0.30).setStroke()
        track.stroke()
        let label: String
        if error {
            strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 0, to: 360)
            label = "!"
        } else if let remaining {
            let pct = min(100, max(0, remaining))
            if pct >= 99.95 {
                strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 0, to: 360)
            } else if pct > 0.05 {
                strokeArc(cx: cx, cy: cy, r: midR, w: ringW, from: 90, to: 90 - pct / 100 * 360)
            }
            label = percentLabel(remaining, error: false)
        } else {
            label = "–"
        }
        let fontSize: CGFloat
        if label == "100" {
            fontSize = innerR * 0.96
        } else if label.count >= 2 {
            fontSize = innerR * 1.18
        } else {
            fontSize = innerR * 1.32
        }
        drawCentered(label, cx: cx, cy: cy, size: fontSize)
    }

    static func strokeArc(cx: CGFloat, cy: CGFloat, r: CGFloat, w: CGFloat, from: CGFloat, to: CGFloat) {
        let path = NSBezierPath()
        if abs(abs(to - from) - 360) < 0.5 {
            path.appendArc(withCenter: NSPoint(x: cx, y: cy), radius: r, startAngle: 0, endAngle: 360, clockwise: false)
        } else {
            path.appendArc(withCenter: NSPoint(x: cx, y: cy), radius: r, startAngle: from, endAngle: to, clockwise: true)
        }
        path.lineWidth = w
        path.lineCapStyle = .round
        NSColor.black.setStroke()
        path.stroke()
    }

    static func drawCentered(_ text: String, cx: CGFloat, cy: CGFloat, size: CGFloat) {
        let font = NSFont.monospacedDigitSystemFont(ofSize: size, weight: .semibold)
        let attrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.black,
        ]
        let s = NSAttributedString(string: text, attributes: attrs)
        let sz = s.size()
        s.draw(at: NSPoint(x: cx - sz.width / 2, y: cy - sz.height / 2 - size * 0.04))
    }
}
