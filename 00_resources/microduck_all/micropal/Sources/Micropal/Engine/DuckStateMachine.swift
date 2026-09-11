import Foundation

struct BehaviorConfig {
    var activity: Double = 1.0        // 0.25 … 3.0, scales how often behaviors fire
    var clickEnabled = true
    var dragEnabled = true
    var cursorEnabled = true
    var kickEnabled = true
    var peckEnabled = true
    var fallEnabled = true
    var skateEnabled = true
    var sitEnabled = true
}

enum DuckState: String {
    case idle, walking, sitting, kick, peck
    case fallOver, gettingUp, skate
    case dragged, falling, landRecover
    case clickHop, clickLook
    case walkToCursor
}

enum ClickReactKind { case hop, kick, lookAtUser }

/// Pure-math animation state machine. tick(dt) advances time and returns the pose
/// plus a horizontal speed in design-units/second. The controller owns world
/// position, facing, and vertical physics.
final class DuckStateMachine {
    var config = BehaviorConfig()

    private(set) var state: DuckState = .idle
    private var stateTime: TimeInterval = 0
    private var stateDuration: TimeInterval = 3

    private var walkPhase: Double = 0
    private var clock: TimeInterval = 0

    // Blinking (shared across grounded states).
    private var nextBlinkAt: TimeInterval = 1.5
    private var blinkStartedAt: TimeInterval = -1

    // Idle look-around.
    private var lookTilt: Double = 0
    private var lookTarget: Double = 0
    private var nextLookAt: TimeInterval = 2

    struct TickOutput {
        var pose = DuckPose.neutral
        var speedDesign: CGFloat = 0   // horizontal speed along facing, design units/s
    }

    /// Whether the controller may steer the pupil toward the cursor right now.
    var pupilFollowsCursor: Bool {
        switch state {
        case .idle, .walking, .sitting, .walkToCursor, .skate: return true
        default: return false
        }
    }

    var isInterruptibleByClick: Bool {
        switch state {
        case .dragged, .falling, .fallOver, .gettingUp, .landRecover, .clickHop: return false
        default: return true
        }
    }

    // MARK: External events (from PetController)

    func beginDrag() { enter(.dragged, duration: .infinity) }

    func endDragFalling() { enter(.falling, duration: .infinity) }

    /// Called when vertical physics puts the duck back on the ground.
    func landed(hard: Bool) {
        switch state {
        case .falling:
            if hard && config.fallEnabled {
                enter(.fallOver, duration: 1.5)
            } else {
                enter(.landRecover, duration: 0.55)
            }
        case .clickHop:
            enter(.landRecover, duration: 0.4)
        default:
            break
        }
    }

    /// Picks and starts a click reaction; returns it so the controller can apply
    /// a hop impulse. Returns nil while mid-fall/drag.
    func clickReact() -> ClickReactKind? {
        guard isInterruptibleByClick else { return nil }
        var kinds: [ClickReactKind] = [.hop, .lookAtUser]
        if config.kickEnabled { kinds.append(.kick) }
        let kind = kinds.randomElement()!
        switch kind {
        case .hop: enter(.clickHop, duration: .infinity) // ended by landed()
        case .kick: enter(.kick, duration: 0.9)
        case .lookAtUser: enter(.clickLook, duration: 1.4)
        }
        return kind
    }

    /// Controller reports the duck reached (or gave up reaching) the cursor.
    func finishWalkToCursor() {
        if state == .walkToCursor { enter(.idle, duration: randomDuration(2...4)) }
    }

    // MARK: Tick

    func tick(dt: TimeInterval, cursorAvailable: Bool) -> TickOutput {
        clock += dt
        stateTime += dt

        if stateTime >= stateDuration {
            advance(cursorAvailable: cursorAvailable)
        }

        var out = TickOutput()
        switch state {
        case .idle: poseIdle(&out, dt: dt)
        case .walking, .walkToCursor: poseWalking(&out, dt: dt)
        case .sitting: poseSitting(&out)
        case .kick: poseKick(&out)
        case .peck: posePeck(&out)
        case .fallOver: poseFallOver(&out)
        case .gettingUp: poseGettingUp(&out)
        case .skate: poseSkate(&out, dt: dt)
        case .dragged: poseDragged(&out)
        case .falling: poseFalling(&out)
        case .landRecover: poseLandRecover(&out)
        case .clickHop: poseClickHop(&out)
        case .clickLook: poseClickLook(&out)
        }

        applyBlink(&out.pose)
        return out
    }

    // MARK: Scheduling

    private func enter(_ newState: DuckState, duration: TimeInterval) {
        state = newState
        stateTime = 0
        stateDuration = duration
    }

    private func randomDuration(_ range: ClosedRange<Double>) -> TimeInterval {
        Double.random(in: range) / max(0.25, config.activity)
    }

    private func advance(cursorAvailable: Bool) {
        switch state {
        case .idle, .walking, .sitting:
            scheduleNext(cursorAvailable: cursorAvailable)
        case .kick, .peck, .skate, .landRecover, .clickLook:
            enter(Bool.random() ? .walking : .idle, duration: randomDuration(2...5))
        case .fallOver:
            enter(.gettingUp, duration: 1.0)
        case .gettingUp:
            enter(.idle, duration: randomDuration(1.5...3))
        case .walkToCursor:
            // Timeout safety; normally ended by finishWalkToCursor().
            enter(.idle, duration: randomDuration(2...4))
        case .dragged, .falling, .clickHop:
            break // ended by external events
        }
    }

    private func scheduleNext(cursorAvailable: Bool) {
        var weighted: [(DuckState, Double)] = [(.walking, 40), (.idle, 25)]
        if config.peckEnabled { weighted.append((.peck, 10)) }
        if config.sitEnabled { weighted.append((.sitting, 8)) }
        if config.kickEnabled { weighted.append((.kick, 6)) }
        if config.skateEnabled { weighted.append((.skate, 6)) }
        if config.fallEnabled { weighted.append((.fallOver, 3)) }
        if config.cursorEnabled && cursorAvailable { weighted.append((.walkToCursor, 4)) }

        let total = weighted.reduce(0) { $0 + $1.1 }
        var roll = Double.random(in: 0..<total)
        var picked: DuckState = .walking
        for (candidate, weight) in weighted {
            roll -= weight
            if roll <= 0 { picked = candidate; break }
        }

        switch picked {
        case .walking: enter(.walking, duration: randomDuration(2.5...6))
        case .idle: enter(.idle, duration: randomDuration(2...5))
        case .peck: enter(.peck, duration: 1.6)
        case .sitting: enter(.sitting, duration: randomDuration(3...5.5))
        case .kick: enter(.kick, duration: 0.9)
        case .skate: enter(.skate, duration: 2.8)
        case .fallOver: enter(.fallOver, duration: 1.5)
        case .walkToCursor: enter(.walkToCursor, duration: 7) // timeout cap
        default: enter(.idle, duration: 3)
        }
    }

    // MARK: Easing helpers

    private func smoothstep(_ x: Double) -> Double {
        let t = max(0, min(1, x))
        return t * t * (3 - 2 * t)
    }

    /// 0→1 during the first `rise` seconds, 1 until the last `fall` seconds, back to 0.
    private func plateau(rise: Double, fall: Double) -> Double {
        guard stateDuration.isFinite else { return smoothstep(stateTime / rise) }
        let up = smoothstep(stateTime / rise)
        let down = smoothstep((stateDuration - stateTime) / fall)
        return min(up, down)
    }

    // MARK: Blinking

    private func applyBlink(_ pose: inout DuckPose) {
        switch state {
        case .dragged, .falling: return // handled by their own poses
        case .fallOver:
            if stateTime < 0.9 { pose.blink = 1 } // eyes shut on impact
            return
        default: break
        }
        if blinkStartedAt < 0 && clock >= nextBlinkAt {
            blinkStartedAt = clock
        }
        if blinkStartedAt >= 0 {
            let t = clock - blinkStartedAt
            let duration = 0.16
            if t >= duration {
                blinkStartedAt = -1
                nextBlinkAt = clock + Double.random(in: 2...5)
            } else {
                pose.blink = CGFloat(sin(.pi * t / duration))
            }
        }
    }

    // MARK: Pose generators

    private func poseWalking(_ out: inout TickOutput, dt: TimeInterval) {
        walkPhase += dt * 7.0
        let swing = 0.32 * sin(walkPhase)
        out.pose.frontLegAngle = swing
        out.pose.backLegAngle = -swing
        out.pose.frontFootAngle = -swing * 0.55
        out.pose.backFootAngle = swing * 0.55
        out.pose.bodyBobY = 1.4 * sin(2 * walkPhase)
        out.pose.headBobY = -1.0 * sin(2 * walkPhase + 0.6)
        out.pose.bodyTilt = 0.03 * sin(walkPhase)
        out.speedDesign = state == .walkToCursor ? 62 : 55
    }

    private func poseIdle(_ out: inout TickOutput, dt: TimeInterval) {
        out.pose.bodyBobY = 1.1 * sin(clock * 2.4)
        out.pose.headBobY = 0.6 * sin(clock * 2.4 + 0.8)
        if clock >= nextLookAt {
            lookTarget = Double.random(in: -0.12...0.18)
            nextLookAt = clock + Double.random(in: 1.5...3.5)
        }
        lookTilt += (lookTarget - lookTilt) * min(1, dt * 6)
        out.pose.headTilt = lookTilt
    }

    private func poseSitting(_ out: inout TickOutput) {
        let e = plateau(rise: 0.5, fall: 0.5)
        out.pose.bodyBobY = -13 * e
        out.pose.headBobY = -3 * e
        out.pose.frontLegAngle = 0.55 * e
        out.pose.backLegAngle = -0.55 * e
        out.pose.frontFootAngle = -0.55 * e
        out.pose.backFootAngle = 0.55 * e
        out.pose.bodyTilt = -0.05 * e
    }

    private func poseKick(_ out: inout TickOutput) {
        let t = stateTime
        var leg: Double = 0
        if t < 0.3 {
            leg = -0.5 * smoothstep(t / 0.3)                     // wind-up
        } else if t < 0.45 {
            leg = -0.5 + 1.6 * smoothstep((t - 0.3) / 0.15)      // strike
        } else {
            leg = 1.1 * (1 - smoothstep((t - 0.45) / 0.4))       // recover
        }
        out.pose.frontLegAngle = leg
        out.pose.frontFootAngle = -leg * 0.4
        out.pose.bodyTilt = -0.10 * smoothstep(min(t / 0.45, 1)) * (t < 0.7 ? 1 : (1 - smoothstep((t - 0.7) / 0.2)))
        out.pose.headBobY = t > 0.3 && t < 0.6 ? -2 : 0
    }

    private func posePeck(_ out: inout TickOutput) {
        // Two quick dips of the beak toward the ground.
        let dip = max(0, sin(stateTime * .pi * 2 / 0.8))
        let overall = plateau(rise: 0.25, fall: 0.3)
        out.pose.headTilt = -0.55 * dip * overall
        out.pose.headBobY = -8 * dip * overall
        out.pose.bodyTilt = -0.18 * dip * overall
        out.pose.bodyBobY = -3 * dip * overall
    }

    private func poseFallOver(_ out: inout TickOutput) {
        let t = stateTime
        if t < 0.45 {
            let p = t / 0.45
            out.pose.bodyRotation = .pi / 2 * p * p // ease-in: tips over backward
        } else {
            let wobble = 0.06 * sin((t - 0.45) * 18) * max(0, 1 - (t - 0.45) * 2)
            out.pose.bodyRotation = .pi / 2 + wobble
            let twitch = 0.22 * sin(t * 11) * max(0, 1 - (t - 0.45))
            out.pose.frontLegAngle = twitch
            out.pose.backLegAngle = -twitch
        }
    }

    private func poseGettingUp(_ out: inout TickOutput) {
        let p = smoothstep(stateTime / 0.85)
        out.pose.bodyRotation = .pi / 2 * (1 - p)
        if p < 0.6 {
            let scramble = 0.3 * sin(stateTime * 20) * (1 - p)
            out.pose.frontLegAngle = scramble
            out.pose.backLegAngle = -scramble
        }
        out.pose.headTilt = 0.1 * (1 - p)
    }

    private func poseSkate(_ out: inout TickOutput, dt: TimeInterval) {
        out.pose.showSkates = true
        out.pose.frontLegAngle = 0.25
        out.pose.backLegAngle = -0.25
        out.pose.frontFootAngle = -0.25
        out.pose.backFootAngle = 0.25
        out.pose.bodyTilt = 0.09
        out.pose.bodyBobY = -2
        out.speedDesign = CGFloat(150 * sin(.pi * min(1, stateTime / stateDuration)))
    }

    private func poseDragged(_ out: inout TickOutput) {
        let t = stateTime
        out.pose.frontLegAngle = 0.5 * sin(t * 14)
        out.pose.backLegAngle = 0.5 * sin(t * 14 + .pi)
        out.pose.frontFootAngle = -0.35
        out.pose.backFootAngle = -0.35
        out.pose.bodyTilt = 0.1 * sin(t * 5)
        out.pose.headTilt = 0.08 * sin(t * 4)
        out.pose.pupilScale = 1.15
    }

    private func poseFalling(_ out: inout TickOutput) {
        out.pose.frontLegAngle = 0.35
        out.pose.backLegAngle = -0.35
        out.pose.frontFootAngle = -0.45
        out.pose.backFootAngle = -0.2
        out.pose.headTilt = 0.15
        out.pose.pupilScale = 1.2
    }

    private func poseLandRecover(_ out: inout TickOutput) {
        let p = min(1, stateTime / 0.35)
        out.pose.squash = 1 - 0.28 * sin(.pi * p)
        out.pose.bodyBobY = -4 * sin(.pi * p)
    }

    private func poseClickHop(_ out: inout TickOutput) {
        out.pose.frontLegAngle = 0.4
        out.pose.backLegAngle = -0.4
        out.pose.frontFootAngle = -0.5
        out.pose.backFootAngle = -0.3
        out.pose.squash = 1.06
        out.pose.headTilt = 0.08
    }

    private func poseClickLook(_ out: inout TickOutput) {
        let env = plateau(rise: 0.25, fall: 0.35)
        out.pose.pupilScale = 1 + 0.35 * env
        out.pose.headTilt = 0.13 * env
        out.pose.bodyBobY = 1.0 * sin(clock * 2.4)
    }
}
