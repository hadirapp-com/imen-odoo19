# 13 — Troubleshooting

## "Internal Server Error" saat halaman dibuka

1. Cek log **file** (bukan docker logs):
   ```bash
   docker exec imen-odoo19-odoo19-1 tail -100 /etc/odoo/odoo-server.log
   ```
2. Penyebab umum di environment ini: server berjalan dengan
   `dev_mode = reload` — mengedit file `.py` modul memicu restart; request yang
   datang di tengah restart → 500 sesaat. **Solusi**: refresh setelah beberapa
   detik; untuk stabilitas harian, matikan `dev_mode` di `/etc/odoo/odoo.conf`.
3. Gangguan jaringan docker (DB "closed the connection unexpectedly") —
   cek `docker ps`, restart container odoo bila perlu.

## Upgrade modul gagal

- Log ke stdout **kosong** karena config memakai `logfile` — selalu cek file log.
- `ParseError: Field "..." does not exist in model ...` → view memakai field
  yang tidak ada di versi Odoo (contoh nyata: `project.task` **tidak punya
  field `fold`** di Odoo 19 — gunakan `stage_id.fold`). Perbaiki view, ulangi
  `-u hadir_umrah`.
- Verifikasi versi terpasang:
  ```bash
  docker exec imen-odoo19-db-1 psql -U odoo -d imen -t -c \
    "SELECT state, latest_version FROM ir_module_module WHERE name='hadir_umrah';"
  ```

## Portal

| Gejala | Penyebab & Solusi |
|---|---|
| `/my/umrah` → 404 via curl/insomnia | Session belum terikat ke DB — perilaku normal. Buka lewat browser setelah login. |
| Kartu My Umrah tidak muncul | Jamaah belum punya *Related Contact* dengan akses portal — lakukan **Grant Portal Access** pada kontak jamaah. |
| Jamaah tidak melihat apa-apa | Portal access diberikan ke kontak customer, bukan kontak jamaah. |
| Upload gagal "can no longer be updated" | Dokumen sudah `verified`/`expired` — verifikasi ulang lewat backend (Reset/Verify). |
| Ikon menu lama masih tampil | Cache browser — hard refresh (Ctrl+Shift+R). |

## Notifikasi WhatsApp

| Gejala | Solusi |
|---|---|
| Tidak ada notifikasi masuk antrian | Cron *Umrah: Queue Notifications* belum jalan — jalankan manual di Settings > Technical > Scheduled Actions. Pastikan ada template untuk event tsb. |
| Status `failed` "Missing phone number" | Isi nomor di record notifikasi → **Re-queue** → **Send Now**. |
| `http` gagal autentikasi | Cek URL & token di Settings > Companies (token hanya terlihat grup System). |
| Nomor salah format | Sistem menormalkan `08xx` → `628xx`; simpan nomor di kontak/jamaah tanpa spasi. |

## Data

- **Demo tidak muncul** — DB dibuat tanpa demo; resep memuat ada di
  [Instalasi](02-instalasi-konfigurasi.md#memuat-data-demo-opsional).
- **Sequence booking tidak berjalan** — pastikan tidak mengedit record
  `ir.sequence` berkode `umrah.booking` (noupdate).
- **Activity reminder berduplikat** — dedup berdasar judul activity; jangan
  mengubah template judul cron.

## Perintah Berguna

```bash
# Log server (otoritatif)
docker exec imen-odoo19-odoo19-1 tail -f /etc/odoo/odoo-server.log

# Status modul & versi
docker exec imen-odoo19-db-1 psql -U odoo -d imen -t -c \
  "SELECT state, latest_version FROM ir_module_module WHERE name='hadir_umrah';"

# Jalankan cron notifikasi manual (shell)
docker exec -it imen-odoo19-odoo19-1 python3 /usr/bin/odoo shell -d imen \
  --db_host db --db_port 5432 --db_user odoo --db_password '<password-dari-compose>'
>>> env['umrah.notification']._cron_queue_notifications()
>>> env['umrah.notification']._cron_send_notifications()
```
