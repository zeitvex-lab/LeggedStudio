import type { SourceCodeDocumentFlavor } from '../types';
import type { ValidationError } from './urdfValidation.ts';

export interface XmlDocumentValidationTexts {
  xmlParseError?: string;
  cannotParseXml?: string;
}

const parseXmlOrCollectErrors = (
  xmlString: string,
  texts: XmlDocumentValidationTexts,
): { doc: Document | null; errors: ValidationError[] } => {
  const xmlParseErrorText = texts.xmlParseError || 'XML parsing error';
  const cannotParseXmlText = texts.cannotParseXml || 'Cannot parse XML';

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlString, 'text/xml');
    const parseError = doc.querySelector('parsererror');

    if (parseError) {
      const errorText = parseError.textContent || xmlParseErrorText;
      const lineMatch = errorText.match(/line\s*(\d+)/i);
      const columnMatch = errorText.match(/column\s*(\d+)/i);
      return {
        doc: null,
        errors: [
          {
            line: lineMatch ? parseInt(lineMatch[1], 10) : 1,
            column: columnMatch ? parseInt(columnMatch[1], 10) : 1,
            message: `${xmlParseErrorText}: ${errorText.split('\n')[0].substring(0, 100)}`,
          },
        ],
      };
    }

    return { doc, errors: [] };
  } catch (error) {
    return {
      doc: null,
      errors: [
        {
          line: 1,
          column: 1,
          message: `${cannotParseXmlText}: ${error instanceof Error ? error.message : String(error)}`,
        },
      ],
    };
  }
};

const validateXmlSyntax = (
  xmlString: string,
  texts: XmlDocumentValidationTexts,
): ValidationError[] => {
  const { errors } = parseXmlOrCollectErrors(xmlString, texts);
  return errors;
};

export const validateXmlDocumentByFlavor = (
  xmlString: string,
  documentFlavor: SourceCodeDocumentFlavor,
  texts: XmlDocumentValidationTexts = {},
): ValidationError[] => {
  switch (documentFlavor) {
    case 'urdf':
    case 'xacro':
    case 'sdf':
    case 'mjcf':
    case 'equivalent-mjcf':
      return validateXmlSyntax(xmlString, texts);
    case 'usd':
    default:
      return [];
  }
};
