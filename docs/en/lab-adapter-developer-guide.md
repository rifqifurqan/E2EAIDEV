# Lab Adapter Developer Guide

Requirement: FR-F22. This guide explains how to add a Lab tool adapter without mixing tool dependencies into the platform API environment.

## Scope

Lab adapters let E2EAIDEV compare tools across the lifecycle: evaluation, retrieval, serving, red-team testing, document understanding, and future stages. Each adapter normalizes a tool into the same contract so comparison reports can be reproducible.

## Architecture Rules

- Every Lab tool runs in its own container. Do not install Ragas, DeepEval, promptfoo, garak, Phoenix, or other tool-specific dependency stacks into `apps/api`.
- The API talks to adapters through a narrow HTTP/contract boundary and stores normalized results only.
- Adapter outputs must be safe to persist: no raw secrets, bearer tokens, API keys, passwords, provider credentials, or unrestricted document payloads.
- Model and judge calls from an adapter go through the configured gateway key for the run so cost and budgets can be tracked.

## Adapter Contract

Each adapter exposes these HTTP endpoints:

### GET /info

Returns static metadata:

```json
{
  "name": "ragas.local",
  "version": "0.1.0",
  "stage": "test",
  "license": "Apache-2.0",
  "operations": ["faithfulness", "answer_correctness"],
  "capabilities": {"read_only": true, "supports_cancel": false}
}
```

### GET /health

Returns liveness/readiness for the adapter container:

```json
{"healthy": true, "version": "0.1.0", "detail": "ready"}
```

### POST /run

Runs one normalized operation over fixed inputs:

```json
{
  "run_id": "uuidv7-or-test-id",
  "operation": "faithfulness",
  "inputs": [{"item_id": "1", "question": "...", "answer": "..."}],
  "config": {"temperature": 0, "seed": 7},
  "judge": {"base_url": "http://litellm:4000/v1", "model": "chosen-judge"}
}
```

Response shape:

```json
{
  "results": [
    {"item_id": "1", "metric": "faithfulness", "score": 0.92, "details": {}, "judge_prompt": "prompt-ref-or-redacted-template"}
  ]
}
```

Do not return raw provider credentials, tool API keys, or full confidential documents in `details`.

## Python Boundary in the Platform

The in-process platform contract lives in `apps/api/src/e2eai/tool_adapter.py`:

- `ToolAdapter` protocol: `name`, `version`, `capabilities`, `health()`, `configure()`, and async `run()`.
- `ToolCapabilities`: read-only/cancel/resume/max input/streaming metadata.
- `AdapterHealth`: health snapshot.
- `ToolAdapterRegistry`: registration and lookup.
- `check_adapter_contract` and `check_registry_contract`: contract checks used by tests.

Use this protocol for local/deterministic adapters and for test doubles around HTTP containers.

## Contract Tests

Add or extend tests under `apps/api/tests/` for each adapter. Minimum checks:

1. `GET /info` metadata has name, version, stage, license, and operations.
2. `GET /health` returns a healthy response with the same version as `/info`.
3. `POST /run` returns deterministic normalized rows for a small fixture.
4. Output contains no secrets or raw credentials.
5. The adapter handles empty inputs safely.
6. The adapter container can run without mutating platform state.

Focused test command:

```bash
cd apps/api && uv run pytest -q tests/test_us_tool_adapter_p1.py
```

## Implementation Checklist

- [ ] Create an adapter folder under `adapters/<stage>/<tool>/`.
- [ ] Pin the container image or package versions; never use floating `latest` tags.
- [ ] Implement `GET /info`, `GET /health`, and `POST /run`.
- [ ] Add deterministic fixtures and contract tests.
- [ ] Ensure all outputs are normalized and secret-safe.
- [ ] Update the tool catalog and any docs for the stage.
- [ ] Run focused adapter tests plus adjacent Lab tests.

## No Secrets

Never store or print generated passwords, API keys, bearer tokens, OAuth tokens, LiteLLM master keys, database DSNs with passwords, or raw external-provider credentials. Use environment references and redact human-facing logs as `[REDACTED]`.
