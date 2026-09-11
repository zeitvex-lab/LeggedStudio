import AppKit

/// Pure CGPath builders for every part of the duck, in a fixed design space:
/// 100 wide x 120 tall, origin bottom-left, feet on y = 0, duck facing RIGHT.
/// Facing left is a single scaleX = -1 flip on the root layer.
enum DuckPaths {
    static let designSize = CGSize(width: 100, height: 120)
    static let designRect = CGRect(origin: .zero, size: designSize)

    // Joint pivots (absolute design coordinates).
    static let backHip = CGPoint(x: 37, y: 50)
    static let frontHip = CGPoint(x: 49, y: 50)
    static let backAnkle = CGPoint(x: 39, y: 10)
    static let frontAnkle = CGPoint(x: 51, y: 10)
    static let torsoPivot = CGPoint(x: 44, y: 50)
    static let neckTop = CGPoint(x: 54, y: 86)   // head group pivot
    static let eyeCenter = CGPoint(x: 73, y: 100)

    private static func rounded(_ rect: CGRect, _ radius: CGFloat) -> CGPath {
        CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)
    }

    // MARK: Head (dominates the body)

    /// Big horseshoe / half-cylinder head shell.
    static func headShell() -> CGPath {
        let p = CGMutablePath()
        // Rounded profile: tall arched back, long flat-ish top, blunt front.
        p.move(to: CGPoint(x: 33, y: 84))
        p.addCurve(to: CGPoint(x: 28, y: 104),
                   control1: CGPoint(x: 29, y: 88), control2: CGPoint(x: 28, y: 96))
        p.addCurve(to: CGPoint(x: 48, y: 118),
                   control1: CGPoint(x: 28, y: 112), control2: CGPoint(x: 36, y: 118))
        p.addCurve(to: CGPoint(x: 88, y: 114),
                   control1: CGPoint(x: 62, y: 118), control2: CGPoint(x: 79, y: 118))
        p.addCurve(to: CGPoint(x: 92, y: 92),
                   control1: CGPoint(x: 95, y: 110), control2: CGPoint(x: 94, y: 98))
        p.addCurve(to: CGPoint(x: 84, y: 84),
                   control1: CGPoint(x: 91, y: 88), control2: CGPoint(x: 88, y: 85))
        p.closeSubpath()
        return p
    }

    /// Dark visor: the recessed face panel on the lower front of the head.
    /// The eye ring overlaps its top edge, like the camera on the real robot.
    static func visor() -> CGPath {
        rounded(CGRect(x: 44, y: 84, width: 48, height: 14), 7)
    }

    /// The accent-colored beak: the head's protruding lower lip, hugging the
    /// bottom-front of the shell and poking out past it.
    static func beak() -> CGPath {
        let p = CGMutablePath()
        p.move(to: CGPoint(x: 54, y: 86))
        p.addLine(to: CGPoint(x: 92, y: 86))
        p.addCurve(to: CGPoint(x: 99, y: 81),
                   control1: CGPoint(x: 96, y: 86), control2: CGPoint(x: 99, y: 84))
        p.addCurve(to: CGPoint(x: 93, y: 76),
                   control1: CGPoint(x: 99, y: 78), control2: CGPoint(x: 97, y: 76))
        p.addLine(to: CGPoint(x: 60, y: 76))
        p.addCurve(to: CGPoint(x: 54, y: 86),
                   control1: CGPoint(x: 55, y: 76), control2: CGPoint(x: 52, y: 82))
        p.closeSubpath()
        return p
    }

    static func eyeRing() -> CGPath {
        CGPath(ellipseIn: CGRect(x: eyeCenter.x - 11, y: eyeCenter.y - 11, width: 22, height: 22),
               transform: nil)
    }

    static func eyeLens() -> CGPath {
        CGPath(ellipseIn: CGRect(x: eyeCenter.x - 6, y: eyeCenter.y - 6, width: 12, height: 12),
               transform: nil)
    }

    static func eyeHighlight() -> CGPath {
        CGPath(ellipseIn: CGRect(x: eyeCenter.x + 0.5, y: eyeCenter.y + 1.5, width: 4.5, height: 4.5),
               transform: nil)
    }

    /// Shell-colored disc that covers the eye when blinking (opacity-driven).
    static func eyelid() -> CGPath {
        CGPath(ellipseIn: CGRect(x: eyeCenter.x - 11.5, y: eyeCenter.y - 11.5, width: 23, height: 23),
               transform: nil)
    }

    // MARK: Neck & body

    /// Thin black articulated servo neck.
    static func neck() -> CGPath {
        rounded(CGRect(x: 49, y: 58, width: 10, height: 28), 4)
    }

    /// Two thin separator lines that hint at stacked servo blocks.
    static func neckSegments() -> CGPath {
        let p = CGMutablePath()
        p.addPath(rounded(CGRect(x: 49.5, y: 66, width: 9, height: 2), 1))
        p.addPath(rounded(CGRect(x: 49.5, y: 74, width: 9, height: 2), 1))
        return p
    }

    /// Small rounded backpack-style body shell, sits behind the neck.
    static func bodyShell() -> CGPath {
        rounded(CGRect(x: 22, y: 45, width: 36, height: 27), 10)
    }

    /// Subtle darker shading along the bottom of the body shell.
    static func bodyShading() -> CGPath {
        rounded(CGRect(x: 24, y: 45, width: 32, height: 8), 4)
    }

    // MARK: Legs (digitigrade; hipX picks front vs back leg)

    /// Black servo block at the hip/thigh.
    static func thighServo(hipX: CGFloat) -> CGPath {
        rounded(CGRect(x: hipX - 5, y: 30, width: 10, height: 22), 3)
    }

    /// Pastel guard plate over the thigh (rounded triangle-ish wedge). Sits
    /// below the body shell so the black hip servo peeks out between them.
    static func thighPlate(hipX: CGFloat) -> CGPath {
        let p = CGMutablePath()
        p.move(to: CGPoint(x: hipX - 9, y: 44))
        p.addLine(to: CGPoint(x: hipX + 6, y: 44))
        p.addCurve(to: CGPoint(x: hipX + 3, y: 26),
                   control1: CGPoint(x: hipX + 8, y: 38), control2: CGPoint(x: hipX + 7, y: 29))
        p.addCurve(to: CGPoint(x: hipX - 7, y: 29),
                   control1: CGPoint(x: hipX - 1, y: 22), control2: CGPoint(x: hipX - 6, y: 24))
        p.addCurve(to: CGPoint(x: hipX - 9, y: 44),
                   control1: CGPoint(x: hipX - 9, y: 34), control2: CGPoint(x: hipX - 10, y: 40))
        p.closeSubpath()
        return p
    }

    /// Lower leg servo: knee block down to the ankle.
    static func shank(hipX: CGFloat) -> CGPath {
        rounded(CGRect(x: hipX - 3.5, y: 8, width: 8, height: 26), 3)
    }

    /// Chunky upper foot (feetTop color). Extends forward of the ankle.
    static func footTop(ankleX: CGFloat) -> CGPath {
        let p = CGMutablePath()
        p.move(to: CGPoint(x: ankleX - 9, y: 4))
        p.addLine(to: CGPoint(x: ankleX - 9, y: 10))
        p.addCurve(to: CGPoint(x: ankleX + 2, y: 13),
                   control1: CGPoint(x: ankleX - 9, y: 13), control2: CGPoint(x: ankleX - 2, y: 13))
        p.addCurve(to: CGPoint(x: ankleX + 15, y: 6),
                   control1: CGPoint(x: ankleX + 9, y: 13), control2: CGPoint(x: ankleX + 15, y: 10))
        p.addLine(to: CGPoint(x: ankleX + 15, y: 4))
        p.closeSubpath()
        return p
    }

    /// Foot sole (feetSole color), slightly wider than the top.
    static func footSole(ankleX: CGFloat) -> CGPath {
        rounded(CGRect(x: ankleX - 10, y: 0, width: 27, height: 5.5), 2.75)
    }

    /// Two little roller-skate wheels under a foot (shown only while skating).
    static func skateWheels(ankleX: CGFloat) -> CGPath {
        let p = CGMutablePath()
        p.addEllipse(in: CGRect(x: ankleX - 8, y: -4.5, width: 7, height: 7))
        p.addEllipse(in: CGRect(x: ankleX + 7, y: -4.5, width: 7, height: 7))
        return p
    }

    // MARK: Hit testing

    /// Cheap union silhouette for hit-testing: clicks outside pass through.
    static func silhouette() -> CGPath {
        let p = CGMutablePath()
        p.addPath(rounded(CGRect(x: 26, y: 76, width: 73, height: 44), 14)) // head
        p.addPath(rounded(CGRect(x: 20, y: 42, width: 42, height: 34), 10)) // body
        p.addPath(rounded(CGRect(x: 26, y: 0, width: 42, height: 46), 8))   // legs + feet
        return p
    }
}
