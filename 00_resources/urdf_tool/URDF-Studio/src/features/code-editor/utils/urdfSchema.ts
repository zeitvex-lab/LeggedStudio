import {
  urdfElementTypeMap,
  urdfSchemaNodes,
  type GeneratedUrdfSchemaAttribute,
  type GeneratedUrdfSchemaNode,
} from './urdfSchema.generated.ts';

type SchemaNodeMap = Record<string, GeneratedUrdfSchemaNode>;

const schemaNodes = urdfSchemaNodes as SchemaNodeMap;
const rootTypeName = urdfElementTypeMap.robot;

const uniqueSorted = <T>(values: T[]): T[] => Array.from(new Set(values));

const collectAllElementNames = (): string[] => {
  const names = ['robot'];

  for (const node of Object.values(schemaNodes)) {
    names.push(...node.children.map((child) => child.name));
  }

  return uniqueSorted(names).sort();
};

const collectAllAttributeNames = (): string[] => {
  const names: string[] = [];

  for (const node of Object.values(schemaNodes)) {
    names.push(...node.attributes.map((attribute) => attribute.name));
  }

  return uniqueSorted(names).sort();
};

const candidateSchemaTypeNamesByElementName = new Map<string, string[]>();

const registerCandidateType = (elementName: string, typeName: string) => {
  const current = candidateSchemaTypeNamesByElementName.get(elementName) || [];
  if (!current.includes(typeName)) {
    current.push(typeName);
    candidateSchemaTypeNamesByElementName.set(elementName, current);
  }
};

registerCandidateType('robot', rootTypeName);

for (const [typeName, node] of Object.entries(schemaNodes)) {
  registerCandidateType(typeName, typeName);
  for (const child of node.children) {
    registerCandidateType(child.name, child.type);
  }
}

const getSchemaNodeByType = (typeName: string | null | undefined): GeneratedUrdfSchemaNode | null => {
  if (!typeName) {
    return null;
  }

  return schemaNodes[typeName] || null;
};

const mergeAttributes = (attributes: GeneratedUrdfSchemaAttribute[]): GeneratedUrdfSchemaAttribute[] => {
  const merged = new Map<string, GeneratedUrdfSchemaAttribute>();

  for (const attribute of attributes) {
    const existing = merged.get(attribute.name);
    if (!existing) {
      merged.set(attribute.name, {
        ...attribute,
        values: [...attribute.values],
      });
      continue;
    }

    merged.set(attribute.name, {
      ...existing,
      required: existing.required || attribute.required,
      values: uniqueSorted([...existing.values, ...attribute.values]).sort(),
    });
  }

  return Array.from(merged.values()).sort((a, b) => a.name.localeCompare(b.name));
};

export const getUrdfRootSchema = (): GeneratedUrdfSchemaNode => schemaNodes[rootTypeName];

export const getUrdfSchemaNodeByType = (typeName: string): GeneratedUrdfSchemaNode | null =>
  getSchemaNodeByType(typeName);

export const resolveUrdfChildSchemaType = (
  parentTypeName: string,
  childElementName: string,
): string | null => {
  const parent = getSchemaNodeByType(parentTypeName);
  if (!parent) {
    return null;
  }

  return parent.children.find((child) => child.name === childElementName)?.type || null;
};

export const getUrdfCandidateSchemasForElement = (
  elementName: string,
): GeneratedUrdfSchemaNode[] => {
  const typeNames = candidateSchemaTypeNamesByElementName.get(elementName) || [];
  return typeNames
    .map((typeName) => getSchemaNodeByType(typeName))
    .filter((node): node is GeneratedUrdfSchemaNode => Boolean(node));
};

export const getUrdfAttributesForElement = (elementName: string): GeneratedUrdfSchemaAttribute[] =>
  mergeAttributes(
    getUrdfCandidateSchemasForElement(elementName)
      .flatMap((node) => node.attributes),
  );

export const getUrdfEnumValuesForAttribute = (
  elementName: string,
  attributeName: string,
): string[] => uniqueSorted(
  getUrdfAttributesForElement(elementName)
    .filter((attribute) => attribute.name === attributeName)
    .flatMap((attribute) => attribute.values),
).sort();

export const getAllUrdfElementNames = (): string[] => collectAllElementNames();

export const getAllUrdfAttributeNames = (): string[] => collectAllAttributeNames();
