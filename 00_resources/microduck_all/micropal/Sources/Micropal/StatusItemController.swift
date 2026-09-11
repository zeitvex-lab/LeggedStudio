import AppKit

/// Menu bar duck-head icon with the app's menu. The app has no Dock icon
/// (LSUIElement / .accessory), so this is the only persistent UI entry point.
final class StatusItemController: NSObject, NSMenuDelegate {
    private let statusItem: NSStatusItem
    private let store: SettingsStore
    private let petController: PetController
    private let settingsWindowController: SettingsWindowController
    private var pauseItem: NSMenuItem!
    private var loginItem: NSMenuItem!

    init(store: SettingsStore, petController: PetController,
         settingsWindowController: SettingsWindowController) {
        self.store = store
        self.petController = petController
        self.settingsWindowController = settingsWindowController
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        super.init()

        statusItem.button?.image = Self.duckHeadTemplate()
        statusItem.button?.toolTip = "Micropal"

        let menu = NSMenu()
        menu.delegate = self

        let settings = NSMenuItem(title: "Settings…", action: #selector(openSettings), keyEquivalent: ",")
        settings.target = self
        menu.addItem(settings)

        pauseItem = NSMenuItem(title: "Pause Pal", action: #selector(togglePause), keyEquivalent: "")
        pauseItem.target = self
        menu.addItem(pauseItem)

        menu.addItem(.separator())

        loginItem = NSMenuItem(title: "Launch at Login", action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
        loginItem.target = self
        menu.addItem(loginItem)

        menu.addItem(.separator())

        let quit = NSMenuItem(title: "Quit Micropal", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quit)

        statusItem.menu = menu
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        pauseItem.title = petController.paused ? "Resume Pal" : "Pause Pal"
        loginItem.state = store.launchAtLoginEnabled ? .on : .off
        loginItem.isEnabled = SettingsStore.canManageLaunchAtLogin
    }

    @objc private func openSettings() {
        settingsWindowController.show()
    }

    @objc private func togglePause() {
        petController.paused.toggle()
    }

    @objc private func toggleLaunchAtLogin() {
        try? store.setLaunchAtLogin(!store.launchAtLoginEnabled)
    }

    /// 18x18 template image: the duck head profile with a punched-out eye.
    private static func duckHeadTemplate() -> NSImage {
        let image = NSImage(size: NSSize(width: 18, height: 18), flipped: false) { rect in
            guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
            // Fit the head (design x 26…99, y 76…120) into the 18pt box.
            let scale = rect.width / 78
            ctx.translateBy(x: -26 * scale, y: -70 * scale)
            ctx.scaleBy(x: scale, y: scale)
            ctx.setFillColor(NSColor.black.cgColor)
            ctx.addPath(DuckPaths.headShell())
            ctx.addPath(DuckPaths.beak())
            ctx.fillPath()
            ctx.setBlendMode(.clear)
            ctx.addPath(DuckPaths.eyeLens())
            ctx.fillPath()
            return true
        }
        image.isTemplate = true
        return image
    }
}
