import AppKit

/// The parameterized colors of a Micropal. Pastel plastic shells over black robotics.
struct DuckPalette: Equatable {
    var shell: NSColor      // head + body + thigh plates
    var accent: NSColor     // beak lip + trim
    var eyeRing: NSColor    // ring around the camera lens
    var feetTop: NSColor    // upper foot shell
    var feetSole: NSColor   // sole of the foot

    // Fixed robotics colors shared by every colorway.
    static let robotBlack = NSColor(srgbRed: 0.13, green: 0.13, blue: 0.15, alpha: 1)
    static let robotDark = NSColor(srgbRed: 0.22, green: 0.22, blue: 0.25, alpha: 1)
    static let visorDark = NSColor(srgbRed: 0.17, green: 0.16, blue: 0.18, alpha: 1)
    static let lensDark = NSColor(srgbRed: 0.08, green: 0.08, blue: 0.10, alpha: 1)
    static let screwGray = NSColor(hex: "#6E6E76")

    struct Preset {
        let name: String
        let palette: DuckPalette
    }

    /// The four official colorways from pollen-robotics.com.
    static let presets: [Preset] = [
        Preset(name: "Teal", palette: DuckPalette(
            shell: NSColor(hex: "#9FD8DB"), accent: NSColor(hex: "#F0662B"),
            eyeRing: NSColor(hex: "#F5A623"), feetTop: NSColor(hex: "#F0662B"),
            feetSole: NSColor(hex: "#F5C531"))),
        Preset(name: "Grey", palette: DuckPalette(
            shell: NSColor(hex: "#83838A"), accent: NSColor(hex: "#F5C531"),
            eyeRing: NSColor(hex: "#7B5EA7"), feetTop: NSColor(hex: "#F5C531"),
            feetSole: NSColor(hex: "#8A6FBF"))),
        Preset(name: "Cream", palette: DuckPalette(
            shell: NSColor(hex: "#F1E9D7"), accent: NSColor(hex: "#F0662B"),
            eyeRing: NSColor(hex: "#F5A623"), feetTop: NSColor(hex: "#F0662B"),
            feetSole: NSColor(hex: "#F5A623"))),
        Preset(name: "Lavender", palette: DuckPalette(
            shell: NSColor(hex: "#B5A3D6"), accent: NSColor(hex: "#F5C531"),
            eyeRing: NSColor(hex: "#7FD6E0"), feetTop: NSColor(hex: "#F5C531"),
            feetSole: NSColor(hex: "#B5A3D6"))),
    ]
}

extension NSColor {
    /// sRGB color from "#RRGGBB". Falls back to magenta on a malformed string.
    convenience init(hex: String) {
        var value: UInt64 = 0
        let cleaned = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        guard cleaned.count == 6, Scanner(string: cleaned).scanHexInt64(&value) else {
            self.init(srgbRed: 1, green: 0, blue: 1, alpha: 1)
            return
        }
        self.init(
            srgbRed: CGFloat((value >> 16) & 0xFF) / 255,
            green: CGFloat((value >> 8) & 0xFF) / 255,
            blue: CGFloat(value & 0xFF) / 255,
            alpha: 1)
    }

    var hexString: String {
        let c = usingColorSpace(.sRGB) ?? NSColor.magenta
        let r = Int(round(c.redComponent * 255))
        let g = Int(round(c.greenComponent * 255))
        let b = Int(round(c.blueComponent * 255))
        return String(format: "#%02X%02X%02X", r, g, b)
    }

    /// Darkened variant, used to shade the back leg for depth.
    func darkened(_ amount: CGFloat) -> NSColor {
        let c = usingColorSpace(.sRGB) ?? self
        return NSColor(
            srgbRed: c.redComponent * (1 - amount),
            green: c.greenComponent * (1 - amount),
            blue: c.blueComponent * (1 - amount),
            alpha: c.alphaComponent)
    }
}
