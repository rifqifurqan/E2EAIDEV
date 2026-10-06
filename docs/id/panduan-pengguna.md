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
