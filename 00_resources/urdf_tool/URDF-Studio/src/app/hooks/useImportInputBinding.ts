import { useEffect, type RefObject } from 'react';

interface UseImportInputBindingOptions {
  importInputRef: RefObject<HTMLInputElement | null>;
  importFolderInputRef: RefObject<HTMLInputElement | null>;
  onImport: (files: FileList | null) => void | Promise<unknown>;
}

export function useImportInputBinding({
  importInputRef,
  importFolderInputRef,
  onImport,
}: UseImportInputBindingOptions) {
  useEffect(() => {
    const input = importInputRef.current;
    const folderInput = importFolderInputRef.current;
    const handleChange = (event: Event) => {
      const target = event.target as HTMLInputElement;
      void Promise.resolve(onImport(target.files)).finally(() => {
        target.value = '';
      });
    };

    if (input) {
      input.addEventListener('change', handleChange as EventListener);
    }

    if (folderInput) {
      folderInput.addEventListener('change', handleChange as EventListener);
    }

    return () => {
      if (input) {
        input.removeEventListener('change', handleChange as EventListener);
      }

      if (folderInput) {
        folderInput.removeEventListener('change', handleChange as EventListener);
      }
    };
  }, [importFolderInputRef, importInputRef, onImport]);
}
