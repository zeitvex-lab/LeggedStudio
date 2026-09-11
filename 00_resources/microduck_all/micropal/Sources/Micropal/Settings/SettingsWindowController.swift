import AppKit
import SwiftUI

final class SettingsWindowController {
    private let window: NSWindow

    init(store: SettingsStore) {
        let hosting = NSHostingController(rootView: SettingsView(store: store))
        window = NSWindow(contentViewController: hosting)
        window.title = "Micropal Settings"
        window.styleMask = [.titled, .closable, .miniaturizable]
        // Reopening a closed-and-released window crashes; keep it around.
        window.isReleasedWhenClosed = false
        window.setContentSize(hosting.view.fittingSize)
        window.center()
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}
