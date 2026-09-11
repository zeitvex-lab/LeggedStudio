/**
 * Generated from src/features/code-editor/resources/urdf.xsd
 * Source: https://github.com/ros/urdfdom/blob/rolling/xsd/urdf.xsd
 * Do not edit manually. Re-run scripts/generate/generate_urdf_schema_metadata.mjs after updating the XSD.
 */

export interface GeneratedUrdfSchemaAttribute {
  name: string;
  required: boolean;
  type: string;
  values: string[];
}

export interface GeneratedUrdfSchemaChild {
  name: string;
  type: string;
  minOccurs: string | null;
  maxOccurs: string | null;
}

export interface GeneratedUrdfSchemaNode {
  typeName: string;
  allowAnyChildren: boolean;
  attributes: GeneratedUrdfSchemaAttribute[];
  children: GeneratedUrdfSchemaChild[];
}

export const urdfElementTypeMap = {
  "robot": "robot"
} as const;

export const urdfSchemaNodes = {
  "actuator_transmission": {
    "typeName": "actuator_transmission",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "mechanicalReduction",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "axis": {
    "typeName": "axis",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "xyz",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "box": {
    "typeName": "box",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "size",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "calibration": {
    "typeName": "calibration",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "reference_position",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "rising",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "falling",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "camera": {
    "typeName": "camera",
    "allowAnyChildren": false,
    "attributes": [],
    "children": [
      {
        "name": "image",
        "type": "image",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "capsule": {
    "typeName": "capsule",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "radius",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "length",
        "required": true,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "child": {
    "typeName": "child",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "link",
        "required": true,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "collision": {
    "typeName": "collision",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "origin",
        "type": "pose",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "geometry",
        "type": "geometry",
        "minOccurs": "1",
        "maxOccurs": "1"
      },
      {
        "name": "verbose",
        "type": "verbose",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "color": {
    "typeName": "color",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "rgba",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "cylinder": {
    "typeName": "cylinder",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "radius",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "length",
        "required": true,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "dynamics": {
    "typeName": "dynamics",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "damping",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "friction",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "gap_joint_transmission": {
    "typeName": "gap_joint_transmission",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "L0",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "a",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "b",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "gear_ratio",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "h",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "mechanical_reduction",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "phi0",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "r",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "screw_reduction",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "t0",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "theta0",
        "required": true,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "gazebo": {
    "typeName": "gazebo",
    "allowAnyChildren": true,
    "attributes": [],
    "children": []
  },
  "geometry": {
    "typeName": "geometry",
    "allowAnyChildren": false,
    "attributes": [],
    "children": [
      {
        "name": "box",
        "type": "box",
        "minOccurs": null,
        "maxOccurs": null
      },
      {
        "name": "cylinder",
        "type": "cylinder",
        "minOccurs": null,
        "maxOccurs": null
      },
      {
        "name": "sphere",
        "type": "sphere",
        "minOccurs": null,
        "maxOccurs": null
      },
      {
        "name": "mesh",
        "type": "mesh",
        "minOccurs": null,
        "maxOccurs": null
      },
      {
        "name": "capsule",
        "type": "capsule",
        "minOccurs": null,
        "maxOccurs": null
      }
    ]
  },
  "image": {
    "typeName": "image",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "width",
        "required": true,
        "type": "xs:unsignedInt",
        "values": []
      },
      {
        "name": "height",
        "required": true,
        "type": "xs:unsignedInt",
        "values": []
      },
      {
        "name": "format",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "hfov",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "near",
        "required": true,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "far",
        "required": true,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "inertia": {
    "typeName": "inertia",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "ixx",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "ixy",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "ixz",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "iyy",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "iyz",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "izz",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "inertial": {
    "typeName": "inertial",
    "allowAnyChildren": false,
    "attributes": [],
    "children": [
      {
        "name": "origin",
        "type": "pose",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "mass",
        "type": "mass",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "inertia",
        "type": "inertia",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "joint": {
    "typeName": "joint",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "type",
        "required": true,
        "type": "JointType",
        "values": [
          "revolute",
          "continuous",
          "prismatic",
          "fixed",
          "floating",
          "planar"
        ]
      }
    ],
    "children": [
      {
        "name": "origin",
        "type": "pose",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "parent",
        "type": "parent",
        "minOccurs": "1",
        "maxOccurs": "1"
      },
      {
        "name": "child",
        "type": "child",
        "minOccurs": "1",
        "maxOccurs": "1"
      },
      {
        "name": "axis",
        "type": "axis",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "calibration",
        "type": "calibration",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "dynamics",
        "type": "dynamics",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "limit",
        "type": "limit",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "safety_controller",
        "type": "safety_controller",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "mimic",
        "type": "mimic",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "LaserRay": {
    "typeName": "LaserRay",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "samples",
        "required": false,
        "type": "xs:unsignedInt",
        "values": []
      },
      {
        "name": "resolution",
        "required": false,
        "type": "xs:unsignedInt",
        "values": []
      },
      {
        "name": "min_angle",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "max_angle",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "limit": {
    "typeName": "limit",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "lower",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "upper",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "effort",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "velocity",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "link": {
    "typeName": "link",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "type",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "inertial",
        "type": "inertial",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "visual",
        "type": "visual",
        "minOccurs": null,
        "maxOccurs": null
      },
      {
        "name": "collision",
        "type": "collision",
        "minOccurs": null,
        "maxOccurs": null
      }
    ]
  },
  "mass": {
    "typeName": "mass",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "value",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "material": {
    "typeName": "material",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "color",
        "type": "color",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "texture",
        "type": "texture",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "material_global": {
    "typeName": "material_global",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "color",
        "type": "color",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "texture",
        "type": "texture",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "mesh": {
    "typeName": "mesh",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "filename",
        "required": true,
        "type": "xs:anyURI",
        "values": []
      },
      {
        "name": "scale",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "mimic": {
    "typeName": "mimic",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "joint",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "multiplier",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "offset",
        "required": false,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "name": {
    "typeName": "name",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "parent": {
    "typeName": "parent",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "link",
        "required": true,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "passive_joint_transmission": {
    "typeName": "passive_joint_transmission",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "pose": {
    "typeName": "pose",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "xyz",
        "required": false,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "rpy",
        "required": false,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "quat_xyzw",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "ray": {
    "typeName": "ray",
    "allowAnyChildren": false,
    "attributes": [],
    "children": [
      {
        "name": "horizontal",
        "type": "LaserRay",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "vertical",
        "type": "LaserRay",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "robot": {
    "typeName": "robot",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "version",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "joint",
        "type": "joint",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      },
      {
        "name": "link",
        "type": "link",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      },
      {
        "name": "material",
        "type": "material_global",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      },
      {
        "name": "transmission",
        "type": "transmission",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      },
      {
        "name": "gazebo",
        "type": "gazebo",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      },
      {
        "name": "sensor",
        "type": "sensor",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      }
    ]
  },
  "safety_controller": {
    "typeName": "safety_controller",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "soft_lower_limit",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "soft_upper_limit",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "k_position",
        "required": false,
        "type": "xs:double",
        "values": []
      },
      {
        "name": "k_velocity",
        "required": true,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "sensor": {
    "typeName": "sensor",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "update_rate",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "origin",
        "type": "pose",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "parent",
        "type": "parent",
        "minOccurs": "1",
        "maxOccurs": "1"
      },
      {
        "name": "camera",
        "type": "camera",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "ray",
        "type": "ray",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "sphere": {
    "typeName": "sphere",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "radius",
        "required": true,
        "type": "xs:double",
        "values": []
      }
    ],
    "children": []
  },
  "texture": {
    "typeName": "texture",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "filename",
        "required": false,
        "type": "xs:anyURI",
        "values": []
      }
    ],
    "children": []
  },
  "transmission": {
    "typeName": "transmission",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": true,
        "type": "xs:string",
        "values": []
      },
      {
        "name": "type",
        "required": true,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "leftActuator",
        "type": "actuator_transmission",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "rightActuator",
        "type": "actuator_transmission",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "flexJoint",
        "type": "actuator_transmission",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "rollJoint",
        "type": "actuator_transmission",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "gap_joint",
        "type": "gap_joint_transmission",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "passive_joint",
        "type": "passive_joint_transmission",
        "minOccurs": "0",
        "maxOccurs": "unbounded"
      },
      {
        "name": "use_simulated_gripper_joint",
        "type": "transmission.use_simulated_gripper_joint",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "mechanicalReduction",
        "type": "xs:double",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "actuator",
        "type": "name",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "joint",
        "type": "name",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  },
  "transmission.use_simulated_gripper_joint": {
    "typeName": "transmission.use_simulated_gripper_joint",
    "allowAnyChildren": false,
    "attributes": [],
    "children": []
  },
  "verbose": {
    "typeName": "verbose",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "value",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": []
  },
  "visual": {
    "typeName": "visual",
    "allowAnyChildren": false,
    "attributes": [
      {
        "name": "name",
        "required": false,
        "type": "xs:string",
        "values": []
      }
    ],
    "children": [
      {
        "name": "origin",
        "type": "pose",
        "minOccurs": "0",
        "maxOccurs": "1"
      },
      {
        "name": "geometry",
        "type": "geometry",
        "minOccurs": "1",
        "maxOccurs": "1"
      },
      {
        "name": "material",
        "type": "material",
        "minOccurs": "0",
        "maxOccurs": "1"
      }
    ]
  }
} as const satisfies Record<string, GeneratedUrdfSchemaNode>;
