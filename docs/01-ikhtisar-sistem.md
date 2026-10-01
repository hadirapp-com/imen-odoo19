# 01 — Ikhtisar Sistem

## Apa yang Dikerjakan Modul Ini

`hadir_umrah` mengelola proses bisnis travel umroh dari penjualan sampai selesai
keberangkatan, dengan **Umrah Booking sebagai objek sentral**:

```
Product Paket Umroh  (katalog, dijual berulang kali)
        │
   Sales Order  (1 SO boleh banyak pax / satu keluarga)
        │  tombol "Create Umrah Booking"
        ▼
   Umrah Booking  UMR/2027/00001  ◄── objek sentral
        │
        ├── Jamaah           (data perorangan + passport + NIK)
        ├── Document Checklist (per jamaah, otomatis dari template paket)
        ├── Visa             (per jamaah, snapshot paspor)
        ├── Manasik          (sesi + daftar hadir)
        ├── Payment Status   (dihitung dari invoice/payment standard)
        └── Tasks/Activities (operasional per booking + reminder otomatis)
```

## Prinsip Desain

| Prinsip | Implementasi |
|---|---|
| Maksimalkan Odoo standard | Customer, SO, Invoice, Payment, Project/Task, Calendar, Activity, Portal, Chatter — semua memakai aplikasi standard Odoo |
| Tidak ada accounting sendiri | Semua angka pembayaran **dihitung** dari `sale.order` + `account.move` standard |
| Product ≠ Project | Paket umroh adalah produk biasa; Project dibuat **per booking** untuk workflow operasional |
| Skalabilitas | Task operasional dibuat **per booking** (bukan per jamaah). 300 jamaah → ±9 task + checklist dokumen per jamaah |
| Tanpa Odoo Enterprise | Hanya Community: `sale_management`, `account`, `project`, `calendar`, `portal` |

## Aplikasi yang Terlibat

- **Travel** — menu utama modul (Dashboard, Booking, Jamaah, Operation, Sales, Configuration).
- **Sales** — quotation/SO paket umroh.
- **Accounting** — invoice & payment (standard).
- **Project** — task operasional per booking.
- **Calendar** — sesi manasik bisa dijadwalkan ke kalender.
- **Settings > Companies** — konfigurasi provider WhatsApp.

## Versi & Ketergantungan

| Item | Nilai |
|---|---|
| Modul | `hadir_umrah` 19.0.4.0.0 (Application) |
| Odoo | 19.0 Community |
| Depends | `sale_management`, `account`, `project`, `calendar`, `portal` |
| Multi-company | Didukung (record rule semua model utama) |

## Fasilitas yang Tidak Dibuat Sengaja

- **Model Hotel** — belum masuk scope 4 phase (ditandai untuk pengembangan berikutnya).
- **WhatsApp nyata** — arsitektur & antrian siap; aktivasi menunggu kredensial
  gateway (lihat [Notifikasi WhatsApp](10-notifikasi-whatsapp.md)).
- **Menu alias Finance di bawah Travel** — invoice/payment diakses via aplikasi
  Accounting standard + smart button di booking.
