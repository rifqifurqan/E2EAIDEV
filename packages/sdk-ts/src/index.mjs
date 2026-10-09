export class E2EAIClient {
  constructor({ apiKey, baseUrl = 'http://localhost:8000', fetchFn = globalThis.fetch } = {}) {
    if (!apiKey) throw new Error('apiKey is required');
    if (!fetchFn) throw new Error('fetchFn is required in this runtime');
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.fetchFn = fetchFn;
  }

  async request(method, path, { query, body } = {}) {
    const url = new URL(`${this.baseUrl}${path}`);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
      }
    }
    const options = {
      method,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        Accept: 'application/json',
      },
    };
    if (body !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const response = await this.fetchFn(url.toString(), options);
    const payload = await response.json();
    if (!response.ok) {
      const title = payload?.title || response.statusText || 'Request failed';
      throw new Error(`${response.status} ${title}`);
    }
    return payload;
  }

  healthCheck() { return this.request('GET', '/api/v1/health'); }

  chatListConversations() { return this.request('GET', '/api/v1/chat/conversations'); }
  chatSendMessage(conversationId, question, extra = {}) {
    return this.request('POST', `/api/v1/chat/conversations/${conversationId}/messages`, { body: { question, ...extra } });
  }

  documentList(view = 'shared_with_me') {
    return this.request('GET', '/api/v1/documents', { query: { view } });
  }
  documentSearch(q, params = {}) {
    return this.request('GET', '/api/v1/documents/search', { query: { q, ...params } });
  }
  documentShare(documentId, principal, level = 'viewer', expiresAt = undefined) {
    const body = { principal, level };
    if (expiresAt) body.expires_at = expiresAt;
    return this.request('POST', `/api/v1/documents/${documentId}/shares`, { body });
  }
  accessRequestCreate(documentId) {
    return this.request('POST', '/api/v1/documents/access-requests', { body: { document_id: documentId } });
  }
  accessRequestList() { return this.request('GET', '/api/v1/documents/access-requests'); }
  accessRequestApprove(requestId) { return this.request('POST', `/api/v1/documents/access-requests/${requestId}/approve`); }
  accessRequestDeny(requestId) { return this.request('POST', `/api/v1/documents/access-requests/${requestId}/deny`); }

  evalCreateDataset(name, items, source = 'sdk') {
    return this.request('POST', '/api/v1/evals/datasets', { body: { name, items, source } });
  }
  evalRun(datasetId, adapter = 'local-ragas') {
    return this.request('POST', '/api/v1/evals/runs', { body: { dataset_id: datasetId, adapter } });
  }

  botCreate(name) { return this.request('POST', '/api/v1/bots', { body: { name } }); }
  botAsk(botId, question) { return this.request('POST', `/api/v1/bots/${botId}/ask`, { body: { question } }); }
  botRelease(botId, bundle) { return this.request('POST', `/api/v1/bots/${botId}/bundles`, { body: { bundle } }); }
  botGrant(botId, principal, level = 'user') {
    return this.request('POST', `/api/v1/bots/${botId}/grants`, { body: { principal, level } });
  }
}
