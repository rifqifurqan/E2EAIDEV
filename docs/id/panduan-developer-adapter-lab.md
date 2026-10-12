# Panduan Developer Adapter Lab

Requirement: FR-F22. Panduan ini menjelaskan cara menambah adapter tool Lab tanpa mencampur dependensi tool ke environment API platform.

## Ruang Lingkup

Adapter Lab membuat E2EAIDEV dapat membandingkan tool di seluruh lifecycle: evaluasi, retrieval, serving, red-team testing, pemahaman dokumen, dan stage berikutnya. Setiap adapter menormalkan tool ke kontrak yang sama agar laporan perbandingan dapat direproduksi.

## Aturan Arsitektur

- Setiap tool Lab berjalan di container sendiri. Jangan memasang Ragas, DeepEval, promptfoo, garak, Phoenix, atau dependency tool lain ke `apps/api`.
- API berbicara dengan adapter melalui boundary HTTP/kontrak yang sempit dan hanya menyimpan hasil yang sudah dinormalisasi.
- Output adapter harus aman disimpan: tidak ada secret mentah, bearer token, API key, password, kredensial provider, atau payload dokumen tidak terbatas.
- Panggilan model dan judge dari adapter melewati gateway key yang dikonfigurasi untuk run supaya biaya dan budget dapat dilacak.

## Kontrak Adapter

Setiap adapter menyediakan endpoint HTTP berikut:

### GET /info

Mengembalikan metadata statis:

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

Mengembalikan status liveness/readiness container adapter:

```json
{"healthy": true, "version": "0.1.0", "detail": "ready"}
```

### POST /run

Menjalankan satu operasi ternormalisasi di atas input yang tetap:

```json
{
  "run_id": "uuidv7-atau-test-id",
  "operation": "faithfulness",
  "inputs": [{"item_id": "1", "question": "...", "answer": "..."}],
  "config": {"temperature": 0, "seed": 7},
  "judge": {"base_url": "http://litellm:4000/v1", "model": "chosen-judge"}
}
```

Bentuk respons:

```json
{
  "results": [
    {"item_id": "1", "metric": "faithfulness", "score": 0.92, "details": {}, "judge_prompt": "prompt-ref-atau-template-teredaksi"}
  ]
}
```

Jangan mengembalikan kredensial provider, API key tool, atau dokumen rahasia penuh di `details`.

## Boundary Python di Platform

Kontrak in-process platform berada di `apps/api/src/e2eai/tool_adapter.py`:

- `ToolAdapter` protocol: `name`, `version`, `capabilities`, `health()`, `configure()`, dan async `run()`.
- `ToolCapabilities`: metadata read-only/cancel/resume/maksimum input/streaming.
- `AdapterHealth`: snapshot health.
- `ToolAdapterRegistry`: registrasi dan lookup.
- `check_adapter_contract` dan `check_registry_contract`: pemeriksaan kontrak yang digunakan test.

Gunakan protocol ini untuk adapter lokal/deterministik dan test double di sekitar container HTTP.

## Contract Tests

Tambah atau perluas test di `apps/api/tests/` untuk setiap adapter. Pemeriksaan minimum:

1. Metadata `GET /info` memiliki name, version, stage, license, dan operations.
2. `GET /health` mengembalikan respons sehat dengan version yang sama seperti `/info`.
3. `POST /run` mengembalikan baris ternormalisasi deterministik untuk fixture kecil.
4. Output tidak berisi secret atau kredensial mentah.
5. Adapter menangani input kosong secara aman.
6. Container adapter dapat berjalan tanpa memutasi state platform.

Perintah test fokus:

```bash
cd apps/api && uv run pytest -q tests/test_us_tool_adapter_p1.py
```

## Checklist Implementasi

- [ ] Buat folder adapter di `adapters/<stage>/<tool>/`.
- [ ] Pin image container atau versi package; jangan gunakan tag floating `latest`.
- [ ] Implementasikan `GET /info`, `GET /health`, dan `POST /run`.
- [ ] Tambahkan fixture deterministik dan contract tests.
- [ ] Pastikan semua output ternormalisasi dan aman dari secret.
- [ ] Update tool catalog dan dokumentasi stage terkait.
- [ ] Jalankan test adapter fokus plus test Lab terdekat.

## No Secrets

Jangan pernah menyimpan atau mencetak password generated, API key, bearer token, OAuth token, LiteLLM master key, DSN database dengan password, atau kredensial provider eksternal mentah. Gunakan referensi environment dan redaksi log yang terlihat manusia sebagai `[REDACTED]`.
