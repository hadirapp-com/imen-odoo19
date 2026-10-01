# 06 — Pembayaran

## Prinsip

Modul **tidak membuat pembukuan sendiri**. Semua invoice & payment dikelola lewat
Accounting standard Odoo dari Sales Order; booking hanya **menampilkan** hasilnya.

## Angka di Tab Payment (Form Booking)

| Field | Sumber |
|---|---|
| Total Amount | `amount_total` Sales Order terhubung |
| Invoiced | Σ total invoice (customer invoice, state *posted*) |
| Paid | Σ (total − sisa) semua invoice posted |
| Amount Due | Total − Paid |
| Payment Status | lihat aturan bawah |

Aturan **Payment Status** (dihitung otomatis, tersimpan, ikut ke kanban/list):

1. Ada invoice posted **telat bayar** (due date terlewat, belum lunas) → `Overdue`
2. Belum ada SO → `Unpaid`
3. Due ≤ 0 dan sudah ada invoice → `Paid`
4. Belum ada pembayaran → `Unpaid`
5. Selainnya → `Partially Paid`

## Cara Kerja Harian

1. Dari form **Sales Order** → *Create Invoice* (standard Odoo) → Confirm.
2. Terima pembayaran via Accounting standard (*Register Payment*).
3. Angka di booking, dashboard, dan portal **mengikuti otomatis**.

## Pembayaran di Portal Jamaah

Bagian *Payment* pada halaman My Umrah menampilkan **Total / Paid /
Outstanding** (format mata uang) + bar progres + badge status. Jamaah tidak
diberi akses ke data akuntansi internal.

## Reminder

- Cron harian membuat activity *"Payment overdue"* pada booking yang telat
  (berisi jumlah invoice & tanggal telat tertua).
- Cron notifikasi mengantrikan **WhatsApp "Payment Reminder"** ke nomor customer
  dengan rincian sisa tagihan (lihat [WhatsApp](10-notifikasi-whatsapp.md)).
