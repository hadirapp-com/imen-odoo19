# 11 — Hak Akses & Keamanan

## Grup Pengguna (Settings > Users)

| Grup | Fungsi |
|---|---|
| **Travel / Admin** | Operasional penuh: booking, jamaah, dokumen, manasik, task, flight, notifikasi |
| **Travel / Finance** | Read-only data operasional; hak invoice/payment dari grup Accounting standard |
| **Travel / Visa Officer** | Kelola dokumen & visa; read-only booking/jamaah |
| **Travel / Manager** | Gabungan ketiganya (implied) |
| **Portal User** | Hanya data miliknya via portal (lihat [Portal](09-portal-jamaah.md)) |

## Matriks Akses

| Model | Admin | Finance | Visa Officer | Portal |
|---|---|---|---|---|
| umrah.booking | CRUD | R | R | R (miliknya) |
| umrah.pilgrim | CRUD | R | R | R (dirinya) |
| umrah.document | CRUD | R | CRUD | R (miliknya; upload via portal controller) |
| umrah.document.type / template | CRUD | R | R | — |
| umrah.visa | CRUD | R | CRUD | R (miliknya) |
| umrah.manasik (+attendance) | CRUD | R | R (attendance R) | R (sesi booking; attendance dirinya) |
| umrah.task.type | CRUD | — | — | — |
| umrah.flight | CRUD | R | — | R (booking-nya) |
| umrah.notification | CRU (tanpa delete) | R | R | — |
| umrah.notification.template | CRUD | — | — | — |
| project.task operasional | via grup Project standard | | | — |

## Perlindungan Data Sensitif

- **NIK** dan **nomor paspor pada visa** — hanya grup *Travel / Admin* dan
  *Travel / Visa Officer* (pembatasan di level field, termasuk view).
- **NIK tidak pernah tampil di portal**.
- **Token WhatsApp API** — hanya grup *System*; dibaca sistem saat pengiriman.
- Attachments dokumen jamaah diunduh via tautan bertoken per-file.

## Record Rules

- **Multi-company** — semua model utama difilter per perusahaan.
- **Portal (7 rules)** — booking via jamaah-terkait-kontak; dokumen/visa/
  attendance via jamaah sendiri; manasik/flight via booking miliknya.
  Membuka record milik jamaah lain menghasilkan kosong/redirect, bukan data.

## Catatan Keamanan untuk Admin

- Jangan menambahkan *Portal User* ke grup internal.
- `sudo()` di kode hanya pada 2 titik terkontrol & terdokumentasi (upload
  portal setelah cek kepemilikan; baca kredensial saat kirim).
- Semua aksi penting ber-tracking ke chatter (state, tanggal, paspor, dll).
