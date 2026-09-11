import { Import } from 'lucide-react';

interface FileDropOverlayProps {
  visible: boolean;
  title: string;
  hint: string;
}

export function FileDropOverlay({ visible, title, hint }: FileDropOverlayProps) {
  if (!visible) {
    return null;
  }

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[150] flex items-center justify-center bg-app-bg/78 backdrop-blur-[3px] animate-in fade-in duration-200"
    >
      <div className="absolute inset-4 rounded-[32px] border-2 border-dashed border-system-blue/30 bg-system-blue/8 shadow-xl" />

      <div className="relative mx-6 w-full max-w-xl animate-in zoom-in-95 duration-200">
        <div className="flex flex-col items-center gap-4 rounded-[28px] border border-border-black bg-panel-bg/96 px-8 py-10 text-center shadow-2xl">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-system-blue/20 bg-system-blue/10 text-system-blue shadow-lg">
            <Import className="h-8 w-8" strokeWidth={2.2} />
          </div>

          <div className="space-y-1">
            <p className="text-xl font-semibold tracking-tight text-text-primary">
              {title}
            </p>
            <p className="text-sm leading-6 text-text-secondary">
              {hint}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
