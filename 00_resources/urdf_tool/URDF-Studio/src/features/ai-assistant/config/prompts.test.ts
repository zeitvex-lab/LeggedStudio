import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  CONVERSATION_PROMPT_PLACEHOLDERS,
  CONVERSATION_SYSTEM_PROMPT_TEMPLATES,
  GENERATION_PROMPT_PLACEHOLDERS,
  GENERATION_SYSTEM_PROMPT_TEMPLATE,
  getConversationSystemPrompt,
  getGenerationSystemPrompt,
  getInspectionSystemPrompt,
  INSPECTION_PROMPT_PLACEHOLDERS,
  INSPECTION_SYSTEM_PROMPT_TEMPLATES,
} from './prompts.ts';
import { AI_PROMPT_TEMPLATES } from './aiPromptTemplates.generated.ts';

const promptMarkdownSource = fs.readFileSync(new URL('./aiPromptTemplates.md', import.meta.url), 'utf8');

const extractPromptFromMarkdown = (id: string): string => {
  const pattern = new RegExp(`<!-- PROMPT: ${id} -->\\n([\\s\\S]*?)\\n<!-- \\/PROMPT -->`, 'm');
  const match = promptMarkdownSource.match(pattern);
  assert.ok(match, `Prompt section "${id}" should exist in aiPromptTemplates.md`);
  return match[1].trim();
};

test('markdown prompt source documents the editable sections and placeholders for maintainers', () => {
  assert.match(promptMarkdownSource, /^# AI Prompt Templates/m);
  assert.match(promptMarkdownSource, /^## Editable Sections/m);
  assert.match(promptMarkdownSource, /`generation`/);
  assert.match(promptMarkdownSource, /`inspection\.en`/);
  assert.match(promptMarkdownSource, /`inspection\.zh`/);
  assert.match(promptMarkdownSource, /`conversation\.en`/);
  assert.match(promptMarkdownSource, /`conversation\.zh`/);
  assert.match(promptMarkdownSource, /^## Placeholders/m);
  assert.match(promptMarkdownSource, /`__ROBOT_CONTEXT__`/);
  assert.match(promptMarkdownSource, /`__MOTOR_LIBRARY_CONTEXT__`/);
  assert.match(promptMarkdownSource, /`__CRITERIA_DESCRIPTION__`/);
  assert.match(promptMarkdownSource, /`__INSPECTION_NOTES__`/);
  assert.match(promptMarkdownSource, /`__LANGUAGE_INSTRUCTION__`/);
  assert.match(promptMarkdownSource, /`__CONVERSATION_MODE__`/);
  assert.match(promptMarkdownSource, /`__CONVERSATION_CONTEXT__`/);
  assert.match(promptMarkdownSource, /`__CONVERSATION_HISTORY__`/);
});

test('markdown prompt sections use structured subsection headings for easier editing', () => {
  const generationPrompt = extractPromptFromMarkdown('generation');
  const inspectionEnPrompt = extractPromptFromMarkdown('inspection.en');
  const inspectionZhPrompt = extractPromptFromMarkdown('inspection.zh');
  const conversationEnPrompt = extractPromptFromMarkdown('conversation.en');
  const conversationZhPrompt = extractPromptFromMarkdown('conversation.zh');

  assert.match(generationPrompt, /^## Role/m);
  assert.match(generationPrompt, /^## Context/m);
  assert.match(generationPrompt, /^## Rules/m);

  assert.match(inspectionEnPrompt, /^## Role/m);
  assert.match(inspectionEnPrompt, /^## Input Context/m);
  assert.match(inspectionEnPrompt, /^## Output Contract/m);
  assert.match(inspectionEnPrompt, /^## Rules/m);

  assert.match(inspectionZhPrompt, /^## 角色/m);
  assert.match(inspectionZhPrompt, /^## 输入上下文/m);
  assert.match(inspectionZhPrompt, /^## 输出契约/m);
  assert.match(inspectionZhPrompt, /^## 规则/m);

  assert.match(conversationEnPrompt, /^## Role/m);
  assert.match(conversationEnPrompt, /^## Input Context/m);
  assert.match(conversationEnPrompt, /^## Output Contract/m);
  assert.match(conversationEnPrompt, /^## Rules/m);

  assert.match(conversationZhPrompt, /^## 角色/m);
  assert.match(conversationZhPrompt, /^## 输入上下文/m);
  assert.match(conversationZhPrompt, /^## 输出契约/m);
  assert.match(conversationZhPrompt, /^## 规则/m);
});

test('generated prompt module stays in sync with the single markdown source of truth', () => {
  assert.equal(AI_PROMPT_TEMPLATES.generation, extractPromptFromMarkdown('generation'));
  assert.equal(AI_PROMPT_TEMPLATES.inspection.en, extractPromptFromMarkdown('inspection.en'));
  assert.equal(AI_PROMPT_TEMPLATES.inspection.zh, extractPromptFromMarkdown('inspection.zh'));
  assert.equal(AI_PROMPT_TEMPLATES.conversation.en, extractPromptFromMarkdown('conversation.en'));
  assert.equal(AI_PROMPT_TEMPLATES.conversation.zh, extractPromptFromMarkdown('conversation.zh'));
});

test('generation prompt template lives in a standalone config module', () => {
  assert.equal(typeof GENERATION_SYSTEM_PROMPT_TEMPLATE, 'string');
  assert.match(GENERATION_SYSTEM_PROMPT_TEMPLATE, /You are an expert Robotics Engineer and URDF Studio Expert/);
  assert.match(GENERATION_SYSTEM_PROMPT_TEMPLATE, new RegExp(GENERATION_PROMPT_PLACEHOLDERS.robot));
  assert.match(GENERATION_SYSTEM_PROMPT_TEMPLATE, new RegExp(GENERATION_PROMPT_PLACEHOLDERS.motorLibrary));
});

test('getGenerationSystemPrompt keeps the existing context injection contract', () => {
  const prompt = getGenerationSystemPrompt({
    robot: { name: 'demo_bot' },
    motorLibrary: [{ brand: 'Unitree' }],
  });

  assert.match(prompt, /demo_bot/);
  assert.match(prompt, /Unitree/);
  assert.match(prompt, /If the user asks for a \*new\* robot, generate a complete new structure/);
  assert.match(prompt, /For hardware changes, use the exact 'motorType' names from the library/);
});

test('inspection prompt templates live in a standalone config module', () => {
  assert.equal(typeof INSPECTION_SYSTEM_PROMPT_TEMPLATES.en, 'string');
  assert.equal(typeof INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh, 'string');
  assert.match(INSPECTION_SYSTEM_PROMPT_TEMPLATES.en, /You are an expert URDF Robot Inspector/);
  assert.match(INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh, /你是一位专业的URDF机器人检查专家/);
  assert.match(
    INSPECTION_SYSTEM_PROMPT_TEMPLATES.en,
    new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.criteriaDescription),
  );
  assert.match(
    INSPECTION_SYSTEM_PROMPT_TEMPLATES.en,
    new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.inspectionNotes),
  );
  assert.match(
    INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh,
    new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.criteriaDescription),
  );
  assert.match(
    INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh,
    new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.inspectionNotes),
  );
});

test('inspection prompt contract is profile-only and rejects legacy category fields', () => {
  assert.match(INSPECTION_SYSTEM_PROMPT_TEMPLATES.en, /"profileId"/);
  assert.match(INSPECTION_SYSTEM_PROMPT_TEMPLATES.en, /"itemId"/);
  assert.match(INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh, /"profileId"/);
  assert.match(INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh, /"itemId"/);
  assert.doesNotMatch(INSPECTION_SYSTEM_PROMPT_TEMPLATES.en, /"category"/);
  assert.doesNotMatch(INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh, /"category"/);
  assert.doesNotMatch(INSPECTION_SYSTEM_PROMPT_TEMPLATES.en, /legacy/i);
  assert.doesNotMatch(INSPECTION_SYSTEM_PROMPT_TEMPLATES.zh, /旧字段/);
});

test('getInspectionSystemPrompt injects english profile criteria without changing the profile JSON contract', () => {
  const criteriaDescription = 'base.robot_model.reference_integrity';
  const inspectionNotes = '**Source-Format Notes:**\n- MJCF summary: 2 sites';
  const prompt = getInspectionSystemPrompt('en', { criteriaDescription, inspectionNotes });

  assert.match(prompt, /base\.robot_model\.reference_integrity/);
  assert.match(prompt, /Source-Format Notes/);
  assert.doesNotMatch(prompt, new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.criteriaDescription));
  assert.doesNotMatch(prompt, new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.inspectionNotes));
  assert.match(prompt, /Return a pure JSON object/);
  assert.match(prompt, /Each issue MUST include 'profileId' and 'itemId'/);
  assert.doesNotMatch(prompt, /category/);
});

test('getInspectionSystemPrompt injects chinese profile criteria without changing the profile JSON contract', () => {
  const criteriaDescription = 'base.robot_model.reference_integrity';
  const inspectionNotes = '**源格式附加说明:**\n- MJCF 摘要：2 个 site';
  const prompt = getInspectionSystemPrompt('zh', { criteriaDescription, inspectionNotes });

  assert.match(prompt, /base\.robot_model\.reference_integrity/);
  assert.match(prompt, /源格式附加说明/);
  assert.doesNotMatch(prompt, new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.criteriaDescription));
  assert.doesNotMatch(prompt, new RegExp(INSPECTION_PROMPT_PLACEHOLDERS.inspectionNotes));
  assert.match(prompt, /返回一个纯JSON对象/);
  assert.match(prompt, /每个问题必须包含 'profileId' 和 'itemId'/);
  assert.doesNotMatch(prompt, /category/);
});

test('conversation prompt templates live in a standalone config module', () => {
  assert.equal(typeof CONVERSATION_SYSTEM_PROMPT_TEMPLATES.en, 'string');
  assert.equal(typeof CONVERSATION_SYSTEM_PROMPT_TEMPLATES.zh, 'string');
  assert.match(CONVERSATION_SYSTEM_PROMPT_TEMPLATES.en, /URDF Studio conversation assistant/);
  assert.match(CONVERSATION_SYSTEM_PROMPT_TEMPLATES.zh, /URDF Studio 的对话助手/);
  assert.match(CONVERSATION_SYSTEM_PROMPT_TEMPLATES.en, /Use lightweight Markdown/);
  assert.match(CONVERSATION_SYSTEM_PROMPT_TEMPLATES.zh, /轻量 Markdown/);
  assert.match(
    CONVERSATION_SYSTEM_PROMPT_TEMPLATES.en,
    new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.mode),
  );
  assert.match(
    CONVERSATION_SYSTEM_PROMPT_TEMPLATES.en,
    new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.context),
  );
  assert.match(
    CONVERSATION_SYSTEM_PROMPT_TEMPLATES.en,
    new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.history),
  );
});

test('getConversationSystemPrompt injects context for general mode', () => {
  const prompt = getConversationSystemPrompt('en', {
    mode: 'general',
    context: '{"robot":{"name":"demo_bot"}}',
    history: '[{"role":"user","content":"What is this robot for?"}]',
  });

  assert.match(prompt, /conversation mode: general/i);
  assert.match(prompt, /demo_bot/);
  assert.match(prompt, /What is this robot for\?/);
  assert.doesNotMatch(prompt, new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.mode));
  assert.doesNotMatch(prompt, new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.context));
  assert.doesNotMatch(prompt, new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.history));
  assert.match(prompt, /Please respond in English/);
});

test('getConversationSystemPrompt injects context for inspection follow-up mode in chinese', () => {
  const prompt = getConversationSystemPrompt('zh', {
    mode: 'inspection-followup',
    context: '{"inspectionReport":{"summary":"存在关节限位风险"}}',
    history: '[{"role":"assistant","content":"已发现 2 个 warning"}]',
  });

  assert.match(prompt, /对话模式：inspection-followup/);
  assert.match(prompt, /存在关节限位风险/);
  assert.match(prompt, /已发现 2 个 warning/);
  assert.doesNotMatch(prompt, new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.mode));
  assert.doesNotMatch(prompt, new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.context));
  assert.doesNotMatch(prompt, new RegExp(CONVERSATION_PROMPT_PLACEHOLDERS.history));
  assert.match(prompt, /请使用中文回复/);
});
