import { useEffect, type RefObject } from 'react';

export function useFocusInputWhenEditing(
  inputRef: RefObject<HTMLInputElement | null>,
  isEditing: boolean,
) {
  useEffect(() => {
    if (!isEditing) {
      return;
    }

    inputRef.current?.focus();
    inputRef.current?.select();
  }, [inputRef, isEditing]);
}
