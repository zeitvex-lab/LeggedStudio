import * as THREE from 'three';

type TransformGizmoRoot = THREE.Object3D & {
    isTransformControlsGizmo?: boolean;
    gizmo?: Record<string, THREE.Object3D>;
    picker?: Record<string, THREE.Object3D>;
    helper?: Record<string, THREE.Object3D>;
};

const resolveTransformGizmoRoot = (controls: unknown) => {
    const candidate = controls as {
        gizmo?: THREE.Object3D;
        children?: THREE.Object3D[];
    } | null;

    if (candidate?.gizmo && (candidate.gizmo as TransformGizmoRoot).isTransformControlsGizmo) {
        return candidate.gizmo as TransformGizmoRoot;
    }

    const childGizmo = candidate?.children?.find((child) => (child as TransformGizmoRoot).isTransformControlsGizmo);
    if (childGizmo) {
        return childGizmo as TransformGizmoRoot;
    }

    return candidate?.children?.[0] as TransformGizmoRoot | undefined;
};

const AXIS_NAMES = new Set(['X', 'Y', 'Z']);
const FREE_ROTATE_NAMES = new Set(['E', 'XYZE']);
const FREE_TRANSLATE_NAMES = new Set(['XY', 'YZ', 'XZ', 'XYZ']);
const TRANSLATE_PICKER_REMOVE_NAMES = new Set(['XY', 'YZ', 'XZ', 'XYZ']);
const TRANSLATE_ARROW_RADIUS = 0.11;
const TRANSLATE_ARROW_HEIGHT = 0.34;
const TRANSLATE_TIP_KNOB_RADIUS = 0.13;
const TRANSLATE_ARROW_HIT_RADIUS = 0.26;
const ROTATE_KNOB_RADIUS = 0.11;
const ROTATE_KNOB_HIT_RADIUS = 0.15;
const THICK_TRANSLATE_SHAFT_RADIUS = 0.075;
const THICK_ROTATE_ARC_RADIUS = 0.06;
const TRANSLATE_AXIS_PICKER_SCALE = { x: 1.35, y: 1.8, z: 1.35 } as const;
const TRANSLATE_PLANE_PICKER_SCALE = 0.68;
const ROTATE_PICKER_REMOVE_NAMES = new Set(['X', 'Y', 'Z', 'E', 'XYZE']);
const GIZMO_RENDER_ORDER = 10000;
const GIZMO_ARC_RENDER_ORDER = 10005;
const GIZMO_KNOB_RENDER_ORDER = 10020;
const GIZMO_KNOB_OUTLINE_RENDER_ORDER = 10025;
const GIZMO_PICKER_RENDER_ORDER = 10030;
const ROTATE_ANCHOR_FRACTION: Record<'X' | 'Y' | 'Z', number> = {
    X: 0.18,
    Y: 0.52,
    Z: 0.86
};

const normalizeVisibleGizmoMaterials = (root?: TransformGizmoRoot) => {
    if (!root?.gizmo) return;

    const groups = [root.gizmo.translate, root.gizmo.rotate, root.gizmo.scale].filter(Boolean) as THREE.Object3D[];
    for (const group of groups) {
        group.traverse((node) => {
            if (node.userData?.urdfHideStockAxisLine) {
                node.visible = false;
            }

            const renderOrder = typeof node.userData?.urdfRenderOrder === 'number'
                ? node.userData.urdfRenderOrder
                : GIZMO_RENDER_ORDER;
            node.renderOrder = renderOrder;
            if (node.userData?.urdfRotateKnobOutline) return;

            const material = (node as any).material;
            if (!material) return;

            const materials = Array.isArray(material) ? material : [material];
            for (const mat of materials) {
                if (!mat) continue;

                // Only enforce render-state properties — let TransformControls manage
                // opacity and color so its hover highlight/dimming feedback is visible.
                const needsDepthReset = mat.depthTest !== false || mat.depthWrite !== false || mat.transparent !== true;
                if (needsDepthReset) {
                    mat.transparent = true;
                    mat.depthTest = false;
                    mat.depthWrite = false;
                    mat.needsUpdate = true;
                }
            }
        });
    }

    // Normalize helper geometry (axis lines, plane indicators shown during transform).
    // Without this, helper materials default to depthTest=true and are occluded by
    // transparent collision meshes that render with depthTest=false.
    if (root.helper) {
        const helperGroups = Object.values(root.helper).filter(Boolean) as THREE.Object3D[];
        for (const group of helperGroups) {
            group.traverse((node) => {
                if (node.renderOrder < GIZMO_RENDER_ORDER) {
                    node.renderOrder = GIZMO_RENDER_ORDER;
                }
                const material = (node as any).material;
                if (!material) return;
                const materials = Array.isArray(material) ? material : [material];
                for (const mat of materials) {
                    if (!mat) continue;
                    if (mat.depthTest !== false || mat.depthWrite !== false) {
                        mat.depthTest = false;
                        mat.depthWrite = false;
                        mat.transparent = true;
                        mat.needsUpdate = true;
                    }
                }
            });
        }
    }
};

const patchGizmoUpdateMatrixWorld = (root: TransformGizmoRoot) => {
    if (root.userData.urdfStudioGizmoMaterialPatched) return;

    const originalUpdateMatrixWorld = root.updateMatrixWorld.bind(root);
    root.updateMatrixWorld = function patchedUpdateMatrixWorld(force?: boolean) {
        originalUpdateMatrixWorld(force);
        normalizeVisibleGizmoMaterials(this as TransformGizmoRoot);
    };

    root.userData.urdfStudioGizmoMaterialPatched = true;
};

const disposeObjectResources = (object: THREE.Object3D) => {
    object.traverse((node) => {
        const mesh = node as THREE.Mesh;
        const material = (mesh as any).material;
        const geometry = (mesh as any).geometry as THREE.BufferGeometry | undefined;

        geometry?.dispose?.();

        if (Array.isArray(material)) {
            material.forEach((mat) => mat?.dispose?.());
        } else {
            material?.dispose?.();
        }
    });
};

const getGeometryCenter = (geometry: THREE.BufferGeometry) => {
    geometry.computeBoundingBox();
    const center = new THREE.Vector3();
    geometry.boundingBox?.getCenter(center);
    return center;
};

const replaceMeshGeometry = (mesh: THREE.Mesh, nextGeometry: THREE.BufferGeometry) => {
    const previousGeometry = mesh.geometry as THREE.BufferGeometry | undefined;
    mesh.geometry = nextGeometry;
    previousGeometry?.dispose?.();
};

const getAxisDirection = (axis: 'X' | 'Y' | 'Z', sign: 1 | -1) => {
    if (axis === 'X') return new THREE.Vector3(sign, 0, 0);
    if (axis === 'Y') return new THREE.Vector3(0, sign, 0);
    return new THREE.Vector3(0, 0, sign);
};

const replaceWithTranslateArrow = (
    mesh: THREE.Mesh,
    axis: 'X' | 'Y' | 'Z',
    directionSign: 1 | -1
) => {
    const center = getGeometryCenter(mesh.geometry as THREE.BufferGeometry);
    const arrow = new THREE.ConeGeometry(TRANSLATE_ARROW_RADIUS, TRANSLATE_ARROW_HEIGHT, 18);
    replaceMeshGeometry(mesh, arrow);
    mesh.position.copy(center);

    const direction = getAxisDirection(axis, directionSign);
    const quaternion = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
    mesh.setRotationFromQuaternion(quaternion);

    mesh.userData.urdfTranslateArrowHead = true;
    mesh.userData.urdfTranslateDirection = directionSign > 0 ? 'fwd' : 'bwd';
};

const cloneAxisColorMaterial = (sourceMaterial: THREE.Material | null) => {
    const color = new THREE.Color(0xffffff);
    if (sourceMaterial && (sourceMaterial as any).color) {
        color.copy((sourceMaterial as any).color as THREE.Color);
    }

    const material = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 1,
        depthTest: false,
        depthWrite: false,
        toneMapped: false
    });
    material.userData = { ...material.userData, urdfBaseColor: color.clone() };
    return material;
};

const markAsGizmo = (root: THREE.Object3D) => {
    root.traverse((node) => {
        node.userData.isGizmo = true;
    });
};

const styleVisibleHandles = (group?: THREE.Object3D) => {
    if (!group) return;

    group.traverse((node) => {
        const material = (node as any).material;
        if (!material) return;

        const materials = Array.isArray(material) ? material : [material];
        for (const mat of materials) {
            if (!mat || mat.userData?.urdfHandleStyled) continue;

            mat.transparent = true;
            mat.opacity = 1;
            mat.depthTest = false;
            mat.depthWrite = false;
            (mat as any).tempOpacity = 1;
            const baseColor = (mat as any).color?.clone?.();
            mat.userData = {
                ...mat.userData,
                urdfHandleStyled: true,
                urdfBaseColor: mat.userData?.urdfBaseColor || baseColor
            };
            mat.needsUpdate = true;
        }
    });
};

const removeHandlesByName = (group: THREE.Object3D | undefined, names: Set<string>) => {
    if (!group) return;

    const targets: THREE.Object3D[] = [];
    group.traverse((node) => {
        if (node === group) return;
        if (!names.has(node.name)) return;
        targets.push(node);
    });

    for (const node of targets) {
        node.parent?.remove(node);
        disposeObjectResources(node);
    }
};

const hideStockAxisLines = (group?: THREE.Object3D) => {
    if (!group) return;

    group.traverse((node) => {
        const line = node as THREE.Line;
        if (!line.isLine || !AXIS_NAMES.has(line.name)) return;

        line.userData.urdfHideStockAxisLine = true;
        line.visible = false;

        const material = (line as any).material;
        if (!material) return;

        const materials = Array.isArray(material) ? material : [material];
        for (const mat of materials) {
            if (!mat) continue;
            mat.transparent = true;
            mat.opacity = 0;
            mat.depthTest = false;
            mat.depthWrite = false;
            mat.needsUpdate = true;
        }
    });
};

const enhanceTranslateGizmo = (group?: THREE.Object3D) => {
    if (!group) return;

    group.traverse((node) => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh || mesh.userData.urdfTranslateKnobApplied) return;
        if (!AXIS_NAMES.has(mesh.name)) return;

        const tag = (mesh as any).tag;
        if (tag !== 'fwd' && tag !== 'bwd') return;

        const axis = mesh.name as 'X' | 'Y' | 'Z';
        const sign = tag === 'fwd' ? 1 : -1;
        replaceWithTranslateArrow(mesh, axis, sign);
        mesh.userData.urdfTranslateKnobApplied = true;
    });
};

type TranslateArrowTip = {
    axis: 'X' | 'Y' | 'Z';
    direction: 'fwd' | 'bwd';
    tipWorld: THREE.Vector3;
};

const collectTranslateArrowTips = (group?: THREE.Object3D) => {
    const tips: TranslateArrowTip[] = [];
    if (!group) return tips;

    group.updateWorldMatrix(true, true);
    group.traverse((node) => {
        const line = node as THREE.Line;
        if (!line.isLine || !AXIS_NAMES.has(line.name)) return;

        const position = line.geometry.getAttribute('position');
        if (!position || position.count < 2) return;

        let farthestIdx = 0;
        let farthestLenSq = -1;
        for (let i = 0; i < position.count; i++) {
            const x = position.getX(i);
            const y = position.getY(i);
            const z = position.getZ(i);
            const lenSq = x * x + y * y + z * z;
            if (lenSq > farthestLenSq) {
                farthestLenSq = lenSq;
                farthestIdx = i;
            }
        }

        const tipWorld = line.localToWorld(new THREE.Vector3(
            position.getX(farthestIdx),
            position.getY(farthestIdx),
            position.getZ(farthestIdx)
        ));
        tips.push({ axis: line.name as 'X' | 'Y' | 'Z', direction: 'fwd', tipWorld });
    });

    return tips;
};

const convertRotateLinesToFullCircle = (group?: THREE.Object3D) => {
    if (!group) return;

    const fallbackBasis: Record<'X' | 'Y' | 'Z', { u: THREE.Vector3; v: THREE.Vector3 }> = {
        X: { u: new THREE.Vector3(0, 1, 0), v: new THREE.Vector3(0, 0, 1) },
        Y: { u: new THREE.Vector3(1, 0, 0), v: new THREE.Vector3(0, 0, 1) },
        Z: { u: new THREE.Vector3(1, 0, 0), v: new THREE.Vector3(0, 1, 0) }
    };

    group.traverse((node) => {
        const line = node as THREE.Line;
        if (!line.isLine || !AXIS_NAMES.has(line.name)) return;
        if (line.userData?.urdfRotateLineFullCircleApplied) return;

        const position = line.geometry.getAttribute('position');
        if (!position || position.count < 3) return;

        const samples: THREE.Vector3[] = [];
        for (let i = 0; i < position.count; i++) {
            samples.push(new THREE.Vector3(position.getX(i), position.getY(i), position.getZ(i)));
        }

        const radiusCandidates = samples.map((point) => point.length()).filter((len) => len > 1e-4);
        const radius = radiusCandidates.length > 0
            ? radiusCandidates.reduce((sum, len) => sum + len, 0) / radiusCandidates.length
            : 1;

        let u = samples.find((point) => point.lengthSq() > 1e-6)?.clone().normalize();
        let v: THREE.Vector3 | undefined;

        if (u) {
            for (const candidate of samples) {
                const candidateNorm = candidate.clone();
                if (candidateNorm.lengthSq() <= 1e-6) continue;
                candidateNorm.normalize();

                const normal = u.clone().cross(candidateNorm);
                if (normal.lengthSq() <= 1e-4) continue;
                normal.normalize();
                v = normal.clone().cross(u).normalize();
                break;
            }
        }

        if (!u || !v || v.lengthSq() <= 1e-6) {
            const basis = fallbackBasis[line.name as 'X' | 'Y' | 'Z'];
            u = basis.u.clone();
            v = basis.v.clone();
        }

        const segments = 128;
        const vertices: number[] = [];
        for (let i = 0; i <= segments; i++) {
            const theta = (i / segments) * Math.PI * 2;
            const point = u.clone().multiplyScalar(Math.cos(theta) * radius).add(v.clone().multiplyScalar(Math.sin(theta) * radius));
            vertices.push(point.x, point.y, point.z);
        }

        const fullGeometry = new THREE.BufferGeometry();
        fullGeometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        const previousGeometry = line.geometry as THREE.BufferGeometry;
        line.geometry = fullGeometry;
        previousGeometry.dispose?.();
        line.userData.urdfRotateLineFullCircleApplied = true;
    });
};

type RotateAnchor = {
    line: THREE.Line;
    point: THREE.Vector3;
};

const collectRotateArcAnchors = (group?: THREE.Object3D) => {
    const anchors = new Map<string, RotateAnchor>();
    if (!group) return anchors;

    group.traverse((node) => {
        const line = node as THREE.Line;
        if (!line.isLine || !AXIS_NAMES.has(line.name)) return;
        if (anchors.has(line.name)) return;

        const position = line.geometry.getAttribute('position');
        if (!position || position.count < 2) return;

        const axisName = line.name as 'X' | 'Y' | 'Z';
        const sampleRatio = ROTATE_ANCHOR_FRACTION[axisName] ?? 0.25;
        const anchorIndex = Math.max(0, Math.min(position.count - 1, Math.floor((position.count - 1) * sampleRatio)));
        const anchorPoint = new THREE.Vector3(
            position.getX(anchorIndex),
            position.getY(anchorIndex),
            position.getZ(anchorIndex)
        );
        anchors.set(line.name, { line, point: anchorPoint });
    });

    return anchors;
};

const enhanceRotateGizmo = (group?: THREE.Object3D, anchors?: Map<string, RotateAnchor>) => {
    if (!group) return;

    const axisMaterials = new Map<string, THREE.Material>();
    const legacyKnobs: THREE.Mesh[] = [];

    group.traverse((node) => {
        if ((node as any).isLine && AXIS_NAMES.has(node.name) && !axisMaterials.has(node.name)) {
            const mat = Array.isArray((node as any).material) ? (node as any).material[0] : (node as any).material;
            if (mat) axisMaterials.set(node.name, mat);
            return;
        }

        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh) return;
        if (!AXIS_NAMES.has(mesh.name)) return;
        if (mesh.userData?.urdfRotateArcMesh || mesh.userData?.urdfRotateKnob) return;
        legacyKnobs.push(mesh);
    });

    // Remove legacy octahedron handles and replace with explicit arc knobs.
    for (const mesh of legacyKnobs) {
        mesh.parent?.remove(mesh);
        disposeObjectResources(mesh);
    }

    for (const axis of ['X', 'Y', 'Z'] as const) {
        const anchorMeta = anchors?.get(axis);
        if (!anchorMeta) continue;
        const { line, point } = anchorMeta;

        const material = cloneAxisColorMaterial(axisMaterials.get(axis) || null);
        const knob = new THREE.Mesh(new THREE.SphereGeometry(ROTATE_KNOB_RADIUS, 20, 16), material);
        knob.name = axis;
        knob.position.copy(point);
        knob.renderOrder = GIZMO_KNOB_RENDER_ORDER;
        knob.userData.isGizmo = true;
        knob.userData.urdfKnobAnchor = point.clone();
        knob.userData.urdfRenderOrder = GIZMO_KNOB_RENDER_ORDER;
        knob.userData.urdfRotateKnob = true;
        knob.userData.urdfRotateKnobApplied = true;
        line.add(knob);
    }
};

const addRotateKnobOutlinePoints = (group?: THREE.Object3D) => {
    if (!group) return;

    const existing = new Set<string>();
    group.traverse((node) => {
        if (node.userData?.urdfRotateKnobOutline && AXIS_NAMES.has(node.name)) {
            existing.add(node.name);
        }
    });

    group.traverse((node) => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh || !mesh.userData?.urdfRotateKnob) return;
        if (existing.has(mesh.name)) return;

        const position = (mesh.geometry as THREE.BufferGeometry).getAttribute('position');
        if (!position) return;

        const pointsGeometry = new THREE.BufferGeometry();
        pointsGeometry.setAttribute('position', position.clone());
        const pointsMaterial = new THREE.PointsMaterial({
            color: 0xffffff,
            size: 0.012,
            transparent: true,
            opacity: 0,
            depthTest: false,
            depthWrite: false,
            sizeAttenuation: true
        });

        const points = new THREE.Points(pointsGeometry, pointsMaterial);
        points.name = mesh.name;
        points.renderOrder = GIZMO_KNOB_OUTLINE_RENDER_ORDER;
        points.userData.isGizmo = true;
        points.userData.urdfRenderOrder = GIZMO_KNOB_OUTLINE_RENDER_ORDER;
        points.userData.urdfRotateKnobOutline = true;
        mesh.add(points);
    });
};

const addTranslateShaftMeshes = (group?: THREE.Object3D) => {
    if (!group) return;

    const existing = new Set<string>();
    group.traverse((node) => {
        if (node.userData?.urdfTranslateShaft && AXIS_NAMES.has(node.name)) {
            existing.add(node.name);
        }
    });

    const axisMaterials = new Map<string, THREE.Material>();
    group.traverse((node) => {
        if (!AXIS_NAMES.has(node.name) || !(node as any).isLine) return;
        if (axisMaterials.has(node.name)) return;
        const mat = Array.isArray((node as any).material) ? (node as any).material[0] : (node as any).material;
        if (mat) axisMaterials.set(node.name, mat);
    });

    const createShaft = (axis: 'X' | 'Y' | 'Z') => {
        const geometry = new THREE.CylinderGeometry(
            THICK_TRANSLATE_SHAFT_RADIUS,
            THICK_TRANSLATE_SHAFT_RADIUS,
            0.82,
            10
        );
        if (axis === 'X') {
            geometry.rotateZ(-Math.PI / 2);
            geometry.translate(0.41, 0, 0);
        } else if (axis === 'Y') {
            geometry.translate(0, 0.41, 0);
        } else {
            geometry.rotateX(Math.PI / 2);
            geometry.translate(0, 0, 0.41);
        }
        return geometry;
    };

    for (const axis of ['X', 'Y', 'Z'] as const) {
        if (existing.has(axis)) continue;
        const material = cloneAxisColorMaterial(axisMaterials.get(axis) || null);
        const shaft = new THREE.Mesh(createShaft(axis), material);
        shaft.name = axis;
        shaft.renderOrder = GIZMO_ARC_RENDER_ORDER;
        shaft.userData.isGizmo = true;
        shaft.userData.urdfRenderOrder = GIZMO_ARC_RENDER_ORDER;
        shaft.userData.urdfTranslateShaft = true;
        group.add(shaft);
    }
};

const addTranslateTipKnobs = (group: THREE.Object3D | undefined, tips: TranslateArrowTip[]) => {
    if (!group || tips.length === 0) return;

    const existing = new Set<string>();
    group.traverse((node) => {
        const key = node.userData?.urdfTranslateTipKnobKey;
        if (typeof key === 'string') existing.add(key);
    });

    const axisMaterials = new Map<string, THREE.Material>();
    group.traverse((node) => {
        const line = node as THREE.Line;
        if (!line.isLine || !AXIS_NAMES.has(line.name)) return;
        if (axisMaterials.has(line.name)) return;
        const mat = Array.isArray((line as any).material) ? (line as any).material[0] : (line as any).material;
        if (mat) axisMaterials.set(line.name, mat);
    });

    group.updateWorldMatrix(true, false);

    for (const tip of tips) {
        const key = `${tip.axis}_${tip.direction}`;
        if (existing.has(key)) continue;

        const material = cloneAxisColorMaterial(axisMaterials.get(tip.axis) || null);
        const knob = new THREE.Mesh(new THREE.SphereGeometry(TRANSLATE_TIP_KNOB_RADIUS, 18, 14), material);
        knob.name = tip.axis;
        knob.position.copy(group.worldToLocal(tip.tipWorld.clone()));
        knob.renderOrder = GIZMO_KNOB_RENDER_ORDER;
        knob.userData.isGizmo = true;
        knob.userData.urdfRenderOrder = GIZMO_KNOB_RENDER_ORDER;
        knob.userData.urdfTranslateTipKnob = true;
        knob.userData.urdfTranslateTipKnobKey = key;
        group.add(knob);
    }
};

const addRotateArcMeshes = (group?: THREE.Object3D) => {
    if (!group) return;

    const existing = new Set<string>();
    group.traverse((node) => {
        if (node.userData?.urdfRotateArcMesh && AXIS_NAMES.has(node.name)) {
            existing.add(node.name);
        }
    });

    group.traverse((node) => {
        const line = node as THREE.Line;
        if (!line.isLine || !AXIS_NAMES.has(line.name)) return;
        if (existing.has(line.name)) return;

        const position = line.geometry.getAttribute('position');
        if (!position || position.count < 3) return;

        const points: THREE.Vector3[] = [];
        for (let i = 0; i < position.count; i++) {
            points.push(new THREE.Vector3(position.getX(i), position.getY(i), position.getZ(i)));
        }

        if (points.length > 2 && points[0].distanceToSquared(points[points.length - 1]) < 1e-8) {
            points.pop();
        }

        const curve = new THREE.CatmullRomCurve3(points, true);
        const tube = new THREE.TubeGeometry(curve, Math.max(points.length * 2, 80), THICK_ROTATE_ARC_RADIUS, 10, true);
        const sourceMaterial = Array.isArray((line as any).material) ? (line as any).material[0] : (line as any).material;
        const arcMesh = new THREE.Mesh(tube, cloneAxisColorMaterial(sourceMaterial || null));
        arcMesh.name = line.name;
        arcMesh.renderOrder = GIZMO_ARC_RENDER_ORDER;
        arcMesh.userData.isGizmo = true;
        arcMesh.userData.urdfRenderOrder = GIZMO_ARC_RENDER_ORDER;
        arcMesh.userData.urdfRotateArcMesh = true;
        group.add(arcMesh);
    });
};

const collectRotateKnobCenters = (group?: THREE.Object3D) => {
    const centers = new Map<string, THREE.Vector3>();
    if (!group) return centers;

    group.updateWorldMatrix(true, true);

    group.traverse((node) => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh || !AXIS_NAMES.has(mesh.name)) return;
        if ((mesh.geometry as THREE.BufferGeometry).type !== 'SphereGeometry') return;
        if (!mesh.userData.urdfRotateKnobApplied) return;

        if (!centers.has(mesh.name)) {
            centers.set(mesh.name, mesh.getWorldPosition(new THREE.Vector3()));
        }
    });

    return centers;
};

const addRotateSpherePickers = (pickerGroup: THREE.Object3D | undefined, knobCenters: Map<string, THREE.Vector3>) => {
    if (!pickerGroup || knobCenters.size === 0) return;

    pickerGroup.updateWorldMatrix(true, false);

    const existing = new Set<string>();
    pickerGroup.traverse((node) => {
        if (node.userData?.urdfRotateKnobPicker && AXIS_NAMES.has(node.name)) {
            existing.add(node.name);
        }
    });

    for (const [axis, center] of knobCenters.entries()) {
        if (existing.has(axis)) continue;

        const axisPickerMaterial = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0.001,
            depthTest: false,
            depthWrite: false,
            toneMapped: false
        });

        const sphereGeometry = new THREE.SphereGeometry(ROTATE_KNOB_HIT_RADIUS, 12, 10);
        const localCenter = pickerGroup.worldToLocal(center.clone());

        const spherePicker = new THREE.Mesh(sphereGeometry, axisPickerMaterial);
        spherePicker.name = axis;
        spherePicker.position.copy(localCenter);
        spherePicker.renderOrder = GIZMO_PICKER_RENDER_ORDER;
        spherePicker.userData.isGizmo = true;
        spherePicker.userData.urdfRenderOrder = GIZMO_PICKER_RENDER_ORDER;
        spherePicker.userData.urdfRotateKnobPicker = true;
        spherePicker.userData.urdfPickerCentered = true;
        pickerGroup.add(spherePicker);
    }
};

const addTranslateArrowTipPickers = (pickerGroup: THREE.Object3D | undefined, tips: TranslateArrowTip[]) => {
    if (!pickerGroup || tips.length === 0) return;

    pickerGroup.updateWorldMatrix(true, false);
    const existing = new Set<string>();
    pickerGroup.traverse((node) => {
        const key = node.userData?.urdfTranslateTipPickerKey;
        if (typeof key === 'string') existing.add(key);
    });

    for (const tip of tips) {
        const key = `${tip.axis}_${tip.direction}`;
        if (existing.has(key)) continue;

        const material = new THREE.MeshBasicMaterial({
            color: 0xffffff,
            transparent: true,
            opacity: 0.001,
            depthTest: false,
            depthWrite: false,
            toneMapped: false
        });

        const localCenter = pickerGroup.worldToLocal(tip.tipWorld.clone());
        const geometry = new THREE.SphereGeometry(TRANSLATE_ARROW_HIT_RADIUS, 12, 10);
        const picker = new THREE.Mesh(geometry, material);
        picker.name = tip.axis;
        picker.position.copy(localCenter);
        picker.renderOrder = GIZMO_PICKER_RENDER_ORDER;
        picker.userData.isGizmo = true;
        picker.userData.urdfRenderOrder = GIZMO_PICKER_RENDER_ORDER;
        picker.userData.urdfTranslateTipPicker = true;
        picker.userData.urdfTranslateTipPickerKey = key;
        pickerGroup.add(picker);
    }
};

const tuneTranslatePickers = (group?: THREE.Object3D) => {
    if (!group) return;

    group.traverse((node) => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh || !mesh.geometry || mesh.userData.urdfPickerTuned) return;
        if (mesh.userData?.urdfTranslateTipPicker) {
            mesh.userData.urdfPickerTuned = true;
            return;
        }

        if (AXIS_NAMES.has(mesh.name)) {
            mesh.geometry.scale(
                TRANSLATE_AXIS_PICKER_SCALE.x,
                TRANSLATE_AXIS_PICKER_SCALE.y,
                TRANSLATE_AXIS_PICKER_SCALE.z
            );
        } else if (mesh.name === 'XY' || mesh.name === 'YZ' || mesh.name === 'XZ') {
            // Reduce accidental plane catches; prioritize axis dragging.
            mesh.geometry.scale(
                TRANSLATE_PLANE_PICKER_SCALE,
                TRANSLATE_PLANE_PICKER_SCALE,
                TRANSLATE_PLANE_PICKER_SCALE
            );
        }

        mesh.userData.urdfPickerTuned = true;
    });
};

const tuneRotatePickers = (group?: THREE.Object3D) => {
    if (!group) return;

    group.traverse((node) => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh || mesh.userData.urdfRotatePickerTuned) return;
        if (!AXIS_NAMES.has(mesh.name)) return;
        if ((mesh.geometry as THREE.BufferGeometry).type !== 'TorusGeometry') return;

        const params = (mesh.geometry as any).parameters || {};
        const radius = typeof params.radius === 'number' ? params.radius : 1;
        const tube = Math.max(typeof params.tube === 'number' ? params.tube : 0.1, 0.16);
        const radialSegments = Math.max(typeof params.radialSegments === 'number' ? params.radialSegments : 4, 8);
        const tubularSegments = Math.max(typeof params.tubularSegments === 'number' ? params.tubularSegments : 24, 48);
        const arc = typeof params.arc === 'number' ? params.arc : Math.PI * 2;

        const geometry = new THREE.TorusGeometry(radius, tube, radialSegments, tubularSegments, arc);
        replaceMeshGeometry(mesh, geometry);
        mesh.userData.urdfRotatePickerTuned = true;
    });
};

export const enhanceTransformControlsGizmo = (controls: unknown) => {
    const root = resolveTransformGizmoRoot(controls);
    if (!root || root.userData.urdfStudioGizmoEnhanced) return;

    const translateGizmo = root.gizmo?.translate;
    const rotateGizmo = root.gizmo?.rotate;
    const translatePicker = root.picker?.translate;
    const rotatePicker = root.picker?.rotate;

    markAsGizmo(root);
    styleVisibleHandles(translateGizmo);
    styleVisibleHandles(rotateGizmo);

    removeHandlesByName(rotateGizmo, FREE_ROTATE_NAMES);
    removeHandlesByName(rotatePicker, ROTATE_PICKER_REMOVE_NAMES);
    removeHandlesByName(translateGizmo, FREE_TRANSLATE_NAMES);
    removeHandlesByName(translatePicker, TRANSLATE_PICKER_REMOVE_NAMES);

    enhanceTranslateGizmo(translateGizmo);
    convertRotateLinesToFullCircle(rotateGizmo);
    const rotateAnchors = collectRotateArcAnchors(rotateGizmo);
    enhanceRotateGizmo(rotateGizmo, rotateAnchors);
    addRotateKnobOutlinePoints(rotateGizmo);
    addTranslateShaftMeshes(translateGizmo);
    const translateTips = collectTranslateArrowTips(translateGizmo);
    addTranslateTipKnobs(translateGizmo, translateTips);
    addRotateArcMeshes(rotateGizmo);
    addRotateSpherePickers(rotatePicker, collectRotateKnobCenters(rotateGizmo));
    addTranslateArrowTipPickers(translatePicker, translateTips);
    tuneTranslatePickers(translatePicker);
    tuneRotatePickers(rotatePicker);
    hideStockAxisLines(translateGizmo);
    hideStockAxisLines(rotateGizmo);
    normalizeVisibleGizmoMaterials(root);
    patchGizmoUpdateMatrixWorld(root);

    root.userData.urdfStudioGizmoEnhanced = true;
};
