// swift-tools-version: 5.9
import PackageDescription

var targets: [Target] = [
    .target(
        name: "CursorTokenCore",
        path: "Sources/CursorTokenCore",
        linkerSettings: [.linkedLibrary("sqlite3")]
    ),
    .testTarget(
        name: "CursorTokenCoreTests",
        dependencies: ["CursorTokenCore"],
        path: "Tests/CursorTokenCoreTests"
    ),
]

#if os(macOS)
targets.append(
    .executableTarget(
        name: "CursorTokenTray",
        dependencies: ["CursorTokenCore"],
        path: "Sources/CursorTokenTray"
    )
)
#endif

var products: [Product] = [
    .library(name: "CursorTokenCore", targets: ["CursorTokenCore"]),
]
#if os(macOS)
products.append(.executable(name: "CursorTokenTray", targets: ["CursorTokenTray"]))
#endif

let package = Package(
    name: "CursorTokenTray",
    platforms: [.macOS(.v13)],
    products: products,
    targets: targets
)
