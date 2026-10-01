# 09 — Portal Jamaah (My Umrah)

## Memberi Akses ke Jamaah

1. Buka form **jamaah** → klik kontak terkait (field *Related Contact*).
2. Di form kontak → **Grant Portal Access** → isi email → Send.
3. Jamaah menerima email untuk membuat password, lalu login ke portal `/my`.

> Penting: berikan akses pada **kontak jamaah** (yang dibuat otomatis), bukan
> kontak customer keluarga. Isolasi data dihitung per kontak jamaah.

## Yang Dilihat Jamaah

Kartu **My Umrah** muncul di portal home. Bila jamaah punya 1 booking,
langsung terbuka halaman detail:

| Bagian | Isi |
|---|---|
| Trip Information | nomor booking, paket, departure/return, progress %, meeting point |
| My Documents | daftar dokumen **miliknya sendiri** + status (Missing/Submitted/In Verification/Verified/Rejected/Expired) + alasan penolakan + **form upload** |
| Payment | Total / Paid / Outstanding + bar progres + badge status |
| Manasik Schedule | sesi booking + status kehadiran pribadi |
| Flights | penerbangan pergi & pulang (maskapai, rute, jam) |

## Upload Dokumen dari Portal

1. Pilih file pada baris dokumen → **Upload**.
2. File tersimpan pada dokumen, status otomatis menjadi **Submitted**.
3. Staf memverifikasi di backend (Verify/Reject). Jika ditolak, jamaah melihat
   alasan dan bisa **mengunggah ulang**.
4. Dokumen `verified`/`expired` tidak menampilkan form upload.

## Jaminan Isolasi Data

- Jamaah hanya melihat: booking tempat ia terdaftar, **dokumennya sendiri**
  (bukan dokumen jamaah lain dalam group yang sama), visa-nya, sesi manasik
  booking-nya, status kehadirannya sendiri, flight booking-nya.
- **NIK tidak pernah dikirim ke portal** (pembatasan di level field).
- Membuka URL booking milik orang lain → dialihkan kembali (record rule).
- Portal tidak dapat memanggil aksi verifikasi/mengubah data operasional.

## Pertanyaan Umum

- *Lupa password* → alur reset standard Odoo dari halaman login portal.
- *Jamaah punya 2 booking* → tampil daftar; pilih salah satu.
- *Portal user tanpa booking* → link My Umrah mengembalikan ke /my.
