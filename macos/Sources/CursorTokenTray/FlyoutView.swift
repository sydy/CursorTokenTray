import AppKit
import Combine
import CursorTokenCore
import SwiftUI

enum FlyoutLayout {
    static let width: CGFloat = 500
    static let height: CGFloat = 300
    static let size = CGSize(width: width, height: height)
    static let cornerRadius: CGFloat = 16
    static let padding: CGFloat = 16
    static let columnGap: CGFloat = 16
    static let leftWidth: CGFloat = 176
    static let ringSize: CGFloat = 148
    static let ringLine: CGFloat = 10
    static let cardRadius: CGFloat = 10
    static let cardPadding: CGFloat = 10
    static let cardGap: CGFloat = 8
    static let barHeight: CGFloat = 5
    static let sparkHeight: CGFloat = 36
}

struct FlyoutView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        HStack(alignment: .top, spacing: FlyoutLayout.columnGap) {
            leftColumn
            rightColumn
        }
        .padding(FlyoutLayout.padding)
        .frame(width: FlyoutLayout.width, height: FlyoutLayout.height)
        .background(.ultraThinMaterial)
    }

    var remaining: Double? { store.usage?.remainingPercent }
    var isError: Bool { store.usage == nil && store.errorMessage != nil }
    var isUnlimited: Bool { store.usage?.isUnlimited == true }

    var leftColumn: some View {
        VStack(spacing: 10) {
            RemainingGauge(
                remaining: remaining,
                error: isError,
                unlimited: isUnlimited,
                color: gaugeColor
            ) {
                pill
            }
            if let remaining, !isError {
                Text(planCaption)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            } else {
                Text(store.errorMessage ?? "等待刷新…")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: FlyoutLayout.leftWidth, alignment: .center)
            }
            Button(UsageParser.dashboardLinkLabel(store.usage)) { store.openDashboard() }
                .buttonStyle(.plain)
                .foregroundStyle(Color.accentColor)
                .font(.caption)
            Spacer(minLength: 0)
        }
        .frame(width: FlyoutLayout.leftWidth)
    }

    var planCaption: String {
        guard let usage = store.usage else { return "" }
        var text = StatusText.formatPlanCaption(usage.membershipType, accountLabel: store.config.activeAccount?.displayLabel)
        if usage.isUnlimited { text += " · 不限量" }
        return text
    }

    var gaugeColor: Color { RemainingTone.color(remaining: remaining, error: isError, unlimited: isUnlimited) }

    var pill: some View {
        let text = StatusText.statusPillText(remaining, error: isError)
        return Text(text)
            .font(.caption)
            .padding(.horizontal, 10)
            .padding(.vertical, 3)
            .background(gaugeColor.opacity(0.25), in: Capsule())
    }

    var rightColumn: some View {
        VStack(alignment: .leading, spacing: FlyoutLayout.cardGap) {
            if let usage = store.usage, !isError {
                if usage.showsAmount {
                    card {
                        labeled("金额", UsageParser.formatSpendRange(used: usage.usedCents, limit: usage.limitCents))
                        if let used = usage.usedCents, let limit = usage.limitCents, limit > 0 {
                            bar(used / limit, color: Color(red: 48 / 255, green: 209 / 255, blue: 88 / 255))
                        }
                    }
                }
                if usage.autoPercentUsed != nil || usage.apiPercentUsed != nil {
                    card {
                        if let auto = usage.autoPercentUsed {
                            meterRow("First-party", auto, color: Color(red: 50 / 255, green: 180 / 255, blue: 170 / 255))
                        }
                        if let api = usage.apiPercentUsed {
                            meterRow("API", api, color: Color(red: 142 / 255, green: 142 / 255, blue: 147 / 255))
                        }
                    }
                }
                if hasMeta(usage) {
                    card {
                        HStack(spacing: 12) {
                            if let tokens = usage.totalTokens, tokens > 0 {
                                Text("Token  \(UsageParser.formatTokenCount(Double(tokens)))")
                            }
                            if let end = usage.billingCycleEnd {
                                Text("重置  \(StatusText.formatResetDate(end))")
                            }
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        Text(StatusText.formatEstimateCaption(usage))
                            .font(.caption)
                            .foregroundStyle(estimateColor(usage))
                    }
                }
                sparkline
            } else if let updated = store.updatedAt {
                Text("更新  \(updated)").font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            HStack(spacing: 6) {
                Spacer()
                toolButton("复制", "doc.on.doc") { store.copySummary() }
                toolButton("刷新", "arrow.clockwise") { store.requestRefresh() }
                toolButton("报表", "chart.bar") {
                    FlyoutWindowController.shared.close()
                    store.openReport()
                }
                toolButton("设置", "gearshape") {
                    FlyoutWindowController.shared.close()
                    store.openSettings()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    func hasMeta(_ usage: UsageSnapshot) -> Bool {
        if let tokens = usage.totalTokens, tokens > 0 { return true }
        if usage.billingCycleEnd != nil { return true }
        return true
    }

    func estimateColor(_ usage: UsageSnapshot) -> Color {
        let text = StatusText.formatEstimateCaption(usage)
        if text.contains("可撑过") { return Color(red: 48 / 255, green: 209 / 255, blue: 88 / 255) }
        if text.contains("耗尽") || text.contains("紧张") { return Color(red: 231 / 255, green: 76 / 255, blue: 60 / 255) }
        return .secondary
    }

    func card<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            content()
        }
        .padding(FlyoutLayout.cardPadding)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: FlyoutLayout.cardRadius, style: .continuous))
    }

    func labeled(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.caption.monospacedDigit()).fontWeight(.medium)
        }
    }

    func meterRow(_ title: String, _ percent: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Circle().fill(color).frame(width: 6, height: 6)
                Text(title).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text(String(format: "%.1f%%", percent)).font(.caption.monospacedDigit())
            }
            bar(percent / 100, color: color)
        }
    }

    func bar(_ fraction: Double, color: Color) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.2))
                Capsule()
                    .fill(color)
                    .frame(width: geo.size.width * min(1, max(0, fraction)))
            }
        }
        .frame(height: FlyoutLayout.barHeight)
    }

    func toolButton(_ title: String, _ systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: systemImage)
                Text(title)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Color.primary.opacity(0.08), in: Capsule())
        }
        .buttonStyle(.plain)
        .help(title)
    }

    var sparkline: some View {
        let values = store.historyValues()
        return Group {
            if values.count >= 2 {
                Sparkline(values: values)
                    .frame(height: FlyoutLayout.sparkHeight)
                    .padding(.top, 2)
            }
        }
    }
}

enum RemainingTone {
    static func color(remaining: Double?, error: Bool, unlimited: Bool = false) -> Color {
        if error { return Color(nsColor: .systemGray) }
        if unlimited { return Color(red: 48 / 255, green: 209 / 255, blue: 88 / 255) }
        guard let remaining else { return Color(nsColor: .systemGray) }
        if remaining < 20 { return Color(red: 231 / 255, green: 76 / 255, blue: 60 / 255) }
        if remaining < 50 { return Color(red: 241 / 255, green: 196 / 255, blue: 15 / 255) }
        return Color(red: 46 / 255, green: 204 / 255, blue: 113 / 255)
    }
}

struct RemainingGauge<Pill: View>: View {
    var remaining: Double?
    var error: Bool
    var unlimited: Bool
    var color: Color
    @ViewBuilder var pill: () -> Pill

    var progress: CGFloat {
        if error { return 0 }
        if unlimited { return 1 }
        return CGFloat(min(1, max(0, (remaining ?? 0) / 100)))
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.primary.opacity(0.12), lineWidth: FlyoutLayout.ringLine)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(color, style: StrokeStyle(lineWidth: FlyoutLayout.ringLine, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeInOut(duration: 0.35), value: progress)
            VStack(spacing: 4) {
                Text("剩余").font(.caption).foregroundStyle(.secondary)
                if unlimited {
                    Text("不限量").font(.system(size: 22, weight: .bold, design: .rounded))
                } else if let remaining, !error {
                    HStack(alignment: .firstTextBaseline, spacing: 2) {
                        Text(String(format: "%.1f", remaining))
                            .font(.system(size: 28, weight: .bold, design: .rounded))
                            .monospacedDigit()
                        Text("%").font(.headline).foregroundStyle(.secondary)
                    }
                } else {
                    Text(error ? "—" : "…")
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                pill()
            }
        }
        .frame(width: FlyoutLayout.ringSize, height: FlyoutLayout.ringSize)
    }
}

struct Sparkline: View {
    var values: [Double]
    var body: some View {
        GeometryReader { geo in
            let minV = min(values.min() ?? 0, 0)
            let maxV = max(values.max() ?? 100, minV + 1)
            let pts: [CGPoint] = values.enumerated().map { i, v in
                CGPoint(
                    x: geo.size.width * CGFloat(i) / CGFloat(max(values.count - 1, 1)),
                    y: geo.size.height * (1 - CGFloat((v - minV) / (maxV - minV)))
                )
            }
            ZStack {
                Path { p in
                    guard let first = pts.first, let last = pts.last else { return }
                    p.move(to: CGPoint(x: first.x, y: geo.size.height))
                    for pt in pts { p.addLine(to: pt) }
                    p.addLine(to: CGPoint(x: last.x, y: geo.size.height))
                    p.closeSubpath()
                }
                .fill(
                    LinearGradient(
                        colors: [Color.accentColor.opacity(0.32), Color.accentColor.opacity(0.02)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                Path { p in
                    for (i, pt) in pts.enumerated() {
                        if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
                    }
                }
                .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.5, lineJoin: .round))
            }
        }
    }
}

@MainActor
final class FlyoutWindowController: NSObject, NSWindowDelegate {
    static let shared = FlyoutWindowController()
    private var window: NSPanel?
    private var monitor: Any?
    private weak var store: AppStore?

    func toggle(store: AppStore, statusButton: NSStatusBarButton?) {
        if window?.isVisible == true {
            // 多次点击只打开，不关闭
            update(store: store)
            position(statusButton: statusButton)
            window?.makeKeyAndOrderFront(nil)
            return
        }
        show(store: store, statusButton: statusButton)
    }

    func show(store: AppStore, statusButton: NSStatusBarButton?) {
        self.store = store
        store.flyoutVisible = true
        if window == nil {
            let panel = NSPanel(
                contentRect: NSRect(origin: .zero, size: FlyoutLayout.size),
                styleMask: [.borderless, .nonactivatingPanel],
                backing: .buffered,
                defer: false
            )
            panel.isFloatingPanel = true
            panel.level = .floating
            panel.isOpaque = false
            panel.backgroundColor = .clear
            panel.hasShadow = true
            panel.hidesOnDeactivate = false
            panel.delegate = self
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
            window = panel
        }
        window?.contentView = hostedView(store: store)
        position(statusButton: statusButton)
        window?.makeKeyAndOrderFront(nil)
        installMonitor()
    }

    func update(store: AppStore) {
        guard window?.isVisible == true else { return }
        window?.contentView = hostedView(store: store)
    }

    func hostedView(store: AppStore) -> NSView {
        let root = FlyoutView(store: store)
            .clipShape(RoundedRectangle(cornerRadius: FlyoutLayout.cornerRadius, style: .continuous))
        return NSHostingView(rootView: root)
    }

    func close() {
        store?.flyoutVisible = false
        window?.orderOut(nil)
        removeMonitor()
    }

    func windowDidResignKey(_ notification: Notification) { close() }

    func position(statusButton: NSStatusBarButton?) {
        guard let window else { return }
        let size = FlyoutLayout.size
        var icon = NSRect(x: 0, y: 0, width: 22, height: 22)
        if let button = statusButton, let win = button.window {
            icon = win.convertToScreen(button.convert(button.bounds, to: nil))
        }
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let origin = popupOrigin(icon: icon, popup: size, visible: screen)
        window.setFrame(NSRect(origin: origin, size: size), display: true)
    }

    func popupOrigin(icon: NSRect, popup: NSSize, visible: NSRect, gap: CGFloat = 10, margin: CGFloat = 8) -> NSPoint {
        let left = visible.minX + margin
        let right = visible.maxX - margin
        let bottom = visible.minY + margin
        let top = visible.maxY
        var x = icon.maxX - popup.width
        if x < left { x = left }
        if x + popup.width > right { x = right - popup.width }
        if x < left { x = left }
        var y = top - gap - popup.height
        if y + popup.height > icon.minY - 2 {
            y = icon.minY - gap - popup.height
        }
        if y < bottom { y = bottom }
        return NSPoint(x: x, y: y)
    }

    func installMonitor() {
        removeMonitor()
        monitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] event in
            let loc = event.locationInWindow
            Task { @MainActor in
                guard let self, let window = self.window, window.isVisible else { return }
                if !window.frame.contains(loc) {
                    self.close()
                }
            }
        }
    }

    func removeMonitor() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
    }
}
