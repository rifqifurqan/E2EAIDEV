#!/bin/sh
# Runs once, on a fresh data volume. One database and one login per service (least privilege).
# Passwords are restricted by the wizard to [A-Za-z0-9._~-], so quoting them in SQL is safe.
set -eu

create() {
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE $1 LOGIN PASSWORD '$2';
CREATE DATABASE $1 OWNER $1;
SQL
}

create openfga "$OPENFGA_DB_PASSWORD"
create litellm "$LITELLM_DB_PASSWORD"
create keycloak "$KEYCLOAK_DB_PASSWORD"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"
