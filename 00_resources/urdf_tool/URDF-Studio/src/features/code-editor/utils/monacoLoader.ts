import { loader } from '@monaco-editor/react';
// Trim Monaco to only what the source editor uses. `edcore.main` is the core
// editor with every editor UX contribution (completion, hover, find, folding,
// marker navigation) but NO languages and NONE of the language services. We add
// just the XML grammar on top. The default `monaco-editor` entry (editor.main)
// additionally ships the TypeScript/JSON/CSS/HTML language services — the TS
// service alone embeds a full compiler — plus ~80 Monarch grammars we never
// load, which is why the full bundle is several megabytes heavier.
import * as monaco from 'monaco-editor/esm/vs/editor/edcore.main';
import 'monaco-editor/esm/vs/basic-languages/xml/xml.contribution';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import type * as Monaco from 'monaco-editor';

type MonacoEnvironmentGlobal = typeof globalThis & {
  MonacoEnvironment?: {
    getWorker?: (_workerId: string, label: string) => Worker;
  };
};

const monacoGlobal = globalThis as MonacoEnvironmentGlobal;
monacoGlobal.MonacoEnvironment = {
  getWorker(): Worker {
    // The editor only drives XML/plaintext documents, which run on the base
    // editor worker; the json/css/html/ts language workers are never needed.
    return new EditorWorker();
  },
};

loader.config({ monaco });

export type MonacoInstance = typeof Monaco;

let monacoLoaderPromise: Promise<MonacoInstance> | null = null;
let monacoWorkerWarmupPromise: Promise<void> | null = null;

const ensureXmlDerivedLanguage = (
  monacoInstance: MonacoInstance,
  _id: string,
  _aliases: string[],
) => {
  // URDF/Xacro/MJCF/SDF all render through Monaco's XML grammar (registered via
  // the xml.contribution import above); their dialect-specific behavior is
  // provided by editor-side completion/validation logic, not a derived language.
  void monacoInstance;
};

export const ensureSourceCodeEditorLanguages = (
  monacoInstance: MonacoInstance,
): MonacoInstance => {
  ensureXmlDerivedLanguage(monacoInstance, 'urdf', ['URDF']);
  ensureXmlDerivedLanguage(monacoInstance, 'xacro', ['Xacro']);
  return monacoInstance;
};

export const preloadMonacoEditor = (): Promise<MonacoInstance> => {
  if (!monacoLoaderPromise) {
    monacoLoaderPromise = loader.init()
      .then((monacoInstance) => ensureSourceCodeEditorLanguages(monacoInstance))
      .catch((error) => {
        monacoLoaderPromise = null;
        throw error;
      });
  }

  return monacoLoaderPromise;
};

export const preloadMonacoEditorWorker = (): Promise<void> => {
  if (!monacoWorkerWarmupPromise) {
    monacoWorkerWarmupPromise = preloadMonacoEditor().then(() => undefined).catch((error) => {
      monacoWorkerWarmupPromise = null;
      throw error;
    });
  }

  return monacoWorkerWarmupPromise;
};
