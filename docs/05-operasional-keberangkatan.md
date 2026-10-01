# 05 — Operasional Keberangkatan (Visa, Manasik, Flight)

## Visa

Satu record visa **per jamaah per booking** (sistem mencegah duplikat).

Membuat: tombol **Generate Visas** pada tab Visa booking (membuat draft untuk
semua jamaah yang sudah punya nomor paspor, menyalin nomor paspor sebagai
snapshot), atau input manual.

Alur status:

```
draft ──Submit──► submitted ──Start Processing──► processing ──Approve──► approved
                     │                                │
                     └────────── Reject ──────────────┘──► rejected
approved ──(cron harian, expiry_date terlewat)──► expired
Reset to Draft: dari rejected/expired
```

- *Approve* otomatis mencatat tanggal approval dan **mengantrikan notifikasi
  WhatsApp "Visa Update"** ke jamaah.
- Tombol **Notify Pilgrim** mengirim update manual pada status apa pun.
- Paspor pada visa adalah **snapshot** — aman bila jamaah memperbarui paspornya.
- Field nomor paspor pada visa hanya terlihat *Travel / Admin* & *Visa Officer*.

**Gate**: booking tidak bisa *Set Ready* bila masih ada visa belum `approved`.

## Manasik

Menu: Travel → Operation → Manasik.

1. New: isi nama (default mengikuti nomor booking), tanggal, jam (Start/End),
   lokasi, trainer.
2. **Fill Attendees from Booking** — mengundang semua jamaah booking.
3. Setelah sesi: ubah status kehadiran per jamaah — *Present / Absent /
   Reschedule* — atau **Mark All Present**.
4. **Schedule to Calendar** — membuat `calendar.event` dengan peserta
   (koordinator + trainer + jamaah) dan tautan dua arah dari form manasik.

Jadwal manasik + status kehadiran pribadi tampil di portal jamaah.

## Flight & Informasi Keberangkatan

- Tab **Flight** pada booking: catat penerbangan *Outbound* dan *Return*
  (maskapai, nomor penerbangan, bandara/kota + waktu berangkat & tiba).
- Field **Meeting Point**: titik kumpul — tampil di portal pada bagian
  informasi keberangkatan dan di pesan WhatsApp H-1.
- Menu Travel → Operation → Flight: daftar semua penerbangan lintas booking.
