# 07 — Task Operasional

## Konsep Skalabilitas

Task dibuat **per booking, bukan per jamaah** — satu group umroh menghasilkan
±9 task, bukan 300×10. Checklist personal ditangani fitur Dokumen; pengingat
individual memakai Activity/WhatsApp.

## Katalog Task (Configuration → Task Template)

Dibuat otomatis saat instalasi; boleh diedit/dinonaktifkan (*Active* = false).

| Task | Deadline | Keterangan |
|---|---|---|
| Payment Follow Up | H-90 | tidak wajib |
| Passport Collection | H-60 | |
| Document Verification | H-45 | |
| Visa Processing | H-30 | |
| Ticket Confirmation | H-14 | |
| Hotel Confirmation | H-10 | |
| Manasik Session | H-7 | |
| Departure Preparation | H-7 | |
| Post Trip Follow Up | **Return +3** | setelah kepulangan |

- **Anchor** menentukan basis: *Before Departure* (H-offset) atau
  *After Return* (return + offset).
- *Responsible* kosong = task mengikuti koordinator booking.
- *Required* dipakai untuk validasi keberangkatan (phase berikutnya).

## Kapan Task Dibuat

- Saat booking **Confirm** — otomatis (project dibuat dulu bila belum ada).
- Tombol **Generate / Update Tasks** pada tab Operation — menambahkan task untuk
  katalog yang baru dibuat (yang sudah ada tidak diduplikasi).
- **Ubah tanggal booking → deadline semua task terbuka ikut bergeser** otomatis.

## Membuka Task

- Tab **Operation** di form booking (daftar + stage).
- Smart button *Open Tasks*.
- Menu Travel → Operation → Tasks (dikelompokkan per booking).
- Task tampil juga di aplikasi Project standard (project per booking).
