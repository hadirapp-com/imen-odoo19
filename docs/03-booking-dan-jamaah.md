# 03 — Booking & Jamaah

## Alur Membuat Booking

Booking **tidak dibuat otomatis** saat SO dikonfirmasi — selalu lewat wizard agar
ada validasi manusia:

```
Sales > Quotations → buat SO (pilih Paket Umroh, qty = jumlah pax)
   → Confirm
   → tombol "Create Umrah Booking"
   → Wizard: Customer · Package · Departure Date · Return Date ·
             Create Project (✓) · daftar Jamaah (otomatis sebanyak qty)
   → Create Booking
```

Hasil wizard:

1. Booking bernomor `UMR/<tahun-keberangkatan>/00001`.
2. Terhubung ke SO, customer, dan paket.
3. Checklist dokumen otomatis dibuat untuk setiap jamaah.
4. Project + 9 task operasional dibuat saat **Confirm** booking.
5. SO mendapat catatan di chatter + smart button ke booking.

## State Machine Booking

| State | Arti | Tombol di Form |
|---|---|---|
| `draft` | Baru dibuat | **Confirm** |
| `confirmed` | Disetujui, task & checklist siap | **Start Documents** |
| `document` | Pengumpulan dokumen berjalan | **Start Verification** |
| `verification` | Pemeriksaan dokumen | **Ready for Visa** |
| `visa` | Proses visa | **Set Ready** (gate ketat, lihat bawah) |
| `ready` | Siap berangkat | **Departed** |
| `departed` | Sudah berangkat | **Returned** |
| `returned` | Sudah pulang | **Complete** |
| `completed` | Selesai | — |
| `cancelled` | Batal | **Reset to Draft** |

Aturan penting:

- **Confirm** menolak bila jamaah kosong atau tanggal departure di masa lalu.
- **Set Ready** hanya lolos jika (a) semua dokumen *required* sudah *verified*,
  (b) semua visa sudah *approved* — pesan error menyebut nama jamaah yang
  tertahan.
- Batal dilarang pada `completed`; hanya `draft`/`cancelled` yang bisa dihapus.
- Mengubah tanggal departure/return akan **menggeser otomatis** deadline task
  yang masih terbuka.

## Smart Buttons di Form Booking

Sales Order · Pilgrims (jumlah jamaah) · Documents · Visas · Manasik ·
Open Tasks · Notifications · Invoiced · Paid · Project.

## Tab di Form Booking

General · Jamaah · Documents · Payment · Visa · Manasik · Flight · Operation · Notes.

## Mengelola Jamaah

- Tambah langsung di tab **Jamaah** (inline) atau wizard saat create.
- Setiap jamaah **otomatis mendapat kontak (`res.partner`)** — ini dasar akses
  portal nanti.
- **NIK unik per booking** (validasi sistem).
- Field passport: nama sesuai paspor, nomor, tanggal terbit/kedaluwarsa, tempat
  terbit. Status paspor dihitung otomatis:
  - `Expired` — sudah lewat tanggal kedaluwarsa;
  - `Expiring Soon` — akan kedaluwarsa dalam **6 bulan sejak tanggal pulang**
    (aturan Arab Saudi);
  - `Valid` — aman.
- NIK dan sebagian data sensitif hanya terlihat grup *Travel / Admin* dan
  *Travel / Visa Officer* (🔒).
