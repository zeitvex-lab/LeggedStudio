/**
 * Hook for managing motor configuration state.
 * Handles motor brand selection, source detection, and motor switching.
 */
import { useEffect, useState, useTransition } from 'react';
import type { MotorSpec } from '@/types';

interface JointHardware {
  brand?: string;
  motorType?: string;
  armature?: number;
  motorId?: string;
    motorDirection?: 1 | -1;
  hardwareInterface?: 'effort' | 'position' | 'velocity';
}

interface JointLimit {
  velocity?: number;
  effort?: number;
  lower?: number;
  upper?: number;
}

export interface JointDataForMotor {
  hardware?: JointHardware;
  limit?: JointLimit;
}

type MotorSource = 'None' | 'Library' | 'Custom';

const NONE_MOTOR_TYPE = 'None';

const findBrandForMotorType = (
  motorLibrary: Record<string, MotorSpec[]>,
  motorType: string | undefined,
): string => {
  if (!motorType || motorType === NONE_MOTOR_TYPE) {
    return '';
  }

  for (const [brand, motors] of Object.entries(motorLibrary)) {
    if (motors.some((motor) => motor.name === motorType)) {
      return brand;
    }
  }

  return '';
};

const inferMotorSource = (
  motorLibrary: Record<string, MotorSpec[]>,
  motorType: string | undefined,
): MotorSource => {
  if (!motorType || motorType === NONE_MOTOR_TYPE) {
    return 'None';
  }

  return findBrandForMotorType(motorLibrary, motorType) ? 'Library' : 'Custom';
};

export function useMotorConfig({
  motorLibrary,
  data,
  selectionId,
  onUpdate,
}: {
  motorLibrary: Record<string, MotorSpec[]>;
  data: JointDataForMotor | null;
  selectionId: string | null;
  onUpdate: (type: 'link' | 'joint', id: string, data: JointDataForMotor) => void;
}) {
  const [motorBrand, setMotorBrand] = useState<string>('');
  const [displayMotorSource, setDisplayMotorSource] = useState<MotorSource>('None');
  const [displayMotorType, setDisplayMotorType] = useState<string>(NONE_MOTOR_TYPE);
  const [, startTransition] = useTransition();

  const availableBrands = Object.keys(motorLibrary);
  const defaultBrand = availableBrands[0] ?? '';
  const persistedMotorType = data?.hardware?.motorType || NONE_MOTOR_TYPE;
  const persistedMotorBrand = findBrandForMotorType(motorLibrary, persistedMotorType);
  const persistedMotorSource = inferMotorSource(motorLibrary, persistedMotorType);

  // Sync local display state from the persisted joint only when the selection
  // or the external joint data changes, so brand/model dropdowns remain
  // responsive while the store update is being processed.
  useEffect(() => {
    if (!defaultBrand) {
      if (motorBrand) {
        setMotorBrand('');
      }
      if (displayMotorSource !== 'None') {
        setDisplayMotorSource('None');
      }
      if (displayMotorType !== NONE_MOTOR_TYPE) {
        setDisplayMotorType(NONE_MOTOR_TYPE);
      }
      return;
    }

    const nextBrand =
      persistedMotorSource === 'Library'
        ? persistedMotorBrand || defaultBrand
        : !motorBrand || !motorLibrary[motorBrand]
          ? defaultBrand
          : motorBrand;

    if (displayMotorSource !== persistedMotorSource) {
      setDisplayMotorSource(persistedMotorSource);
    }
    if (displayMotorType !== persistedMotorType) {
      setDisplayMotorType(persistedMotorType);
    }
    if (nextBrand !== motorBrand) {
      setMotorBrand(nextBrand);
    }
  }, [
    defaultBrand,
    motorLibrary,
    persistedMotorBrand,
    persistedMotorSource,
    persistedMotorType,
    selectionId,
  ]);

  // Derived values
  const currentMotorType = displayMotorType || NONE_MOTOR_TYPE;

  const currentLibMotor =
    displayMotorSource === 'Library' && motorBrand
      ? motorLibrary[motorBrand]?.find((m) => m.name === currentMotorType)
      : null;

  const commitJointUpdates = (updates: { hardware?: JointHardware; limit?: JointLimit }) => {
    if (!selectionId) {
      return;
    }

    startTransition(() => {
      onUpdate('joint', selectionId, Object.assign({}, data, updates));
    });
  };

  // Handlers
  const handleSourceChange = (newSource: string) => {
    const nextSource = newSource as MotorSource;
    const newHardware = { ...data?.hardware };
    const newLimit = { ...data?.limit };

    if (nextSource === 'None') {
      setDisplayMotorSource('None');
      setDisplayMotorType(NONE_MOTOR_TYPE);
      commitJointUpdates({
        hardware: {
          brand: '',
          motorType: NONE_MOTOR_TYPE,
          armature: 0,
          motorId: '',
          motorDirection: 1,
          hardwareInterface: undefined,
        },
        limit: newLimit,
      });
      return;
    } else if (nextSource === 'Library') {
      const nextBrand = motorLibrary[motorBrand] ? motorBrand : defaultBrand;
      const motor = nextBrand ? motorLibrary[nextBrand]?.[0] : undefined;

      setDisplayMotorSource('Library');
      if (nextBrand) {
        setMotorBrand(nextBrand);
      }

      if (motor) {
        setDisplayMotorType(motor.name);
        newHardware.brand = nextBrand;
        newHardware.motorType = motor.name;
        newHardware.armature = motor.armature;
        newLimit.velocity = motor.velocity;
        newLimit.effort = motor.effort;
      }
    } else if (nextSource === 'Custom') {
      const nextMotorType =
        persistedMotorType === NONE_MOTOR_TYPE || persistedMotorSource === 'Library'
          ? 'my_motor'
          : persistedMotorType;
      setDisplayMotorSource('Custom');
      setDisplayMotorType(nextMotorType);
      newHardware.brand = '';
      if (persistedMotorType === NONE_MOTOR_TYPE || persistedMotorSource === 'Library') {
        newHardware.motorType = nextMotorType;
      }
    }

    commitJointUpdates({ hardware: newHardware, limit: newLimit });
  };

  const handleBrandChange = (newBrand: string) => {
    setMotorBrand(newBrand);
    const motor = motorLibrary[newBrand]?.[0];
    if (motor) {
      setDisplayMotorSource('Library');
      setDisplayMotorType(motor.name);
      commitJointUpdates({
        hardware: {
          ...data?.hardware,
          brand: newBrand,
          motorType: motor.name,
          armature: motor.armature,
        },
        limit: { ...data?.limit, velocity: motor.velocity, effort: motor.effort },
      });
    }
  };

  const handleLibraryMotorChange = (motorName: string) => {
    const motor = motorLibrary[motorBrand]?.find((m) => m.name === motorName);
    if (motor) {
      setDisplayMotorSource('Library');
      setDisplayMotorType(motor.name);
      commitJointUpdates({
        hardware: {
          ...data?.hardware,
          brand: motorBrand,
          motorType: motor.name,
          armature: motor.armature,
        },
        limit: { ...data?.limit, velocity: motor.velocity, effort: motor.effort },
      });
    }
  };

  return {
    motorBrand,
    motorSource: displayMotorSource,
    currentMotorType,
    currentLibMotor,
    handleSourceChange,
    handleBrandChange,
    handleLibraryMotorChange,
  };
}
