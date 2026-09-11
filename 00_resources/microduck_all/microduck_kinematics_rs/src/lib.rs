//! Forward kinematics for the microduck robot.
//!
//! Loads a MuJoCo MJCF file, builds an in-memory kinematic tree of bodies,
//! hinge joints and sites, and evaluates site poses in the trunk frame for
//! a given set of joint angles.
//!
//! ```no_run
//! use microduck_kinematics::Model;
//!
//! let model = Model::v1_5();
//! let mut q = model.zero_joints();
//! q.set("head_yaw", 0.3);
//! let pose = model.site_pose("head_camera", &q);
//! println!("{:?}", pose.translation);
//! ```

mod mjcf;
mod model;

pub use model::{JointVector, Model, Pose};
pub use mjcf::ParseError;

/// MJCF text for v1, bundled at compile time.
pub const V1_MJCF: &str = include_str!("../assets/v1/robot_walk.xml");

/// MJCF text for v1.5, bundled at compile time.
pub const V1_5_MJCF: &str = include_str!("../assets/v1.5/robot_walk.xml");

/// MJCF text for alpha, bundled at compile time.
pub const ALPHA_MJCF: &str = include_str!("../assets/alpha/robot_walk.xml");
