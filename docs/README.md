# Dokumentasi Fungsional — Modul `hadir_umrah`

Dokumentasi fungsional **Vertical Solution Odoo untuk bisnis Travel Umroh (HadirApp)**
pada Odoo 19 Community. Modul: `hadir_umrah` versi **19.0.4.0.0**.

> Dokumen ini ditulis dari sudut pandang pengguna/operasional (bukan source code).
> Untuk arsitektur teknis & kode, lihat folder `addons/hadir_umrah/`.

## Daftar Dokumen

| No | File | Isi |
|----|------|-----|
| 01 | [Ikhtisar Sistem](01-ikhtisar-sistem.md) | Gambaran umum, alur bisnis utama, apa yang standard vs custom |
| 02 | [Instalasi & Konfigurasi](02-instalasi-konfigurasi.md) | Cara install/upgrade, checklist konfigurasi pertama |
| 03 | [Booking & Jamaah](03-booking-dan-jamaah.md) | Alur SO → Booking → Jamaah, state machine, wizard |
| 04 | [Dokumen](04-dokumen.md) | Tipe dokumen, template per paket, checklist & verifikasi |
| 05 | [Operasional Keberangkatan](05-operasional-keberangkatan.md) | Visa, Manasik, Flight, Meeting Point |
| 06 | [Pembayaran](06-pembayaran.md) | Status pembayaran, invoice & payment standard Odoo |
| 07 | [Task Operasional](07-task-operasional.md) | Katalog task per booking, deadline H-x otomatis |
| 08 | [Dashboard & Reminder](08-dashboard-dan-reminder.md) | Dashboard "Needs Attention", activity otomatis harian |
| 09 | [Portal Jamaah](09-portal-jamaah.md) | My Umrah: upload dokumen, payment, manasik, flight |
| 10 | [Notifikasi WhatsApp](10-notifikasi-whatsapp.md) | Antrian notifikasi, template, provider, monitoring |
| 11 | [Hak Akses & Keamanan](11-hak-akses-keamanan.md) | Grup pengguna, matriks akses, isolasi data jamaah |
| 12 | [Skenario Pengujian](12-skenario-pengujian.md) | Master UAT + tabel uji per phase |
| 13 | [Troubleshooting](13-troubleshooting.md) | Masalah umum, log, resep perbaikan |

## Quick Start (5 Menit)

1. Pastikan stack Docker jalan (`docker compose up -d`), buka `http://localhost:10019`.
2. Install/upgrade modul — lihat [Instalasi & Konfigurasi](02-instalasi-konfigurasi.md).
3. Buat **Paket Umroh** (produk): centang *Is Umrah Package*, pilih *Document Template*.
4. Buat **Penawaran/SO** untuk customer → **Confirm** → klik **Create Umrah Booking**.
5. Isi tanggal + daftar jamaah di wizard → **Create Booking**.
6. Kerjakan operasional harian dari **Travel → Dashboard** (semua booking yang butuh
   perhatian tampil di filter *Needs Attention*).

## Konvensi

- **Booking** = pemesanan group umroh (objek sentral, nomor `UMR/2027/00001`).
- **Jamaah** = satu orang peziarah dalam sebuah booking.
- Ikon 🔒 pada dokumen lain berarti field/fitur dibatasi grup tertentu.
