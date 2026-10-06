#!/usr/bin/env python3
"""Generate all P0 documentation files (FR-F22, FR-F14, FR-O13).

Run: python scripts/generate_docs.py
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"


def _write(relpath: str, content: str) -> None:
    p = DOCS / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  wrote docs/{relpath}")


# ============================================================================
# English User Guide
# ============================================================================
EN_USER_GUIDE = """\
# E2EAIDEV User Guide

This guide covers everyday tasks for business users and knowledge owners in the E2EAIDEV platform.

## Getting Started

### Logging In

1. Open the E2EAIDEV web application in your browser.
2. Click **Sign in** and authenticate via your organization's SSO (Keycloak OIDC).
   - If SSO is not yet configured, use the local account credentials provided by your administrator.
3. On first login you will see the lifecycle navigation: **Plan > Data > Build > Test > Release > Operate > Improve**.

### Your Profile

After login your profile shows your name, email, role, team, and division. Contact your administrator to correct any details.

### Roles

| Role | Can do |
|------|--------|
| Business User | Upload, share, and chat about documents |
| Knowledge Owner | All of the above plus manage folders and sharing |
| AI Engineer | Configure models, prompts, retrieval, run evaluations |
| Evaluator | Review AI answers, label gold sets |
| Admin | Full platform administration |

---

## Document Upload

### Supported Formats

PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, and image files (PNG, JPG, TIFF).

### Uploading a File

1. Navigate to **Data > Documents**.
2. Click **Upload** or drag files into the upload area.
3. Limits: 100 MB per file, 50 files per batch, 20 GB storage per user (defaults; your admin may adjust these).
4. After upload the document is parsed automatically (layout-aware parsing with table extraction, OCR for scanned pages, figure cropping). You will see a status indicator while processing completes.

### Document Versioning

Re-uploading a file with the same name in the same folder creates a new version. The AI always retrieves from the latest version. Citations in older chats still point to the version they quoted.

### Trash and Deletion

- Deleting a document moves it to **trash**. Within 5 minutes it is excluded from AI retrieval.
- You can restore from trash for 30 days.
- After 30 days (or on "delete permanently"), the file, chunks, and embeddings are purged.

---

## Sharing

### How Sharing Works

E2EAIDEV uses a Google-Drive-style sharing model. You can share a document or folder with:

- A specific **user**
- A **team**
- A **role** (e.g., all AI Engineers)
- A **division**
- The **entire organization**

### Sharing a Document

1. Select a document and click **Share**.
2. Choose the recipient (user, team, role, division, or organization).
3. Choose the permission level: **Viewer** or **Editor**.
4. Click **Confirm**.

The recipient receives an in-app notification that a document has been shared with them.

### Sharing a Folder

Sharing a folder grants the chosen permission to all documents inside it, including documents added later (inherited sharing).

### Revoking Access

1. Open the document or folder's sharing panel.
2. Remove the recipient or change their permission level.
3. Access is revoked immediately; the next AI query will no longer use that document.

### Permission Rules

- Permissions are checked **inside** every vector query, not after retrieval. This prevents information leaks.
- Derived content (e.g., cached answers) inherits the strictest permission of its source documents.
- Sensitivity labels (Public / Internal / Confidential / Restricted) can further limit who a document may be shared with.

---

## Chat

### Asking a Question

1. Navigate to **Chat**.
2. Type your question in natural language. Example: *"What is the revenue share in the WhatsApp partnership?"*
3. The AI searches only documents you have access to, retrieves relevant passages, and responds with an answer and **citations**.

### Citations

Every answer includes citations showing:
- The source document name
- Page number and section
- A clickable link to the source passage (highlighted)

When an answer uses a table or figure, the citation shows that table or figure crop.

### Conversation History

- Your chat history is saved and accessible from the sidebar.
- Each conversation tracks the context so follow-up questions work naturally.
- You can start a new conversation at any time.

### Feedback

- Click **thumbs up** or **thumbs down** on any answer.
- Thumbs-down answers can flow into evaluation datasets to improve future releases.

### What the AI Cannot See

- Documents not shared with you are invisible to the AI, even if they exist in the system.
- If your access to a document is revoked, the AI stops using it from the very next query.
- The system never reveals the existence of documents you cannot access (no existence leaks).

---

## PII and Safety Guardrails

- The platform runs prompt-injection detection on every query. Malicious prompts are blocked and logged.
- PII redaction can be enabled by your administrator to protect sensitive data during ingestion.

---

## Bots

If your organization has published bots (e.g., an HR-policy bot):

1. Go to **Chat > Bots** and select the bot you have access to.
2. Each bot has a defined knowledge scope (specific folders or document sets).
3. **Your effective access = bot scope intersected with your personal permissions.** A bot never shows you documents you would not otherwise be able to see.

---

## Getting Help

- Contact your platform administrator for account issues, access requests, or technical problems.
- Check the **Admin & Operator Guide** for operational details.
"""

# ============================================================================
# English Admin & Operator Guide
# ============================================================================
EN_ADMIN_GUIDE = """\
# E2EAIDEV Admin & Operator Guide

This guide covers installation, configuration, day-to-day operations, and maintenance for platform administrators.

---

## Installation

### Prerequisites

| Component | Minimum |
|-----------|---------|
| OS | Linux (Ubuntu 22.04+), Windows 11 with WSL2, macOS 13+ |
| Docker | Docker Desktop or Docker Engine 24+ with Compose v2 |
| Python | 3.12 (managed via uv; do not modify the system Python) |
| Node.js | 20+ (for the web frontend) |
| RAM | Lite: 8 GB, Standard: 16 GB, Enterprise: 32 GB+ |
| Disk | 20 GB minimum for images + models |

### Install Tiers

| Tier | Description | Components |
|------|-------------|------------|
| **Lite** | Single-machine, minimal resources | Postgres+pgvector, Valkey, OpenFGA, SeaweedFS, LiteLLM, Ollama (host) |
| **Standard** | Full lab with GPU serving | All Lite + vLLM, TEI, Langfuse, Temporal |
| **Enterprise** | Multi-node, HA, SCIM | All Standard + clustering, SCIM sync, advanced audit |

### Step-by-Step Installation

1. **Clone the repository:**

        git clone https://github.com/rifqifurqan/E2EAIDEV.git
        cd E2EAIDEV

2. **Run the install wizard:**

        cd cli && uv run e2eai

   The wizard will:
   - Detect your hardware (CPU, RAM, GPU/VRAM, disk)
   - Recommend a tier (Lite/Standard/Enterprise)
   - Let you choose models for each role (chat, embedding, reranker, judge, safety)
   - Choose the job engine (Celery default, or Temporal for Standard+)
   - Generate deploy/compose/.env (secrets, gitignored) and e2eai.yaml (config)
   - Pull pinned container images

   Use --yes to accept defaults, --force to overwrite an existing .env (a backup is kept).

3. **Start the infrastructure:**

        cd deploy/compose && docker compose up -d

4. **Verify services are running:**

        docker compose ps

   Expected: postgres, valkey, openfga, seaweedfs, litellm all show running or healthy.

5. **Run database migrations:**

        cd apps/api && uv run alembic upgrade head

6. **Bootstrap the admin account:**

        cd apps/api && uv run e2eai-api bootstrap-admin

   This creates the break-glass admin. The password is displayed **once** -- store it securely.

7. **Bootstrap the authorization model:**

        cd apps/api && uv run e2eai-api bootstrap-authz

8. **Seed demo data (optional):**

        cd apps/api && uv run e2eai-api seed-demo

   Creates a demo organization with sample users (Andi/Sales, Budi/HR, Intern).

9. **Verify the full Phase 0 stack:**

        cd apps/api && uv run e2eai-api verify-phase-0

   This runs compose health checks, CLI tests, API tests, Alembic migrations, API health/ready
   endpoints, LiteLLM chat and embedding, and the OpenFGA authorization model check.

### Wizard Tests

    cd cli && uv run pytest -q

### API Tests

    cd apps/api && uv run pytest -q

---

## Configuration

### Configuration File (e2eai.yaml)

The wizard generates e2eai.yaml at the repository root. This file captures the entire
installation: tier, components, models, and policies. It can be versioned in git, diffed,
and re-applied.

- Secrets are **referenced** (e.g., env:POSTGRES_PASSWORD), never stored in the config file.
- Invalid configuration fails at startup with a clear error message.
- Validate config:

        cd apps/api && uv run e2eai-api check-config

### Environment Variables (deploy/compose/.env)

All secrets live in deploy/compose/.env, which is gitignored. The wizard generates this file.
Key variables include database credentials, Valkey auth, OpenFGA preshared key, LiteLLM master
key, and SeaweedFS S3 keys.

All generated secrets use [A-Za-z0-9._~-], at least 16 characters, safe for DSNs and .env
without escaping.

### Port Configuration

Default host ports are in the 1xxxx range, bound to 127.0.0.1:

| Service | Default Port |
|---------|-------------|
| Postgres | 15432 |
| Valkey | 16379 |
| OpenFGA | 18080 |
| SeaweedFS | 18333 |
| LiteLLM | 14000 |
| Ollama (host) | 11434 |
| Keycloak | 18081 / 18082 |

The wizard skips busy ports automatically. Ports can be changed in .env.

### Model Configuration

Models are chosen during wizard setup. Each role (chat, embedding, reranker, judge, safety)
can have one or more models configured. To change models later:

1. Edit e2eai.yaml under the models section.
2. Register or update models in LiteLLM via its admin API or config.
3. Verify:

        cd apps/api && uv run e2eai-api verify-phase-0

### Data Egress Policy

External model APIs are **off by default**. To enable:

1. Set the admin-level egress setting in the configuration.
2. Per sensitivity label, choose allowed destinations (e.g., Confidential/Restricted content
   goes only to local models).
3. The LiteLLM gateway enforces the policy; blocked calls are audited.

---

## Backup

### Database Backup

    # Backup Postgres (run from the host)
    docker compose -f deploy/compose/compose.yaml exec postgres \\
      pg_dump -U "$POSTGRES_USER" e2eai > backup.sql

    # Backup with compression
    docker compose -f deploy/compose/compose.yaml exec postgres \\
      pg_dump -U "$POSTGRES_USER" -Fc e2eai > backup.dump

### Object Storage Backup

SeaweedFS data is stored in Docker volumes. Back up the volume:

    docker volume ls | grep seaweed
    docker run --rm -v e2eaidev_seaweeddata:/data -v "$PWD":/backup alpine \\
      tar czf /backup/seaweedfs_backup.tar.gz /data

### Valkey Backup

    docker run --rm -v e2eaidev_valkeydata:/data -v "$PWD":/backup alpine \\
      tar czf /backup/valkey_backup.tar.gz /data

### Restore

See [Runbook: Restore from Backup](../runbooks/restore-from-backup.md).

---

## Monitoring

### Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| GET /api/v1/health | Application liveness (returns status ok) |
| GET /api/v1/ready | Application readiness (checks database connectivity) |

### Docker Compose Health

    cd deploy/compose && docker compose ps

All services should show running or healthy. If any service shows unhealthy or restarting,
check logs:

    docker compose logs <service-name> --tail=50

### Key Metrics to Watch

- **Postgres**: connections, replication lag, disk usage
- **Valkey**: memory usage, connected clients, evictions
- **LiteLLM**: request latency, error rate, token usage
- **SeaweedFS**: storage utilization, read/write latency
- **OpenFGA**: authorization check latency

### Audit Log

Every login, upload, share, permission change, query, tool call, release, and admin action is
recorded in the audit log. The log is tamper-evident. Audit events are stored in the
audit_events table in Postgres.

---

## User Management

### Organization Model

The platform uses a hierarchical model: **Organization > Division > Team > User**, with roles.

### Creating Users

Users are provisioned through:

1. **SSO/OIDC** (Keycloak): users are created on first login.
2. **Seed command**: cd apps/api && uv run e2eai-api seed-demo (demo data).
3. **API**: POST /api/v1/auth/register (if local registration is enabled).

### Roles

| Role | Permissions |
|------|-------------|
| Admin | Full platform access, user management, configuration |
| AI Engineer | Model configuration, evaluation, bot management |
| Evaluator | Review answers, label datasets |
| Compliance | Audit log access, risk classification |
| Business User | Document upload, sharing, chat |

### User Offboarding

When an employee leaves the organization:

**Via CLI:**

    cd apps/api && uv run e2eai-api deactivate-user <target_email> <transfer_to_email> <admin_email>

**Via API:**

    curl -X POST http://localhost:18000/api/v1/users/<user-id>/deactivate \\
      -H "Authorization: Bearer <admin-token>" \\
      -H "Content-Type: application/json" \\
      -d '{"transfer_to_id": "<manager-user-id>"}'

The offboarding process:

1. Sets the user status to **disabled** -- login and sessions stop immediately.
2. Revokes all active Valkey sessions (within 1 minute).
3. Transfers owned documents and folders to the designated recipient.
4. Existing shares to other users remain intact.
5. Chat history is retained but inaccessible to the disabled user.
6. All actions are audited.

---

## Evaluation Lab

### Creating Eval Datasets

Supports deterministic synthetic Q&A, adversarial, and persona-based test generation from
source chunks. Use the POST /api/v1/evals/datasets endpoint.

### Running Evaluations

Use POST /api/v1/evals/runs with a dataset ID and adapter (e.g., local_ragas). Results include
normalized metrics, item-level results, and regression comparison between runs.

### Permission-Leak Suite

The built-in permission-leak test suite verifies that restricted documents never appear in
unauthorized retrieval results. A leak failure blocks the release.

---

## Bot Management

### Creating and Releasing Bots

Bots are containers for versioned AI configurations. Each release creates an immutable bundle.
Rollback switches the production pointer to a previous bundle.

### Bot Access and Scope

- Grant access to users, teams, roles, or divisions.
- Set a knowledge scope (selected folders/documents).
- Effective retrieval = bot scope intersected with the user permissions.

---

## Runbooks

See the [runbooks directory](../runbooks/) for incident response:

- [Service Down](../runbooks/service-down.md)
- [Restore from Backup](../runbooks/restore-from-backup.md)
- [Model Endpoint Failing](../runbooks/model-endpoint-failing.md)
- [Vector Store Degraded](../runbooks/vector-store-degraded.md)
- [Permission Sync Lag](../runbooks/permission-sync-lag.md)
- [Disk Full](../runbooks/disk-full.md)
- [Leaked Key](../runbooks/leaked-key.md)

---

## Useful Commands Reference

| Task | Command |
|------|---------|
| Run install wizard | cd cli && uv run e2eai |
| Start infrastructure | cd deploy/compose && docker compose up -d |
| Check service status | cd deploy/compose && docker compose ps |
| View service logs | docker compose logs service --tail=50 |
| Run database migrations | cd apps/api && uv run alembic upgrade head |
| Bootstrap admin account | cd apps/api && uv run e2eai-api bootstrap-admin |
| Bootstrap authorization | cd apps/api && uv run e2eai-api bootstrap-authz |
| Seed demo data | cd apps/api && uv run e2eai-api seed-demo |
| Validate config | cd apps/api && uv run e2eai-api check-config |
| Verify Phase 0 | cd apps/api && uv run e2eai-api verify-phase-0 |
| Run CLI tests | cd cli && uv run pytest -q |
| Run API tests | cd apps/api && uv run pytest -q |
| Deactivate user | cd apps/api && uv run e2eai-api deactivate-user target transfer admin |
| Index a document | cd apps/api && uv run e2eai-api index-document doc-uuid |
| Trash a document | cd apps/api && uv run e2eai-api trash-document doc-uuid actor-email |
| Restore from trash | cd apps/api && uv run e2eai-api restore-document doc-uuid actor-email |
| Purge a document | cd apps/api && uv run e2eai-api purge-document doc-uuid actor-email |
| Ingest a doc version | cd apps/api && uv run e2eai-api ingest-version version-uuid |
| Validate docs | python scripts/validate_docs.py |
"""

# ============================================================================
# Indonesian User Guide
# ============================================================================
ID_USER_GUIDE = """\
# Panduan Pengguna E2EAIDEV

Panduan ini menjelaskan tugas sehari-hari untuk pengguna bisnis dan pemilik pengetahuan di platform E2EAIDEV.

## Memulai

### Masuk (Login)

1. Buka aplikasi web E2EAIDEV di browser Anda.
2. Klik **Masuk** dan autentikasi melalui SSO organisasi Anda (Keycloak OIDC).
   - Jika SSO belum dikonfigurasi, gunakan kredensial akun lokal yang diberikan administrator.
3. Setelah login pertama, Anda akan melihat navigasi siklus hidup: **Plan > Data > Build > Test > Release > Operate > Improve**.

### Profil Anda

Setelah login, profil menampilkan nama, email, peran, tim, dan divisi Anda. Hubungi administrator untuk memperbaiki detail yang salah.

### Peran

| Peran | Kemampuan |
|-------|-----------|
| Pengguna Bisnis | Unggah, berbagi, dan tanya-jawab tentang dokumen |
| Pemilik Pengetahuan | Semua di atas ditambah kelola folder dan berbagi |
| AI Engineer | Konfigurasi model, prompt, retrieval, jalankan evaluasi |
| Evaluator | Tinjau jawaban AI, labeli gold set |
| Admin | Administrasi platform penuh |

---

## Unggah Dokumen

### Format yang Didukung

PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, dan file gambar (PNG, JPG, TIFF).

### Mengunggah File

1. Navigasi ke **Data > Dokumen**.
2. Klik **Unggah** atau seret file ke area unggah.
3. Batas: 100 MB per file, 50 file per batch, 20 GB penyimpanan per pengguna (default; admin dapat mengubah).
4. Setelah diunggah, dokumen diproses secara otomatis (parsing layout-aware dengan ekstraksi tabel, OCR untuk halaman pindai, pemotongan gambar). Indikator status akan tampil selama pemrosesan berlangsung.

### Versi Dokumen

Mengunggah ulang file dengan nama yang sama di folder yang sama membuat versi baru. AI selalu mengambil dari versi terbaru. Sitasi di percakapan lama tetap menunjuk ke versi yang dikutip saat itu.

### Tempat Sampah dan Penghapusan

- Menghapus dokumen memindahkannya ke **tempat sampah**. Dalam 5 menit, dokumen tersebut dikecualikan dari pencarian AI.
- Anda dapat memulihkan dari tempat sampah selama 30 hari.
- Setelah 30 hari (atau saat "hapus permanen"), file, chunk, dan embedding dihapus selamanya.

---

## Berbagi

### Cara Kerja Berbagi

E2EAIDEV menggunakan model berbagi ala Google Drive. Anda dapat berbagi dokumen atau folder dengan:

- **Pengguna** tertentu
- Sebuah **tim**
- Sebuah **peran** (misalnya, semua AI Engineer)
- Sebuah **divisi**
- **Seluruh organisasi**

### Berbagi Dokumen

1. Pilih dokumen dan klik **Berbagi**.
2. Pilih penerima (pengguna, tim, peran, divisi, atau organisasi).
3. Pilih tingkat izin: **Viewer** atau **Editor**.
4. Klik **Konfirmasi**.

Penerima akan mendapat notifikasi dalam aplikasi bahwa dokumen telah dibagikan kepada mereka.

### Berbagi Folder

Berbagi folder memberikan izin ke semua dokumen di dalamnya, termasuk dokumen yang ditambahkan kemudian (berbagi terwariskan).

### Mencabut Akses

1. Buka panel berbagi dokumen atau folder.
2. Hapus penerima atau ubah tingkat izin mereka.
3. Akses dicabut segera; query AI berikutnya tidak lagi menggunakan dokumen tersebut.

### Aturan Izin

- Izin diperiksa **di dalam** setiap query vektor, bukan setelah retrieval. Ini mencegah kebocoran informasi.
- Konten turunan (misalnya, jawaban yang di-cache) mewarisi izin paling ketat dari dokumen sumbernya.
- Label sensitivitas (Public / Internal / Confidential / Restricted) dapat membatasi siapa yang boleh menerima berbagi dokumen.

---

## Chat

### Mengajukan Pertanyaan

1. Navigasi ke **Chat**.
2. Ketik pertanyaan Anda dalam bahasa alami. Contoh: *"Berapa revenue share dalam kemitraan WhatsApp?"*
3. AI hanya mencari dokumen yang Anda punya akses, mengambil bagian yang relevan, dan menjawab dengan **sitasi**.

### Sitasi

Setiap jawaban menyertakan sitasi yang menampilkan:
- Nama dokumen sumber
- Nomor halaman dan bagian
- Tautan yang dapat diklik ke bagian sumber (di-highlight)

Jika jawaban menggunakan tabel atau gambar, sitasi menampilkan tabel atau potongan gambar tersebut.

### Riwayat Percakapan

- Riwayat chat Anda tersimpan dan dapat diakses dari sidebar.
- Setiap percakapan melacak konteks sehingga pertanyaan lanjutan berfungsi secara alami.
- Anda dapat memulai percakapan baru kapan saja.

### Umpan Balik

- Klik **jempol ke atas** atau **jempol ke bawah** pada setiap jawaban.
- Jawaban yang di-thumbs-down dapat mengalir ke dataset evaluasi untuk memperbaiki rilis mendatang.

### Apa yang Tidak Dapat Dilihat AI

- Dokumen yang tidak dibagikan dengan Anda tidak terlihat oleh AI, meskipun ada di sistem.
- Jika akses Anda ke dokumen dicabut, AI berhenti menggunakannya mulai dari query berikutnya.
- Sistem tidak pernah mengungkapkan keberadaan dokumen yang tidak dapat Anda akses (tidak ada kebocoran eksistensi).

---

## PII dan Pagar Keamanan

- Platform menjalankan deteksi prompt-injection pada setiap query. Prompt berbahaya diblokir dan dicatat.
- Redaksi PII dapat diaktifkan oleh administrator untuk melindungi data sensitif saat ingestion.

---

## Bot

Jika organisasi Anda telah menerbitkan bot (misalnya, bot kebijakan HR):

1. Buka **Chat > Bot** dan pilih bot yang Anda punya akses.
2. Setiap bot memiliki cakupan pengetahuan yang ditentukan (folder atau set dokumen tertentu).
3. **Akses efektif Anda = cakupan bot diinterseksikan dengan izin pribadi Anda.** Bot tidak pernah menampilkan dokumen yang seharusnya tidak dapat Anda lihat.

---

## Bantuan

- Hubungi administrator platform untuk masalah akun, permintaan akses, atau masalah teknis.
- Lihat **Panduan Admin & Operator** untuk detail operasional.
"""

# ============================================================================
# Indonesian Admin & Operator Guide
# ============================================================================
ID_ADMIN_GUIDE = """\
# Panduan Admin & Operator E2EAIDEV

Panduan ini mencakup instalasi, konfigurasi, operasi harian, dan pemeliharaan untuk administrator platform.

---

## Instalasi

### Prasyarat

| Komponen | Minimum |
|----------|---------|
| OS | Linux (Ubuntu 22.04+), Windows 11 dengan WSL2, macOS 13+ |
| Docker | Docker Desktop atau Docker Engine 24+ dengan Compose v2 |
| Python | 3.12 (dikelola via uv; jangan ubah Python sistem) |
| Node.js | 20+ (untuk frontend web) |
| RAM | Lite: 8 GB, Standard: 16 GB, Enterprise: 32 GB+ |
| Disk | Minimal 20 GB untuk image + model |

### Tier Instalasi

| Tier | Deskripsi | Komponen |
|------|-----------|----------|
| **Lite** | Satu mesin, sumber daya minimal | Postgres+pgvector, Valkey, OpenFGA, SeaweedFS, LiteLLM, Ollama (host) |
| **Standard** | Lab lengkap dengan GPU serving | Semua Lite + vLLM, TEI, Langfuse, Temporal |
| **Enterprise** | Multi-node, HA, SCIM | Semua Standard + clustering, SCIM sync, audit lanjutan |

### Langkah-Langkah Instalasi

1. **Clone repositori:**

        git clone https://github.com/rifqifurqan/E2EAIDEV.git
        cd E2EAIDEV

2. **Jalankan wizard instalasi:**

        cd cli && uv run e2eai

   Wizard akan:
   - Mendeteksi hardware Anda (CPU, RAM, GPU/VRAM, disk)
   - Merekomendasikan tier (Lite/Standard/Enterprise)
   - Memilih model untuk setiap peran (chat, embedding, reranker, judge, safety)
   - Memilih engine job (Celery default, atau Temporal untuk Standard+)
   - Menghasilkan deploy/compose/.env (secrets, gitignored) dan e2eai.yaml (konfigurasi)
   - Menarik container image yang sudah di-pin

   Gunakan --yes untuk menerima default, --force untuk menimpa .env yang ada (backup disimpan).

3. **Mulai infrastruktur:**

        cd deploy/compose && docker compose up -d

4. **Verifikasi layanan berjalan:**

        docker compose ps

   Yang diharapkan: postgres, valkey, openfga, seaweedfs, litellm semua menampilkan running atau healthy.

5. **Jalankan migrasi database:**

        cd apps/api && uv run alembic upgrade head

6. **Bootstrap akun admin:**

        cd apps/api && uv run e2eai-api bootstrap-admin

   Ini membuat akun admin darurat (break-glass). Password ditampilkan **sekali** -- simpan dengan aman.

7. **Bootstrap model otorisasi:**

        cd apps/api && uv run e2eai-api bootstrap-authz

8. **Seed data demo (opsional):**

        cd apps/api && uv run e2eai-api seed-demo

   Membuat organisasi demo dengan pengguna contoh (Andi/Sales, Budi/HR, Intern).

9. **Verifikasi stack Phase 0 lengkap:**

        cd apps/api && uv run e2eai-api verify-phase-0

   Ini menjalankan health check compose, tes CLI, tes API, migrasi Alembic, endpoint
   health/ready API, chat dan embedding LiteLLM, dan pemeriksaan model otorisasi OpenFGA.

### Tes Wizard

    cd cli && uv run pytest -q

### Tes API

    cd apps/api && uv run pytest -q

---

## Konfigurasi

### File Konfigurasi (e2eai.yaml)

Wizard menghasilkan e2eai.yaml di root repositori. File ini menangkap seluruh instalasi:
tier, komponen, model, dan kebijakan. Dapat di-version di git, di-diff, dan diterapkan ulang.

- Secret **direferensikan** (misalnya, env:POSTGRES_PASSWORD), tidak pernah disimpan di file konfigurasi.
- Konfigurasi invalid gagal saat startup dengan pesan error yang jelas.
- Validasi konfigurasi:

        cd apps/api && uv run e2eai-api check-config

### Variabel Environment (deploy/compose/.env)

Semua secret berada di deploy/compose/.env, yang di-gitignore. Wizard menghasilkan file ini.
Variabel kunci meliputi kredensial database, auth Valkey, preshared key OpenFGA, master key
LiteLLM, dan kunci S3 SeaweedFS.

Semua secret yang dihasilkan menggunakan [A-Za-z0-9._~-], minimal 16 karakter, aman untuk DSN
dan .env tanpa escaping.

### Konfigurasi Port

Port host default berada di rentang 1xxxx, terikat ke 127.0.0.1:

| Layanan | Port Default |
|---------|-------------|
| Postgres | 15432 |
| Valkey | 16379 |
| OpenFGA | 18080 |
| SeaweedFS | 18333 |
| LiteLLM | 14000 |
| Ollama (host) | 11434 |
| Keycloak | 18081 / 18082 |

Wizard melewatkan port yang sibuk secara otomatis. Port dapat diubah di .env.

### Konfigurasi Model

Model dipilih saat setup wizard. Setiap peran (chat, embedding, reranker, judge, safety)
dapat memiliki satu atau lebih model yang dikonfigurasi. Untuk mengubah model nanti:

1. Edit e2eai.yaml di bagian models.
2. Daftarkan atau perbarui model di LiteLLM melalui admin API atau konfigurasinya.
3. Verifikasi:

        cd apps/api && uv run e2eai-api verify-phase-0

### Kebijakan Egress Data

API model eksternal **dimatikan secara default**. Untuk mengaktifkan:

1. Atur pengaturan egress tingkat admin di konfigurasi.
2. Per label sensitivitas, pilih tujuan yang diizinkan (misalnya, konten Confidential/Restricted
   hanya dikirim ke model lokal).
3. Gateway LiteLLM menegakkan kebijakan; panggilan yang diblokir diaudit.

---

## Pencadangan

### Backup Database

    # Backup Postgres (jalankan dari host)
    docker compose -f deploy/compose/compose.yaml exec postgres \\
      pg_dump -U "$POSTGRES_USER" e2eai > backup.sql

    # Backup dengan kompresi
    docker compose -f deploy/compose/compose.yaml exec postgres \\
      pg_dump -U "$POSTGRES_USER" -Fc e2eai > backup.dump

### Backup Object Storage

Data SeaweedFS disimpan di Docker volume. Backup volume:

    docker volume ls | grep seaweed
    docker run --rm -v e2eaidev_seaweeddata:/data -v "$PWD":/backup alpine \\
      tar czf /backup/seaweedfs_backup.tar.gz /data

### Backup Valkey

    docker run --rm -v e2eaidev_valkeydata:/data -v "$PWD":/backup alpine \\
      tar czf /backup/valkey_backup.tar.gz /data

### Pemulihan

Lihat [Runbook: Pemulihan dari Backup](../runbooks/restore-from-backup.md).

---

## Pemantauan

### Endpoint Kesehatan

| Endpoint | Tujuan |
|----------|--------|
| GET /api/v1/health | Liveness aplikasi (mengembalikan status ok) |
| GET /api/v1/ready | Readiness aplikasi (memeriksa konektivitas database) |

### Kesehatan Docker Compose

    cd deploy/compose && docker compose ps

Semua layanan harus menampilkan running atau healthy. Jika ada layanan yang menampilkan
unhealthy atau restarting, periksa log:

    docker compose logs <nama-layanan> --tail=50

### Metrik Utama yang Dipantau

- **Postgres**: koneksi, replication lag, penggunaan disk
- **Valkey**: penggunaan memori, klien terhubung, eviction
- **LiteLLM**: latensi request, error rate, penggunaan token
- **SeaweedFS**: utilisasi penyimpanan, latensi baca/tulis
- **OpenFGA**: latensi pemeriksaan otorisasi

### Log Audit

Setiap login, unggah, berbagi, perubahan izin, query, panggilan tool, rilis, dan tindakan admin
dicatat di log audit. Log ini tamper-evident. Event audit disimpan di tabel audit_events di
Postgres.

---

## Manajemen Pengguna

### Model Organisasi

Platform menggunakan model hierarkis: **Organisasi > Divisi > Tim > Pengguna**, dengan peran.

### Membuat Pengguna

Pengguna disediakan melalui:

1. **SSO/OIDC** (Keycloak): pengguna dibuat saat login pertama.
2. **Perintah seed**: cd apps/api && uv run e2eai-api seed-demo (data demo).
3. **API**: POST /api/v1/auth/register (jika registrasi lokal diaktifkan).

### Peran

| Peran | Izin |
|-------|------|
| Admin | Akses platform penuh, manajemen pengguna, konfigurasi |
| AI Engineer | Konfigurasi model, evaluasi, manajemen bot |
| Evaluator | Tinjau jawaban, labeli dataset |
| Compliance | Akses log audit, klasifikasi risiko |
| Pengguna Bisnis | Unggah dokumen, berbagi, chat |

### Offboarding Pengguna

Ketika seorang karyawan meninggalkan organisasi:

**Via CLI:**

    cd apps/api && uv run e2eai-api deactivate-user <email_target> <email_penerima> <email_admin>

**Via API:**

    curl -X POST http://localhost:18000/api/v1/users/<user-id>/deactivate \\
      -H "Authorization: Bearer <admin-token>" \\
      -H "Content-Type: application/json" \\
      -d '{"transfer_to_id": "<manager-user-id>"}'

Proses offboarding:

1. Mengatur status pengguna ke **disabled** -- login dan sesi berhenti segera.
2. Mencabut semua sesi Valkey aktif (dalam 1 menit).
3. Mentransfer dokumen dan folder yang dimiliki ke penerima yang ditunjuk.
4. Berbagi yang ada ke pengguna lain tetap utuh.
5. Riwayat chat dipertahankan tetapi tidak dapat diakses oleh pengguna yang dinonaktifkan.
6. Semua tindakan diaudit.

---

## Lab Evaluasi

### Membuat Dataset Evaluasi

Mendukung generasi Q&A sintetis deterministik, adversarial, dan berbasis persona dari chunk
sumber. Gunakan endpoint POST /api/v1/evals/datasets.

### Menjalankan Evaluasi

Gunakan POST /api/v1/evals/runs dengan ID dataset dan adapter (misalnya, local_ragas). Hasil
mencakup metrik ternormalisasi, hasil per-item, dan perbandingan regresi antar run.

### Suite Uji Kebocoran Izin

Suite uji kebocoran izin bawaan memverifikasi bahwa dokumen terbatas tidak pernah muncul dalam
hasil retrieval yang tidak sah. Kegagalan kebocoran memblokir rilis.

---

## Manajemen Bot

### Membuat dan Merilis Bot

Bot adalah kontainer untuk konfigurasi AI berversi. Setiap rilis membuat bundle yang tidak
dapat diubah. Rollback mengalihkan pointer produksi ke bundle sebelumnya.

### Akses dan Cakupan Bot

- Berikan akses ke pengguna, tim, peran, atau divisi.
- Tetapkan cakupan pengetahuan (folder/dokumen terpilih).
- Retrieval efektif = cakupan bot diinterseksikan dengan izin pengguna.

---

## Runbook

Lihat [direktori runbook](../runbooks/) untuk prosedur respons insiden:

- [Layanan Down](../runbooks/service-down.md)
- [Pemulihan dari Backup](../runbooks/restore-from-backup.md)
- [Endpoint Model Gagal](../runbooks/model-endpoint-failing.md)
- [Vector Store Terdegradasi](../runbooks/vector-store-degraded.md)
- [Lag Sinkronisasi Izin](../runbooks/permission-sync-lag.md)
- [Disk Penuh](../runbooks/disk-full.md)
- [Kunci Bocor](../runbooks/leaked-key.md)

---

## Referensi Perintah

| Tugas | Perintah |
|-------|---------|
| Jalankan wizard instalasi | cd cli && uv run e2eai |
| Mulai infrastruktur | cd deploy/compose && docker compose up -d |
| Cek status layanan | cd deploy/compose && docker compose ps |
| Lihat log layanan | docker compose logs layanan --tail=50 |
| Jalankan migrasi database | cd apps/api && uv run alembic upgrade head |
| Bootstrap akun admin | cd apps/api && uv run e2eai-api bootstrap-admin |
| Bootstrap otorisasi | cd apps/api && uv run e2eai-api bootstrap-authz |
| Seed data demo | cd apps/api && uv run e2eai-api seed-demo |
| Validasi konfigurasi | cd apps/api && uv run e2eai-api check-config |
| Verifikasi Phase 0 | cd apps/api && uv run e2eai-api verify-phase-0 |
| Jalankan tes CLI | cd cli && uv run pytest -q |
| Jalankan tes API | cd apps/api && uv run pytest -q |
| Nonaktifkan pengguna | cd apps/api && uv run e2eai-api deactivate-user target penerima admin |
| Validasi dokumentasi | python scripts/validate_docs.py |
"""

# ============================================================================
# Runbooks
# ============================================================================

RUNBOOK_SERVICE_DOWN = """\
# Runbook: Service Down

## Symptoms

- docker compose ps shows one or more services as "exited", "unhealthy", or "restarting".
- API returns 503 or connection refused.
- Health endpoint GET /api/v1/health or GET /api/v1/ready fails.

## Diagnosis

1. Check which services are down:

        cd deploy/compose && docker compose ps

2. Check logs for the failing service:

        docker compose logs <service-name> --tail=100

3. Check system resources:

        docker stats --no-stream
        df -h

4. Check if ports are in use by another process:

        netstat -tlnp | grep <port>

## Fix

1. **Restart the failing service:**

        docker compose restart <service-name>

2. **If the service fails to start, check for resource issues:**
   - Out of memory: increase Docker memory limit in .wslconfig (Windows) or daemon.json (Linux).
   - Port conflict: stop the conflicting process or change the port in .env.
   - Disk full: see the [Disk Full runbook](disk-full.md).

3. **If the service depends on another (e.g., openfga depends on postgres):**

        docker compose up -d

   This restarts services in dependency order.

4. **For a full stack restart:**

        docker compose down && docker compose up -d

## Verification

1. Confirm all services are healthy:

        docker compose ps

2. Check application health:

        curl http://127.0.0.1:18000/api/v1/health
        curl http://127.0.0.1:18000/api/v1/ready

3. Run the Phase 0 verification:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If a service repeatedly crashes, check for data corruption in its volume.
- If postgres fails to start, check WAL corruption and consider restoring from backup.
- Collect logs and resource metrics before escalating to the platform owner.
"""

RUNBOOK_RESTORE_BACKUP = """\
# Runbook: Restore from Backup

## Symptoms

- Data loss detected (missing documents, corrupted database, accidental deletion).
- Database migration failed and rolled back.
- Disaster recovery scenario.

## Diagnosis

1. Confirm the scope of data loss:

        cd apps/api && uv run e2eai-api verify-phase-0

2. List available backups:

        ls -lt backup*.sql backup*.dump 2>/dev/null

3. Check database state:

        docker compose -f deploy/compose/compose.yaml exec postgres \\
          psql -U "$POSTGRES_USER" -d e2eai -c "SELECT count(*) FROM documents;"

## Fix

### Restoring the Postgres Database

1. **Stop the API to prevent writes:**

        # Stop the API process (if running natively)
        # or remove the API from compose

2. **Drop and recreate the database:**

        docker compose -f deploy/compose/compose.yaml exec postgres \\
          psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS e2eai;"
        docker compose -f deploy/compose/compose.yaml exec postgres \\
          psql -U "$POSTGRES_USER" -c "CREATE DATABASE e2eai;"

3. **Restore from the SQL backup:**

        cat backup.sql | docker compose -f deploy/compose/compose.yaml exec -T postgres \\
          psql -U "$POSTGRES_USER" -d e2eai

   Or from a compressed backup:

        docker compose -f deploy/compose/compose.yaml exec -T postgres \\
          pg_restore -U "$POSTGRES_USER" -d e2eai < backup.dump

4. **Re-run migrations to ensure schema is current:**

        cd apps/api && uv run alembic upgrade head

### Restoring SeaweedFS

1. Stop seaweedfs:

        docker compose stop seaweedfs

2. Restore the volume from backup:

        docker run --rm -v e2eaidev_seaweeddata:/data -v "$PWD":/backup alpine \\
          sh -c "rm -rf /data/* && tar xzf /backup/seaweedfs_backup.tar.gz -C /"

3. Restart:

        docker compose up -d seaweedfs

### Restoring Valkey

1. Stop valkey:

        docker compose stop valkey

2. Restore:

        docker run --rm -v e2eaidev_valkeydata:/data -v "$PWD":/backup alpine \\
          sh -c "rm -rf /data/* && tar xzf /backup/valkey_backup.tar.gz -C /"

3. Restart:

        docker compose up -d valkey

## Verification

1. Run the full verification suite:

        cd apps/api && uv run e2eai-api verify-phase-0

2. Check document counts and data integrity:

        docker compose -f deploy/compose/compose.yaml exec postgres \\
          psql -U "$POSTGRES_USER" -d e2eai -c "SELECT count(*) FROM documents;"

3. Test a sample chat query to confirm retrieval works.

## Escalation

- If the backup is corrupted or too old, contact the platform owner.
- Document the timeline and scope of data loss for the incident report.
- Consider implementing automated daily backups if not already in place.
"""

RUNBOOK_MODEL_ENDPOINT = """\
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

        curl http://127.0.0.1:14000/v1/chat/completions \\
          -H "Authorization: Bearer $LITELLM_MASTER_KEY" \\
          -H "Content-Type: application/json" \\
          -d '{"model": "<model-name>", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8}'

3. Test embedding:

        curl http://127.0.0.1:14000/v1/embeddings \\
          -H "Authorization: Bearer $LITELLM_MASTER_KEY" \\
          -H "Content-Type: application/json" \\
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
"""

RUNBOOK_VECTOR_STORE = """\
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

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"

3. Check chunk and embedding counts:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT count(*) FROM chunks; SELECT count(*) FROM chunk_embeddings;"

4. Check for index bloat or missing indexes:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) FROM pg_indexes WHERE tablename = 'chunk_embeddings';"

5. Check Postgres disk usage:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT pg_size_pretty(pg_database_size('e2eai'));"

6. Check Postgres logs for errors:

        docker compose logs postgres --tail=100

## Fix

1. **Missing embeddings for documents:** re-index the affected document:

        cd apps/api && uv run e2eai-api index-document <doc-uuid>

2. **Corrupted or stale index:** rebuild the HNSW index:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "REINDEX INDEX CONCURRENTLY <index-name>;"

3. **High latency due to table bloat:**

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "VACUUM ANALYZE chunk_embeddings;"

4. **Postgres out of shared memory:** increase shared_buffers or work_mem in the Postgres
   config (requires container restart).

5. **Embedding dimension mismatch** (model changed but old embeddings remain): re-index all
   documents with the new embedding model.

## Verification

1. Check embedding counts match expected documents:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT count(DISTINCT document_id) FROM chunks;"

2. Test a sample retrieval query through the API.

3. Run the Phase 0 verification:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If Postgres is consistently running out of memory, consider increasing the Docker memory limit.
- For large-scale re-indexing, plan for downtime and notify users.
- If switching vector stores (e.g., to Qdrant), follow the migration plan in the admin guide.
"""

RUNBOOK_PERMISSION_SYNC = """\
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

        curl http://127.0.0.1:18080/stores/<store-id>/read \\
          -H "Authorization: Bearer $OPENFGA_PRESHARED_KEY" \\
          -H "Content-Type: application/json" \\
          -d '{"tuple_key": {"user": "user:<user-id>", "relation": "viewer", "object": "document:<doc-id>"}}'

5. Check if the share operation completed in the database:

        docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT * FROM doc_principals WHERE document_id = '<doc-id>';"

6. Check if there is a Valkey cache entry for the user that has stale permissions:

        docker compose exec valkey valkey-cli -a "$VALKEY_PASSWORD" \\
          KEYS "session:*"

## Fix

1. **OpenFGA tuple was not written:** re-run the share operation through the API.

2. **Stale cache:** clear the user session cache in Valkey:

        docker compose exec valkey valkey-cli -a "$VALKEY_PASSWORD" \\
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
"""

RUNBOOK_DISK_FULL = """\
# Runbook: Disk Full

## Symptoms

- Docker containers fail to start or crash with write errors.
- Postgres logs show "No space left on device".
- File uploads fail.
- docker system df shows high disk usage.

## Diagnosis

1. Check host disk usage:

        df -h

2. Check Docker disk usage:

        docker system df

3. Check individual volume sizes:

        docker system df -v | head -40

4. Check Postgres database size:

        docker compose -f deploy/compose/compose.yaml exec postgres \\
          psql -U "$POSTGRES_USER" -d e2eai -c "SELECT pg_size_pretty(pg_database_size('e2eai'));"

5. Identify largest tables:

        docker compose -f deploy/compose/compose.yaml exec postgres \\
          psql -U "$POSTGRES_USER" -d e2eai \\
          -c "SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) \\
              FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"

## Fix

1. **Clean up Docker:**

        # Remove unused images, containers, and build cache
        docker system prune -f

        # Remove dangling volumes (be careful -- this removes ALL unused volumes)
        docker volume prune -f

2. **Clean up Postgres:**
   - Vacuum to reclaim space:

            docker compose exec postgres psql -U "$POSTGRES_USER" -d e2eai \\
              -c "VACUUM FULL;"

   - Purge trashed documents past retention:

            cd apps/api && uv run e2eai-api purge-document <doc-uuid> <admin-email>

3. **Clean up old model files (Ollama):**

        ollama list
        ollama rm <unused-model>

4. **Clean up old backups:**

        ls -lt backup*.sql backup*.dump
        # Remove old backups after confirming a recent one exists

5. **Expand disk (if possible):** increase the Docker volume size or move Docker data
   to a larger disk.

## Verification

1. Confirm disk space recovered:

        df -h
        docker system df

2. Restart any services that crashed:

        cd deploy/compose && docker compose up -d

3. Verify system health:

        cd apps/api && uv run e2eai-api verify-phase-0

## Escalation

- If disk is consistently full, plan for capacity expansion.
- Consider setting up monitoring alerts for disk usage above 80%.
- Review data retention policies and automate old backup cleanup.
"""

RUNBOOK_LEAKED_KEY = """\
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
"""


def main():
    print("Generating P0 documentation (FR-F22, FR-F14, FR-O13)...")

    _write("en/user-guide.md", EN_USER_GUIDE)
    _write("en/admin-operator-guide.md", EN_ADMIN_GUIDE)
    _write("id/panduan-pengguna.md", ID_USER_GUIDE)
    _write("id/panduan-admin-operator.md", ID_ADMIN_GUIDE)

    _write("runbooks/service-down.md", RUNBOOK_SERVICE_DOWN)
    _write("runbooks/restore-from-backup.md", RUNBOOK_RESTORE_BACKUP)
    _write("runbooks/model-endpoint-failing.md", RUNBOOK_MODEL_ENDPOINT)
    _write("runbooks/vector-store-degraded.md", RUNBOOK_VECTOR_STORE)
    _write("runbooks/permission-sync-lag.md", RUNBOOK_PERMISSION_SYNC)
    _write("runbooks/disk-full.md", RUNBOOK_DISK_FULL)
    _write("runbooks/leaked-key.md", RUNBOOK_LEAKED_KEY)

    print("Done. Run: python scripts/validate_docs.py")


if __name__ == "__main__":
    main()
