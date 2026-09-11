import test from 'node:test';
import assert from 'node:assert/strict';

import {
  AiBackendRequestError,
  isAiBackendEnabled,
  requestAiBackendContent,
  setAiBackendAuthTokenProvider,
  streamAiBackendChat,
} from './aiBackendTransport.ts';

const BACKEND_URL = 'https://backend.test/api/ai/urdf-studio';

const withBackendEnv = async (fn: () => Promise<void> | void): Promise<void> => {
  const previous = process.env.AI_BACKEND_URL;
  process.env.AI_BACKEND_URL = `${BACKEND_URL}/`;
  try {
    await fn();
  } finally {
    if (previous === undefined) {
      delete process.env.AI_BACKEND_URL;
    } else {
      process.env.AI_BACKEND_URL = previous;
    }
  }
};

interface CapturedRequest {
  url: string;
  init: RequestInit;
}

const withFetch = async (
  impl: (url: string, init: RequestInit) => Promise<unknown>,
  fn: (requests: CapturedRequest[]) => Promise<void> | void,
): Promise<void> => {
  const previousFetch = globalThis.fetch;
  const requests: CapturedRequest[] = [];
  globalThis.fetch = (async (url: unknown, init?: RequestInit) => {
    const captured = { url: String(url), init: init ?? {} };
    requests.push(captured);
    return impl(captured.url, captured.init);
  }) as typeof fetch;
  try {
    await fn(requests);
  } finally {
    globalThis.fetch = previousFetch;
  }
};

const jsonResponse = (status: number, payload: unknown): unknown => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => payload,
});

const sseBody = (chunks: string[]): ReadableStream<Uint8Array> => {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
};

test('isAiBackendEnabled reflects the backend URL env', async () => {
  assert.equal(isAiBackendEnabled(), false);
  await withBackendEnv(() => {
    assert.equal(isAiBackendEnabled(), true);
  });
});

test('requestAiBackendContent posts JSON and returns data.content', async () => {
  await withBackendEnv(() =>
    withFetch(
      async () => jsonResponse(200, { success: true, data: { content: '{"a":1}' } }),
      async (requests) => {
        const content = await requestAiBackendContent('/generate', { prompt: 'hi' });
        assert.equal(content, '{"a":1}');
        assert.equal(requests.length, 1);
        assert.equal(requests[0].url, `${BACKEND_URL}/generate`);
        assert.equal(requests[0].init.method, 'POST');
        assert.equal(JSON.parse(String(requests[0].init.body)).prompt, 'hi');
        const headers = requests[0].init.headers as Record<string, string>;
        assert.equal(headers['Content-Type'], 'application/json');
        assert.equal(headers.Authorization, undefined);
      },
    ),
  );
});

test('requestAiBackendContent attaches the registered auth token as Bearer', async () => {
  setAiBackendAuthTokenProvider(() => 'jwt-token');
  try {
    await withBackendEnv(() =>
      withFetch(
        async () => jsonResponse(200, { success: true, data: { content: 'ok' } }),
        async (requests) => {
          await requestAiBackendContent('/inspect', { robot: {} });
          const headers = requests[0].init.headers as Record<string, string>;
          assert.equal(headers.Authorization, 'Bearer jwt-token');
        },
      ),
    );
  } finally {
    setAiBackendAuthTokenProvider(null);
  }
});

test('requestAiBackendContent surfaces backend error messages with status', async () => {
  await withBackendEnv(() =>
    withFetch(
      async () => jsonResponse(401, { success: false, message: 'JWT Bearer token required' }),
      async () => {
        await assert.rejects(
          requestAiBackendContent('/generate', { prompt: 'hi' }),
          (error: unknown) => {
            assert.ok(error instanceof AiBackendRequestError);
            assert.equal(error.message, 'JWT Bearer token required');
            assert.equal(error.status, 401);
            return true;
          },
        );
      },
    ),
  );
});

test('requestAiBackendContent rejects empty content', async () => {
  await withBackendEnv(() =>
    withFetch(
      async () => jsonResponse(200, { success: true, data: { content: '' } }),
      async () => {
        await assert.rejects(
          requestAiBackendContent('/generate', { prompt: 'hi' }),
          AiBackendRequestError,
        );
      },
    ),
  );
});

test('streamAiBackendChat forwards deltas and resolves on done', async () => {
  await withBackendEnv(() =>
    withFetch(
      async () => ({
        ok: true,
        status: 200,
        body: sseBody([
          'data: {"delta":"你好"}\n\n',
          'data: {"del',
          'ta":"，世界"}\n\ndata: {"done":true}\n\n',
        ]),
        json: async () => null,
      }),
      async (requests) => {
        const deltas: string[] = [];
        const result = await streamAiBackendChat(
          { userMessage: 'hi' },
          { onDelta: (delta) => deltas.push(delta) },
        );
        assert.equal(requests[0].url, `${BACKEND_URL}/chat`);
        assert.deepEqual(deltas, ['你好', '，世界']);
        assert.deepEqual(result, { reply: '你好，世界', status: 'completed' });
      },
    ),
  );
});

test('streamAiBackendChat throws on protocol error events', async () => {
  await withBackendEnv(() =>
    withFetch(
      async () => ({
        ok: true,
        status: 200,
        body: sseBody(['data: {"delta":"部分"}\n\n', 'data: {"error":"provider exploded"}\n\n']),
        json: async () => null,
      }),
      async () => {
        await assert.rejects(streamAiBackendChat({ userMessage: 'hi' }), (error: unknown) => {
          assert.ok(error instanceof AiBackendRequestError);
          assert.equal(error.message, 'provider exploded');
          return true;
        });
      },
    ),
  );
});

test('streamAiBackendChat throws when the stream ends without done', async () => {
  await withBackendEnv(() =>
    withFetch(
      async () => ({
        ok: true,
        status: 200,
        body: sseBody(['data: {"delta":"半截"}\n\n']),
        json: async () => null,
      }),
      async () => {
        await assert.rejects(streamAiBackendChat({ userMessage: 'hi' }), AiBackendRequestError);
      },
    ),
  );
});

test('streamAiBackendChat returns the partial reply when aborted', async () => {
  const controller = new AbortController();
  const abortError = Object.assign(new Error('aborted'), { name: 'AbortError' });
  const encoder = new TextEncoder();
  let pullCount = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(streamController) {
      pullCount += 1;
      if (pullCount === 1) {
        streamController.enqueue(encoder.encode('data: {"delta":"第一段"}\n\n'));
        return;
      }
      throw abortError;
    },
  });

  await withBackendEnv(() =>
    withFetch(
      async () => ({ ok: true, status: 200, body, json: async () => null }),
      async () => {
        const result = await streamAiBackendChat(
          { userMessage: 'hi' },
          {
            signal: controller.signal,
            onDelta: () => controller.abort(),
          },
        );
        assert.deepEqual(result, { reply: '第一段', status: 'aborted' });
      },
    ),
  );
});
