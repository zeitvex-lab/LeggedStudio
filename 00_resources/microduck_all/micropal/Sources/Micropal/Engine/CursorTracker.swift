import AppKit

/// Reads the global cursor position. `NSEvent.mouseLocation` needs no
/// accessibility or input-monitoring permission (unlike CGEvent taps).
enum CursorTracker {
    /// Global cursor location in screen coordinates (bottom-left origin).
    static var location: CGPoint { NSEvent.mouseLocation }

    /// Whether the cursor is currently on the given screen.
    static func isOnScreen(_ screen: NSScreen) -> Bool {
        screen.frame.contains(location)
    }
}
