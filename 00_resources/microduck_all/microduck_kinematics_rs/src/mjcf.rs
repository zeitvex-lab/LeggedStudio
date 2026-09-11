//! Minimal MJCF parser for forward kinematics.
//!
//! Reads the kinematic tree (bodies, hinge joints, sites) and ignores
//! everything else (geoms, inertials, actuators, sensors, assets,
//! defaults). Quaternions are returned in MuJoCo convention `[w, x, y, z]`.

use nalgebra::{UnitQuaternion, Vector3};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ParseError {
    #[error("xml parse error: {0}")]
    Xml(#[from] roxmltree::Error),
    #[error("missing <worldbody> in MJCF")]
    NoWorldbody,
    #[error("missing <body name=\"trunk_base\"> in MJCF")]
    NoTrunkBase,
    #[error("body {0:?} has no name attribute")]
    UnnamedBody(String),
    #[error("failed to parse float in attribute {attr:?} on <{tag}>: {value:?}")]
    BadFloat { tag: String, attr: String, value: String },
    #[error("attribute {attr:?} on <{tag}> must have {expected} components, got {got}")]
    BadVector { tag: String, attr: String, expected: usize, got: usize },
}

#[derive(Debug, Clone)]
pub(crate) struct Body {
    #[allow(dead_code)] // kept for Debug output / diagnostics
    pub name: String,
    /// Index into `Model::bodies`. `None` only for the root (trunk_base).
    pub parent: Option<usize>,
    /// Rest pose of this body in its parent's frame (identity for the root).
    pub pos: Vector3<f64>,
    pub quat: UnitQuaternion<f64>,
    /// Hinge joint connecting this body to its parent. `None` = welded.
    pub joint: Option<Joint>,
}

#[derive(Debug, Clone)]
pub(crate) struct Joint {
    pub name: String,
    pub axis: Vector3<f64>,
}

#[derive(Debug, Clone)]
pub(crate) struct Site {
    pub name: String,
    pub body: usize,
    pub pos: Vector3<f64>,
    pub quat: UnitQuaternion<f64>,
}

#[derive(Debug, Clone)]
pub(crate) struct Tree {
    pub bodies: Vec<Body>,
    pub sites: Vec<Site>,
}

pub(crate) fn parse(xml: &str) -> Result<Tree, ParseError> {
    let doc = roxmltree::Document::parse(xml)?;
    let root = doc.root_element();
    let worldbody = root
        .children()
        .find(|n| n.is_element() && n.tag_name().name() == "worldbody")
        .ok_or(ParseError::NoWorldbody)?;

    let trunk = worldbody
        .children()
        .find(|n| n.is_element() && n.tag_name().name() == "body" && n.attribute("name") == Some("trunk_base"))
        .ok_or(ParseError::NoTrunkBase)?;

    let mut bodies = Vec::new();
    let mut sites = Vec::new();

    // Root is trunk_base, anchored at identity so all FK output is in trunk frame.
    bodies.push(Body {
        name: "trunk_base".into(),
        parent: None,
        pos: Vector3::zeros(),
        quat: UnitQuaternion::identity(),
        joint: None,
    });
    collect_sites(trunk, 0, &mut sites)?;

    for child in element_children(trunk) {
        if child.tag_name().name() == "body" {
            walk_body(child, 0, &mut bodies, &mut sites)?;
        }
    }

    Ok(Tree { bodies, sites })
}

fn walk_body<'a, 'input>(
    node: roxmltree::Node<'a, 'input>,
    parent: usize,
    bodies: &mut Vec<Body>,
    sites: &mut Vec<Site>,
) -> Result<(), ParseError> {
    let name = node
        .attribute("name")
        .ok_or_else(|| ParseError::UnnamedBody(format!("child of body index {parent}")))?;

    let pos = parse_vec3(node, "pos")?.unwrap_or_else(Vector3::zeros);
    let quat = parse_quat(node, "quat")?.unwrap_or_else(UnitQuaternion::identity);

    let joint = node
        .children()
        .find(|n| n.is_element() && n.tag_name().name() == "joint")
        .map(|j| -> Result<Joint, ParseError> {
            let jname = j.attribute("name").unwrap_or("").to_string();
            let axis = parse_vec3(j, "axis")?.unwrap_or_else(|| Vector3::new(0.0, 0.0, 1.0));
            Ok(Joint { name: jname, axis })
        })
        .transpose()?;

    let idx = bodies.len();
    bodies.push(Body {
        name: name.to_string(),
        parent: Some(parent),
        pos,
        quat,
        joint,
    });

    collect_sites(node, idx, sites)?;

    for child in element_children(node) {
        if child.tag_name().name() == "body" {
            walk_body(child, idx, bodies, sites)?;
        }
    }
    Ok(())
}

fn collect_sites<'a, 'input>(
    node: roxmltree::Node<'a, 'input>,
    body_idx: usize,
    sites: &mut Vec<Site>,
) -> Result<(), ParseError> {
    for child in element_children(node) {
        if child.tag_name().name() == "site" {
            let Some(name) = child.attribute("name") else { continue };
            let pos = parse_vec3(child, "pos")?.unwrap_or_else(Vector3::zeros);
            let quat = parse_quat(child, "quat")?.unwrap_or_else(UnitQuaternion::identity);
            sites.push(Site {
                name: name.to_string(),
                body: body_idx,
                pos,
                quat,
            });
        }
    }
    Ok(())
}

fn element_children<'a, 'input>(
    node: roxmltree::Node<'a, 'input>,
) -> impl Iterator<Item = roxmltree::Node<'a, 'input>> {
    node.children().filter(|n| n.is_element())
}

fn parse_floats(s: &str, tag: &str, attr: &str) -> Result<Vec<f64>, ParseError> {
    s.split_whitespace()
        .map(|tok| {
            tok.parse::<f64>().map_err(|_| ParseError::BadFloat {
                tag: tag.into(),
                attr: attr.into(),
                value: tok.into(),
            })
        })
        .collect()
}

fn parse_vec3(node: roxmltree::Node, attr: &str) -> Result<Option<Vector3<f64>>, ParseError> {
    let Some(s) = node.attribute(attr) else { return Ok(None) };
    let v = parse_floats(s, node.tag_name().name(), attr)?;
    if v.len() != 3 {
        return Err(ParseError::BadVector {
            tag: node.tag_name().name().into(),
            attr: attr.into(),
            expected: 3,
            got: v.len(),
        });
    }
    Ok(Some(Vector3::new(v[0], v[1], v[2])))
}

fn parse_quat(node: roxmltree::Node, attr: &str) -> Result<Option<UnitQuaternion<f64>>, ParseError> {
    let Some(s) = node.attribute(attr) else { return Ok(None) };
    let v = parse_floats(s, node.tag_name().name(), attr)?;
    if v.len() != 4 {
        return Err(ParseError::BadVector {
            tag: node.tag_name().name().into(),
            attr: attr.into(),
            expected: 4,
            got: v.len(),
        });
    }
    // MJCF stores quaternions as (w, x, y, z). nalgebra's Quaternion::new is (w, i, j, k).
    let q = nalgebra::Quaternion::new(v[0], v[1], v[2], v[3]);
    Ok(Some(UnitQuaternion::from_quaternion(q)))
}
