export interface ConversationSubmitKeyboardEvent {
  key: string
  shiftKey?: boolean
  altKey?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  nativeEvent?: {
    isComposing?: boolean
    keyCode?: number
  }
}

interface ConversationSubmitOptions {
  isComposing?: boolean
}

export const isConversationInputComposing = (
  event: ConversationSubmitKeyboardEvent,
  options?: ConversationSubmitOptions,
): boolean => {
  if (options?.isComposing) {
    return true
  }

  if (event.nativeEvent?.isComposing) {
    return true
  }

  return event.nativeEvent?.keyCode === 229
}

export const shouldSubmitConversationInput = (
  event: ConversationSubmitKeyboardEvent,
  options?: ConversationSubmitOptions,
): boolean => {
  if (event.key !== 'Enter') {
    return false
  }

  if (event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) {
    return false
  }

  if (isConversationInputComposing(event, options)) {
    return false
  }

  return true
}
