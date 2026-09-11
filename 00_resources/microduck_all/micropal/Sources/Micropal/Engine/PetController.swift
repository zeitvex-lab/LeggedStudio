import AppKit

/// Owns the pet window, the duck view, the 60 Hz tick, and the world model:
/// x along the screen bottom, height above ground, vertical velocity, facing.
final class PetController: NSObject, DuckViewDelegate {
    private let store: SettingsStore
    private let window: PetWindow
    private let duckView: DuckLayerView
    private let stateMachine = DuckStateMachine()

    private var timer: Timer?
    private var lastTickAt = CACurrentMediaTime()

    // World model (screen coordinates, bottom-left origin). x is the duck's
    // bottom-center; y is height above the ground line.
    private var x: CGFloat = 0
    private var y: CGFloat = 0
    private var vy: CGFloat = 0
    private var facing: CGFloat = 1

    private var groundY: CGFloat = 0
    private var minX: CGFloat = 0
    private var maxX: CGFloat = 800

    // Interaction bookkeeping.
    private var pressStartLocation = CGPoint.zero
    private var isDragging = false
    private var grabOffset = CGPoint.zero
    private var lastState: DuckState = .idle

    // Change detection for live settings.
    private var appliedPalette: DuckPalette?
    private var appliedScale: CGFloat = 0
    private var appliedStyle: DuckStyle = .classic

    private let debug = CommandLine.arguments.contains("--debug")
    private var lastDebugLogAt: TimeInterval = 0

    var paused = false {
        didSet {
            if paused {
                timer?.invalidate()
                timer = nil
                window.orderOut(nil)
            } else if timer == nil {
                window.orderFrontRegardless()
                startTimer()
            }
        }
    }

    init(store: SettingsStore) {
        self.store = store
        let scale = CGFloat(store.sizeScale)
        let size = DuckLayerView.viewSize(scale: scale)
        window = PetWindow(contentRect: NSRect(origin: .zero, size: size))
        duckView = DuckLayerView(frame: NSRect(origin: .zero, size: size))
        super.init()

        duckView.delegate = self
        duckView.setScale(scale)
        window.contentView = duckView
        appliedScale = scale

        refreshScreenMetrics()
        x = minX + (maxX - minX) * CGFloat.random(in: 0.3...0.7)
        positionWindow()
        window.orderFrontRegardless()

        NotificationCenter.default.addObserver(
            self, selector: #selector(screenParamsChanged),
            name: NSApplication.didChangeScreenParametersNotification, object: nil)

        startTimer()
    }

    private func startTimer() {
        lastTickAt = CACurrentMediaTime()
        let t = Timer(timeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    // MARK: Screen metrics

    private var screen: NSScreen? { NSScreen.screens.first }

    @objc private func screenParamsChanged() {
        refreshScreenMetrics()
        x = max(minX, min(maxX, x))
        positionWindow()
    }

    private func refreshScreenMetrics() {
        guard let screen else { return }
        let visible = screen.visibleFrame
        groundY = visible.minY
        let halfDuck = 50 * appliedScale
        minX = visible.minX + halfDuck
        maxX = visible.maxX - halfDuck
    }

    // MARK: Tick

    private func tick() {
        let now = CACurrentMediaTime()
        let dt = min(0.05, max(0.001, now - lastTickAt))
        lastTickAt = now

        applySettingsIfChanged()

        let cursor = CursorTracker.location
        let cursorOnScreen = screen.map { CursorTracker.isOnScreen($0) } ?? false
        let cursorAvailable = store.cursorEnabled && cursorOnScreen

        if isDragging {
            // Window glued to the cursor; world position derives from the window.
            let origin = CGPoint(x: cursor.x - grabOffset.x, y: cursor.y - grabOffset.y)
            window.setFrameOrigin(origin)
            syncWorldFromWindow()
            let out = stateMachine.tick(dt: dt, cursorAvailable: cursorAvailable)
            duckView.apply(pose: out.pose, facing: facing)
            logDebugIfNeeded()
            return
        }

        var out = stateMachine.tick(dt: dt, cursorAvailable: cursorAvailable)
        handleStateEntry(cursorAvailable: cursorAvailable)

        // Horizontal movement.
        if stateMachine.state == .walkToCursor {
            let target = max(minX, min(maxX, cursor.x))
            if abs(target - x) < 40 * appliedScale {
                stateMachine.finishWalkToCursor()
            } else {
                facing = target > x ? 1 : -1
            }
        }
        let speed = out.speedDesign * appliedScale
        if speed > 0 {
            x += speed * facing * CGFloat(dt)
            if x <= minX { x = minX; facing = 1 }
            if x >= maxX { x = maxX; facing = -1 }
        }

        // Vertical physics (hop and post-drag falls).
        let airborne = stateMachine.state == .falling || stateMachine.state == .clickHop
        if airborne || y > 0 {
            let gravity = 2500 * appliedScale
            vy -= gravity * CGFloat(dt)
            y += vy * CGFloat(dt)
            if y <= 0 {
                let impact = -vy
                y = 0
                vy = 0
                stateMachine.landed(hard: impact > 900 * appliedScale)
            }
        }

        // Eye tracks the cursor when allowed.
        if cursorAvailable && stateMachine.pupilFollowsCursor {
            let eyeInView = duckView.eyePositionInView
            let eyeScreen = CGPoint(x: window.frame.origin.x + eyeInView.x,
                                    y: window.frame.origin.y + eyeInView.y)
            let dx = cursor.x - eyeScreen.x
            let dy = cursor.y - eyeScreen.y
            let dist = max(1, hypot(dx, dy))
            // Mirror x into design space when facing left.
            out.pose.pupilOffset = CGPoint(x: (dx / dist) * 3 * facing, y: (dy / dist) * 3)
        }

        positionWindow()
        duckView.apply(pose: out.pose, facing: facing)
        logDebugIfNeeded()
    }

    /// Give freshly started walks some variety by occasionally turning around.
    private func handleStateEntry(cursorAvailable: Bool) {
        let state = stateMachine.state
        defer { lastState = state }
        guard state != lastState else { return }
        if state == .walking && CGFloat.random(in: 0...1) < 0.35 {
            facing = -facing
        }
    }

    private func positionWindow() {
        let size = window.frame.size
        let bottomInset = DuckLayerView.bottomMarginDesign * appliedScale
        window.setFrameOrigin(CGPoint(x: x - size.width / 2,
                                      y: groundY + y - bottomInset))
    }

    private func syncWorldFromWindow() {
        let frame = window.frame
        let bottomInset = DuckLayerView.bottomMarginDesign * appliedScale
        x = frame.origin.x + frame.size.width / 2
        y = frame.origin.y + bottomInset - groundY
    }

    // MARK: Live settings

    private func applySettingsIfChanged() {
        let styleChoice = store.currentStyle
        if styleChoice != appliedStyle {
            appliedStyle = styleChoice
            duckView.apply(style: styleChoice)
        }

        let palette = store.currentPalette
        if palette != appliedPalette {
            duckView.apply(palette: palette)
            appliedPalette = palette
        }

        let scale = CGFloat(store.sizeScale)
        if abs(scale - appliedScale) > 0.001 {
            appliedScale = scale
            let size = DuckLayerView.viewSize(scale: scale)
            duckView.setScale(scale)
            window.setContentSize(size)
            refreshScreenMetrics()
            x = max(minX, min(maxX, x))
            positionWindow()
        }

        stateMachine.config = store.behaviorConfig
    }

    private func logDebugIfNeeded() {
        guard debug else { return }
        let now = CACurrentMediaTime()
        if now - lastDebugLogAt > 2 {
            lastDebugLogAt = now
            let frame = window.frame
            // stderr is unbuffered, so logs appear immediately even when redirected.
            fputs(String(format: "[duck] state=%@ x=%.0f y=%.0f facing=%+.0f window=(%.0f,%.0f %.0fx%.0f)\n",
                         stateMachine.state.rawValue, x, y, facing,
                         frame.origin.x, frame.origin.y, frame.size.width, frame.size.height), stderr)
        }
    }

    // MARK: DuckViewDelegate (click vs drag)

    func duckMouseDown(_ event: NSEvent) {
        pressStartLocation = CursorTracker.location
        isDragging = false
    }

    func duckMouseDragged(_ event: NSEvent) {
        guard store.dragEnabled else { return }
        let location = CursorTracker.location
        if !isDragging {
            let moved = hypot(location.x - pressStartLocation.x,
                              location.y - pressStartLocation.y)
            guard moved > 4 else { return }
            isDragging = true
            grabOffset = CGPoint(x: location.x - window.frame.origin.x,
                                 y: location.y - window.frame.origin.y)
            stateMachine.beginDrag()
        }
        window.setFrameOrigin(CGPoint(x: location.x - grabOffset.x,
                                      y: location.y - grabOffset.y))
    }

    func duckMouseUp(_ event: NSEvent) {
        if isDragging {
            isDragging = false
            syncWorldFromWindow()
            x = max(minX, min(maxX, x))
            y = max(0, y)
            vy = 0
            stateMachine.endDragFalling()
            if y <= 0 {
                stateMachine.landed(hard: false) // dropped at ground level
            }
        } else if store.clickEnabled {
            if let kind = stateMachine.clickReact(), kind == .hop {
                vy = 420 * appliedScale
                y = max(y, 0.01)
            }
        }
    }
}
