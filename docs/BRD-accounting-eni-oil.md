# BRD — Modul Accounting
## Odoo Enterprise `eni-oil.odoo.com`

---

## 1. Informasi Dokumen

| Item | Keterangan |
|---|---|
| Judul | Business Requirements Document — Modul Accounting |
| Sistem yang diaudit | Odoo Enterprise (Odoo Online/SaaS) — **Odoo 20.0** |
| URL | https://eni-oil.odoo.com/odoo/accounting |
| Database | `eni-oil` |
| Perusahaan | eni-oil (tunggal, tidak multi-perusahaan) |
| Mata uang / Negara | IDR / Indonesia (negara fiskal: Indonesia) |
| Tanggal audit | 2026-10-20 |
| Metode | Login akun administrator (Accounting/Administrator, Bookkeeper, Invoicing & Banks) + inventarisasi via JSON-RPC |
| Status | Final draf untuk review |

---

## 2. Ringkasan Eksekutif

`eni-oil` adalah **Odoo 20.0 Enterprise** dengan aplikasi **Accounting penuh** (`account_accountant`) beserta seluruh pelengkap Enterprise: aset tetap, laporan keuangan (22 laporan root), rekonsiliasi & sinkronisasi bank, penagihan (follow-up), pinjaman, dokumen, OCR/AI, EDI, dan lokalisasi Indonesia **era Coretax** — termasuk modul **e-Faktur Coretax** dan **QRIS**.

**Status instance: tahap konfigurasi awal, belum operasional** — 0 jurnal transaksi, 0 produk, 0 partner eksternal, 0 rekening bank terdaftar, NPWP perusahaan belum diisi. Seluruh infrastruktur akuntansi (CoA 200 akun, 19 pajak PPN/PPnBM, 9 jurnal, 22 laporan, 38 cron otomatisasi) sudah terpasang dan aktif.

Dokumen ini merumuskan kebutuhan bisnis yang dijawab modul accounting, sebagai basis: (a) tata kelola & rollout instance, (b) gap-analysis terhadap build Community internal (`hadir_accounting`).

---

## 3. Latar Belakang & Tujuan

**Latar belakang:** Perusahaan menyiapkan akuntansi pada Odoo Enterprise SaaS dan memerlukan dokumentasi kebutuhan bisnis yang menjelaskan cakupan fungsional modul accounting yang dipakai.

**Tujuan:**
1. Acuan tunggal cakupan fungsional accounting di `eni-oil` + checklist kelengkapan sebelum go-live transaksi.
2. Baseline perbandingan terhadap build Community internal Odoo 19 (`hadir_accounting` / `hadir_account_reports`).
3. Input keputusan lisensi/konfigurasi modul tambahan.

---

## 4. Ruang Lingkup

**Dalam lingkup:** modul akuntansi & pelengkapnya yang terpasang (Invoicing, Accounting EE, Assets, Reports, Bank, Follow-up, Loans, l10n Indonesia, Documents, AI/OCR, EDI) beserta konfigurasi terpasangnya.

**Di luar lingkup:** modul non-accounting (Sales, Purchase, HR, Website, dsb.), proses bisnis pasca-go-live (belum ada transaksi untuk diaudit).

---

## 5. Profil Platform

| Aspek | Temuan |
|---|---|
| Edisi & versi | Odoo Enterprise 20.0 (Odoo Online) |
| Modul terpasang | 114 modul |
| Perusahaan | 1 — eni-oil; negara fiskal Indonesia; **NPWP belum diisi** |
| Mata uang | IDR (kurs live `currency_rate_live` aktif, cron harian) |
| Chart of Accounts | Template Indonesia (`l10n_id`) — **200 akun** |
| Pajak | 19 pajak + 7 tax group (lihat §6.3) |
| Jurnal | **9 jurnal** (lihat §6.1) |
| Rekening bank | **0 terdaftar** (modul bank sync siap, proxy mode terkonfigurasi) |
| Pengguna internal | 2 — NEO (admin), sunendi |
| Volume transaksi | **0** (instance juvenil) |
| Keamanan | TOTP/2FA + passkey tersedia; portal payment aktif |

---

## 6. Kebutuhan Fungsional per Area

### 6.1 Inti Akuntansi (KB-01)
**Modul:** `account` (Invoicing), `account_accountant` (Accounting EE), `analytic`, `analytic_enterprise`

Jurnal terpasang:

| Kode | Nama | Tipe |
|---|---|---|
| INV | Sales | sale |
| BILL | Purchases | purchase |
| BNK1 | Bank | bank |
| CSH1 | Cash | cash |
| MISC | Miscellaneous Operations | general |
| CABA | Cash Basis Taxes | general |
| EXCH | Exchange Difference | general |
| STJ | Inventory Valuation | general |
| TAX | Tax Returns | general |

Kebutuhan bisnis: pembukuan double-entry lengkap (faktur, bill, jurnal umum, credit note, pembayaran), aplikasi akuntan penuh (rekonsiliasi, tutup buku, dashboard), jurnal khusus cash-basis pajak & selisih kurs → menandakan kebutuhan **PSAK berbasis akrual dengan pelaporan cash-basis pajak** dan valuasi valuta asing.

### 6.2 Struktur Akun Keuangan (KB-02)
**Temuan:** 200 akun CoA Indonesia.

| Tipe | Jml | Tipe | Jml |
|---|---:|---|---:|
| Kas & bank | 3 | Beban | 73 |
| Aset lancar | 8 | Beban penyusutan | 16 |
| Aset tetap | 33 | Beban langsung | 1 |
| Prepaid | 8 | Beban lain | 1 |
| Piutang | 5 | Pendapatan | 4 |
| Utang dagang | 5 | Pendapatan lain | 6 |
| Utang lancar | 28 | Ekuitas | 8 |
| | | Laba ditahan | 1 |

Granularitas tinggi pada aset tetap (33) dan beban (90) → pelaporan per kategori tanpa bergantung analytic.

### 6.3 Perpajakan Indonesia — Era Coretax (KB-03)
**Modul:** `l10n_id`, `l10n_id_efaktur_coretax`, `l10n_id_reports`

| Tax Group | Pajak terpasang |
|---|---|
| Non-luxury Good Taxes | PPN 12% (Non-Luxury Good) — amount 11 = mekanisme DPP 11/12 (sale & purchase) |
| Luxury Good Taxes | PPN 12% penuh |
| SLTG | PPnBM 20% (STLG) |
| Zero-rated | 0%, 0% EXPORT |
| Tax Exempted | 0% EXEMPT |
| Collected by VAT Collector | 12% / 20% Pemungut PPN (dipungut penuh) |
| Impor & koreksi | 12% IM (impor, DPP 11/12), 12% NCR, WAPU 12% / Luxury WAPU / STLG WAPU |

Kebutuhan bisnis:
1. Kepatuhan **PPN 12% Coretax**: DPP nilai lain 11/12 barang non-mewah; 12% penuh + PPnBM untuk barang mewah.
2. Mekanisme **Pemungut PPN** dan **WAPU** (pungut sendiri).
3. **e-Faktur Coretax** — model data terpasang: `E-Faktur Document`, katalog `Product.code` & `UoM.code` e-Faktur → faktur pajak dikirim/dipetakan ke Coretax DJP.
4. Laporan pajak (`l10n_id_reports`) + **TAX Returns journal** + cron *"Generate or refresh account return for every companies"* → SPT masa otomatis.
5. **QRIS** — model `l10n_id.qris.transaction` + cron *"QRIS Fetch Status"* → penerimaan pembayaran QR pelanggan terekonsiliasi otomatis.

### 6.4 Posisi Fiskal & Termin (KB-04)
- Fiscal positions: `Domestic`, `Foreign Trade`, `Pemungut PPN`.
- Payment terms: Immediate, 15/21/30/45 hari, End of Following Month, 10 Days after End of Next Month.

### 6.5 Aset Tetap & Penyusutan (KB-05)
**Modul:** `account_asset`. Laporan **Depreciation Schedule** + varian *Group by: Account / Asset Group*. 33 akun aset + 16 akun beban penyusutan. Kebutuhan: registrasi, penyusutan periodik otomatis, disposal, buku aset per kategori.

### 6.6 Pelaporan Keuangan (KB-06)
**Modul:** `account_reports`, `account_reports_cash_basis`, `account_reports_spreadsheet`, `accountant_knowledge`, `account_fiscal_categories`

**22 laporan root terpasang:** Balance Sheet, Profit and Loss, Cash Flow Statement, Trial Balance, General Ledger, Partner Ledger, Journal Report, Aged Receivable, Aged Payable, Customer Statement, Open Items, Executive Summary, Bank Reconciliation Report, Generic Tax report, Annual Statements, Fiscal Report, Deferred Expense Report, Deferred Revenue Report, Unrealized Currency Gains/Losses, EC Sales List, **Interco Comparison**, Depreciation Schedule (+ varian group-by).

Kebutuhan: laporan statutori lengkap, basis tunai untuk pelaporan pajak, anotasi tahunan, dashboard spreadsheet dengan formula akuntansi, dan laporan perbandingan antar-perusahaan (Interco).

### 6.7 Perbankan & Rekonsiliasi (KB-07)
**Modul:** `account_online_synchronization`, `account_bank_statement_import` (+CAMT/CSV/OFX), `account_bank_statement_extract`

Kebutuhan: feed bank otomatis (cron sinkronisasi harian aktif), impor statement multi-format, OCR statement, rekonsiliasi otomatis (cron *"Try to reconcile automatically"*), toleransi rekonsiliasi (payment/foreign-currency tolerance terkonfigurasi). **Status: belum ada rekening bank terdaftar** — checklist go-live.

### 6.8 Piutang, Penagihan & Pembayaran (KB-08)
**Modul:** `account_followup`, `account_payment`, `payment`, `portal`, `sms`

Model terpasang: kriteria follow-up bertahap (`followup.line`), reminder manual, laporan follow-up; portal payment aktif (`enable_portal_payment`); QRIS (§6.3). Kebutuhan: penagihan bertahap otomatis, pembayaran online/QR pelanggan, notifikasi SMS.

### 6.9 Pinjaman (KB-09)
**Modul:** `account_loans` + `account_loans_extract`. **0 record** — disiapkan untuk pencatatan kredit (amortisasi pokok/bunga otomatis).

### 6.10 E-Faktur & EDI (KB-10)
**Modul:** `l10n_id_efaktur_coretax` (nasional), `account_edi_ubl_cii` (UBL/CII internasional).

### 6.11 Dokumen & AI (KB-11 / KB-12)
- `documents` + `documents_account` + grup Documents Administrator → arsip faktur/bill otomatis.
- OCR & AI: `account_invoice_extract` (bill → draft jurnal; cron validasi OCR aktif), `account_bank_statement_extract`, suite `ai_*` (embedding, AI fields, AI reports, AI MCP server).

### 6.12 Pendukung Umum (KB-13)
Kurs live, digest KPI, mail/Outlook/Gmail, SMS, TOTP/passkey, base import.

### Otomatisasi Terjadwal (38 cron) — pilihan akuntansi
| Cron | Peran |
|---|---|
| Journal online sync (+cleanup, reminder) | feed bank harian |
| Try to reconcile automatically | rekonsiliasi otomatis |
| Post draft entries with auto_post | auto-post jurnal terjadwal |
| Invoice OCR: Validate Invoices / Update Status | OCR bill |
| Generate or refresh account return | SPT pajak |
| Currency: rate update | kurs harian |
| Send invoices / Send account reports automatically | distribusi otomatis |
| Create/GC snapshots of accounting reports | snapshot laporan |
| Inventory Valuation Closing | tutup persediaan |
| QRIS Fetch Status | status pembayaran QRIS |

---

## 7. Matriks Fitur → Kebutuhan Bisnis

| ID | Kebutuhan Bisnis | Modul EE | Status Instance |
|---|---|---|---|
| KB-01 | Pembukuan inti + aplikasi akuntan | account, account_accountant | ✔ terkonfigurasi (9 jurnal) |
| KB-02 | CoA Indonesia granular | l10n_id | ✔ 200 akun |
| KB-03 | PPN Coretax, PPnBM, Pemungut, WAPU, e-Faktur, QRIS | l10n_id* | ✔ pajak terpasang; **NPWP & API Coretax belum diset** |
| KB-04 | Posisi fiskal + termin | account (core) | ✔ |
| KB-05 | Aset tetap & penyusutan | account_asset | ✔ siap (belum ada aset) |
| KB-06 | Laporan keuangan lengkap + cash basis + spreadsheet | account_reports* | ✔ 22 laporan |
| KB-07 | Bank feed + rekonsiliasi otomatis | account_online_synchronization | ⚠ **rekening bank belum didaftarkan** |
| KB-08 | Follow-up + pembayaran online/QR | account_followup, account_payment, QRIS | ✔ siap |
| KB-09 | Pinjaman | account_loans | ✔ siap (0 record) |
| KB-10 | EDI UBL/CII | account_edi_ubl_cii | ✔ terpasang |
| KB-11 | Arsip dokumen | documents_account | ✔ |
| KB-12 | AI/OCR | ai_*, account_invoice_extract | ✔ aktif (IAP credit dibutuhkan) |
| KB-13 | Kurs live, digest, 2FA | pendukung | ✔ |

**Checklist pra-go-live transaksi:** (1) isi NPWP & profil pajak perusahaan; (2) daftarkan rekening bank + koneksi bank sync; (3) kredensial Coretax e-Faktur; (4) master data partner (dengan NPWP) & produk (kode e-Faktur); (5) uji end-to-end satu faktur PPN 12% non-mewah → e-Faktur → laporan pajak.

---

## 8. Peran & Hak Akses

Pengguna internal (2):

| User | Grup (temuan audit) |
|---|---|
| NEO (nendi.n30@gmail.com) | Accounting/Administrator, Bookkeeper, Invoicing, Invoicing & Banks, Read-only, Documents/Administrator, Dashboard/Admin, Technical Features |
| sunendi (nendi165@gmail.com) | internal user (grup belum diaudit detail) |

Rekomendasi peran operasional (least-privilege):
1. **Bookkeeper** — transaksi harian.
2. **Accountant/Advisor (Administrator)** — CoA, tutup buku, konfigurasi pajak, laporan.
3. Akses bank/rekonsiliasi terbatas tim finance (grup *Invoicing & Banks*).

> Catatan keamanan: password akun administrator pernah dikirim melalui chat — disarankan **rotasi password** dan mengaktifkan 2FA (TOTP) untuk semua user accounting.

---

## 9. Batasan & Asumsi

1. Audit dilakukan **setelah hak administrator diberikan**; seluruh konfigurasi akuntansi terbaca. Data operasional (transaksi) belum ada sehingga pengujian proses bukan bagian audit ini.
2. Chart template persisnya tidak terbaca (model `account.chart.template` dibatasi Odoo SaaS); disimpulkan `l10n_id` dari pola CoA & pajak.
3. Kredensial eksternal (Coretax, bank sync proxy, IAP OCR) tidak dapat/boleh diekstrak — hanya keberadaan konfigurasinya yang dicatat.

---

## 10. Lampiran A — Inventaris Teknis Ringkas

**Modul accounting & pendukung (114 total terpasang):**

| Area | Modul |
|---|---|
| Inti | account, account_accountant, accountant, accountant_knowledge, analytic(+enterprise) |
| Aset | account_asset |
| Laporan | account_reports, account_reports_cash_basis, account_reports_spreadsheet, spreadsheet_account(+dashboards) |
| Pajak ID | l10n_id, l10n_id_efaktur_coretax, l10n_id_reports |
| Bank | account_online_synchronization, account_bank_statement_import(_camt/_csv/_ofx), account_bank_statement_extract, account_base_import |
| Piutang | account_followup, account_payment, payment, portal, sms |
| Pinjaman | account_loans, account_loans_extract |
| EDI | account_edi_ubl_cii |
| Dokumen | documents, documents_account, documents_product |
| AI/OCR | ai, ai_account, ai_account_reports, ai_mcp, ai_fields, ai_knowledge, iap_extract, partner_autocomplete |
| Pendukung | currency_rate_live, digest(+enterprise), mail(+enterprise), microsoft_outlook, google_gmail, auth_totp(+), auth_passkey(+), base_import, product, uom, web_enterprise, web_* views |

**Pajak terpasang (19):**
```
Sale:     12% (Non-Luxury Good) [11], 12% [12], 20% (STLG) [20], 0%, 0% EXPORT, 0% EXEMPT,
          12% Luxury Pemungut PPN [100], 12% Pemungut PPN [100], 20% STLG Pemungut PPN [100]
Purchase: 12% (Non-Luxury Good) [11], 12% [12], 20% (STLG) [20], 0%, 0% EXEMPT, 12% NCR, 12% IM [11]
None:     12% WAPU [-11], 12% Luxury WAPU [-12], 20% STLG WAPU [-20]
```
([n] = amount; 11 = efektif DPP 11/12; -n = akumulasi pungutan; 100 = dipungut penuh)

---

## 11. Lampiran B — Gap vs Build Community Internal (hadir_accounting, Odoo 19)

| Kapabilitas EE (eni-oil) | Status hadir_accounting |
|---|---|
| Inti pembukuan, CoA, pajak, invoice/bill/payment | ✔ tersedia (native `account`) |
| Aset tetap + penyusutan + disposal | ✔ `hadir_accounting` |
| Laporan keuangan (BS/PL/CF/TB/GL/AR/AP/Statement) | ✔ `hadir_account_reports` (engine sendiri, UI EE-style) |
| Konsolidasi multi-cabang & eliminasi | ✔ unik hpr (tidak ada di EE standar) |
| Depreciation Schedule + group-by | ✔ fase 4 hpr |
| Tax report per pajak (base/tax) | ✔ fase 2 hpr (dinamis) |
| Cash-basis reports & jurnal cash-basis | ✘ belum |
| Bank feed otomatis + rekonsiliasi otomatis | ✘ (impor statement manual) |
| Follow-up multi-level + reminder manual | ✔ dasar (cron + template) |
| Pinjaman (loans) | ✘ belum |
| e-Faktur Coretax / QRIS | ✘ belum (butuh integrasi DJP) |
| OCR/AI dokumen | ✘ belum |
| Spreadsheet dashboards / snapshot laporan | ✘ belum |
| Interco Comparison report | ✔ sebagian via `hadir_intercompany_transaction` (bridge chain, bukan laporan) |

> Lampiran ini sekaligus backlog kandidat pengembangan build Community berikutnya.
