import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createConversationMessage,
  createNewConversationDivider,
  getActiveConversationHistory,
  replaceActiveConversationTimeline,
} from './conversationTimeline.ts'

test('getActiveConversationHistory only returns turns after the latest new conversation divider', () => {
  const timeline = [
    createConversationMessage('user', 'older question'),
    createConversationMessage('assistant', 'older answer'),
    createNewConversationDivider(),
    createConversationMessage('user', 'current question'),
    createConversationMessage('assistant', 'current answer'),
  ]

  assert.deepEqual(getActiveConversationHistory(timeline), [
    { role: 'user', content: 'current question' },
    { role: 'assistant', content: 'current answer' },
  ])
})

test('replaceActiveConversationTimeline preserves previous conversations when rebuilding the active one', () => {
  const timeline = [
    createConversationMessage('user', 'first question'),
    createConversationMessage('assistant', 'first answer'),
    createNewConversationDivider(),
    createConversationMessage('user', 'draft question'),
    createConversationMessage('assistant', 'draft answer'),
  ]

  const rebuiltTimeline = replaceActiveConversationTimeline(timeline, [
    createConversationMessage('user', 'retry question'),
    createConversationMessage('assistant', ''),
  ])

  assert.deepEqual(rebuiltTimeline, [
    createConversationMessage('user', 'first question'),
    createConversationMessage('assistant', 'first answer'),
    timeline[2]!,
    createConversationMessage('user', 'retry question'),
    createConversationMessage('assistant', ''),
  ])
})
