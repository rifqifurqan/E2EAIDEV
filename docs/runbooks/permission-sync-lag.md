# Runbook: Permission Sync Lag

## Symptoms

- A user who was just granted access cannot retrieve the shared document.
- A user whose access was just revoked can still retrieve the document.
- OpenFGA check results are stale (permission changes take more than a few seconds to apply).

## Diagnosis

1. Check OpenFGA is running:

        cd deploy/compose && docker compose ps openfga

2. Check OpenFGA logs for errors:

        docker compose logs openfga --tail=100

3. Verify the authorization model is current:

        cd apps/api && uv run e2eai-api bootstrap-authz

4. Check the specific tuple in OpenFGA (use the OpenFGA API or playground):

        curl http://127.0.0.1:18080/stores/<store-id>/read \
          -H "Authorization: Bearer $OPENFGA_PRESHARED_KEY" \
          -H "Content-Type: application/json" \
          -d '{"tuple_key": {"user": "user:<user-id>", "relation": "viewer", "object": "document:<doc-id>"}}'

5. Check if the share operation completed in the database:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \
          -c "SELECT * FROM doc_principals WHERE document_id = '<doc-id>';"

6. Check if there is a Valkey cache entry for the user that has stale permissions:

        docker compose exec valkey valkey-cli -a "$VALKEY_PASSWORD" \
          KEYS "session:*"

## Fix

1. **OpenFGA tuple was not written:** re-run the share operation through the API.

2. **Stale cache:** clear the user session cache in Valkey:

        docker compose exec valkey valkey-cli -a "$VALKEY_PASSWORD" \
          DEL "session:<session-id>"

3. **OpenFGA is down or unresponsive:** restart it:

        docker compose restart openfga

4. **Authorization model is outdated:** re-apply it:

        cd apps/api && uv run e2eai-api bootstrap-authz

5. **SCIM sync delay (P2):** check the SCIM sync job status and logs.

## Verification

1. Verify the tuple exists in OpenFGA:

        # Use the read endpoint or playground to confirm

2. Test the permission check:

        cd apps/api && uv run e2eai-api verify-phase-0

3. Have the affected user attempt the operation that was failing.

## Escalation

- If OpenFGA consistently loses tuples, check its Postgres backend for disk or connection issues.
- For SCIM sync issues (P2), check the identity provider webhook delivery logs.
- Document the affected users and time window for the incident report.
