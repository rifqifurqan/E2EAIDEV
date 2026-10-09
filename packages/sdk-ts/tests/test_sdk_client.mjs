/**
 * FR-F12 TypeScript SDK: typed client tests with mocked fetch (no live network).
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { E2EAIClient } from '../src/index.mjs';

function mockFetch(status, body) {
  return async (url, options) => ({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: async () => body,
    url,
    _request: { url, ...options },
  });
}

describe('E2EAIClient', () => {
  it('sets base URL and API key', () => {
    const client = new E2EAIClient({ baseUrl: 'http://localhost:9000', apiKey: 'e2eai_test' });
    assert.equal(client.baseUrl, 'http://localhost:9000');
    assert.equal(client.apiKey, 'e2eai_test');
  });

  it('defaults base URL to localhost:8000', () => {
    const client = new E2EAIClient({ apiKey: 'e2eai_test', fetchFn: mockFetch(200, {}) });
    assert.equal(client.baseUrl, 'http://localhost:8000');
  });

  it('sends Bearer token in Authorization header', async () => {
    let capturedHeaders;
    const client = new E2EAIClient({
      apiKey: 'e2eai_mykey',
      fetchFn: async (_url, opts) => {
        capturedHeaders = opts.headers;
        return { ok: true, status: 200, json: async () => ({}) };
      },
    });
    await client.healthCheck();
    assert.equal(capturedHeaders['Authorization'], 'Bearer e2eai_mykey');
  });

  it('chat.listConversations calls correct endpoint', async () => {
    let capturedUrl;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (url, _opts) => {
      capturedUrl = url; return { ok: true, status: 200, json: async () => ({ conversations: [] }) };
    }});
    const result = await client.chatListConversations();
    assert.ok(capturedUrl.includes('/api/v1/chat/conversations'));
    assert.deepEqual(result.conversations, []);
  });

  it('chat.sendMessage calls correct endpoint with body', async () => {
    let capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (_url, opts) => {
      capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ answer: '42', citations: [] }) };
    }});
    const result = await client.chatSendMessage('conv-1', 'What?');
    assert.equal(capturedBody.question, 'What?');
    assert.equal(result.answer, '42');
  });

  it('documents.search calls correct endpoint', async () => {
    let capturedUrl;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (url, _opts) => {
      capturedUrl = url; return { ok: true, status: 200, json: async () => ({ results: [] }) };
    }});
    const result = await client.documentSearch('test');
    assert.ok(capturedUrl.includes('/api/v1/documents/search'));
    assert.ok(capturedUrl.includes('q=test'));
    assert.deepEqual(result.results, []);
  });

  it('documents.share calls correct endpoint', async () => {
    let capturedUrl, capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (url, opts) => {
      capturedUrl = url; capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ status: 'ok' }) };
    }});
    const result = await client.documentShare('doc-1', 'user:abc', 'viewer');
    assert.ok(capturedUrl.includes('/api/v1/documents/doc-1/shares'));
    assert.equal(capturedBody.principal, 'user:abc');
    assert.equal(result.status, 'ok');
  });

  it('accessRequests.create calls correct endpoint', async () => {
    let capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (_url, opts) => {
      capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ id: 'r1', status: 'pending' }) };
    }});
    const result = await client.accessRequestCreate('doc-1');
    assert.equal(capturedBody.document_id, 'doc-1');
    assert.equal(result.status, 'pending');
  });

  it('evals.createDataset calls correct endpoint', async () => {
    let capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (_url, opts) => {
      capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ id: 'ds-1', name: 'test' }) };
    }});
    const result = await client.evalCreateDataset('test', [{ q: 'hi' }]);
    assert.equal(capturedBody.name, 'test');
    assert.equal(result.name, 'test');
  });

  it('evals.run calls correct endpoint', async () => {
    let capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (_url, opts) => {
      capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ id: 'run-1', metrics: {} }) };
    }});
    const result = await client.evalRun('ds-1');
    assert.equal(capturedBody.dataset_id, 'ds-1');
    assert.deepEqual(result.metrics, {});
  });

  it('bots.ask calls correct endpoint', async () => {
    let capturedUrl, capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (url, opts) => {
      capturedUrl = url; capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ answer: 'Hi', citations: [] }) };
    }});
    const result = await client.botAsk('bot-1', 'Hello?');
    assert.ok(capturedUrl.includes('/api/v1/bots/bot-1/ask'));
    assert.equal(capturedBody.question, 'Hello?');
    assert.equal(result.answer, 'Hi');
  });

  it('bots.create calls correct endpoint', async () => {
    let capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (_url, opts) => {
      capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ id: 'b1', name: 'Bot' }) };
    }});
    const result = await client.botCreate('Bot');
    assert.equal(capturedBody.name, 'Bot');
    assert.equal(result.name, 'Bot');
  });

  it('bots.release calls correct endpoint', async () => {
    let capturedUrl;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (url, _opts) => {
      capturedUrl = url; return { ok: true, status: 200, json: async () => ({ id: 'bu1', version: 1 }) };
    }});
    await client.botRelease('bot-1', { model: 'test' });
    assert.ok(capturedUrl.includes('/api/v1/bots/bot-1/bundles'));
  });

  it('bots.grant calls correct endpoint', async () => {
    let capturedBody;
    const client = new E2EAIClient({ apiKey: 'key', fetchFn: async (_url, opts) => {
      capturedBody = JSON.parse(opts.body); return { ok: true, status: 200, json: async () => ({ principal: 'user:x', level: 'user' }) };
    }});
    await client.botGrant('bot-1', 'user:x');
    assert.equal(capturedBody.principal, 'user:x');
  });

  it('throws on non-OK response', async () => {
    const client = new E2EAIClient({ apiKey: 'bad-key', fetchFn: mockFetch(403, { title: 'Forbidden' }) });
    await assert.rejects(() => client.chatListConversations(), /403/);
  });
});
