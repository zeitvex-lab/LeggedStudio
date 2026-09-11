//! Kinematic model + forward kinematics.

use std::collections::HashMap;

use nalgebra::{Isometry3, Translation3, UnitQuaternion, Vector3};

use crate::mjcf::{self, ParseError, Tree};

/// SE(3) pose returned by [`Model::site_pose`].
///
/// `translation` is in the trunk frame (metres). `rotation` is the
/// orientation of the site frame expressed in the trunk frame.
#[derive(Debug, Clone, Copy)]
pub struct Pose {
    pub translation: Vector3<f64>,
    pub rotation: UnitQuaternion<f64>,
}

impl From<Isometry3<f64>> for Pose {
    fn from(t: Isometry3<f64>) -> Self {
        Self {
            translation: t.translation.vector,
            rotation: t.rotation,
        }
    }
}

/// Joint configuration: a name → angle (radians) map.
///
/// Unset joints default to 0. Names that don't exist in the model are
/// silently ignored, so the same vector can be reused across versions.
#[derive(Debug, Default, Clone)]
pub struct JointVector {
    angles: HashMap<String, f64>,
}

impl JointVector {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set(&mut self, name: &str, q: f64) -> &mut Self {
        self.angles.insert(name.to_string(), q);
        self
    }

    pub fn get(&self, name: &str) -> f64 {
        self.angles.get(name).copied().unwrap_or(0.0)
    }

    pub fn from_pairs<I, S>(pairs: I) -> Self
    where
        I: IntoIterator<Item = (S, f64)>,
        S: Into<String>,
    {
        Self {
            angles: pairs.into_iter().map(|(k, v)| (k.into(), v)).collect(),
        }
    }
}

/// Forward-kinematics model parsed from an MJCF.
///
/// The trunk frame is the reference: all poses returned by [`Self::site_pose`]
/// are in the `trunk_base` body's frame at identity. The `freejoint` on the
/// trunk is ignored.
#[derive(Debug, Clone)]
pub struct Model {
    tree: Tree,
    /// joint name → index of the body that joint drives
    joint_body: HashMap<String, usize>,
    /// site name → index into `tree.sites`
    site_idx: HashMap<String, usize>,
    /// canonical joint name order (depth-first body traversal, skips passive)
    joint_names: Vec<String>,
}

impl Model {
    /// Bundled microduck v1 model.
    pub fn v1() -> Self {
        Self::from_mjcf_str(crate::V1_MJCF).expect("bundled v1 MJCF must parse")
    }

    /// Bundled microduck v1.5 model.
    pub fn v1_5() -> Self {
        Self::from_mjcf_str(crate::V1_5_MJCF).expect("bundled v1.5 MJCF must parse")
    }

    /// Bundled microduck alpha model. New leg/head geometry; unlike
    /// v1/v1.5 the mouth has no passive linkage, so `mouth_tip` is a rigid
    /// site on `bottom_head_shell` and is FK-computable directly.
    pub fn alpha() -> Self {
        Self::from_mjcf_str(crate::ALPHA_MJCF).expect("bundled alpha MJCF must parse")
    }

    /// Parse an MJCF from a string.
    pub fn from_mjcf_str(xml: &str) -> Result<Self, ParseError> {
        let tree = mjcf::parse(xml)?;
        let mut joint_body = HashMap::new();
        let mut joint_names = Vec::new();
        for (i, b) in tree.bodies.iter().enumerate() {
            if let Some(j) = &b.joint {
                joint_body.insert(j.name.clone(), i);
                joint_names.push(j.name.clone());
            }
        }
        let site_idx = tree
            .sites
            .iter()
            .enumerate()
            .map(|(i, s)| (s.name.clone(), i))
            .collect();
        Ok(Self { tree, joint_body, site_idx, joint_names })
    }

    /// All site names exposed by this model, in declaration order.
    pub fn site_names(&self) -> Vec<&str> {
        self.tree.sites.iter().map(|s| s.name.as_str()).collect()
    }

    /// All joint names in canonical order (depth-first over the tree).
    pub fn joint_names(&self) -> &[String] {
        &self.joint_names
    }

    /// A [`JointVector`] with every joint set to 0.
    pub fn zero_joints(&self) -> JointVector {
        JointVector::from_pairs(self.joint_names.iter().map(|n| (n.clone(), 0.0)))
    }

    /// Return the pose of the named site in the trunk frame.
    ///
    /// Panics if `name` is not a site of this model — site sets are version-
    /// specific and known at compile time, so this is a programming error.
    pub fn site_pose(&self, name: &str, q: &JointVector) -> Pose {
        let site = self
            .site_idx
            .get(name)
            .map(|&i| &self.tree.sites[i])
            .unwrap_or_else(|| panic!("unknown site {name:?}"));
        let body_world = self.body_pose(site.body, q);
        let site_local = Isometry3::from_parts(Translation3::from(site.pos), site.quat);
        (body_world * site_local).into()
    }

    /// Compute the pose of every site for the given joint vector.
    pub fn all_site_poses(&self, q: &JointVector) -> HashMap<String, Pose> {
        let body_poses = self.body_poses(q);
        self.tree
            .sites
            .iter()
            .map(|s| {
                let local = Isometry3::from_parts(Translation3::from(s.pos), s.quat);
                (s.name.clone(), (body_poses[s.body] * local).into())
            })
            .collect()
    }

    fn body_pose(&self, idx: usize, q: &JointVector) -> Isometry3<f64> {
        self.body_poses(q)[idx]
    }

    fn body_poses(&self, q: &JointVector) -> Vec<Isometry3<f64>> {
        let n = self.tree.bodies.len();
        let mut out = Vec::with_capacity(n);
        for (i, body) in self.tree.bodies.iter().enumerate() {
            let local = local_pose(body, q);
            let world = match body.parent {
                Some(p) => out[p] * local,
                None => local,
            };
            debug_assert_eq!(out.len(), i);
            out.push(world);
        }
        out
    }

    /// Map a joint name to its axis in the joint's body frame.
    /// Useful for debugging; not part of the canonical FK API.
    pub fn joint_axis_local(&self, name: &str) -> Option<Vector3<f64>> {
        let &idx = self.joint_body.get(name)?;
        self.tree.bodies[idx].joint.as_ref().map(|j| j.axis)
    }
}

fn local_pose(body: &mjcf::Body, q: &JointVector) -> Isometry3<f64> {
    let rest = Isometry3::from_parts(Translation3::from(body.pos), body.quat);
    match &body.joint {
        None => rest,
        Some(j) => {
            // MJCF hinge convention: the joint rotates the body by `q` about
            // its axis (in body frame), applied after the rest transform.
            let axis = nalgebra::Unit::new_normalize(j.axis);
            let rot = UnitQuaternion::from_axis_angle(&axis, q.get(&j.name));
            let joint_tf = Isometry3::from_parts(Translation3::identity(), rot);
            rest * joint_tf
        }
    }
}

