import AppKit

// CLI rendering modes (used by the icon build script and for verification):
//   Micropal --render-icon <path> <pixels> [colorwayIndex] [styleIndex]
//   Micropal --render-duck <path> <pixels> [colorwayIndex] [styleIndex]
// Otherwise: run the menu-bar pet app. `--debug` logs state every 2 s.

let arguments = CommandLine.arguments

func parseRender(flag: String) -> (path: String, pixels: Int, colorway: Int, style: DuckStyle)? {
    guard let i = arguments.firstIndex(of: flag), arguments.count > i + 2,
          let pixels = Int(arguments[i + 2]) else { return nil }
    let colorway = arguments.count > i + 3 ? (Int(arguments[i + 3]) ?? 0) : 0
    let style = arguments.count > i + 4
        ? (DuckStyle(rawValue: Int(arguments[i + 4]) ?? 0) ?? .classic) : .classic
    return (arguments[i + 1], pixels, colorway, style)
}

if arguments.contains("--render-icon") || arguments.contains("--render-duck") {
    let iconMode = arguments.contains("--render-icon")
    guard let req = parseRender(flag: iconMode ? "--render-icon" : "--render-duck") else {
        fputs("usage: Micropal --render-icon|--render-duck <path> <pixels> [colorway 0-3] [style 0-2]\n", stderr)
        exit(2)
    }
    _ = NSApplication.shared // initialize AppKit for offscreen drawing
    let ok = IconRenderer.render(to: req.path, pixels: req.pixels,
                                 colorway: req.colorway, iconBackground: iconMode,
                                 style: req.style)
    exit(ok ? 0 : 1)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
