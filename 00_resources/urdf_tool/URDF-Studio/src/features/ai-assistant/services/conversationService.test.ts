import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildConversationMessages,
  extractConversationDelta,
  isConversationAbortError,
  sendConversationTurn,
  sendConversationTurnStream,
  serializeConversationHistory,
} from './conversationService.ts';
import OpenAI from 'openai';

const API_KEY_ENV_NAMES = ['API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY'] as const;

const captureApiKeyEnv = (): Record<(typeof API_KEY_ENV_NAMES)[number], string | undefined> => ({
  API_KEY: process.env.API_KEY,
  OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  GEMINI_API_KEY: process.env.GEMINI_API_KEY,
});

const restoreApiKeyEnv = (
  snapshot: Record<(typeof API_KEY_ENV_NAMES)[number], string | undefined>,
) => {
  for (const envName of API_KEY_ENV_NAMES) {
    const value = snapshot[envName];
    if (value === undefined) {
      delete process.env[envName];
      continue;
    }

    process.env[envName] = value;
  }
};

test('buildConversationMessages keeps only valid recent history and appends current user message', () => {
  const history = [
    { role: 'user' as const, content: '  first question  ' },
    { role: 'assistant' as const, content: '' },
    { role: 'assistant' as const, content: 'first answer' },
    { role: 'user' as const, content: 'second question' },
  ];

  const messages = buildConversationMessages(history, '  current question ');

  assert.equal(messages.length, 4);
  assert.deepEqual(messages[0], { role: 'user', content: 'first question' });
  assert.deepEqual(messages[1], { role: 'assistant', content: 'first answer' });
  assert.deepEqual(messages[2], { role: 'user', content: 'second question' });
  assert.deepEqual(messages[3], { role: 'user', content: 'current question' });
});

test('buildConversationMessages limits history to the latest eight turns', () => {
  const history = Array.from({ length: 10 }, (_, index) => ({
    role: (index % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
    content: `turn-${index}`,
  }));

  const messages = buildConversationMessages(history, 'latest-question');

  assert.equal(messages.length, 9);
  assert.deepEqual(messages[0], { role: 'user', content: 'turn-2' });
  assert.deepEqual(messages[7], { role: 'assistant', content: 'turn-9' });
  assert.deepEqual(messages[8], { role: 'user', content: 'latest-question' });
});

test('serializeConversationHistory applies the same sanitization contract as message building', () => {
  const history = [
    { role: 'user' as const, content: '  hello  ' },
    { role: 'assistant' as const, content: '' },
    { role: 'assistant' as const, content: 'world' },
  ];

  const serialized = serializeConversationHistory(history);
  assert.equal(
    serialized,
    '[{"role":"user","content":"hello"},{"role":"assistant","content":"world"}]',
  );
});

test('sendConversationTurn returns localized error when api key is missing', async () => {
  const envSnapshot = captureApiKeyEnv();
  delete process.env.API_KEY;
  delete process.env.OPENAI_API_KEY;
  delete process.env.GEMINI_API_KEY;

  try {
    const result = await sendConversationTurn({
      mode: 'general',
      lang: 'en',
      context: '{"robot":{"name":"demo"}}',
      history: [],
      userMessage: 'What can this robot do?',
    });

    assert.equal(result.reply, '');
    assert.equal(result.error?.code, 'missing_api_key');
    assert.match(String(result.error?.message || ''), /API Key/i);
  } finally {
    restoreApiKeyEnv(envSnapshot);
  }
});

test('sendConversationTurnStream returns localized error when api key is missing', async () => {
  const envSnapshot = captureApiKeyEnv();
  delete process.env.API_KEY;
  delete process.env.OPENAI_API_KEY;
  delete process.env.GEMINI_API_KEY;

  try {
    const result = await sendConversationTurnStream({
      mode: 'general',
      lang: 'zh',
      context: '{"robot":{"name":"demo"}}',
      history: [],
      userMessage: '这个机器人适合做什么？',
    });

    assert.equal(result.status, 'error');
    assert.equal(result.reply, '');
    assert.equal(result.error?.code, 'missing_api_key');
    assert.match(String(result.error?.message || ''), /API Key/i);
  } finally {
    restoreApiKeyEnv(envSnapshot);
  }
});

test('extractConversationDelta concatenates streamed content fragments', () => {
  const delta = extractConversationDelta({
    choices: [{ delta: { content: 'First' } }, { delta: { content: ' second' } }],
  });

  assert.equal(delta, 'First second');
  assert.equal(extractConversationDelta(undefined), '');
});

test('isConversationAbortError recognizes SDK abort errors and AbortError names', () => {
  assert.equal(isConversationAbortError(new OpenAI.APIUserAbortError()), true);

  const abortError = new Error('Request aborted');
  abortError.name = 'AbortError';
  assert.equal(isConversationAbortError(abortError), true);

  assert.equal(isConversationAbortError(new Error('Other error')), false);
});

test('sendConversationTurnStream surfaces stream failures instead of retrying without stream', async () => {
  const envSnapshot = captureApiKeyEnv();
  const originalCreate = OpenAI.Chat.Completions.prototype.create;
  const createCalls: Array<boolean> = [];

  delete process.env.API_KEY;
  process.env.OPENAI_API_KEY = 'test-openai-key';
  delete process.env.GEMINI_API_KEY;

  OpenAI.Chat.Completions.prototype.create = async function mockCreate(
    this: unknown,
    params: { stream?: boolean },
  ) {
    createCalls.push(Boolean(params.stream));
    throw new OpenAI.APIConnectionError({});
  } as unknown as typeof OpenAI.Chat.Completions.prototype.create;

  try {
    const result = await sendConversationTurnStream({
      mode: 'general',
      lang: 'en',
      context: '{"robot":{"name":"demo"}}',
      history: [],
      userMessage: 'How should I improve this robot?',
    });

    assert.equal(result.status, 'error');
    assert.equal(result.reply, '');
    assert.equal(result.error?.code, 'request_failed');
    assert.match(String(result.error?.message || ''), /connection/i);
    assert.deepEqual(createCalls, [true]);
  } finally {
    OpenAI.Chat.Completions.prototype.create = originalCreate;
    restoreApiKeyEnv(envSnapshot);
  }
});

test('sendConversationTurnStream clears partial streamed replies when the request fails', async () => {
  const envSnapshot = captureApiKeyEnv();
  const originalCreate = OpenAI.Chat.Completions.prototype.create;
  const streamedDeltas: string[] = [];

  delete process.env.API_KEY;
  process.env.OPENAI_API_KEY = 'test-openai-key';
  delete process.env.GEMINI_API_KEY;

  OpenAI.Chat.Completions.prototype.create = async function mockCreate() {
    return {
      async *[Symbol.asyncIterator]() {
        yield {
          choices: [
            {
              delta: {
                content: 'Partial answer',
              },
            },
          ],
        };
        throw new Error('stream exploded');
      },
    } as AsyncIterable<unknown>;
  } as unknown as typeof OpenAI.Chat.Completions.prototype.create;

  try {
    const result = await sendConversationTurnStream({
      mode: 'general',
      lang: 'en',
      context: '{"robot":{"name":"demo"}}',
      history: [],
      userMessage: 'How should I improve this robot?',
      onReplyDelta: (delta) => {
        streamedDeltas.push(delta);
      },
    });

    assert.deepEqual(streamedDeltas, ['Partial answer']);
    assert.equal(result.status, 'error');
    assert.equal(result.reply, '');
    assert.equal(result.error?.code, 'request_failed');
    assert.match(String(result.error?.message || ''), /stream exploded/i);
  } finally {
    OpenAI.Chat.Completions.prototype.create = originalCreate;
    restoreApiKeyEnv(envSnapshot);
  }
});

test('sendConversationTurnStream uses the backend transport when AI_BACKEND_URL is set', async () => {
  const previousBackendUrl = process.env.AI_BACKEND_URL;
  process.env.AI_BACKEND_URL = 'https://backend.test/api/ai/urdf-studio';
  const previousFetch = globalThis.fetch;

  const requests: Array<{ url: string; init: RequestInit }> = [];
  globalThis.fetch = (async (url: unknown, init?: RequestInit) => {
    requests.push({ url: String(url), init: init ?? {} });
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"delta":"后端"}\n\n'));
        controller.enqueue(encoder.encode('data: {"delta":"回复"}\n\ndata: {"done":true}\n\n'));
        controller.close();
      },
    });
    return { ok: true, status: 200, body, json: async () => null };
  }) as typeof fetch;

  try {
    const streamedDeltas: string[] = [];
    const result = await sendConversationTurnStream({
      mode: 'general',
      lang: 'zh',
      context: '{"robot":{"name":"demo"}}',
      history: [
        { role: 'user', content: '  之前的问题  ' },
        { role: 'assistant', content: '' },
      ],
      userMessage: '  这个机器人怎么样？ ',
      onReplyDelta: (delta) => {
        streamedDeltas.push(delta);
      },
    });

    assert.deepEqual(streamedDeltas, ['后端', '回复']);
    assert.equal(result.status, 'completed');
    assert.equal(result.reply, '后端回复');
    assert.equal(result.error, null);

    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, 'https://backend.test/api/ai/urdf-studio/chat');
    const sentPayload = JSON.parse(String(requests[0].init.body));
    assert.equal(sentPayload.userMessage, '这个机器人怎么样？');
    assert.equal(sentPayload.mode, 'general');
    assert.equal(sentPayload.lang, 'zh');
    assert.deepEqual(sentPayload.history, [{ role: 'user', content: '之前的问题' }]);
  } finally {
    globalThis.fetch = previousFetch;
    if (previousBackendUrl === undefined) {
      delete process.env.AI_BACKEND_URL;
    } else {
      process.env.AI_BACKEND_URL = previousBackendUrl;
    }
  }
});

test('sendConversationTurnStream maps backend 401 to a login-required error', async () => {
  const previousBackendUrl = process.env.AI_BACKEND_URL;
  process.env.AI_BACKEND_URL = 'https://backend.test/api/ai/urdf-studio';
  const previousFetch = globalThis.fetch;

  globalThis.fetch = (async () => ({
    ok: false,
    status: 401,
    body: null,
    json: async () => ({ success: false, message: 'JWT Bearer token required' }),
  })) as unknown as typeof fetch;

  try {
    const result = await sendConversationTurnStream({
      mode: 'general',
      lang: 'zh',
      context: '',
      history: [],
      userMessage: '这个机器人怎么样？',
    });

    assert.equal(result.status, 'error');
    assert.equal(result.error?.code, 'login_required');
    assert.equal(result.error?.message, '请先登录后再使用 AI 助手。');
    assert.ok(!String(result.error?.message).includes('JWT'));
  } finally {
    globalThis.fetch = previousFetch;
    if (previousBackendUrl === undefined) {
      delete process.env.AI_BACKEND_URL;
    } else {
      process.env.AI_BACKEND_URL = previousBackendUrl;
    }
  }
});
