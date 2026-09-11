import {
  getUrdfRootSchema,
  getUrdfSchemaNodeByType,
  resolveUrdfChildSchemaType,
} from './urdfSchema.ts';

export interface ValidationError {
  line: number;
  column?: number;
  endLine?: number;
  endColumn?: number;
  message: string;
}

export interface UrdfValidationTexts {
  xmlParseError: string;
  missingRobotRoot: string;
  robotMissingName: string;
  linkMissingName: string;
  jointMissingName: string;
  jointMissingType: string;
  jointMissingParent: string;
  jointMissingChild: string;
  unknownElement: string;
  unknownAttribute: string;
  missingRequiredAttribute: string;
  invalidAttributeValue: string;
  cannotParseXml: string;
}

const defaultTexts: UrdfValidationTexts = {
  xmlParseError: 'XML parsing error',
  missingRobotRoot: 'Missing <robot> root element',
  robotMissingName: '<robot> element missing name attribute',
  linkMissingName: 'Link #{0} missing name attribute',
  jointMissingName: 'Joint #{0} missing name attribute',
  jointMissingType: 'Joint "{0}" missing type attribute',
  jointMissingParent: 'Joint "{0}" missing <parent> element',
  jointMissingChild: 'Joint "{0}" missing <child> element',
  unknownElement: 'Unknown <{0}> element under <{1}>',
  unknownAttribute: '<{0}> has unknown "{1}" attribute',
  missingRequiredAttribute: '<{0}> missing required "{1}" attribute',
  invalidAttributeValue: '<{0}> attribute "{1}" has invalid value "{2}"',
  cannotParseXml: 'Cannot parse XML',
};

const formatMsg = (msg: string, ...args: (string | number)[]): string => {
  let result = msg;
  args.forEach((arg, index) => {
    result = result.replace(`{${index}}`, String(arg));
  });
  return result;
};

const findElementLine = (xmlString: string, tagName: string, index: number): number => {
  const lines = xmlString.split('\n');
  let count = 0;

  for (let i = 0; i < lines.length; i += 1) {
    const regex = new RegExp(`<${tagName}[\\s>/]`, 'g');
    const matches = lines[i].match(regex);
    if (matches) {
      count += matches.length;
      if (count > index) {
        return i + 1;
      }
    }
  }

  return 1;
};

const getElementLine = (
  xmlString: string,
  tagName: string,
  counters: Map<string, number>,
): number => {
  const currentIndex = counters.get(tagName) || 0;
  counters.set(tagName, currentIndex + 1);
  return findElementLine(xmlString, tagName, currentIndex);
};

const isIgnorableAttribute = (attributeName: string): boolean =>
  attributeName === 'xmlns' || attributeName.startsWith('xmlns:');

export const validateUrdfDocument = (
  xmlString: string,
  texts: Partial<UrdfValidationTexts> = {},
): ValidationError[] => {
  const t = { ...defaultTexts, ...texts };
  const errors: ValidationError[] = [];

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlString, 'text/xml');
    const parseError = doc.querySelector('parsererror');

    if (parseError) {
      const errorText = parseError.textContent || t.xmlParseError;
      const lineMatch = errorText.match(/line\s*(\d+)/i);
      const columnMatch = errorText.match(/column\s*(\d+)/i);
      errors.push({
        line: lineMatch ? parseInt(lineMatch[1], 10) : 1,
        column: columnMatch ? parseInt(columnMatch[1], 10) : 1,
        message: `${t.xmlParseError}: ${errorText.split('\n')[0].substring(0, 100)}`,
      });
      return errors;
    }

    const robot = doc.querySelector('robot');
    if (!robot) {
      errors.push({ line: 1, column: 1, message: t.missingRobotRoot });
      return errors;
    }

    const occurrenceCounters = new Map<string, number>();
    const rootSchema = getUrdfRootSchema();

    const visitElement = (
      element: Element,
      schemaTypeName: string,
      parentElementName: string | null,
    ) => {
      const schemaNode = getUrdfSchemaNodeByType(schemaTypeName);
      const line = getElementLine(xmlString, element.tagName, occurrenceCounters);

      if (!schemaNode) {
        return;
      }

      const attributesByName = new Map(
        schemaNode.attributes.map((attribute) => [attribute.name, attribute]),
      );

      for (const attribute of Array.from(element.attributes)) {
        if (isIgnorableAttribute(attribute.name)) {
          continue;
        }

        const schemaAttribute = attributesByName.get(attribute.name);
        if (!schemaAttribute) {
          errors.push({
            line,
            column: 1,
            message: formatMsg(t.unknownAttribute, element.tagName, attribute.name),
          });
          continue;
        }

        if (
          schemaAttribute.values.length > 0
          && !schemaAttribute.values.includes(attribute.value)
        ) {
          errors.push({
            line,
            column: 1,
            message: formatMsg(
              t.invalidAttributeValue,
              element.tagName,
              attribute.name,
              attribute.value,
            ),
          });
        }
      }

      for (const requiredAttribute of schemaNode.attributes.filter((attribute) => attribute.required)) {
        if (!element.hasAttribute(requiredAttribute.name)) {
          errors.push({
            line,
            column: 1,
            message: formatMsg(
              t.missingRequiredAttribute,
              element.tagName,
              requiredAttribute.name,
            ),
          });
        }
      }

      for (const child of Array.from(element.children)) {
        const childTypeName = resolveUrdfChildSchemaType(schemaTypeName, child.tagName);
        if (!childTypeName) {
          if (!schemaNode.allowAnyChildren) {
            errors.push({
              line: getElementLine(xmlString, child.tagName, occurrenceCounters),
              column: 1,
              message: formatMsg(
                t.unknownElement,
                child.tagName,
                parentElementName || element.tagName,
              ),
            });
          }
          continue;
        }

        visitElement(child, childTypeName, element.tagName);
      }
    };

    visitElement(robot, rootSchema.typeName, null);

    const links = doc.querySelectorAll('link');
    links.forEach((link, index) => {
      if (!link.getAttribute('name')) {
        errors.push({
          line: findElementLine(xmlString, 'link', index),
          column: 1,
          message: formatMsg(t.linkMissingName, index + 1),
        });
      }
    });

    const joints = doc.querySelectorAll('joint');
    joints.forEach((joint, index) => {
      const jointName = joint.getAttribute('name');
      const jointType = joint.getAttribute('type');
      const line = findElementLine(xmlString, 'joint', index);

      if (!jointName) {
        errors.push({
          line,
          column: 1,
          message: formatMsg(t.jointMissingName, index + 1),
        });
      }

      if (!jointType) {
        errors.push({
          line,
          column: 1,
          message: formatMsg(t.jointMissingType, jointName || String(index + 1)),
        });
      }

      if (!joint.querySelector('parent')) {
        errors.push({
          line,
          column: 1,
          message: formatMsg(t.jointMissingParent, jointName || String(index + 1)),
        });
      }

      if (!joint.querySelector('child')) {
        errors.push({
          line,
          column: 1,
          message: formatMsg(t.jointMissingChild, jointName || String(index + 1)),
        });
      }
    });

    if (!robot.getAttribute('name')) {
      errors.push({
        line: findElementLine(xmlString, 'robot', 0),
        column: 1,
        message: t.robotMissingName,
      });
    }
  } catch {
    errors.push({ line: 1, column: 1, message: t.cannotParseXml });
  }

  return errors;
};
