# 04 — Dokumen

## Konsep

```
Product (paket) ──pilih──► Document Template ──isi──► daftar tipe dokumen + required
                                   │
                    saat booking dibuat / jamaah ditambahkan
                                   ▼
              Checklist otomatis: 1 baris per jamaah per tipe dokumen
```

- **Tipe dokumen** (Configuration → Document Type): Passport, KTP, KK, Photo 4x6,
  Marriage Book, Vaccine, Visa, Ticket. Flag *Has Expiry* mengaktifkan pelacakan
  tanggal kedaluwarsa.
- **Template per paket** (Configuration → Document Template): tentukan dokumen
  apa saja yang wajib untuk paket tertentu. Template dengan *Default Template*
  dipakai bila paket tidak menentukan template (satu default per perusahaan).
- **Checklist otomatis** dibuat pada 3 momen: booking dibuat (wizard), booking
  dikonfirmasi, dan jamaah baru ditambahkan. Tombol *Generate / Complete
  Checklist* pada tab Documents menambahkan yang kurang **tanpa** menduplikasi
  yang sudah ada.

## Siklus Status Dokumen

```
missing ──Submit──► submitted ──Send to Verification──► verification ──Verify──► verified
   ▲                    │                                    │                        │
   │   Reset            ▼                                    ▼                        ▼
   └──────────────(rejected ◄──Reject, wajib isi alasan)      expired (cron harian,
                                                              expiry_date terlewat)
                       not_required (tandai bila tidak relevan untuk jamaah tsb)
```

Aturan tombol:

| Tombol | Syarat |
|---|---|
| Submit | Status `missing`/`rejected`, **wajib ada attachment** (scan/foto) |
| Send to Verification | Status `submitted` |
| Verify | Status `submitted`/`verification` + attachment ada; tercatat *verified_by* & tanggal |
| Reject | Status `submitted`/`verification`, **wajib isi alasan** (tampil di portal jamaah) |
| Mark Not Required | Status apa pun → `not_required` (tidak dihitung progress) |
| Reset | Kembali ke `missing`, membersihkan tanggal/verifikator/alasan |

## Progress

- Progress dokumen per jamaah & per booking = *verified* ÷ *required*
  (bar `Document Progress` di form/list booking).
- Dokumen `not_required` tidak dihitung.

## Input Dokumen

1. **Backend** — tab Documents di booking, atau menu Jamaah → Document;
   unggah file di field *Attachments* lalu Submit.
2. **Portal jamaah** — jamaah mengunggah sendiri; otomatis menjadi `submitted`
   (lihat [Portal](09-portal-jamaah.md)).

## Reminder Otomatis

Cron harian membuat activity *"Missing documents"* di booking yang akan
berangkat ≤30 hari namun dokumen required-nya belum lengkap. Bila semua dokumen
sudah verified pada state `verification`, activity *"Ready for visa"* dibuat
sebagai penanda boleh lanjut proses visa.
