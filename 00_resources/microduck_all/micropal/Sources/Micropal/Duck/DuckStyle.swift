import AppKit

/// The three selectable duck designs. Each style supplies a complete geometry
/// spec; DuckLayerView builds the same animation rig (hips, ankles, torso,
/// neck-top, eye) from whichever spec is active, so every style animates.
enum DuckStyle: Int, CaseIterable {
    case classic = 0   // the original bubbly cartoon
    case faithful = 1  // design A: angular clamshell, crouched like the robot
    case boxbot = 2    // design B: slab head + grille chest, BD-droid industrial

    var displayName: String {
        switch self {
        case .classic: return "Classic"
        case .faithful: return "Faithful"
        case .boxbot: return "Boxbot"
        }
    }

    var spec: DuckStyleSpec {
        switch self {
        case .classic: return .classic
        case .faithful: return .faithful
        case .boxbot: return .boxbot
        }
    }
}

/// What a shape is, which decides its fill color for the active palette.
enum PartRole {
    case shell, shellShade, black, dark, visor, screw
    case accent, accentDark, feetTop, feetSole
    case eyeRingRole, lensRole, eyelidRole // used by the view's built-in eye
}

struct StylePart {
    let path: CGPath
    let role: PartRole
}

/// Full geometry of one duck design, in the shared 100x120 design space
/// (origin bottom-left, feet on y = 0, facing right).
struct DuckStyleSpec {
    let backHip, frontHip, backAnkle, frontAnkle: CGPoint
    let torsoPivot, neckTop: CGPoint
    let eyeCenter: CGPoint
    let eyeRadius: CGFloat
    let backLegParts, frontLegParts: [StylePart]     // hip to shank
    let backFootParts, frontFootParts: [StylePart]   // sole, shoe, detail dots
    let torsoParts: [StylePart]                      // body shell + neck
    let headParts: [StylePart]                       // everything but the eye
    let silhouette: CGPath                           // hit-test union
}

// MARK: - Path builders

private func poly(_ pts: [(CGFloat, CGFloat)], _ radii: [CGFloat]) -> CGPath {
    let p = CGMutablePath()
    let n = pts.count
    p.move(to: CGPoint(x: (pts[n - 1].0 + pts[0].0) / 2, y: (pts[n - 1].1 + pts[0].1) / 2))
    for i in 0..<n {
        p.addArc(tangent1End: CGPoint(x: pts[i].0, y: pts[i].1),
                 tangent2End: CGPoint(x: pts[(i + 1) % n].0, y: pts[(i + 1) % n].1),
                 radius: radii[i])
    }
    p.closeSubpath()
    return p
}

private func poly(_ pts: [(CGFloat, CGFloat)], r: CGFloat) -> CGPath {
    poly(pts, Array(repeating: r, count: pts.count))
}

private func rrect(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ r: CGFloat) -> CGPath {
    CGPath(roundedRect: CGRect(x: x, y: y, width: w, height: h),
           cornerWidth: r, cornerHeight: r, transform: nil)
}

private func circle(_ cx: CGFloat, _ cy: CGFloat, _ r: CGFloat) -> CGPath {
    CGPath(ellipseIn: CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r), transform: nil)
}

private func circles(_ pts: [(CGFloat, CGFloat)], r: CGFloat) -> CGPath {
    let p = CGMutablePath()
    for (x, y) in pts { p.addPath(circle(x, y, r)) }
    return p
}

private func union(_ paths: [CGPath]) -> CGPath {
    let p = CGMutablePath()
    for path in paths { p.addPath(path) }
    return p
}

// MARK: - Classic (delegates to the original DuckPaths geometry)

extension DuckStyleSpec {
    static let classic = DuckStyleSpec(
        backHip: DuckPaths.backHip, frontHip: DuckPaths.frontHip,
        backAnkle: DuckPaths.backAnkle, frontAnkle: DuckPaths.frontAnkle,
        torsoPivot: DuckPaths.torsoPivot, neckTop: DuckPaths.neckTop,
        eyeCenter: DuckPaths.eyeCenter, eyeRadius: 11,
        backLegParts: [
            StylePart(path: DuckPaths.thighServo(hipX: DuckPaths.backHip.x), role: .black),
            StylePart(path: DuckPaths.thighPlate(hipX: DuckPaths.backHip.x), role: .shell),
            StylePart(path: DuckPaths.shank(hipX: DuckPaths.backHip.x), role: .black),
        ],
        frontLegParts: [
            StylePart(path: DuckPaths.thighServo(hipX: DuckPaths.frontHip.x), role: .black),
            StylePart(path: DuckPaths.thighPlate(hipX: DuckPaths.frontHip.x), role: .shell),
            StylePart(path: DuckPaths.shank(hipX: DuckPaths.frontHip.x), role: .black),
        ],
        backFootParts: [
            StylePart(path: DuckPaths.footSole(ankleX: DuckPaths.backAnkle.x), role: .feetSole),
            StylePart(path: DuckPaths.footTop(ankleX: DuckPaths.backAnkle.x), role: .feetTop),
        ],
        frontFootParts: [
            StylePart(path: DuckPaths.footSole(ankleX: DuckPaths.frontAnkle.x), role: .feetSole),
            StylePart(path: DuckPaths.footTop(ankleX: DuckPaths.frontAnkle.x), role: .feetTop),
        ],
        torsoParts: [
            StylePart(path: DuckPaths.bodyShell(), role: .shell),
            StylePart(path: DuckPaths.bodyShading(), role: .shellShade),
            StylePart(path: DuckPaths.neck(), role: .black),
            StylePart(path: DuckPaths.neckSegments(), role: .dark),
        ],
        headParts: [
            StylePart(path: DuckPaths.headShell(), role: .shell),
            StylePart(path: DuckPaths.visor(), role: .visor),
            StylePart(path: DuckPaths.beak(), role: .accent),
        ],
        silhouette: DuckPaths.silhouette())
}

// MARK: - Faithful (design A): angular clamshell head, crouched stance

extension DuckStyleSpec {
    /// Bent digitigrade leg drawn hip → backward knee → forward ankle.
    private static func faithfulLeg(hip: CGPoint, knee: CGPoint, ankle: CGPoint) -> [StylePart] {
        let hx = hip.x, kx = knee.x
        return [
            StylePart(path: poly([(hx - 4, hip.y + 2), (hx + 4, hip.y + 1),
                                  (kx + 4, knee.y - 3), (kx - 4, knee.y - 1)], r: 2),
                      role: .black),                                  // thigh servo
            StylePart(path: poly([(hx - 11, hip.y - 3), (hx + 8, hip.y - 1),
                                  (kx + 3, knee.y - 9)], [3, 3, 4]),
                      role: .shell),                                  // triangular guard
            StylePart(path: poly([(kx - 3, knee.y + 2), (kx + 4, knee.y + 3),
                                  (ankle.x + 3, ankle.y + 1), (ankle.x - 4, ankle.y - 2)],
                                 r: 2),
                      role: .black),                                  // shank
        ]
    }

    private static func faithfulFoot(ankleX x: CGFloat) -> [StylePart] {
        [
            StylePart(path: rrect(x - 11, 0, 28, 4, 2), role: .feetSole),
            StylePart(path: poly([(x - 10, 1), (x - 10, 11), (x + 2, 12),
                                  (x + 16, 3), (x + 16, 1)], r: 2), role: .feetTop),
            StylePart(path: circles([(x - 4, 6.5), (x + 1, 6.5), (x + 6, 5.5)], r: 1),
                      role: .visor),
        ]
    }

    static let faithful: DuckStyleSpec = {
        let backHip = CGPoint(x: 37, y: 48), frontHip = CGPoint(x: 49, y: 48)
        let backKnee = CGPoint(x: 31, y: 30), frontKnee = CGPoint(x: 43, y: 30)
        let backAnkle = CGPoint(x: 41, y: 10), frontAnkle = CGPoint(x: 53, y: 10)
        return DuckStyleSpec(
            backHip: backHip, frontHip: frontHip,
            backAnkle: backAnkle, frontAnkle: frontAnkle,
            torsoPivot: CGPoint(x: 44, y: 46), neckTop: CGPoint(x: 54, y: 81),
            eyeCenter: CGPoint(x: 64, y: 99), eyeRadius: 10,
            backLegParts: faithfulLeg(hip: backHip, knee: backKnee, ankle: backAnkle),
            frontLegParts: faithfulLeg(hip: frontHip, knee: frontKnee, ankle: frontAnkle),
            backFootParts: faithfulFoot(ankleX: backAnkle.x),
            frontFootParts: faithfulFoot(ankleX: frontAnkle.x),
            torsoParts: [
                StylePart(path: rrect(18, 38, 36, 26, 7), role: .shell),
                StylePart(path: rrect(20, 38, 32, 7, 3.5), role: .shellShade),
                StylePart(path: circles([(23, 58), (23, 52), (23, 46)], r: 1.2), role: .dark),
                StylePart(path: rrect(46, 54, 13, 14, 2), role: .black),   // neck brick 1
                StylePart(path: rrect(49, 68, 12, 14, 2), role: .black),   // neck brick 2
                StylePart(path: circles([(48.5, 65), (56.5, 57), (51.5, 79), (58.5, 71)],
                                        r: 1), role: .screw),
            ],
            headParts: [
                StylePart(path: poly([(30, 85), (28, 107), (52, 117), (84, 111),
                                      (94, 93), (88, 83)], [4, 12, 14, 8, 5, 3]),
                          role: .shell),                                   // clamshell
                StylePart(path: poly([(36, 85), (38, 101), (74, 97), (90, 85)],
                                     [2, 6, 6, 2]), role: .visor),         // face panel
                StylePart(path: poly([(44, 83), (44, 86.5), (90, 83.5), (91, 80)],
                                     r: 1.5), role: .accent),              // trim rim
                StylePart(path: poly([(52, 81), (92, 82), (92, 78), (52, 77)],
                                     r: 1.5), role: .visor),               // mouth slot
                StylePart(path: poly([(52, 79), (95, 80.5), (98, 70), (55, 67)],
                                     r: 3), role: .accent),                // beak plate
                StylePart(path: circle(82, 101, 1.6), role: .visor),       // sensor vent
            ],
            silhouette: union([
                rrect(26, 70, 72, 44, 12),  // head
                rrect(14, 34, 46, 30, 8),   // body
                rrect(24, 0, 48, 40, 6),    // legs + feet
            ]))
    }()
}

// MARK: - Boxbot (design B): slab head, antenna, grille chest

extension DuckStyleSpec {
    private static func boxbotLeg(hipX: CGFloat) -> [StylePart] {
        [
            StylePart(path: rrect(hipX - 5, 42, 10, 10, 2), role: .black),   // hip servo
            StylePart(path: poly([(hipX - 8, 46), (hipX + 6, 46),
                                  (hipX + 9, 28), (hipX - 5, 28)], r: 2),
                      role: .shell),                                          // slanted guard
            StylePart(path: rrect(hipX - 4, 20, 9, 10, 2), role: .black),    // knee box
            StylePart(path: rrect(hipX - 2, 5, 6, 18, 1.5), role: .black),   // shank
        ]
    }

    private static func boxbotFoot(ankleX x: CGFloat) -> [StylePart] {
        [
            StylePart(path: rrect(x - 10, 0, 29, 3.5, 1.5), role: .feetSole),
            StylePart(path: poly([(x - 9, 1), (x - 9, 10), (x + 9, 10),
                                  (x + 17, 4), (x + 17, 1)], r: 1.5), role: .feetTop),
            StylePart(path: circles([(x - 3, 5.5), (x + 3, 5.5)], r: 1), role: .visor),
        ]
    }

    static let boxbot: DuckStyleSpec = {
        DuckStyleSpec(
            backHip: CGPoint(x: 37, y: 46), frontHip: CGPoint(x: 49, y: 46),
            backAnkle: CGPoint(x: 39, y: 8), frontAnkle: CGPoint(x: 51, y: 8),
            torsoPivot: CGPoint(x: 39, y: 48), neckTop: CGPoint(x: 55, y: 88),
            eyeCenter: CGPoint(x: 64, y: 102), eyeRadius: 8.5,
            backLegParts: boxbotLeg(hipX: 37),
            frontLegParts: boxbotLeg(hipX: 49),
            backFootParts: boxbotFoot(ankleX: 39),
            frontFootParts: boxbotFoot(ankleX: 51),
            torsoParts: [
                StylePart(path: rrect(20, 36, 38, 34, 4), role: .shell),
                StylePart(path: rrect(20, 62, 38, 5, 2.5), role: .accent),   // top stripe
                StylePart(path: union([rrect(26, 42, 22, 2.5, 1.25),         // intake grille
                                       rrect(26, 47, 20, 2.5, 1.25),
                                       rrect(26, 52, 18, 2.5, 1.25)]), role: .dark),
                StylePart(path: circles([(24, 39.5), (54, 39.5), (24, 58), (54, 58)],
                                        r: 1.2), role: .dark),
                StylePart(path: rrect(50, 64, 10, 28, 2), role: .black),     // neck column
                StylePart(path: union([rrect(50.5, 72, 9, 2, 1),
                                       rrect(50.5, 80, 9, 2, 1)]), role: .dark),
            ],
            headParts: [
                StylePart(path: rrect(33.5, 112, 1.6, 12, 0.8), role: .black), // antenna
                StylePart(path: circle(34.3, 125, 1.8), role: .accent),        // antenna tip
                StylePart(path: poly([(26, 94), (28, 114), (96, 108), (92, 88)],
                                     r: 3), role: .shell),                     // slab
                StylePart(path: poly([(28, 92), (29, 97), (92, 91), (91, 87)],
                                     r: 1.5), role: .shellShade),              // underside
                StylePart(path: poly([(84, 90), (87, 108), (96, 108), (92, 88)],
                                     r: 2), role: .visor),                     // sensor face
                StylePart(path: circles([(90.5, 102), (89.5, 95)], r: 2.2),
                          role: .accent),                                      // lamps
                StylePart(path: rrect(85, 83, 14, 8, 2), role: .accent),       // beak block
                StylePart(path: circles([(38, 108), (44, 107.4), (50, 106.8)],
                                        r: 1), role: .dark),                   // rivets
            ],
            silhouette: union([
                rrect(24, 84, 76, 34, 6),   // head slab
                rrect(18, 32, 44, 42, 6),   // chest
                rrect(26, 0, 46, 34, 4),    // legs + feet
            ]))
    }()
}
