# Runbook: GPU Out of Memory

## Symptoms

- Chat or embedding requests fail with "CUDA out of memory", "cudaMalloc failed", or HTTP 500/503.
- Ollama logs show "model requires more memory" or silently falls back to CPU (very slow answers).
- vLLM exits at startup or restarts in a loop.
- nvidia-smi shows memory.used close to memory.total.

## Diagnosis

1. Check GPU memory and which processes hold it:

        nvidia-smi
        nvidia-smi --query-gpu=memory.used,memory.total --format=csv

2. List models currently loaded in Ollama (host or container):

        ollama ps

3. Check serving logs for the exact allocation failure:

        docker compose logs ollama --tail=100
        docker compose logs vllm --tail=100

4. Compare the model footprint with the catalog estimate:

        cd cli && uv run e2eai models

5. Check whether several roles (chat, embedding, VLM) share the same GPU.

## Fix

1. **Unload models that are not needed:**

        ollama stop <model-name>

2. **Use a smaller or more quantized model** (for example Q4_K_M instead of Q8_0), then
   register it again in Admin -> Models.
3. **Ollama:** set OLLAMA_MAX_LOADED_MODELS=1 and OLLAMA_NUM_PARALLEL=1, then restart Ollama.
4. **vLLM:** lower --max-model-len and --gpu-memory-utilization, or reduce --max-num-seqs.
5. **Move embeddings or the VLM add-on to CPU** or to an external API (only for
   non-confidential data, see the egress policy FR-M9).
6. **Enable model routing** so simple questions use the small model (FR-M3).
7. **Free GPU memory held by other applications** on the same machine.
   The reference Lite laptop has 6 GB VRAM: vLLM does not fit there.

## Verification

1. Confirm free VRAM:

        nvidia-smi --query-gpu=memory.used,memory.total --format=csv

2. Send a test prompt through the gateway:

        curl http://127.0.0.1:14000/v1/chat/completions           -H "Authorization: Bearer $LITELLM_MASTER_KEY"           -H "Content-Type: application/json"           -d '{"model": "<model-name>", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8}'

3. Run the stack check:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If the model still does not fit, choose a smaller model in the install wizard or use a larger GPU.
- Record the failure as an AI incident (FR-O8) if users were affected.
- Never paste real keys into tickets: use [REDACTED].
