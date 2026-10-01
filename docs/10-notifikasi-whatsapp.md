# 10 — Notifikasi WhatsApp

## Arsitektur (Provider-Agnostic)

```
Event operasional ──► ANTRIAN (umrah.notification)          PENGIRIMAN (cron per jam)
                      body di-render saat masuk antrian  ──►  provider "log"   → catat di log, status sent
                      dedup 3 hari per event+nomor+booking   provider "http"   → POST JSON ke gateway
                                                             extension points untuk provider lain
```

Status antrian: `queued → sent` / `failed` (bisa *Re-queue*) / `cancelled`.
Admin tidak dapat menghapus record antrian (jejak audit terjaga).

## Event & Penerima

| Event | Penerima | Isi Pesan (contoh variabel) |
|---|---|---|
| Document Reminder | tiap jamaah | kemajuan dokumen, ajakan upload via portal |
| Payment Reminder | customer booking | sisa tagihan, total, terbayar |
| Manasik Reminder | tiap jamaah | nama, tanggal, jam, lokasi sesi besok |
| Visa Update | jamaah terkait | status visa + nomor paspor terdaftar |
| H-7 Departure | tiap jamaah | checklist 7 hari |
| H-1 Departure | tiap jamaah | meeting point, ajakan tepat waktu |

Pemicu: cron harian (reminder) + otomatis saat **visa di-Approve** +
tombol **Notify Pilgrim** di form visa.

## Template Pesan

Menu **Travel → Configuration → Notification Template** (6 template default
Bahasa Indonesia, boleh diedit). Syntax mail.template standar:

- Document/H-7/H-1 → `object` = jamaah: `${object.full_name}`,
  `${object.booking_id.name}`, `${object.booking_id.departure_date}`,
  `${object.document_progress}`
- Payment → `object` = booking: `${object.partner_id.name}`,
  `${object.amount_due}`, `${object.currency_id.name}`
- Manasik → `object` = sesi: `${object.time_label}`, `${object.location}`
- Visa → `object` = visa: `${object.pilgrim_id.full_name}`,
  `${object.state_label}`

## Mengaktifkan Gateway Nyata

1. Settings → Companies → perusahaan Anda:
   - **WhatsApp Provider** = *Generic HTTP API*
   - **WhatsApp API URL** = endpoint gateway
   - **WhatsApp API Token** = token (hanya terlihat grup *System*)
2. Format default: `POST {target: <nomor>, message: <teks>}`, token di header
   `Authorization`. Nomor dinormalisasi ke format internasional tanpa `+`
   (`0811…` → `62811…`).
3. Gateway dengan format lain: buat modul kecil turunan yang meng-override
   `_prepare_provider_payload()` / `_process_provider_response()` —
   modul `hadir_umrah` tidak perlu diubah.

> Default *Log only (testing)*: semua notifikasi tercatat di log server dengan
> status `sent` — aman untuk UAT tanpa gateway.

## Monitoring Harian

Menu **Travel → Operation → Notifications** (default filter *Queued*):

- `failed` → perbaiki (mis. isi nomor) → **Re-queue** → **Send Now**.
- `queued` → **Cancel** bila tidak jadi dikirim.
