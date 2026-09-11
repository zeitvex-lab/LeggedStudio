interface HeaderMenuOverlayProps {
  onClose: () => void;
  label: string;
}

export function HeaderMenuOverlay({ onClose, label }: HeaderMenuOverlayProps) {
  return (
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-transparent"
      onClick={onClose}
      aria-label={label}
      tabIndex={-1}
    />
  );
}
