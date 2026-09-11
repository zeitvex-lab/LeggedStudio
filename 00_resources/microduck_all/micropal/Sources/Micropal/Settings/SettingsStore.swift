import AppKit
import Combine
import ServiceManagement

/// All user preferences, persisted to UserDefaults and observable from SwiftUI.
/// PetController reads it every tick (cheap in-memory reads) so changes apply live.
final class SettingsStore: ObservableObject {
    private let defaults = UserDefaults.standard

    /// Duck design: 0 = Classic, 1 = Faithful (A), 2 = Boxbot (B).
    @Published var styleIndex: Int { didSet { defaults.set(styleIndex, forKey: "styleIndex") } }

    /// 0…3 = official colorway preset, -1 = custom colors.
    @Published var colorwayIndex: Int { didSet { defaults.set(colorwayIndex, forKey: "colorwayIndex") } }
    @Published var customShell: String { didSet { defaults.set(customShell, forKey: "customShell") } }
    @Published var customAccent: String { didSet { defaults.set(customAccent, forKey: "customAccent") } }
    @Published var customEyeRing: String { didSet { defaults.set(customEyeRing, forKey: "customEyeRing") } }
    @Published var customFeetTop: String { didSet { defaults.set(customFeetTop, forKey: "customFeetTop") } }
    @Published var customFeetSole: String { didSet { defaults.set(customFeetSole, forKey: "customFeetSole") } }

    @Published var sizeScale: Double { didSet { defaults.set(sizeScale, forKey: "sizeScale") } }
    @Published var activity: Double { didSet { defaults.set(activity, forKey: "activity") } }

    @Published var clickEnabled: Bool { didSet { defaults.set(clickEnabled, forKey: "clickEnabled") } }
    @Published var dragEnabled: Bool { didSet { defaults.set(dragEnabled, forKey: "dragEnabled") } }
    @Published var cursorEnabled: Bool { didSet { defaults.set(cursorEnabled, forKey: "cursorEnabled") } }
    @Published var kickEnabled: Bool { didSet { defaults.set(kickEnabled, forKey: "kickEnabled") } }
    @Published var peckEnabled: Bool { didSet { defaults.set(peckEnabled, forKey: "peckEnabled") } }
    @Published var fallEnabled: Bool { didSet { defaults.set(fallEnabled, forKey: "fallEnabled") } }
    @Published var skateEnabled: Bool { didSet { defaults.set(skateEnabled, forKey: "skateEnabled") } }
    @Published var sitEnabled: Bool { didSet { defaults.set(sitEnabled, forKey: "sitEnabled") } }

    init() {
        defaults.register(defaults: [
            "styleIndex": 0,
            "colorwayIndex": 0,
            "customShell": "#9FD8DB", "customAccent": "#F0662B",
            "customEyeRing": "#F5A623", "customFeetTop": "#F0662B",
            "customFeetSole": "#F5C531",
            "sizeScale": 1.0, "activity": 1.0,
            "clickEnabled": true, "dragEnabled": true, "cursorEnabled": true,
            "kickEnabled": true, "peckEnabled": true, "fallEnabled": true,
            "skateEnabled": true, "sitEnabled": true,
        ])
        styleIndex = defaults.integer(forKey: "styleIndex")
        colorwayIndex = defaults.integer(forKey: "colorwayIndex")
        customShell = defaults.string(forKey: "customShell") ?? "#9FD8DB"
        customAccent = defaults.string(forKey: "customAccent") ?? "#F0662B"
        customEyeRing = defaults.string(forKey: "customEyeRing") ?? "#F5A623"
        customFeetTop = defaults.string(forKey: "customFeetTop") ?? "#F0662B"
        customFeetSole = defaults.string(forKey: "customFeetSole") ?? "#F5C531"
        sizeScale = defaults.double(forKey: "sizeScale")
        activity = defaults.double(forKey: "activity")
        clickEnabled = defaults.bool(forKey: "clickEnabled")
        dragEnabled = defaults.bool(forKey: "dragEnabled")
        cursorEnabled = defaults.bool(forKey: "cursorEnabled")
        kickEnabled = defaults.bool(forKey: "kickEnabled")
        peckEnabled = defaults.bool(forKey: "peckEnabled")
        fallEnabled = defaults.bool(forKey: "fallEnabled")
        skateEnabled = defaults.bool(forKey: "skateEnabled")
        sitEnabled = defaults.bool(forKey: "sitEnabled")
    }

    var currentStyle: DuckStyle {
        DuckStyle(rawValue: styleIndex) ?? .classic
    }

    var currentPalette: DuckPalette {
        if colorwayIndex >= 0 && colorwayIndex < DuckPalette.presets.count {
            return DuckPalette.presets[colorwayIndex].palette
        }
        return DuckPalette(
            shell: NSColor(hex: customShell), accent: NSColor(hex: customAccent),
            eyeRing: NSColor(hex: customEyeRing), feetTop: NSColor(hex: customFeetTop),
            feetSole: NSColor(hex: customFeetSole))
    }

    var behaviorConfig: BehaviorConfig {
        var c = BehaviorConfig()
        c.activity = activity
        c.clickEnabled = clickEnabled
        c.dragEnabled = dragEnabled
        c.cursorEnabled = cursorEnabled
        c.kickEnabled = kickEnabled
        c.peckEnabled = peckEnabled
        c.fallEnabled = fallEnabled
        c.skateEnabled = skateEnabled
        c.sitEnabled = sitEnabled
        return c
    }

    /// Seed the custom colors from the currently selected preset, then switch to custom.
    func startCustomizing() {
        let p = currentPalette
        customShell = p.shell.hexString
        customAccent = p.accent.hexString
        customEyeRing = p.eyeRing.hexString
        customFeetTop = p.feetTop.hexString
        customFeetSole = p.feetSole.hexString
        colorwayIndex = -1
    }

    // MARK: Launch at login

    /// Only meaningful when running from a real .app bundle (not `swift run`).
    static var canManageLaunchAtLogin: Bool {
        Bundle.main.bundleURL.pathExtension == "app"
    }

    var launchAtLoginEnabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    func setLaunchAtLogin(_ enabled: Bool) throws {
        if enabled {
            try SMAppService.mainApp.register()
        } else {
            try SMAppService.mainApp.unregister()
        }
        objectWillChange.send()
    }
}
