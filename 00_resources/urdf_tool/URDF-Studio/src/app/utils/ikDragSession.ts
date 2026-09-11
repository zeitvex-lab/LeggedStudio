import type { InteractionSelection } from '@/types';

export function clearIkDragHelperSelection(
  selection: InteractionSelection | null | undefined,
): InteractionSelection | null {
  if (!selection?.id || selection.type !== 'link' || selection.helperKind !== 'ik-handle') {
    return null;
  }

  return {
    type: 'link',
    id: selection.id,
  };
}
