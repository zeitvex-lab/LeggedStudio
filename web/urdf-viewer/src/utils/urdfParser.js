/**
 * URDF 解析器（简化版）
 *
 * 功能：
 * - 解析 URDF XML
 * - 提取 link 和 joint 信息
 * - 提取 mesh 文件路径
 */

export function parseURDF(xmlString) {
  const parser = new DOMParser();
  const xml = parser.parseFromString(xmlString, 'text/xml');

  // 检查解析错误
  const parseError = xml.querySelector('parsererror');
  if (parseError) {
    throw new Error('XML 解析失败: ' + parseError.textContent);
  }

  const robotElement = xml.querySelector('robot');
  if (!robotElement) {
    throw new Error('未找到 <robot> 元素');
  }

  const robot = {
    name: robotElement.getAttribute('name') || 'unnamed',
    links: [],
    joints: []
  };

  // 解析 links
  xml.querySelectorAll('link').forEach(link => {
    const name = link.getAttribute('name');
    const visual = link.querySelector('visual');

    const linkData = {
      name,
      visual: null
    };

    if (visual) {
      const geometry = visual.querySelector('geometry');

      if (geometry) {
        const mesh = geometry.querySelector('mesh');
        const box = geometry.querySelector('box');
        const cylinder = geometry.querySelector('cylinder');
        const sphere = geometry.querySelector('sphere');

        if (mesh) {
          linkData.visual = {
            type: 'mesh',
            filename: mesh.getAttribute('filename'),
            scale: parseVector(mesh.getAttribute('scale'), [1, 1, 1])
          };
        } else if (box) {
          linkData.visual = {
            type: 'box',
            size: parseVector(box.getAttribute('size'), [1, 1, 1])
          };
        } else if (cylinder) {
          linkData.visual = {
            type: 'cylinder',
            radius: parseFloat(cylinder.getAttribute('radius') || 1),
            length: parseFloat(cylinder.getAttribute('length') || 1)
          };
        } else if (sphere) {
          linkData.visual = {
            type: 'sphere',
            radius: parseFloat(sphere.getAttribute('radius') || 1)
          };
        }
      }

      // 解析 origin（位置和旋转）
      const origin = visual.querySelector('origin');
      if (origin) {
        linkData.visual.origin = {
          xyz: parseVector(origin.getAttribute('xyz'), [0, 0, 0]),
          rpy: parseVector(origin.getAttribute('rpy'), [0, 0, 0])
        };
      } else {
        linkData.visual.origin = {
          xyz: [0, 0, 0],
          rpy: [0, 0, 0]
        };
      }

      // 解析材质颜色
      const material = visual.querySelector('material');
      if (material) {
        const color = material.querySelector('color');
        if (color) {
          linkData.visual.color = parseVector(color.getAttribute('rgba'), [0.8, 0.8, 0.8, 1.0]);
        }
      }
    }

    robot.links.push(linkData);
  });

  // 解析 joints（简化版：仅父子关系）
  xml.querySelectorAll('joint').forEach(joint => {
    const name = joint.getAttribute('name');
    const type = joint.getAttribute('type');
    const parent = joint.querySelector('parent');
    const child = joint.querySelector('child');

    const jointData = {
      name,
      type,
      parent: parent ? parent.getAttribute('link') : null,
      child: child ? child.getAttribute('link') : null
    };

    // 解析 origin
    const origin = joint.querySelector('origin');
    if (origin) {
      jointData.origin = {
        xyz: parseVector(origin.getAttribute('xyz'), [0, 0, 0]),
        rpy: parseVector(origin.getAttribute('rpy'), [0, 0, 0])
      };
    }

    robot.joints.push(jointData);
  });

  return robot;
}

/**
 * 解析向量字符串 "x y z" -> [x, y, z]
 */
function parseVector(str, defaultValue) {
  if (!str) return defaultValue;
  return str.trim().split(/\s+/).map(parseFloat);
}

/**
 * 构建机器人树结构（用于后续渲染）
 */
export function buildRobotTree(urdfData) {
  const linkMap = new Map();

  // 创建 link map
  urdfData.links.forEach(link => {
    linkMap.set(link.name, {
      ...link,
      children: []
    });
  });

  // 根据 joint 建立父子关系
  urdfData.joints.forEach(joint => {
    if (joint.parent && joint.child) {
      const parent = linkMap.get(joint.parent);
      const child = linkMap.get(joint.child);

      if (parent && child) {
        parent.children.push({
          joint,
          link: child
        });
      }
    }
  });

  // 找到根 link（没有父节点的）
  const childLinks = new Set(urdfData.joints.map(j => j.child));
  const rootLinks = urdfData.links.filter(l => !childLinks.has(l.name));

  return rootLinks.length > 0 ? linkMap.get(rootLinks[0].name) : null;
}
