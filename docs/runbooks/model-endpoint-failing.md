# Runbook: Model Endpoint Failing

## Symptoms

- Chat queries return errors or time out.
- LiteLLM returns 500, 502, or 504 errors.
- Embedding requests fail (document indexing stalls).
- verify-phase-0 fails at the "litellm chat" or "litellm embedding" step.

## Diagnosis

1. Check LiteLLM health:

        curl http://127.0.0.1:14000/health

2. Test a direct chat completion:

        curl http://127.0.0.1:14000/v1/chat/completions \
          -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
          -H "Content-Type: application/json" \
          -d '{"model": "<model-name>", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8}'

3. Test embedding:

        curl http://127.0.0.1:14000/v1/embeddings \
          -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
          -H "Content-Type: application/json" \
          -d '{"model": "<embedding-model>", "input": "test"}'

4. Check the upstream model server:
   - **Ollama (host):** curl http://127.0.0.1:11434/api/tags
   - **Ollama (Docker):** docker compose logs ollama --tail=50
   - **vLLM:** docker compose logs vllm --tail=50

5. Check LiteLLM logs:

        docker compose logs litellm --tail=100

6. Check GPU memory (if using GPU models):

        nvidia-smi

## Fix

1. **Ollama model not loaded:**

        ollama list
        ollama pull <model-name>

2. **LiteLLM config mismatch:** verify the model is registered in LiteLLM config
   (deploy/compose/litellm/config.yaml or via admin API).

3. **Out of memory (GPU):**
   - Unload unused models: ollama stop <model-name>
   - Switch to a smaller quantization (e.g., Q4_K_M instead of Q8_0).
   - For vLLM: reduce --max-model-len or --gpu-memory-utilization.

4. **Restart LiteLLM:**

        docker compose restart litellm

5. **Restart Ollama (host):**

        # On Windows: restart the Ollama service from the system tray
        # On Linux:
        sudo systemctl restart ollama

## Verification

1. Re-test the model endpoints:

        curl http://127.0.0.1:14000/health

2. Run the Phase 0 verification:

        cd apps/api && uv run e2eai-api verify-phase-0

3. Test a sample chat query through the application.

## Escalation

- If the model repeatedly crashes with OOM, consider switching to a smaller model or
  increasing GPU/RAM resources.
- Check model compatibility notes in the catalog (catalog/models.yaml).
- For external API failures, check the provider status page and API key validity.
