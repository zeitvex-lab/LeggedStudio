import { useCallback, useEffect, useRef, useState } from 'react';

interface DeferredColorPickerInputProps {
  ariaLabel: string;
  className?: string;
  onCommit: (value: string) => void;
  value: string;
}

export const DeferredColorPickerInput = ({
  ariaLabel,
  className,
  onCommit,
  value,
}: DeferredColorPickerInputProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [draftValue, setDraftValue] = useState(value);
  const draftValueRef = useRef(value);
  const committedValueRef = useRef(value);
  const onCommitRef = useRef(onCommit);
  const pendingCommitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    onCommitRef.current = onCommit;
  }, [onCommit]);

  useEffect(() => {
    draftValueRef.current = value;
    committedValueRef.current = value;
    setDraftValue(value);
  }, [value]);

  const setDraft = useCallback((nextValue: string) => {
    draftValueRef.current = nextValue;
    setDraftValue((currentValue) => (currentValue === nextValue ? currentValue : nextValue));
  }, []);

  const clearPendingCommit = useCallback(() => {
    if (pendingCommitTimeoutRef.current === null) {
      return;
    }

    clearTimeout(pendingCommitTimeoutRef.current);
    pendingCommitTimeoutRef.current = null;
  }, []);

  const commitDraft = useCallback(() => {
    clearPendingCommit();
    const nextValue = draftValueRef.current;
    if (nextValue === committedValueRef.current) {
      return;
    }

    committedValueRef.current = nextValue;
    onCommitRef.current(nextValue);
  }, [clearPendingCommit]);

  const scheduleCommit = useCallback(() => {
    clearPendingCommit();
    pendingCommitTimeoutRef.current = setTimeout(() => {
      pendingCommitTimeoutRef.current = null;
      commitDraft();
    }, 50);
  }, [clearPendingCommit, commitDraft]);

  const handleDraftChange = useCallback(
    (nextValue: string) => {
      setDraft(nextValue);
      scheduleCommit();
    },
    [scheduleCommit, setDraft],
  );

  useEffect(() => clearPendingCommit, [clearPendingCommit]);

  useEffect(() => {
    const input = inputRef.current;
    if (!input) {
      return;
    }

    const handleNativeChange = () => {
      setDraft(input.value);
      commitDraft();
    };

    input.addEventListener('change', handleNativeChange);
    return () => {
      input.removeEventListener('change', handleNativeChange);
    };
  }, [commitDraft, setDraft]);

  return (
    <input
      ref={inputRef}
      type="color"
      value={draftValue}
      onInput={(event) => handleDraftChange(event.currentTarget.value)}
      onChange={(event) => handleDraftChange(event.currentTarget.value)}
      onPointerUp={commitDraft}
      onMouseUp={commitDraft}
      onBlur={commitDraft}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          commitDraft();
        }
      }}
      aria-label={ariaLabel}
      className={className}
    />
  );
};
