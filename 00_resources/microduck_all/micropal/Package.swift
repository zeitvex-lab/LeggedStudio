// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Micropal",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "Micropal",
            path: "Sources/Micropal"
        )
    ]
)
