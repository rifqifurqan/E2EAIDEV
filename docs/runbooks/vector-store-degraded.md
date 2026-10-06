# Runbook: Vector Store Degraded

## Symptoms

- Chat queries return no results or incomplete results.
- Retrieval latency significantly increased.
- Document indexing (embedding + insert) fails.
- verify-phase-0 passes but search quality is noticeably worse.

## Diagnosis

1. Check postgres (pgvector) is running and healthy:

        cd deploy/compose && docker compose ps postgres

2. Check pgvector extension:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"

3. Check chunk and embedding counts:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT count(*) FROM chunks; SELECT count(*) FROM chunk_embeddings;"

4. Check for index bloat or missing indexes:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) FROM pg_indexes WHERE tablename = 'chunk_embeddings';"

5. Check Postgres disk usage:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT pg_size_pretty(pg_database_size('e2eai'));"

6. Check Postgres logs for errors:

        docker compose logs postgres --tail=100

## Fix

1. **Missing embeddings for documents:** re-index the affected document:

        cd apps/api && uv run e2eai-api index-document <doc-uuid>

2. **Corrupted or stale index:** rebuild the HNSW index:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "REINDEX INDEX CONCURRENTLY <index-name>;"

3. **High latency due to table bloat:**

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "VACUUM ANALYZE chunk_embeddings;"

4. **Postgres out of shared memory:** increase shared_buffers or work_mem in the Postgres
   config (requires container restart).

5. **Embedding dimension mismatch** (model changed but old embeddings remain): re-index all
   documents with the new embedding model.

## Verification

1. Check embedding counts match expected documents:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT count(DISTINCT document_id) FROM chunks;"

2. Test a sample retrieval query through the API.

3. Run the Phase 0 verification:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If Postgres is consistently running out of memory, consider increasing the Docker memory limit.
- For large-scale re-indexing, plan for downtime and notify users.
- If switching vector stores (e.g., to Qdrant), follow the migration plan in the admin guide.
