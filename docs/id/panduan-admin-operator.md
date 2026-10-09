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
    docker compose -f deploy/compose/compose.yaml exec postgres \
      pg_dump -U "$POSTGRES_USER" e2eai > backup.sql

    # Backup dengan kompresi
    docker compose -f deploy/compose/compose.yaml exec postgres \
      pg_dump -U "$POSTGRES_USER" -Fc e2eai > backup.dump

### Backup Object Storage

Data SeaweedFS disimpan di Docker volume. Backup volume:

    docker volume ls | grep seaweed
    docker run --rm -v e2eaidev_seaweeddata:/data -v "$PWD":/backup alpine \
      tar czf /backup/seaweedfs_backup.tar.gz /data

### Backup Valkey

    docker run --rm -v e2eaidev_valkeydata:/data -v "$PWD":/backup alpine \
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

    curl -X POST http://localhost:18000/api/v1/users/<user-id>/deactivate \
      -H "Authorization: Bearer <admin-token>" \
      -H "Content-Type: application/json" \
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

### Registri Prompt

Prompt dikelola sebagai versi yang tidak dapat diubah sebelum dipakai oleh bundle bot. Gunakan API
registri prompt untuk membuat prompt, menambah versi baru, memindahkan label `staging` atau
`production` ke suatu versi, membandingkan dua versi dengan unified diff, dan merender preview
playground lokal memakai placeholder `{{ variable }}`. Preview playground berjalan offline dan tidak
memanggil LLM; placeholder yang hilang atau tidak aman akan ditolak.

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
