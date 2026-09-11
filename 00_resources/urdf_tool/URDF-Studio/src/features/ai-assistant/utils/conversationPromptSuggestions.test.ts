import test from 'node:test'
import assert from 'node:assert/strict'

import { buildConversationPromptSuggestions } from './conversationPromptSuggestions.ts'

test('buildConversationPromptSuggestions returns contextual general suggestions', () => {
  const suggestions = buildConversationPromptSuggestions({
    lang: 'en',
    isReportFollowup: false,
    selectedEntityName: 'hip_joint',
  })

  assert.equal(suggestions.length, 3)
  assert.match(suggestions[0] || '', /top 3 modeling risks/i)
  assert.match(suggestions[1] || '', /hip_joint/)
  assert.match(suggestions[2] || '', /easier to simulate/i)
})

test('buildConversationPromptSuggestions falls back when no selected entity is available', () => {
  const suggestions = buildConversationPromptSuggestions({
    lang: 'zh',
    isReportFollowup: false,
    selectedEntityName: null,
  })

  assert.equal(suggestions.length, 3)
  assert.match(suggestions[1] || '', /当前机器人结构/)
  assert.doesNotMatch(suggestions[1] || '', /当前选中部件/)
})

test('buildConversationPromptSuggestions returns report follow-up suggestions', () => {
  const suggestions = buildConversationPromptSuggestions({
    lang: 'zh',
    isReportFollowup: true,
    selectedEntityName: 'knee_joint',
  })

  assert.equal(suggestions.length, 3)
  assert.match(suggestions[0] || '', /先修哪一项/)
  assert.match(suggestions[1] || '', /knee_joint/)
  assert.match(suggestions[2] || '', /重新检查/)
})

test('buildConversationPromptSuggestions prioritizes focused issue prompts for report follow-up', () => {
  const suggestions = buildConversationPromptSuggestions({
    lang: 'en',
    isReportFollowup: true,
    selectedEntityName: 'knee_joint',
    focusedIssueTitle: 'Joint axis is inconsistent',
  })

  assert.equal(suggestions.length, 3)
  assert.match(suggestions[0] || '', /Joint axis is inconsistent/i)
  assert.match(suggestions[1] || '', /fix/i)
  assert.match(suggestions[2] || '', /rerun/i)
})
