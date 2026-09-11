import type { GeometryType, JointType, RobotState } from '@/types'
import { logRegressionError } from '@/shared/debug/consoleDiagnostics'

interface NormalizedRobotData {
  name: string
  rootLinkId?: string
  links: RobotState['links']
  joints: RobotState['joints']
}

const toRecord = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== 'object') return null
  return value as Record<string, unknown>
}

const toObjectArray = (value: unknown): Record<string, unknown>[] => {
  if (Array.isArray(value)) {
    return value
      .map(item => toRecord(item))
      .filter((item): item is Record<string, unknown> => !!item)
  }

  const record = toRecord(value)
  if (record) {
    return Object.values(record)
      .map(item => toRecord(item))
      .filter((item): item is Record<string, unknown> => !!item)
  }

  return []
}

const parseDimensions = (raw: unknown): { x: number; y: number; z: number } => {
  if (Array.isArray(raw)) {
    return {
      x: (raw[0] as number) || 0.1,
      y: (raw[1] as number) || 0.1,
      z: (raw[2] as number) || 0.1
    }
  }

  const record = toRecord(raw)
  if (record) {
    return {
      x: (record.x as number) || (record[0] as number) || 0.1,
      y: (record.y as number) || (record[1] as number) || 0.1,
      z: (record.z as number) || (record[2] as number) || 0.1
    }
  }

  return { x: 0.1, y: 0.1, z: 0.1 }
}

const parseXYZ = (raw: unknown): { x: number; y: number; z: number } => {
  if (Array.isArray(raw)) {
    return {
      x: raw[0] ?? 0,
      y: raw[1] ?? 0,
      z: raw[2] ?? 0
    }
  }

  const record = toRecord(raw)
  return {
    x: (record?.x as number) ?? 0,
    y: (record?.y as number) ?? 0,
    z: (record?.z as number) ?? 0
  }
}

const parseRPY = (raw: unknown): { r: number; p: number; y: number } => {
  if (Array.isArray(raw)) {
    return {
      r: raw[0] ?? 0,
      p: raw[1] ?? 0,
      y: raw[2] ?? 0
    }
  }

  const record = toRecord(raw)
  return {
    r: (record?.r as number) ?? 0,
    p: (record?.p as number) ?? 0,
    y: (record?.y as number) ?? 0
  }
}

const parseAxis = (raw: unknown): { x: number; y: number; z: number } => {
  if (Array.isArray(raw)) {
    return {
      x: raw[0] ?? 0,
      y: raw[1] ?? 0,
      z: raw[2] ?? 1
    }
  }

  const record = toRecord(raw)
  return {
    x: (record?.x as number) ?? 0,
    y: (record?.y as number) ?? 0,
    z: (record?.z as number) ?? 1
  }
}

export function normalizeAIRobotResponse(raw: unknown): NormalizedRobotData | null {
  const data = toRecord(raw)
  if (!data) return null

  const newLinks: Record<string, unknown> = {}
  const newJoints: Record<string, unknown> = {}

  const linksToProcess = toObjectArray(data.links)
  linksToProcess.forEach(link => {
    if (!link.id) {
      logRegressionError('[AI Service] Skipping invalid link:', link)
      return
    }

    const dimensions = parseDimensions(link.dimensions)
    const visual = toRecord(link.visual)
    const visualType = ((link.visualType || visual?.type || 'box') as string) as GeometryType

    newLinks[link.id as string] = {
      id: link.id,
      name: link.name || link.id,
      inertial: {
        mass: link.mass || 1.0,
        inertia: { ixx: 0.1, ixy: 0, ixz: 0, iyy: 0.1, iyz: 0, izz: 0.1 }
      },
      visual: {
        type: visualType,
        dimensions,
        color: link.color || visual?.color || '#3b82f6',
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } }
      },
      collision: {
        type: visualType,
        dimensions,
        color: '#ef4444',
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } }
      }
    }
  })

  const jointsToProcess = toObjectArray(data.joints)
  jointsToProcess.forEach(joint => {
    if (!joint.id) {
      logRegressionError('[AI Service] Skipping invalid joint:', joint)
      return
    }

    const origin = toRecord(joint.origin)
    const originXYZ = joint.originXYZ || origin?.xyz
    const originRPY = joint.originRPY || origin?.rpy
    const axis = joint.axis
    const limit = toRecord(joint.limit)

    newJoints[joint.id as string] = {
      id: joint.id,
      name: joint.name || joint.id,
      type: ((joint.type || 'fixed') as string) as JointType,
      parentLinkId: joint.parentLinkId || joint.parent,
      childLinkId: joint.childLinkId || joint.child,
      origin: {
        xyz: parseXYZ(originXYZ),
        rpy: parseRPY(originRPY)
      },
      axis: parseAxis(axis),
      limit: {
        lower: (joint.lowerLimit as number) ?? (limit?.lower as number) ?? -1.57,
        upper: (joint.upperLimit as number) ?? (limit?.upper as number) ?? 1.57,
        effort: (joint.effortLimit as number) ?? (limit?.effort as number) ?? 100,
        velocity: (joint.velocityLimit as number) ?? (limit?.velocity as number) ?? 10
      },
      dynamics: { damping: 0, friction: 0 },
      hardware: {
        armature: 0,
        motorType: (joint.motorType as string) || 'None',
        motorId: '',
        motorDirection: 1
      }
    }
  })

  return {
    name: (data.name as string) || 'modified_robot',
    rootLinkId: data.rootLinkId as string,
    links: newLinks as RobotState['links'],
    joints: newJoints as RobotState['joints']
  }
}
