import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');
const inputPath = path.resolve(repoRoot, 'src/features/code-editor/resources/urdf.xsd');
const outputPath = path.resolve(repoRoot, 'src/features/code-editor/utils/urdfSchema.generated.ts');

const parser = new JSDOM('').window.DOMParser;

const text = await fs.readFile(inputPath, 'utf8');
const doc = new parser().parseFromString(text, 'text/xml');

const simpleTypes = new Map();
for (const simpleType of Array.from(doc.getElementsByTagName('xs:simpleType'))) {
  const name = simpleType.getAttribute('name');
  if (!name) continue;
  const values = Array.from(simpleType.getElementsByTagName('xs:enumeration'))
    .map((node) => node.getAttribute('value'))
    .filter(Boolean);
  simpleTypes.set(name, values);
}

const typeSchemas = new Map();
const elementTypeNames = new Map();

const elementNodes = Array.from(doc.documentElement.childNodes).filter(
  (node) => node.nodeType === 1 && node.tagName === 'xs:element',
);

const complexTypeNodes = Array.from(doc.documentElement.childNodes).filter(
  (node) => node.nodeType === 1 && node.tagName === 'xs:complexType',
);

const collectChildElements = (node, ownerName, seen = new Set()) => {
  const result = [];

  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType !== 1) continue;

    if (child.tagName === 'xs:element') {
      const name = child.getAttribute('name');
      if (!name) continue;
      const type = child.getAttribute('type') || `${ownerName}.${name}`;

      if (!seen.has(type) && !child.getAttribute('type')) {
        seen.add(type);
        const inlineComplexType = Array.from(child.childNodes).find(
          (candidate) => candidate.nodeType === 1 && candidate.tagName === 'xs:complexType',
        );
        if (inlineComplexType) {
          parseComplexType(inlineComplexType, type);
        }
      }

      result.push({
        name,
        type,
        minOccurs: child.getAttribute('minOccurs') || null,
        maxOccurs: child.getAttribute('maxOccurs') || null,
      });
      continue;
    }

    if (child.tagName === 'xs:any') {
      result.push({
        name: '*',
        type: '*',
        minOccurs: child.getAttribute('minOccurs') || null,
        maxOccurs: child.getAttribute('maxOccurs') || null,
      });
      continue;
    }

    if (
      child.tagName === 'xs:sequence' ||
      child.tagName === 'xs:choice' ||
      child.tagName === 'xs:all'
    ) {
      result.push(...collectChildElements(child, ownerName, seen));
    }
  }

  return result;
};

function parseComplexType(complexTypeNode, typeName) {
  if (typeSchemas.has(typeName)) {
    return;
  }

  const attributes = Array.from(complexTypeNode.childNodes)
    .filter((node) => node.nodeType === 1 && node.tagName === 'xs:attribute')
    .map((node) => {
      const attrName = node.getAttribute('name');
      if (!attrName) return null;
      const attrType = node.getAttribute('type') || 'xs:string';
      return {
        name: attrName,
        required: node.getAttribute('use') === 'required',
        type: attrType,
        values: simpleTypes.get(attrType) || [],
      };
    })
    .filter(Boolean);

  const children = collectChildElements(complexTypeNode, typeName);

  typeSchemas.set(typeName, {
    typeName,
    allowAnyChildren: children.some((child) => child.name === '*'),
    attributes,
    children: children.filter((child) => child.name !== '*'),
  });
}

for (const complexTypeNode of complexTypeNodes) {
  parseComplexType(complexTypeNode, complexTypeNode.getAttribute('name'));
}

for (const elementNode of elementNodes) {
  const name = elementNode.getAttribute('name');
  if (!name) continue;

  const referencedType = elementNode.getAttribute('type');
  if (referencedType) {
    elementTypeNames.set(name, referencedType);
    continue;
  }

  const inlineComplexType = Array.from(elementNode.childNodes).find(
    (candidate) => candidate.nodeType === 1 && candidate.tagName === 'xs:complexType',
  );

  if (inlineComplexType) {
    parseComplexType(inlineComplexType, name);
    elementTypeNames.set(name, name);
  }
}

const schemaNodes = Object.fromEntries(
  Array.from(typeSchemas.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, schema]) => [name, schema]),
);

const elementTypeMap = Object.fromEntries(
  Array.from(elementTypeNames.entries()).sort(([a], [b]) => a.localeCompare(b)),
);

const header = `/**
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

`;

const output = `${header}export const urdfElementTypeMap = ${JSON.stringify(elementTypeMap, null, 2)} as const;

export const urdfSchemaNodes = ${JSON.stringify(schemaNodes, null, 2)} as const satisfies Record<string, GeneratedUrdfSchemaNode>;
`;

await fs.writeFile(outputPath, output);

console.log(
  `Generated ${path.relative(repoRoot, outputPath)} from ${path.relative(repoRoot, inputPath)}`,
);
