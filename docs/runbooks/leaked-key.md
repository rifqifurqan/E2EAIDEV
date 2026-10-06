# Runbook: Leaked Key

## Symptoms

- A secret (API key, database password, OIDC client secret, LiteLLM master key, S3 key)
  has been exposed in a commit, log, error message, or external system.
- Unauthorized access detected in audit logs.
- Security scanner or team member reports a credential exposure.

## Diagnosis

1. Identify which key was leaked and where:
   - Check git history for accidental commits of .env or secrets.
   - Check application logs for logged secrets (search for known key prefixes).
   - Check audit logs for unauthorized access patterns.

2. Determine the blast radius:
   - Which services does this key protect?
   - Was the key used by an unauthorized party? (check audit logs)
   - When was the key first exposed?

## Fix

**Act within 5 minutes of discovery.** The goal is to revoke the compromised credential and
issue a new one before it can be exploited.

1. **Rotate the compromised key immediately:**

   - **Postgres password:** Update POSTGRES_PASSWORD in deploy/compose/.env, restart postgres,
     update connection strings in all dependent services.
   - **Valkey password:** Update VALKEY_PASSWORD in .env, restart valkey and all services that
     connect to it.
   - **OpenFGA preshared key:** Update OPENFGA_PRESHARED_KEY in .env, restart openfga and the API.
   - **LiteLLM master key:** Update LITELLM_MASTER_KEY in .env, restart litellm and the API.
   - **SeaweedFS S3 keys:** Update the keys in .env and seaweedfs/s3.json, restart seaweedfs
     and the API.
   - **OIDC client secret:** Rotate in Keycloak admin console and update .env.

2. **Restart affected services:**

        cd deploy/compose && docker compose down && docker compose up -d

3. **If the key was committed to git:**
   - Do NOT rewrite git history on a shared branch without coordination.
   - Ensure the .env file is in .gitignore (it should already be).
   - Confirm the secret-scan check in the CI/commit workflow catches this pattern.

4. **Revoke any sessions or tokens that used the leaked key:**

        # If user sessions may be compromised, flush Valkey sessions:
        docker compose exec valkey valkey-cli -a "$VALKEY_PASSWORD" FLUSHDB

5. **Audit trail review:**
   - Check the audit_events table for any suspicious activity during the exposure window.
   - Check application and infrastructure logs.

## Verification

1. Confirm the old key no longer works:

        # Test with the OLD key -- should get 401 or connection refused
        curl http://127.0.0.1:14000/health -H "Authorization: Bearer <OLD_KEY>"

2. Confirm the new key works:

        cd apps/api && uv run e2eai-api verify-phase-0

3. Check that .env is not tracked by git:

        git status deploy/compose/.env
        # Should show nothing (file is gitignored)

## Escalation

- Notify the platform owner and security team immediately.
- If the key was exposed publicly (e.g., in a public git repo), treat as a security incident.
- Document: what was leaked, exposure window, blast radius, remediation steps taken.
- Review and tighten access controls to prevent recurrence.
- Never log, print, or store rotated secrets -- generate new ones with the wizard or a
  secure random generator.
