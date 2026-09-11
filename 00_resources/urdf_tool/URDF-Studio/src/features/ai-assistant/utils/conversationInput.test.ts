import test from 'node:test'
import assert from 'node:assert/strict'

import {
  isConversationInputComposing,
  shouldSubmitConversationInput,
} from './conversationInput.ts'

test('shouldSubmitConversationInput accepts a plain Enter keypress', () => {
  assert.equal(shouldSubmitConversationInput({ key: 'Enter' }), true)
})

test('shouldSubmitConversationInput rejects modified Enter shortcuts', () => {
  assert.equal(shouldSubmitConversationInput({ key: 'Enter', shiftKey: true }), false)
  assert.equal(shouldSubmitConversationInput({ key: 'Enter', ctrlKey: true }), false)
  assert.equal(shouldSubmitConversationInput({ key: 'Enter', metaKey: true }), false)
  assert.equal(shouldSubmitConversationInput({ key: 'Enter', altKey: true }), false)
})

test('shouldSubmitConversationInput rejects non-Enter keys', () => {
  assert.equal(shouldSubmitConversationInput({ key: 'a' }), false)
})

test('isConversationInputComposing detects IME composition from the native event', () => {
  assert.equal(
    isConversationInputComposing({
      key: 'Enter',
      nativeEvent: { isComposing: true },
    }),
    true,
  )
})

test('shouldSubmitConversationInput rejects Enter while the IME is composing', () => {
  assert.equal(
    shouldSubmitConversationInput({
      key: 'Enter',
      nativeEvent: { isComposing: true },
    }),
    false,
  )

  assert.equal(
    shouldSubmitConversationInput({
      key: 'Enter',
      nativeEvent: { keyCode: 229 },
    }),
    false,
  )

  assert.equal(
    shouldSubmitConversationInput(
      {
        key: 'Enter',
      },
      { isComposing: true },
    ),
    false,
  )
})
