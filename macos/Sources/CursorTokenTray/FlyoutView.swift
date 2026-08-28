import AppKit
import Combine
import CursorTokenCore
import SwiftUI

struct FlyoutView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            leftColumn
            Divider()
            rightColumn
        }
        .padding(18)
        .frame(width: 456, height: 236)
        .background(.ultraThinMaterial)
    }

    var remaining: Double? { store.usage?.remainingPercent }
    var isError: Bool { store.usage == nil && store.errorMessage != nil }

    var leftColumn: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("剩余").font(.caption).foregroundStyle(.secondary)
            if let remaining, !isError {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(String(format: "%.1f", remaining)).font(.system(size: 34, weight: .bold))
                    Text("%").font(.title3).foregroundStyle(.secondary)
                }
                Text(planCaption).font(.subheadline).foregroundStyle(.secondary)
                pill
            } else {
                Text(store.errorMessage ?? "等待刷新…").font(.subheadline).frame(maxWidth: 180, alignment: .leading)
                pill
            }
            Spacer()
            Button(UsageParser.dashboardLinkLabel(store.usage)) { store.openDashboard() }
                .buttonStyle(.plain)
                .foregroundStyle(Color.accentColor)
                .font(.caption)
        }
        .frame(width: 190, alignment: .leading)
    }

    var planCaption: String {
        guard let usage = store.usage else { return "" }
        var text = StatusText.formatPlanCaption(usage.membershipType, accountLabel: store.config.activeAccount?.displayLabel)
        if usage.isUnlimited { text += " · 不限量" }
        return text
    }

    var pill: some View {
        let text = StatusText.statusPillText(remaining, error: isError)
        let color: Color = {
            if isError || remaining == nil { return Color(nsColor: .systemGray) }
            if let remaining, remaining < 20 { return .red }
            if let remaining, remaining < 50 { return .yellow }
            return .green
        }()
        return Text(text)
            .font(.caption)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(color.opacity(0.25), in: Capsule())
    }

    var rightColumn: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let usage = store.usage, !isError {
                if usage.showsAmount {
                    labeled("金额", UsageParser.formatSpendRange(used: usage.usedCents, limit: usage.limitCents))
                }
                if let auto = usage.autoPercentUsed {
                    labeled("First-party", String(format: "%.1f%%", auto))
                    bar(auto / 100, color: Color(red: 92 / 255, green: 163 / 255, blue: 152 / 255))
                }
                if let api = usage.apiPercentUsed {
                    labeled("API", String(format: "%.1f%%", api))
                    bar(api / 100, color: Color(red: 142 / 255, green: 142 / 255, blue: 147 / 255))
                }
                if let tokens = usage.totalTokens, tokens > 0 {
                    Text("Token  \(UsageParser.formatTokenCount(Double(tokens)))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let end = usage.billingCycleEnd {
                    Text("重置  \(StatusText.formatResetDate(end))").font(.caption).foregroundStyle(.secondary)
                }
                Text(StatusText.formatEstimateCaption(usage)).font(.caption).foregroundStyle(.secondary)
                sparkline
            } else if let updated = store.updatedAt {
                Text("更新  \(updated)").font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            HStack {
                Spacer()
                Button("复制") { store.copySummary() }.buttonStyle(.plain).foregroundStyle(Color.accentColor).font(.caption)
                Button("刷新") { store.requestRefresh() }.buttonStyle(.plain).foregroundStyle(Color.accentColor).font(.caption)
                Button("报表") { FlyoutWindowController.shared.close(); store.openReport() }
                    .buttonStyle(.plain).foregroundStyle(Color.accentColor).font(.caption)
                Button("设置") { FlyoutWindowController.shared.close(); store.openSettings() }
                    .buttonStyle(.plain).foregroundStyle(Color.accentColor).font(.caption)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    func labeled(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.caption)
        }
    }

    func bar(_ fraction: Double, color: Color) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.2))
                Capsule().fill(color).frame(width: max(4, geo.size.width * min(1, max(0, fraction))))
            }
        }
        .frame(height: 5)
    }

    var sparkline: some View {
        let values = store.historyValues()
        return Group {
            if values.count >= 2 {
                Sparkline(values: values)
                    .frame(height: 36)
                    .padding(.top, 4)
            }
        }
    }
}

struct Sparkline: View {
    var values: [Double]
    var body: some View {
        GeometryReader { geo in
            let minV = min(values.min() ?? 0, 0)
            let maxV = max(values.max() ?? 100, minV + 1)
            Path { p in
                for (i, v) in values.enumerated() {
                    let x = geo.size.width * CGFloat(i) / CGFloat(max(values.count - 1, 1))
                    let y = geo.size.height * (1 - CGFloat((v - minV) / (maxV - minV)))
                    if i == 0 { p.move(to: CGPoint(x: x, y: y)) } else { p.addLine(to: CGPoint(x: x, y: y)) }
                }
            }
            .stroke(Color.accentColor, lineWidth: 1.5)
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
                contentRect: NSRect(x: 0, y: 0, width: 456, height: 236),
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
        window?.contentView = NSHostingView(rootView: FlyoutView(store: store).clipShape(RoundedRectangle(cornerRadius: 14)))
        position(statusButton: statusButton)
        window?.makeKeyAndOrderFront(nil)
        installMonitor()
    }

    func update(store: AppStore) {
        guard window?.isVisible == true else { return }
        window?.contentView = NSHostingView(rootView: FlyoutView(store: store).clipShape(RoundedRectangle(cornerRadius: 14)))
    }

    func close() {
        store?.flyoutVisible = false
        window?.orderOut(nil)
        removeMonitor()
    }

    func windowDidResignKey(_ notification: Notification) { close() }

    func position(statusButton: NSStatusBarButton?) {
        guard let window else { return }
        let size = NSSize(width: 456, height: 236)
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
