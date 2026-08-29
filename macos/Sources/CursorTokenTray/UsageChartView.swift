import SwiftUI
import CursorTokenCore

enum UsageChartPalette {
    static let colors: [Color] = [
        Color(red: 0, green: 120 / 255, blue: 212 / 255),
        Color(red: 0, green: 168 / 255, blue: 150 / 255),
        Color(red: 232 / 255, green: 160 / 255, blue: 32 / 255),
        Color(red: 136 / 255, green: 87 / 255, blue: 184 / 255),
        Color(red: 216 / 255, green: 80 / 255, blue: 91 / 255),
        Color(red: 90 / 255, green: 148 / 255, blue: 74 / 255),
        Color(red: 70 / 255, green: 130 / 255, blue: 180 / 255),
        Color(red: 180 / 255, green: 110 / 255, blue: 70 / 255),
    ]

    static func color(models: [String], name: String) -> Color {
        let i = models.firstIndex(of: name) ?? 0
        return colors[i % colors.count]
    }
}

struct UsageChartView: View {
    let series: UsageChartSeries
    var hiddenModels: Set<String>
    var hourly: Bool
    var onHourlyChange: (Bool) -> Void
    var onToggleModel: (String) -> Void

    @State private var hoverKey: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center) {
                Text(series.caption)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Picker("粒度", selection: Binding(
                    get: { hourly },
                    set: onHourlyChange
                )) {
                    Text("按日").tag(false)
                    Text("按小时").tag(true)
                }
                .pickerStyle(.segmented)
                .frame(width: 150)
                .labelsHidden()
            }
            if !series.models.isEmpty {
                FlowLegend(models: series.models, hidden: hiddenModels, onToggle: onToggleModel)
            }
            plot
                .frame(height: 168)
        }
    }

    var plot: some View {
        GeometryReader { geo in
            let layout = PlotLayout(size: geo.size, series: series)
            ZStack(alignment: .topLeading) {
                Canvas { context, size in
                    drawChart(context: context, layout: layout)
                }
                Color.clear
                    .contentShape(Rectangle())
                    .onContinuousHover { phase in
                        switch phase {
                        case .active(let point):
                            hoverKey = layout.bucket(at: point)?.key
                        case .ended:
                            hoverKey = nil
                        }
                    }
                if let hoverKey, let bucket = series.buckets.first(where: { $0.key == hoverKey }) {
                    tooltip(bucket)
                        .offset(x: min(geo.size.width - 168, max(8, layout.barCenterX(for: bucket) + 8)), y: 10)
                }
            }
        }
        .background(Color(nsColor: .textBackgroundColor))
        .overlay(
            Rectangle().stroke(Color.secondary.opacity(0.25), lineWidth: 1)
        )
    }

    func tooltip(_ bucket: ChartBucket) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(bucket.key)  \(UsageEvents.tzLabel)")
            Text("合计 \(UsageParser.formatTokenCount(Double(bucket.tokens)))")
            ForEach(bucket.slices, id: \.model) { slice in
                Text("\(UsageEvents.chartModelLabel(slice.model))  \(UsageParser.formatTokenCount(Double(slice.tokens)))")
            }
            if bucket.cents > 0 {
                Text("费用 \(UsageParser.formatUSDCents(bucket.cents))")
            }
        }
        .font(.caption)
        .foregroundStyle(.white)
        .padding(8)
        .background(Color.black.opacity(0.88), in: RoundedRectangle(cornerRadius: 6))
        .allowsHitTesting(false)
    }

    private func drawChart(context: GraphicsContext, layout: PlotLayout) {
        let ticks = layout.ticks
        let yMax = CGFloat(max(1, ticks.last ?? 1))
        for tick in ticks {
            let y = layout.plot.maxY - CGFloat(tick) / yMax * layout.plot.height
            var grid = Path()
            grid.move(to: CGPoint(x: layout.plot.minX, y: y))
            grid.addLine(to: CGPoint(x: layout.plot.maxX, y: y))
            context.stroke(grid, with: .color(.secondary.opacity(0.18)), lineWidth: 1)
            let label = tick == 0 ? "0" : UsageParser.formatTokenCount(Double(tick))
            context.draw(
                Text(label).font(.system(size: 10)).foregroundColor(.secondary),
                at: CGPoint(x: layout.plot.minX - 6, y: y),
                anchor: .trailing
            )
        }
        if series.buckets.isEmpty {
            context.draw(
                Text("暂无数据").font(.caption).foregroundColor(.secondary),
                at: CGPoint(x: layout.plot.midX, y: layout.plot.midY),
                anchor: .center
            )
            return
        }
        for (i, bucket) in series.buckets.enumerated() {
            var yb = layout.plot.maxY
            let x = layout.barX(i)
            for slice in bucket.slices {
                let h = CGFloat(slice.tokens) / yMax * layout.plot.height
                guard h >= 0.5 else { continue }
                let rect = CGRect(x: x, y: yb - h, width: layout.barW, height: h)
                context.fill(Path(rect), with: .color(UsageChartPalette.color(models: series.models, name: slice.model)))
                yb -= h
            }
        }
        let step = layout.labelStep
        for i in Swift.stride(from: 0, to: series.buckets.count, by: step) {
            let cx = layout.barCenterX(i)
            context.draw(
                Text(series.buckets[i].label).font(.system(size: 10)).foregroundColor(.secondary),
                at: CGPoint(x: cx, y: layout.plot.maxY + 10),
                anchor: .center
            )
        }
    }
}

private struct PlotLayout {
    let plot: CGRect
    let barW: CGFloat
    let slot: CGFloat
    let ticks: [Int]
    let series: UsageChartSeries

    init(size: CGSize, series: UsageChartSeries) {
        self.series = series
        let maxTokens = max(1, series.buckets.map(\.tokens).max() ?? 1)
        ticks = Self.yTicks(maxTokens)
        plot = CGRect(x: 46, y: 8, width: max(8, size.width - 54), height: max(8, size.height - 28))
        let n = max(series.buckets.count, 1)
        slot = plot.width / CGFloat(n)
        barW = max(2, min(slot * 0.58, 72))
    }

    var labelStep: Int {
        max(1, Int(ceil(CGFloat(series.buckets.count) * 28 / max(plot.width, 1))))
    }

    func barX(_ i: Int) -> CGFloat {
        plot.minX + slot * (CGFloat(i) + 0.5) - barW / 2
    }

    func barCenterX(_ i: Int) -> CGFloat {
        plot.minX + slot * (CGFloat(i) + 0.5)
    }

    func barCenterX(for bucket: ChartBucket) -> CGFloat {
        guard let i = series.buckets.firstIndex(where: { $0.key == bucket.key }) else { return plot.midX }
        return barCenterX(i)
    }

    func bucket(at point: CGPoint) -> ChartBucket? {
        guard !series.buckets.isEmpty, plot.contains(point) else { return nil }
        let i = Int((point.x - plot.minX) / slot)
        guard i >= 0, i < series.buckets.count else { return nil }
        return series.buckets[i]
    }

    static func yTicks(_ maxTokens: Int) -> [Int] {
        if maxTokens <= 0 { return [0, 1] }
        let exp = floor(log10(Double(maxTokens)))
        let f = Double(maxTokens) / pow(10, exp)
        let nice: Double = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10
        var top = nice * pow(10, exp)
        if top < Double(maxTokens) { top *= 1.2 }
        let step = top / 4
        return [0, 1, 2, 3, 4].map { Int((Double($0) * step).rounded()) }
    }
}

private struct FlowLegend: View {
    let models: [String]
    var hidden: Set<String>
    var onToggle: (String) -> Void

    var body: some View {
        let columns = [GridItem(.adaptive(minimum: 96), spacing: 8, alignment: .leading)]
        LazyVGrid(columns: columns, alignment: .leading, spacing: 6) {
            ForEach(models, id: \.self) { name in
                let on = !hidden.contains(name)
                let color = UsageChartPalette.color(models: models, name: name)
                Button { onToggle(name) } label: {
                    HStack(spacing: 6) {
                        Circle().fill(on ? color : Color.secondary.opacity(0.4)).frame(width: 8, height: 8)
                        Text(UsageEvents.chartModelLabel(name)).font(.caption)
                            .foregroundStyle(on ? Color.primary : Color.secondary)
                            .lineLimit(1)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Capsule().fill(on ? color.opacity(0.18) : Color.clear))
                    .overlay(Capsule().stroke(on ? color.opacity(0.8) : Color.secondary.opacity(0.35), lineWidth: 1))
                }
                .buttonStyle(.plain)
                .help("显示 / 隐藏此模型")
            }
        }
    }
}
