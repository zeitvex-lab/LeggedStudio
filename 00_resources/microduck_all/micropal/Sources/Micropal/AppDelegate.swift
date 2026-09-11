import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var store: SettingsStore!
    private var petController: PetController!
    private var settingsWindowController: SettingsWindowController!
    private var statusItemController: StatusItemController!

    func applicationDidFinishLaunching(_ notification: Notification) {
        store = SettingsStore()
        petController = PetController(store: store)
        settingsWindowController = SettingsWindowController(store: store)
        statusItemController = StatusItemController(
            store: store,
            petController: petController,
            settingsWindowController: settingsWindowController)
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool { true }
}
