import AppKit

protocol DuckViewDelegate: AnyObject {
    func duckMouseDown(_ event: NSEvent)
    func duckMouseDragged(_ event: NSEvent)
    func duckMouseUp(_ event: NSEvent)
}

/// Layer-hosting NSView that draws the duck as a CAShapeLayer tree built from
/// the active DuckStyle's spec, and poses it procedurally. No CAAnimations —
/// the state machine drives every frame.
final class DuckLayerView: NSView {
    weak var delegate: DuckViewDelegate?

    /// Scale from design units to points. The window is resized around this.
    private(set) var scale: CGFloat = 1
    private(set) var facing: CGFloat = 1 // +1 right, -1 left
    private(set) var style: DuckStyle = .classic
    private var spec: DuckStyleSpec = .classic
    private var currentPose = DuckPose.neutral
    private var currentPalette: DuckPalette?

    // Root + posable groups (rebuilt on style change).
    private let root = CALayer()
    private var backLegGroup = CALayer()
    private var backFootGroup = CALayer()
    private var frontLegGroup = CALayer()
    private var frontFootGroup = CALayer()
    private var torsoGroup = CALayer()
    private var headGroup = CALayer()
    private var pupilGroup = CALayer()
    private var eyelidLayer = CAShapeLayer()
    private var wheelLayers: [CAShapeLayer] = []

    /// Every palette-driven layer: (layer, role, darkened-for-depth?).
    private var colorLayers: [(CAShapeLayer, PartRole, Bool)] = []

    /// Margins around the 100x120 design box, in design units. Wide enough that
    /// the whole duck stays inside the view while rotated flat on the ground,
    /// and tall enough for Boxbot's antenna.
    static let sideMarginDesign: CGFloat = 76
    static let topMarginDesign: CGFloat = 12
    static let bottomMarginDesign: CGFloat = 6

    static func viewSize(scale: CGFloat) -> CGSize {
        CGSize(width: (DuckPaths.designSize.width + 2 * sideMarginDesign) * scale,
               height: (DuckPaths.designSize.height + topMarginDesign + bottomMarginDesign) * scale)
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        layer = CALayer()
        wantsLayer = true
        layer?.masksToBounds = false
        root.bounds = DuckPaths.designRect
        root.anchorPoint = CGPoint(x: 0.5, y: 0)
        root.masksToBounds = false
        layer?.addSublayer(root)
        buildLayers()
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override var isFlipped: Bool { false }

    // MARK: Layer tree

    private func group(anchor: CGPoint) -> CALayer {
        let l = CALayer()
        l.bounds = DuckPaths.designRect
        l.anchorPoint = CGPoint(x: anchor.x / DuckPaths.designSize.width,
                                y: anchor.y / DuckPaths.designSize.height)
        l.position = anchor
        l.masksToBounds = false
        return l
    }

    private func shape(_ path: CGPath) -> CAShapeLayer {
        let s = CAShapeLayer()
        s.frame = DuckPaths.designRect
        s.path = path
        s.lineWidth = 0
        return s
    }

    private func addParts(_ parts: [StylePart], to parent: CALayer, darkened: Bool) {
        for part in parts {
            let s = shape(part.path)
            parent.addSublayer(s)
            colorLayers.append((s, part.role, darkened))
        }
    }

    func apply(style newStyle: DuckStyle) {
        style = newStyle
        spec = newStyle.spec
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        buildLayers()
        if let palette = currentPalette { applyColors(palette) }
        applyPoseLayers()
        CATransaction.commit()
    }

    private func buildLayers() {
        root.sublayers?.forEach { $0.removeFromSuperlayer() }
        colorLayers.removeAll()
        wheelLayers.removeAll()

        // Back leg (darker for depth).
        backLegGroup = group(anchor: spec.backHip)
        addParts(spec.backLegParts, to: backLegGroup, darkened: true)
        backFootGroup = group(anchor: spec.backAnkle)
        let backWheels = shape(DuckPaths.skateWheels(ankleX: spec.backAnkle.x))
        backWheels.opacity = 0
        backFootGroup.addSublayer(backWheels)
        colorLayers.append((backWheels, .dark, false))
        wheelLayers.append(backWheels)
        addParts(spec.backFootParts, to: backFootGroup, darkened: true)
        backLegGroup.addSublayer(backFootGroup)
        root.addSublayer(backLegGroup)

        // Torso: body + neck + head ride together.
        torsoGroup = group(anchor: spec.torsoPivot)
        addParts(spec.torsoParts, to: torsoGroup, darkened: false)

        headGroup = group(anchor: spec.neckTop)
        addParts(spec.headParts, to: headGroup, darkened: false)

        // Eye built from the spec's center + radius.
        let e = spec.eyeCenter, r = spec.eyeRadius
        let ring = shape(CGPath(ellipseIn: CGRect(x: e.x - r, y: e.y - r,
                                                  width: 2 * r, height: 2 * r),
                                transform: nil))
        headGroup.addSublayer(ring)
        colorLayers.append((ring, .eyeRingRole, false))

        pupilGroup = group(anchor: e)
        let lensR = r * 0.55
        let lens = shape(CGPath(ellipseIn: CGRect(x: e.x - lensR, y: e.y - lensR,
                                                  width: 2 * lensR, height: 2 * lensR),
                                transform: nil))
        pupilGroup.addSublayer(lens)
        colorLayers.append((lens, .lensRole, false))
        let hlR = r * 0.19
        let highlight = shape(CGPath(ellipseIn: CGRect(x: e.x + r * 0.12, y: e.y + r * 0.2,
                                                       width: 2 * hlR, height: 2 * hlR),
                                     transform: nil))
        highlight.fillColor = NSColor.white.withAlphaComponent(0.75).cgColor
        pupilGroup.addSublayer(highlight)
        headGroup.addSublayer(pupilGroup)

        eyelidLayer = shape(CGPath(ellipseIn: CGRect(x: e.x - r - 1, y: e.y - r - 1,
                                                     width: 2 * r + 2, height: 2 * r + 2),
                                   transform: nil))
        eyelidLayer.opacity = 0
        headGroup.addSublayer(eyelidLayer)
        colorLayers.append((eyelidLayer, .eyelidRole, false))

        torsoGroup.addSublayer(headGroup)
        root.addSublayer(torsoGroup)

        // Front leg.
        frontLegGroup = group(anchor: spec.frontHip)
        addParts(spec.frontLegParts, to: frontLegGroup, darkened: false)
        frontFootGroup = group(anchor: spec.frontAnkle)
        let frontWheels = shape(DuckPaths.skateWheels(ankleX: spec.frontAnkle.x))
        frontWheels.opacity = 0
        frontFootGroup.addSublayer(frontWheels)
        colorLayers.append((frontWheels, .dark, false))
        wheelLayers.append(frontWheels)
        addParts(spec.frontFootParts, to: frontFootGroup, darkened: false)
        frontLegGroup.addSublayer(frontFootGroup)
        root.addSublayer(frontLegGroup)

        layoutRoot()
    }

    // MARK: Palette

    func apply(palette: DuckPalette) {
        currentPalette = palette
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        applyColors(palette)
        CATransaction.commit()
    }

    private func applyColors(_ p: DuckPalette) {
        for (layer, role, darkened) in colorLayers {
            var color: NSColor
            switch role {
            case .shell: color = p.shell
            case .shellShade: color = p.shell.darkened(0.12)
            case .black: color = DuckPalette.robotBlack
            case .dark: color = DuckPalette.robotDark
            case .visor: color = DuckPalette.visorDark
            case .screw: color = DuckPalette.screwGray
            case .accent: color = p.accent
            case .accentDark: color = p.accent.darkened(0.22)
            case .feetTop: color = p.feetTop
            case .feetSole: color = p.feetSole
            case .eyeRingRole: color = p.eyeRing
            case .lensRole: color = DuckPalette.lensDark
            case .eyelidRole: color = p.shell.darkened(0.05)
            }
            // Only pastel parts recede on the back leg; robotics stay black.
            if darkened, ![PartRole.black, .dark, .visor, .screw].contains(role) {
                color = color.darkened(0.18)
            }
            layer.fillColor = color.cgColor
        }
    }

    // MARK: Scale & layout

    func setScale(_ newScale: CGFloat) {
        scale = newScale
        layoutRoot()
    }

    private func layoutRoot() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        root.position = CGPoint(x: bounds.midX, y: Self.bottomMarginDesign * scale)
        applyRootTransform()
        CATransaction.commit()
    }

    override func layout() {
        super.layout()
        layoutRoot()
    }

    private func applyRootTransform() {
        let squash = currentPose.squash
        let widen = 1 + (1 - squash) * 0.6
        var t = CATransform3DMakeScale(scale * facing * widen, scale * squash, 1)
        t = CATransform3DRotate(t, currentPose.bodyRotation, 0, 0, 1)
        root.transform = t
    }

    // MARK: Pose

    func apply(pose: DuckPose, facing newFacing: CGFloat) {
        currentPose = pose
        facing = newFacing
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        applyPoseLayers()
        CATransaction.commit()
    }

    private func applyPoseLayers() {
        let pose = currentPose
        backLegGroup.transform = CATransform3DMakeRotation(pose.backLegAngle, 0, 0, 1)
        backFootGroup.transform = CATransform3DMakeRotation(pose.backFootAngle, 0, 0, 1)
        frontLegGroup.transform = CATransform3DMakeRotation(pose.frontLegAngle, 0, 0, 1)
        frontFootGroup.transform = CATransform3DMakeRotation(pose.frontFootAngle, 0, 0, 1)

        var torso = CATransform3DMakeTranslation(0, pose.bodyBobY, 0)
        torso = CATransform3DRotate(torso, pose.bodyTilt, 0, 0, 1)
        torsoGroup.transform = torso

        var head = CATransform3DMakeTranslation(0, pose.headBobY, 0)
        head = CATransform3DRotate(head, pose.headTilt, 0, 0, 1)
        headGroup.transform = head

        let maxPupilTravel: CGFloat = spec.eyeRadius * 0.28
        let dx = max(-maxPupilTravel, min(maxPupilTravel, pose.pupilOffset.x))
        let dy = max(-maxPupilTravel, min(maxPupilTravel, pose.pupilOffset.y))
        var pupil = CATransform3DMakeTranslation(dx, dy, 0)
        pupil = CATransform3DScale(pupil, pose.pupilScale, pose.pupilScale, 1)
        pupilGroup.transform = pupil

        eyelidLayer.opacity = Float(max(0, min(1, pose.blink)))
        for wheels in wheelLayers { wheels.opacity = pose.showSkates ? 1 : 0 }

        applyRootTransform()
    }

    // MARK: Hit testing — only the duck's silhouette captures the mouse

    /// Converts a point in view coordinates to design space (undoing scale/flip).
    private func designPoint(fromViewPoint p: CGPoint) -> CGPoint {
        let originX = bounds.midX
        let originY = Self.bottomMarginDesign * scale
        let designX = (p.x - originX) / (scale * facing) + DuckPaths.designSize.width / 2
        let designY = (p.y - originY) / scale
        return CGPoint(x: designX, y: designY)
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        let local = convert(point, from: superview)
        let d = designPoint(fromViewPoint: local)
        return spec.silhouette.contains(d) ? self : nil
    }

    override func mouseDown(with event: NSEvent) { delegate?.duckMouseDown(event) }
    override func mouseDragged(with event: NSEvent) { delegate?.duckMouseDragged(event) }
    override func mouseUp(with event: NSEvent) { delegate?.duckMouseUp(event) }

    /// Design-space position of the eye converted to view coordinates (for cursor tracking).
    var eyePositionInView: CGPoint {
        let e = spec.eyeCenter
        let originX = bounds.midX
        let originY = Self.bottomMarginDesign * scale
        return CGPoint(x: originX + (e.x - DuckPaths.designSize.width / 2) * scale * facing,
                       y: originY + e.y * scale)
    }
}
