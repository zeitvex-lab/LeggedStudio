/**
 * Post-processor for adding capsule geometry support to urdf-loader
 *
 * The urdf-loader library may not support capsule geometry natively,
 * so we need to manually create capsule geometries after parsing.
 */

import * as THREE from 'three';
import { COLLISION_OVERLAY_RENDER_ORDER, createCollisionOverlayMaterial, createMatteMaterial } from '../utils/materials';
import { disposeReplacedMaterials } from './robotLoaderPatchUtils';

/**
 * Create a Three.js capsule geometry group.
 * A capsule consists of a cylinder with hemispherical caps on both ends.
 *
 * @param radius - Capsule radius
 * @param length - Total length including caps
 * @param radialSegments - Number of segments around the circumference
 * @returns Group containing the capsule geometry
 */
function createCapsuleGeometry(
    radius: number,
    length: number,
    radialSegments: number = 32
): THREE.Group {
    const group = new THREE.Group();

    // Calculate cylinder length (total length minus the two hemisphere caps)
    const cylinderLength = Math.max(0, length - 2 * radius);

    // Create cylinder body
    const cylinderGeometry = new THREE.CylinderGeometry(
        radius,
        radius,
        cylinderLength,
        radialSegments,
        1
    );
    const cylinderMesh = new THREE.Mesh(cylinderGeometry, createMatteMaterial({ color: 0x888888 }));
    group.add(cylinderMesh);

    // Create top hemisphere
    const topSphereGeometry = new THREE.SphereGeometry(
        radius,
        radialSegments,
        radialSegments / 2,
        0,
        Math.PI * 2,
        0,
        Math.PI / 2
    );
    const topSphereMesh = new THREE.Mesh(topSphereGeometry, createMatteMaterial({ color: 0x888888 }));
    topSphereMesh.position.y = cylinderLength / 2;
    group.add(topSphereMesh);

    // Create bottom hemisphere
    const bottomSphereGeometry = new THREE.SphereGeometry(
        radius,
        radialSegments,
        radialSegments / 2,
        0,
        Math.PI * 2,
        Math.PI / 2,
        Math.PI / 2
    );
    const bottomSphereMesh = new THREE.Mesh(bottomSphereGeometry, createMatteMaterial({ color: 0x888888 }));
    bottomSphereMesh.position.y = -cylinderLength / 2;
    group.add(bottomSphereMesh);

    // Align with URDFLoader cylinder primitive orientation.
    group.rotation.x = Math.PI / 2;

    return group;
}

/**
 * Process a URDF robot model and add capsule geometries where needed.
 *
 * This function:
 * 1. Parses the URDF XML to find capsule geometry definitions
 * 2. Traverses the Three.js robot model to find matching links
 * 3. Creates and adds capsule geometries to the appropriate links
 *
 * @param robot - The Three.js robot model from urdf-loader
 * @param urdfContent - The original URDF XML content
 */
export function processCapsuleGeometries(
    robot: THREE.Object3D,
    urdfContent: string
): void {
    try {
        const capsuleAxisCorrection = new THREE.Quaternion().setFromEuler(
            new THREE.Euler(Math.PI / 2, 0, 0)
        );

        // Parse URDF XML
        const parser = new DOMParser();
        const doc = parser.parseFromString(urdfContent, 'text/xml');

        // Find all capsule elements
        const capsules = doc.querySelectorAll('capsule');

        if (capsules.length === 0) {
            // No capsules to process
            return;
        }

        // Build a map of link names to capsule definitions
        interface CapsuleDefinition {
            linkName: string;
            type: 'visual' | 'collision';
            radius: number;
            length: number;
            origin?: {
                xyz: [number, number, number];
                rpy: [number, number, number];
            };
            color?: string;
        }

        const capsuleMap = new Map<string, CapsuleDefinition[]>();

        // Parse all links and their capsule geometries
        const links = doc.querySelectorAll('link');
        links.forEach(link => {
            const linkName = link.getAttribute('name');
            if (!linkName) return;

            // Check visual geometries
            const visuals = link.querySelectorAll(':scope > visual');
            visuals.forEach(visual => {
                const capsule = visual.querySelector('geometry > capsule');
                if (capsule) {
                    const radius = parseFloat(capsule.getAttribute('radius') || '0.1');
                    const length = parseFloat(capsule.getAttribute('length') || '0.5');

                    // Parse origin
                    const originEl = visual.querySelector('origin');
                    let origin: CapsuleDefinition['origin'];
                    if (originEl) {
                        const xyzStr = originEl.getAttribute('xyz') || '0 0 0';
                        const rpyStr = originEl.getAttribute('rpy') || '0 0 0';
                        const xyz = xyzStr.split(/\s+/).map(parseFloat) as [number, number, number];
                        const rpy = rpyStr.split(/\s+/).map(parseFloat) as [number, number, number];
                        origin = { xyz, rpy };
                    }

                    // Parse color
                    const materialEl = visual.querySelector('material');
                    let color: string | undefined;
                    if (materialEl) {
                        const colorEl = materialEl.querySelector('color');
                        if (colorEl) {
                            const rgba = colorEl.getAttribute('rgba');
                            if (rgba) {
                                const [r, g, b] = rgba.split(/\s+/).map(parseFloat);
                                color = `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;
                            }
                        }
                    }

                    if (!capsuleMap.has(linkName)) {
                        capsuleMap.set(linkName, []);
                    }
                    capsuleMap.get(linkName)!.push({
                        linkName,
                        type: 'visual',
                        radius,
                        length,
                        origin,
                        color
                    });
                }
            });

            // Check collision geometries
            const collisions = link.querySelectorAll(':scope > collision');
            collisions.forEach(collision => {
                const capsule = collision.querySelector('geometry > capsule');
                if (capsule) {
                    const radius = parseFloat(capsule.getAttribute('radius') || '0.1');
                    const length = parseFloat(capsule.getAttribute('length') || '0.5');

                    // Parse origin
                    const originEl = collision.querySelector('origin');
                    let origin: CapsuleDefinition['origin'];
                    if (originEl) {
                        const xyzStr = originEl.getAttribute('xyz') || '0 0 0';
                        const rpyStr = originEl.getAttribute('rpy') || '0 0 0';
                        const xyz = xyzStr.split(/\s+/).map(parseFloat) as [number, number, number];
                        const rpy = rpyStr.split(/\s+/).map(parseFloat) as [number, number, number];
                        origin = { xyz, rpy };
                    }

                    if (!capsuleMap.has(linkName)) {
                        capsuleMap.set(linkName, []);
                    }
                    capsuleMap.get(linkName)!.push({
                        linkName,
                        type: 'collision',
                        radius,
                        length,
                        origin
                    });
                }
            });
        });

        // Now traverse the robot model and add capsule geometries
        robot.traverse((child: any) => {
            if (child.isURDFLink) {
                const linkName = child.name;
                const capsuleDefs = capsuleMap.get(linkName);

                if (capsuleDefs && capsuleDefs.length > 0) {
                    capsuleDefs.forEach(def => {
                        const capsuleGroup = createCapsuleGeometry(def.radius, def.length);

                        // Apply origin transform
                        if (def.origin) {
                            capsuleGroup.position.set(
                                def.origin.xyz[0],
                                def.origin.xyz[1],
                                def.origin.xyz[2]
                            );
                            const originQuaternion = new THREE.Quaternion().setFromEuler(
                                new THREE.Euler(
                                    def.origin.rpy[0],
                                    def.origin.rpy[1],
                                    def.origin.rpy[2],
                                    'ZYX'
                                )
                            );
                            // Keep capsule axis correction after applying URDF origin rotation.
                            capsuleGroup.quaternion.copy(originQuaternion).multiply(capsuleAxisCorrection);
                        }

                        // Apply color if specified
                        if (def.color && def.type === 'visual') {
                            capsuleGroup.traverse((mesh: any) => {
                                if (mesh.isMesh && mesh.material) {
                                    mesh.material.color.setStyle(def.color!);
                                }
                            });
                        }

                        // Add to appropriate container
                        if (def.type === 'visual') {
                            // Add to visual group
                            let visualContainer = child.children.find((c: any) =>
                                !c.isURDFCollider && !c.isURDFJoint
                            );
                            if (!visualContainer) {
                                visualContainer = child;
                            }

                            capsuleGroup.traverse((mesh: any) => {
                                if (mesh.isMesh) {
                                    mesh.userData.isVisualMesh = true;
                                    mesh.userData.parentLinkName = linkName;
                                }
                            });

                            visualContainer.add(capsuleGroup);
                        } else {
                            // Add to collision group
                            let collisionContainer = child.children.find((c: any) => c.isURDFCollider);

                            if (!collisionContainer) {
                                collisionContainer = new THREE.Group();
                                (collisionContainer as any).isURDFCollider = true;
                                collisionContainer.visible = false;
                                child.add(collisionContainer);
                            }

                            // Apply collision material
                            const disposedMaterials = new Set<THREE.Material>();
                            capsuleGroup.traverse((mesh: any) => {
                                if (mesh.isMesh) {
                                    mesh.userData.isCollisionMesh = true;
                                    mesh.userData.parentLinkName = linkName;
                                    const previousMaterial = mesh.material as THREE.Material | THREE.Material[] | undefined;
                                    mesh.material = createCollisionOverlayMaterial('collision_capsule');
                                    mesh.renderOrder = COLLISION_OVERLAY_RENDER_ORDER;
                                    disposeReplacedMaterials(previousMaterial, disposedMaterials, true);
                                }
                            });

                            collisionContainer.add(capsuleGroup);
                        }
                    });
                }
            }
        });

    } catch (error) {
        console.error('[CapsulePostProcessor] Error processing capsules:', error);
    }
}
