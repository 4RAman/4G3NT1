// swift-tools-version: 5.9
import PackageDescription

// ButtonKit is the half of the phone app that has no UI in it: the models, the
// host client seam, and the pure functions the views render from. It is a
// package rather than a folder in the app target for one reason - `swift test`
// runs it from a Terminal with no simulator and no Xcode project, which is the
// only cheap check this side of the app has.
let package = Package(
    name: "ButtonKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "ButtonKit", targets: ["ButtonKit"]),
    ],
    targets: [
        .target(name: "ButtonKit"),
        .testTarget(name: "ButtonKitTests", dependencies: ["ButtonKit"]),
    ]
)
