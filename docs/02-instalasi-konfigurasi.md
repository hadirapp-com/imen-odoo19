# 02 — Instalasi & Konfigurasi

## Prasyarat

- Stack Docker proyek ini berjalan: `docker compose up -d`
  (container `odoo19` + `db`, web di `http://localhost:10019`).
- Folder `addons/` ter-mount ke `/mnt/extra-addons` di container.

## Install / Upgrade Modul

Jalankan dari root repo (parameter DB mengikuti `docker-compose.yml`):

```bash
docker exec imen-odoo19-odoo19-1 python3 /usr/bin/odoo -d imen -u hadir_umrah \
  --db_host db --db_port 5432 --db_user odoo --db_password '<password-dari-compose>' \
  --addons-path=/mnt/extra-addons --stop-after-init
```

- Log proses mengalir ke **file** `/etc/odoo/odoo-server.log` di dalam container
  (bukan stdout) — lihat [Troubleshooting](13-troubleshooting.md).
- Verifikasi keberhasilan: menu **Apps**, cari `hadir_umrah`, versi harus sesuai;
  atau cek log tidak ada `ParseError`.

> Catatan: server berjalan dengan `dev_mode = reload` — setiap perubahan file
> `.py` memicu restart otomatis; hindari mengedit file saat server dipakai.

## Data Awal yang Otomatis Ter-install

| Data | Isi |
|---|---|
| Tipe dokumen (8) | Passport, KTP, KK, Photo 4x6, Marriage Book, Vaccine, Visa, Ticket |
| Template dokumen (2) | *Umrah Reguler – Default* (default) dan *Umrah Plus – Family* (+ Buku Nikah) |
| Katalog task (9) | Payment Follow Up (H-90) s.d. Post Trip (Return+3) — lihat [Task Operasional](07-task-operasional.md) |
| Template notifikasi (6) | Bahasa Indonesia untuk 6 event — lihat [WhatsApp](10-notifikasi-whatsapp.md) |
| Sequence booking | `UMR/%(year)s/00001` — penomoran mengikuti **tahun keberangkatan** |
| Cron | 8 scheduled action harian/per jam (paspor, dokumen, payment, keberangkatan, visa, notifikasi) |

## Checklist Konfigurasi Pertama Kali

1. **Grup pengguna** — Settings > Users: berikan grup
   *Travel / Admin*, *Travel / Finance*, *Travel / Visa Officer*, atau
   *Travel / Manager* (lihat [Hak Akses](11-hak-akses-keamanan.md)).
2. **Paket Umroh** — Travel → Configuration → Umrah Package → New:
   centang **Is Umrah Package**, isi harga, pilih **Document Template**
   (kosongkan = pakai template default).
3. **Provider WhatsApp** (opsional dulu) — Settings > Companies > perusahaan:
   *WhatsApp Provider = Log only (testing)* sudah cukup untuk UJI tanpa gateway.
4. **Akses portal jamaah** — dilakukan per jamaah saat booking berjalan
   (lihat [Portal Jamaah](09-portal-jamaah.md)).

## Memuat Data Demo (opsional)

Database yang sudah ada umumnya dibuat tanpa demo. Untuk memuat data contoh
(booking 3 jamaah + visa + manasik + flight):

```bash
docker exec imen-odoo19-db-1 psql -U odoo -d imen -c \
  "UPDATE ir_module_module SET demo=true WHERE name='hadir_umrah';"
# lalu jalankan perintah upgrade di atas (-u hadir_umrah)
```

> Demo menulis data nyata ke database — jangan lakukan di database produksi.
