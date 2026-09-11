import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import ts from 'typescript';

test('UnifiedViewer typechecks without unresolved local identifiers', () => {
  const projectRoot = path.resolve(import.meta.dirname, '../../..');
  const configPath = path.join(projectRoot, 'tsconfig.json');
  const sourcePath = path.join(projectRoot, 'src/app/components/UnifiedViewer.tsx');

  const configFile = ts.readConfigFile(configPath, ts.sys.readFile);
  assert.equal(configFile.error, undefined, 'Failed to read tsconfig.json');

  const parsedConfig = ts.parseJsonConfigFileContent(
    configFile.config,
    ts.sys,
    projectRoot,
    undefined,
    configPath,
  );

  const program = ts.createProgram({
    rootNames: [sourcePath],
    options: parsedConfig.options,
  });

  const diagnostics = ts.getPreEmitDiagnostics(program)
    .filter((diagnostic) => diagnostic.file?.fileName === sourcePath);

  assert.deepEqual(
    diagnostics.map((diagnostic) => ({
      code: diagnostic.code,
      message: ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n'),
    })),
    [],
  );
});
