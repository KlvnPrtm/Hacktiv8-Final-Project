# Catatan implementasi

Rencana acuan: Teman Data yang disetujui di percakapan pada 27 September 2026.

- Backend: Flask + google-genai, state di browser, enam pasangan konteks terakhir.
- UI: frontend custom, lokal, terang, satu sesi tanpa database.
- Validasi: unit/integration test memakai provider mock, browser checks, screenshot berlabel mock.
- Gemini nyata: belum diverifikasi sampai API key tersedia.

Keputusan implementasi: Markdown dirender dan disanitasi di backend menggunakan Markdown + Bleach agar tidak memerlukan vendor JavaScript eksternal. HTML hasil sanitasi dan teks asli dikirim bersama.

Workspace ini belum memiliki repository Git. Pengerjaan langsung di folder Output/teman-data yang ditentukan pengguna; tidak membuat worktree, commit, atau publikasi repo.

Hasil akhir:

- Backend: 33 tes lulus, termasuk SDK asli dengan HTTP MockTransport (offline).
- Browser: 11 kelompok pengujian lulus; desktop/mobile, retry/edit, reset, history, clipboard, sanitasi, dan keyboard.
- Visual: empat screenshot berlabel mock diperiksa; tidak ada horizontal overflow di viewport 375/768/1024/1440 px.
- Review backend dan frontend terpisah menemukan satu label aksesibilitas yang belum menunjuk judul; regression test dibuat gagal, ID judul diperbaiki, lalu seluruh suite dijalankan kembali.
- Dependency check dan JavaScript syntax check lulus. Dependency langsung serta snapshot transitif dipin.
- API key belum tersedia, sehingga smoke test Gemini nyata belum dilakukan.
- `.env` kosong disediakan; tidak ada key yang dipublikasi. GitHub/deployment tidak dilakukan.
