import Foundation

/// A complete pose for one frame, in design-space units (see DuckPaths.designSize).
/// Produced by DuckStateMachine, consumed by DuckLayerView. Pure value type.
struct DuckPose {
    // Legs: rotation at the hip in radians; + swings the leg toward the beak.
    var frontLegAngle: CGFloat = 0
    var backLegAngle: CGFloat = 0
    // Feet: rotation at the ankle, used to keep feet flat mid-stride.
    var frontFootAngle: CGFloat = 0
    var backFootAngle: CGFloat = 0

    // Torso group (body shell + neck + head ride together).
    var bodyBobY: CGFloat = 0
    var bodyTilt: CGFloat = 0

    // Head group, relative to the torso.
    var headBobY: CGFloat = 0
    var headTilt: CGFloat = 0

    // Eye.
    var blink: CGFloat = 0            // 0 open … 1 closed
    var pupilOffset: CGPoint = .zero  // clamped to ~3 design units by the view
    var pupilScale: CGFloat = 1       // >1 for the "look at user" reaction

    // Whole-duck effects, applied at the root (pivot = bottom-center, at the feet).
    var bodyRotation: CGFloat = 0     // fall over: rotates the whole duck
    var squash: CGFloat = 1           // <1 squashes vertically (landing), >1 stretches

    var showSkates: Bool = false

    static let neutral = DuckPose()
}
