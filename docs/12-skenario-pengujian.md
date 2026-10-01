# 12 — Skenario Pengujian

## Master UAT End-to-End (alur utama bisnis)

| # | Skenario | Action | Expected Result | Status |
|---|---|---|---|---|
| 1 | Paket umroh | Buat produk, centang *Is Umrah Package*, pilih template dok | Muncul di Travel → Configuration → Umrah Package | ☐ |
| 2 | Customer | Buat kontak customer | Terbentuk `res.partner` | ☐ |
| 3 | Sales Order | SO 1 paket qty 3 | SO quotation | ☐ |
| 4 | Confirm SO | Klik Confirm | Status *Sales Order*; tombol *Create Umrah Booking* aktif | ☐ |
| 5 | Wizard booking | Isi tanggal + 3 jamaah → Create | Booking `UMR/<tahun>/00001`, terhubung SO, checklist 15 dokumen (3 jamaah × 5) | ☐ |
| 6 | Tambah jamaah | Tambah 1 jamaah di draft | Checklist jamaah baru otomatis | ☐ |
| 7 | Confirm booking | Klik Confirm | Project + 9 task terbentuk, deadline sesuai H-offset | ☐ |
| 8 | Upload & verify dok | Upload paspor (backend/portal) → Submit → Verify | Status verified, tercatat verifikator & tanggal | ☐ |
| 9 | Gate dokumen | Set Ready saat ada dok belum verified | Ditolak dengan daftar dokumen | ☐ |
| 10 | Invoice & payment | Create Invoice dari SO → Register Payment parsial | Booking: Partial, Paid/Due ter-update | ☐ |
| 11 | Overdue | Jadikan invoice telat | Status `Overdue` + activity + muncul di dashboard | ☐ |
| 12 | Visa | Generate Visas → Submit → Process → Approve | Tanggal tercatat, notifikasi Visa Update masuk antrian | ☐ |
| 13 | Gate visa | Set Ready saat ada visa belum approved | Ditolak menyebut nama jamaah | ☐ |
| 14 | Manasik | Buat sesi, Fill Attendees, Mark All Present, Schedule to Calendar | Attendance & event kalender terbentuk | ☐ |
| 15 | Flight & meeting point | Isi flight + meeting point | Tampil di portal jamaah | ☐ |
| 16 | Dashboard | Buka Travel → Dashboard | Hanya booking *Needs Attention* tampil | ☐ |
| 17 | Security & portal | Login portal jamaah A | Hanya data miliknya; NIK tidak ada di respons | ☐ |

## Uji Phase 2 — Operation

| Test ID | Skenario | Expected Result | Status |
|---|---|---|---|
| P2-01 | Generate visa | 1 visa draft/jamaah, paspor ter-snapshot | ☐ |
| P2-02 | Alur visa | Submit→Process→Approve, tanggal otomatis | ☐ |
| P2-03 | Gate ready (visa) | Ditolak, sebut jamaah pending | ☐ |
| P2-04 | Task generation | Confirm → project + 9 task H-90…Return+3 | ☐ |
| P2-05 | Reschedule task | Ubah tanggal → deadline terbuka bergeser | ☐ |
| P2-06 | Manasik | Fill attendees = jml jamaah; mark present terhitung | ☐ |
| P2-07 | Kalender | Schedule to Calendar membuat event berpeserta | ☐ |
| P2-08 | Dashboard | Filter Needs Attention akurat | ☐ |
| P2-09 | Cron visa expired | Approved lewat expiry → expired + activity | ☐ |
| P2-10 | Security finance | Passport tersembunyi, read-only | ☐ |

## Uji Phase 3 — Portal

| Test ID | Skenario | Expected Result | Status |
|---|---|---|---|
| P3-01 | Grant akses | Email undangan portal terkirim dari kontak jamaah | ☐ |
| P3-02 | Login portal | Kartu My Umrah tampil di /my | ☐ |
| P3-03 | Halaman MY UMRAH | Paket, tanggal, progress, badge | ☐ |
| P3-04 | Isolasi dokumen | Hanya dokumen milik sendiri | ☐ |
| P3-05 | Upload | File tersimpan, status → Submitted, alert sukses | ☐ |
| P3-06 | Re-upload ditolak | Dok verified tidak punya form upload | ☐ |
| P3-07 | Verifikasi staf | Hasil upload terverifikasi di backend | ☐ |
| P3-08 | Payment | Total/Paid/Outstanding sesuai | ☐ |
| P3-09 | Manasik | Jadwal + kehadiran pribadi | ☐ |
| P3-10 | Flight & meeting point | Tampil sesuai backend | ☐ |
| P3-11 | Isolasi antar booking | URL booking lain → redirect | ☐ |
| P3-12 | NIK | Tidak ada NIK di payload portal | ☐ |

## Uji Phase 4 — Automation

| Test ID | Skenario | Expected Result | Status |
|---|---|---|---|
| P4-01 | Template ter-install | 6 template default muncul & editable | ☐ |
| P4-02 | Queue dokumen | 1 notif/jamaah, phone 628xxx, body ter-render | ☐ |
| P4-03 | Dedup | Cron ulang hari sama → tidak duplikat | ☐ |
| P4-04 | Payment reminder | Notif ke customer, sisa tagihan benar | ☐ |
| P4-05 | Manasik reminder | Notif semua jamaah, jam 09:00 - 11:30 | ☐ |
| P4-06 | H-7 / H-1 | Notif per jamaah, H-1 berisi meeting point | ☐ |
| P4-07 | Visa update | Approve → antrian otomatis | ☐ |
| P4-08 | Kirim (log) | Status sent, body di log server | ☐ |
| P4-09 | Failed & retry | Tanpa nomor → failed; isi nomor → Re-queue → sent | ☐ |
| P4-10 | Provider http | POST ke gateway, error API tercatat | ☐ |
| P4-11 | Cancel | Queued → cancelled, tak ikut cron | ☐ |
| P4-12 | Security | Portal/user biasa tak bisa akses antrian & token | ☐ |
