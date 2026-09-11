
/**
 * File System Access API utilities for handling drag and drop folders
 */
import {
  hasHiddenImportPathSegment,
  isRobotImportCandidatePath,
} from '@/shared/utils/robotFileSupport';

// Helper to read all entries in a directory reader
async function readAllEntries(directoryReader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  const entries: FileSystemEntry[] = [];
  let readEntries = await new Promise<FileSystemEntry[]>((resolve, reject) => {
    directoryReader.readEntries(resolve, reject);
  });

  while (readEntries.length > 0) {
    entries.push(...readEntries);
    readEntries = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      directoryReader.readEntries(resolve, reject);
    });
  }
  return entries;
}

// Recursive function to traverse file system entries
async function traverseEntry(entry: FileSystemEntry, path: string = ''): Promise<File[]> {
  const entryPath = path + entry.name;

  if (entry.isFile) {
    if (!isRobotImportCandidatePath(entryPath)) {
      return [];
    }

    const fileEntry = entry as FileSystemFileEntry;
    return new Promise<File[]>((resolve, reject) => {
      fileEntry.file((file) => {
        // We need to manually inject the path into the file object
        // because File object from drag-and-drop usually has empty webkitRelativePath
        // We can attach a custom property or define a new property
        Object.defineProperty(file, 'webkitRelativePath', {
          value: entryPath,
          writable: true,
        });
        resolve([file]);
      }, reject);
    });
  } else if (entry.isDirectory) {
    if (hasHiddenImportPathSegment(entryPath)) {
      return [];
    }

    const dirEntry = entry as FileSystemDirectoryEntry;
    const dirReader = dirEntry.createReader();
    const entries = await readAllEntries(dirReader);
    const files: File[] = [];
    for (const childEntry of entries) {
      const childFiles = await traverseEntry(childEntry, `${entryPath}/`);
      files.push(...childFiles);
    }
    return files;
  }
  return [];
}

/**
 * Process DataTransferItems from a drop event
 * Handles both files and nested folders
 */
export async function getDroppedFilesFromEntries(entries: readonly FileSystemEntry[]): Promise<File[]> {
  const files: File[] = [];

  for (const entry of entries) {
    const entryFiles = await traverseEntry(entry);
    files.push(...entryFiles);
  }

  return files;
}

/**
 * Process DataTransferItems from a drop event.
 * This must be called synchronously from the drop event when callers pass
 * live DataTransferItems. Lazy callers should capture entries first and then
 * call getDroppedFilesFromEntries after the traverser module loads.
 */
export async function getDroppedFiles(items: DataTransferItemList): Promise<File[]> {
  const entries: FileSystemEntry[] = [];

  // 1. Get all entries first
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind === 'file' && typeof item.webkitGetAsEntry === 'function') {
      const entry = item.webkitGetAsEntry();
      if (entry) {
        entries.push(entry);
      }
    }
  }

  return getDroppedFilesFromEntries(entries);
}
