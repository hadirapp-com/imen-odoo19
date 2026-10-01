# 08 — Dashboard & Reminder

## Dashboard Operasional

Menu **Travel → Dashboard** menampilkan booking **yang butuh tindakan** — filter
default **Needs Attention** menyatukan 4 pengecualian:

| Filter | Booking yang tampil |
|---|---|
| Documents Incomplete | progress dokumen < 100% |
| Payment Overdue | status `Overdue` |
| Visa In Progress | visa berjalan / ditolak / expired |
| Passport Expiry Risk | ada jamaah berpaspor *expiring/expired* |
| Departure Next 30 Days | keberangkatan ≤30 hari |
| Upcoming Manasik | ada sesi manasik mendatang |

Hapus filter *Needs Attention* untuk melihat semua booking. Tampilan kanban
dikelompokkan per state; badge payment & visa terlihat di kartu.

## Activity Otomatis (Internal — untuk staf)

Cron harian membuat **Activity (To-do)** di form booking — dedup: tidak
diduplikasi selama activity serupa masih terbuka:

| Activity | Kondisi |
|---|---|
| Passport expiry risk | jamaah berpaspor kedaluwarsa / ≤6 bulan sejak return |
| Missing documents | dokumen required belum lengkap, departure ≤30 hari |
| Ready for visa | semua dokumen verified, state `verification` |
| Payment overdue | invoice telat bayar |
| Departure H-7 checklist | ringkasan dok/visa/task terbuka |
| Departure tomorrow – final checklist | H-1 |
| Visa expired | visa approved lewat tanggal kedaluwarsa |

Buka via ikon jam ⏱ pada chatter booking, atau menu activity pada list booking.

## Reminder WhatsApp (Eksternal — untuk jamaah/customer)

Terpisah dari activity; dikelola antrian notifikasi —
lihat [Notifikasi WhatsApp](10-notifikasi-whatsapp.md).
