# Kamus Kolom Tabel `materials`

Satu baris = satu spare part. Ada 55 kolom. Di DB Browser, kolom 6–7 (`mrp_recommendation`, `mrp_reason`)
ada tepat setelah `criticality`; di kamus ini keduanya dijelaskan di bagian A (nomor 5a, 5b), jadi nomor lainnya tetap.
Contoh di setiap kolom memakai part **4100000142 BEARING,BALL,ANGULAR,6216BDB**.

> Angka lead time dan "supplier telat" pada contoh bisa sedikit berubah setelah `build_db.py` dijalankan
> ulang, karena duplikat di file PR PO sudah dibuang.

---

## Dulu: Observed vs Derived itu ditentukan bagaimana?

Aturannya sederhana. **Kita yang menentukan**, dengan satu pertanyaan:
**"Angka ini disalin dari file panitia, atau kita hitung sendiri?"**

| Label | Artinya | Contoh |
|---|---|---|
| **Observed** | **Disalin apa adanya** dari Excel panitia. Kita tidak mengubahnya. | Stok = 1 (dari BoM) |
| **Derived** | **Dihitung** dari angka Observed memakai rumus yang jelas. | Forecast 9,01/bulan (dari riwayat pemakaian) |
| **Assumption** | Angka yang **kita tetapkan sendiri** karena tidak ada di data. | Biaya simpan 25%/tahun, kurs USD |

Gunanya: kalau juri bertanya "angka ini dari mana?", jawabannya selalu jelas, yaitu file panitia, rumus kita, atau asumsi kita.
Daftar asumsi ada di tabel `assumptions` di database yang sama.

---

## A. IDENTITAS PART

### 1. `material` (Observed, dari BoM)
Nomor unik spare part di sistem gudang (SAP). Seperti NIK-nya part.
Contoh: `4100000142`

### 2. `description` (Observed, dari BoM)
Nama part dalam format SAP: **JENIS, SUB-JENIS, TIPE, UKURAN/MODEL**.
Contoh: `BEARING,BALL,ANGULAR,6216BDB` = bantalan putar, jenis bola, kontak miring, model 6216BDB.

### 3. `unit` (Observed, dari BoM)
Satuan hitung part.

| Kode | Artinya |
|---|---|
| **EA** | *Each*, per buah (paling banyak, 4.405 part) |
| SET | per set |
| ASS | *assembly*, per rakitan |
| KG / L / M | kilogram / liter / meter |
| LG | *length*, per batang (pipa) |
| RL | *roll*, per gulung |

### 4. `mrp_type` (Observed, dari BoM)
Cara sistem merencanakan part ini.

- **Stock Item**: disimpan di gudang. Sistem otomatis menyuruh beli kalau stok turun di bawah Min.
- **Non Stock**: **tidak direncanakan untuk distok.** Baru dibeli saat ada pekerjaan yang butuh.

**Kenapa Min–Max bearing ini 0/0?** Karena statusnya *Non Stock*. Di data, **semua 3.825 part Non Stock punya Min–Max 0/0**.
Artinya sistem memang tidak pernah menyuruh beli ulang. Masalahnya, bearing ini **dipakai setiap bulan**.
Jadi statusnya yang **salah**, dan ini yang dimaksud brief dengan *"static planning"*.

### 5. `criticality` (Observed, dari FuncLoc list, diambil yang tertinggi)
Kelas kepentingan peralatan tempat part ini dipasang. Huruf ini **sama persis** dengan kolom *ABC Indicator* di Maintenance Plan.

| Kelas | Arti (pemahaman kita) | Isi terbanyak di data |
|---|---|---|
| **A** | Paling kritis | Motor, temperature, safety |
| **S** | **Special**: kebanyakan peralatan keselamatan (*safety valve*) atau yang wajib inspeksi | SAFETY (362 lokasi) |
| **B** | Menengah | Temperature, motor, control |
| **C** | Paling rendah | Pipa (paling banyak) |
| **-** | Kosong di data (33 lokasi level SITE/sistem) | |

Urutan yang kita pakai: **A > S > B > C**. Posisi S di antara A dan B adalah **asumsi** sampai dikonfirmasi ke Chandra Asri.
Satu part bisa dipasang di banyak lokasi; yang diambil **kelas paling tinggi** di antara lokasi-lokasinya.

### 5a. `mrp_recommendation` (Derived), 5b. `mrp_reason` (Derived)
Rekomendasi untuk **status perencanaan** part itu sendiri (bukan cuma angkanya):

| Rekomendasi | Kapan |
|---|---|
| **Change to Stock Item** | Statusnya Non Stock (Min–Max 0/0), tapi dipakai **≥ 3 kali dalam 12 bulan** |
| **Change to Non Stock** | Statusnya Stock Item, **tidak pernah dipakai** 17 bulan, dan kelasnya B/C (tidak kritis) |
| **Keep** | Selain itu |

Contoh bearing: **Change to Stock Item**, karena Non Stock tapi dipakai 91 kali dalam 12 bulan.

### 6. `n_funcloc` (Derived, dari BoM)
Di **berapa lokasi/peralatan** part ini dipasang. Rumus: hitung lokasi unik di BoM.
Contoh: `76` lokasi.

### 7. `installed_qty` (Derived, dari BoM)
Total jumlah part yang **terpasang** di semua lokasi itu. Rumus: jumlahkan *Installed Qty*.
Contoh: `95` buah terpasang di mesin-mesin. Ini bukan stok gudang.

---

## B. STOK SEKARANG

### 8. `stock` (Observed, dari BoM)
Jumlah di gudang **saat ini**. Contoh: `1`

### 9. `min_qty`, 10. `max_qty` (Observed, dari BoM)
Batas Min–Max **yang dipakai sistem sekarang**.
Cara kerjanya: kalau stok turun **sampai Min**, sistem menyuruh beli sampai **Max**.
Contoh: `0` / `0`, jadi tidak pernah ada perintah beli (lihat kolom 4).

---

## C. RIWAYAT PEMAKAIAN (dari Movement Material)

Setiap baris di Movement Material = **satu kali part diambil dari gudang** untuk pekerjaan perawatan.
Contoh 4 pengambilan pertama bearing ini:

| Tanggal | Jumlah | Order (pekerjaan) |
|---|---|---|
| 16 Mei 2025 | 1 | 201000004253 |
| 20 Mei 2025 | 1 | 203000004890 |
| 25 Mei 2025 | 1 | 201000017568 |
| 31 Mei 2025 | 1 | 201000002694 |

### 11. `n_issues` (Derived)
Berapa **kali** diambil selama 17 bulan (Mei 2025 – Sep 2026). Contoh: `123` kali.

### 12. `total_qty` (Derived)
Total **buah** yang diambil. Contoh: `165` buah. Satu pengambilan bisa lebih dari 1 buah.

### 13. `issues_12m`, 14. `qty_12m` (Derived)
Sama, tapi hanya **12 bulan terakhir** (Okt 2025 – Sep 2026). Contoh: `91` kali, `118` buah.
Gunanya: melihat apakah part **masih** dipakai, bukan cuma dulu.

### 15. `last_issue` (Derived)
Tanggal **terakhir** diambil. Contoh: `2026-09-30`, hari terakhir data. Masih aktif dipakai.

### 16. `months_with_demand` (Derived)
Dari 17 bulan, berapa bulan **ada pemakaian**. Contoh: `17`, artinya setiap bulan dipakai.

Pemakaian per bulan bearing ini (dari tabel `monthly_demand`):
```
2025: Mei 4 | Jun 8 | Jul 3 | Agu 25 | Sep 7 | Okt 5 | Nov 10 | Des 21
2026: Jan 28 | Feb 2 | Mar 2 | Apr 4 | Mei 7 | Jun 7 | Jul 15 | Agu 8 | Sep 9
```
Setiap bulan ada pemakaian, tapi jumlahnya naik-turun tajam (2 sampai 28).

### 17. `adi` (Derived)
*Average Demand Interval*: **rata-rata jarak antar-bulan yang ada pemakaian.**
Rumus: 17 bulan ÷ bulan yang ada pemakaian. Contoh: 17 ÷ 17 = `1`, artinya ada pemakaian setiap bulan.
Kalau ADI = 4, artinya rata-rata baru dipakai sekali setiap 4 bulan.

### 18. `cv2` (Derived)
Seberapa **naik-turun** jumlah pemakaian di bulan-bulan yang ada pemakaiannya.
Rumus: (simpangan baku ÷ rata-rata)². 0 = selalu sama; makin besar = makin tidak menentu.
Contoh: `0.63`, cukup naik-turun (2 sampai 28).

### 19. `demand_class` (Derived)
Gabungan ADI dan CV² menjadi 4 jenis pola. Metode ini dari **Syntetos & Boylan**, standar untuk spare part.

|  | CV² kecil (< 0,49): jumlah stabil | CV² besar (≥ 0,49): jumlah naik-turun |
|---|---|---|
| **ADI kecil (< 1,32)**: sering dipakai | **smooth** (31 part) | **erratic** (112 part), contoh bearing ini |
| **ADI besar (≥ 1,32)**: jarang dipakai | **intermittent** (1.634 part) | **lumpy** (153 part) |

Plus **no demand**: tidak pernah dipakai (5.551 part).
Kenapa penting? **Pola yang berbeda butuh cara forecast yang berbeda.**

---

## D. FORECAST

### 20. `forecast_method` (Derived)
**Sumber metode** (bukan dari modul PEMSI; ini metode standar forecasting spare part):
- SES: Brown, *Statistical Forecasting for Inventory Control* (1959)
- Croston, *Forecasting and stock control for intermittent demands* (1972)
- SBA dan klasifikasi ADI/CV²: Syntetos & Boylan (2005), Syntetos, Boylan & Croston (2005)

Yang dari **PEMSI** adalah **simulasi** (bagian G), bukan forecast-nya.

- **SES** (*Simple Exponential Smoothing*) untuk smooth dan erratic.
- **SBA** (*Syntetos–Boylan Approximation*, versi perbaikan metode Croston) untuk intermittent dan lumpy.
  SBA meramal dua hal terpisah: **berapa banyak** sekali pakai, dan **berapa bulan sekali** dipakai.

### 21. `forecast_monthly` (Derived)
Perkiraan pemakaian **per bulan ke depan**. Contoh: `9.01` buah per bulan.

Cara SES (alpha = 0,15), intinya **"rata-rata yang lebih mendengarkan bulan-bulan terakhir"**:
```
perkiraan baru = perkiraan lama + 0,15 × (pemakaian bulan ini − perkiraan lama)
```
Mulai dari bulan pertama (4), lalu diperbarui setiap bulan sampai September 2026, hasilnya 9,01.
Kenapa tidak rata-rata biasa (165 ÷ 17 = 9,7)? Karena SES memberi bobot lebih ke bulan terbaru.

### 22. `demand_sigma_monthly` (Derived)
Simpangan baku pemakaian bulanan: **seberapa jauh biasanya meleset dari rata-rata**.
Contoh: `7.68`. Pemakaiannya rata-rata ±7,7 buah dari perkiraan. Ini besar, jadi cadangan harus besar.

---

## E. SINYAL DARI PERALATAN

Ini menghubungkan part dengan **kondisi mesin**, sesuai poin brief "equipment failures, maintenance activities".
Jalurnya: **part → lokasi tempat ia dipasang (BoM) → laporan kerusakan/jadwal di lokasi itu**.

### 23. `breakdowns_on_equipment` (Derived, dari Notif History)
**Satuan: kejadian, total selama 17 bulan (Mei 2025 – Sep 2026), dijumlah dari semua lokasi tempat part dipasang.** Bukan per bulan.
Yang dihitung: notifikasi **N2** (semuanya prioritas *Emergency* = kerusakan mendadak).
Contoh: `5` kerusakan darurat dalam 17 bulan, di 76 lokasi itu.

### 24. `notifs_on_equipment` (Derived, dari Notif History)
**Satuan: laporan, total 17 bulan, semua lokasi.** Semua jenis laporan perawatan (N1, N2, N3). Contoh: `211` laporan.
Makin banyak = peralatannya makin sering dikerjakan = part-nya makin mungkin dibutuhkan.

### 25. `pm_events_12m` (Derived, dari Mitem & Mplan)
**Satuan: kejadian PM, dalam 12 bulan ke depan (Okt 2026 – Sep 2027), dijumlah dari semua lokasi.**
PM (*Preventive Maintenance*) = perawatan **terjadwal**, misalnya "inspeksi setiap 6 bulan", bukan karena rusak.
Contoh: satu lokasi punya PM "6 MONTHLY" → 2 kejadian dalam 12 bulan. Kalau part dipasang di 76 lokasi, semua dijumlah.
Rumus: dari *Start of cycle* dan siklusnya (misal "6 MONTHLY"), dihitung tanggal-tanggal jatuh temponya.
Contoh: `837` kejadian PM, karena dipasang di 76 lokasi.

### 26. `pm_qty_12m` (Derived)
Jumlah PM × jumlah terpasang. Contoh: `1076`.
⚠️ **Indikatif saja**: data rencana perawatan **tidak mencantumkan part apa yang dipakai**,
jadi kita tidak tahu apakah setiap PM benar-benar mengganti bearing ini. Angka ini **tidak** dipakai untuk menghitung stok, hanya ditampilkan sebagai sinyal.

---

## F. PEMBELIAN (dari PR PO)

Alurnya: **PR** (*Purchase Requisition*, permintaan beli dari gudang) → **PO** (*Purchase Order*, pesanan ke supplier) → barang datang.

### 27. `lead_time_days` (Derived)
**Lead time = berapa hari dari minta beli (PR) sampai barang datang (PO delivery).**
Rumus: median dari (tanggal PO delivery − tanggal PR), semua pembelian part ini.
Contoh: `51` hari, artinya kalau hari ini minta beli, kira-kira 51 hari lagi barang datang.
Inilah kenapa stok harus cukup untuk **51 hari ke depan** saat kita memesan.

### 28. `lead_time_std_days` (Derived)
Seberapa **tidak pasti** lead time-nya. Contoh: `31.1`, artinya bisa 20 hari, bisa 80 hari.

### 29. `lead_time_source` (Derived)
`material` = dari riwayat beli part ini sendiri. `fleet median` = part ini belum pernah dibeli, jadi dipakai median semua part (42 hari).

### 30. `late_share` (Derived)
Berapa persen pesanan yang datang **lebih lambat** dari tanggal yang diminta di PR.
Contoh: `0.575` = 57,5% pesanan telat.

### 31. `main_supplier` (Derived)
Supplier yang paling sering dipakai. Contoh: CAHAYA TEKNIK PERSADA PT.

### 32. `n_po` (Derived)
Berapa PO berbeda untuk part ini. Contoh: `20`.

### 33. `unit_price_idr` (Derived)
**Satuan: rupiah per 1 unit** (per EA, per SET, dst.).
Rumus: **median** semua harga PO part ini selama 17 bulan, dikonversi ke IDR kalau mata uangnya asing.

Kenapa median, bukan harga terakhir atau rata-rata?
- Harga part yang sama **hanya berbeda sedikit** antar periode (selisih tertinggi–terendah rata-rata 7%).
  Bearing ini: Rp1,91 juta sampai Rp2,07 juta dalam 38 pembelian.
- Median **tidak terpengaruh** satu harga yang aneh, sedangkan rata-rata bisa tertarik.
- Nilai stok = stok × harga ini. Perkaliannya dilakukan **otomatis** di kode, bukan manual.
⚠️ Asumsi: kolom *PO-Item Amount* dibaca sebagai **harga per unit** (lihat tabel `assumptions`).
Contoh: Rp 1.999.598.

### 34. `price_source` (Derived)
`PO history` = dari pembelian part ini. `fleet median` = belum pernah dibeli, jadi harganya **perkiraan**.

### 35. `stock_value_idr` (Derived)
Nilai uang stok di gudang: stok × harga. Contoh: 1 × Rp 1.999.598.

---

## G. HITUNGAN STOK BARU (simulasi PEMSI)

### 36. `service_level` (Assumption)
Target: **berapa persen dari waktu stok harus cukup**. Ditentukan dari kelas:
**A 99%, S 97,5%, B 95%, C 90%.**
Makin kritis, makin tinggi targetnya, tapi makin mahal stoknya. Itulah dilema *cost vs risk* di brief.

### 37. `z` (Derived)
Angka statistik padanan service level (99% ≈ 2,33). Sekarang **hanya untuk referensi**, karena reorder point dihitung dengan simulasi.

### 38–40. Simulasi lead-time demand (dari modul PEMSI, Banks Contoh 2.11)

Pertanyaannya: **"Selama menunggu barang datang, berapa yang akan terpakai?"**
Jawabannya tidak pasti, jadi **disimulasikan 2.000 kali**. Setiap putaran:

1. **Undi lead time**: rata-rata 51 hari, ±31 hari. Misal keluar **63 hari**.
2. **Undi berapa kali diambil** selama 63 hari. Rata-rata 123 kali ÷ 518 hari = 0,24 kali/hari, jadi sekitar 15 kali.
3. **Undi jumlah setiap pengambilan** dari riwayat asli bearing ini (kebanyakan 1, kadang 4). Totalnya misal **19 buah**.
4. Catat: putaran ini terpakai **19**.

Setelah 2.000 putaran, didapat 2.000 angka. Diurutkan dari kecil ke besar:
- `lead_time_demand_mean` (**38**) = rata-ratanya = **16,6 buah**
- `reorder_point` (**39**) = angka di urutan ke-99% = **46 buah**. Artinya dengan 46 buah di gudang, **99 dari 100 kali** stok cukup sampai barang baru datang.
- `safety_stock` (**40**) = 46 − 16,6 = **29,4 buah**, yaitu cadangan untuk berjaga kalau pemakaian melonjak atau supplier telat.

Kenapa simulasi, bukan rumus biasa? Rumus biasa mengandaikan pemakaian **merata dan berbentuk lonceng**.
Spare part tidak begitu: sering 0, kadang tiba-tiba 25. Simulasi memakai **pola asli** part itu.

### 41. `eoq` (Derived)
*Economic Order Quantity*: **jumlah sekali pesan yang paling hemat**.
Pesan sedikit-sedikit = biaya administrasi PO sering. Pesan banyak sekaligus = biaya simpan besar. EOQ adalah titik tengahnya.
Rumus: √(2 × pemakaian per tahun × biaya per PO ÷ biaya simpan per unit). Contoh: `18` buah.

### 42. `rec_min`, 43. `rec_max` (Derived): **Min–Max BARU yang kita rekomendasikan**
- **Min baru = reorder point** dibulatkan ke atas = **47**
- **Max baru = Min + EOQ** = 47 + 19 = **66**

Bandingkan dengan sistem sekarang: **0 / 0**.

### 44. `insurance_spare` (Derived)
`1` kalau part **tidak pernah dipakai**, tapi Stock Item di peralatan kritis S/A. Disarankan **simpan 1 sebagai cadangan asuransi**: jarang dibutuhkan, tapi kalau dibutuhkan dan tidak ada, mesin kritis mati lama.

---

## H. HASIL AKHIR

### 45. `p_stockout` (Derived, dari simulasi yang sama)
**Peluang kehabisan** sebelum barang baru datang, kalau dipesan sekarang dengan stok saat ini.
Dari 2.000 putaran, berapa yang pemakaiannya ≥ stok sekarang (1 buah). Contoh: `0.941` = **94%**.

### 46. `stockout_risk` (Derived)
- **HIGH** = peluang habis ≥ 50% **dan** kelas A/S
- **MEDIUM** = peluang habis ≥ 20%
- **LOW** = selain itu

Contoh: **HIGH**.

### 47. `health` (Derived): kesehatan stok
| Status | Artinya |
|---|---|
| dead stock | Ada stok, tapi **tidak pernah** dipakai dalam 17 bulan |
| non-moving | Ada stok, tidak dipakai **12 bulan terakhir** |
| slow-moving | Dipakai ≤ 2 kali setahun, dan stoknya di atas Max baru |
| excess | Stok di atas Max baru |
| below reorder point | Stok di bawah Min baru, **perlu pesan** |
| healthy | Aman |

Contoh: **below reorder point**.

### 48. `excess_qty`, 49. `excess_value_idr` (Derived)
Kelebihan stok di atas Max baru, dalam buah dan rupiah. Contoh: `0`, tidak berlebih.

### 50. `action` (Derived): rekomendasi
| Action | Artinya |
|---|---|
| **REORDER** | Pesan sekarang |
| **REDUCE** | Kurangi stok (jangan beli lagi, pakai dulu, atau jual/pindahkan) |
| **REVIEW** | Engineer harus memutuskan (part kelas A/S yang lama tidak dipakai) |
| **MONITOR** | Pantau dulu, belum perlu diubah |
| **MAINTAIN** | Biarkan, sudah sesuai |

### 51. `action_qty` (Derived)
Berapa buah. REORDER: Max baru − stok = 66 − 1 = **65**.

### 52. `action_reason` (Derived)
Kalimat alasan yang **dirangkai otomatis oleh aturan di kode** dari angka-angka di atas. Bukan ditulis manusia, bukan oleh AI.

### 53. `value_outlier` (Derived)
`1` kalau nilai stoknya **tidak wajar besar** (di atas 99,9% part lain), misalnya 862 thrust pad seharga Rp195 juta per buah.
Dipisahkan supaya total nilai tidak didominasi segelintir data dummy yang aneh.

---

## Cerita lengkap bearing 6216BDB (semua kolom digabung)

1. Dipasang di **76 lokasi kritis S** (kolom 5–7).
2. **Dipakai setiap bulan**, sekitar 9 buah per bulan, tapi naik-turun 2–28 (kolom 11–22).
3. Peralatannya sering dikerjakan: 5 kerusakan darurat, 211 laporan (kolom 23–24).
4. Butuh **51 hari** untuk datang, dan supplier **telat 57%** (kolom 27–30).
5. Tapi sistem mencatatnya **"Non Stock"** dengan Min–Max **0/0** (kolom 4, 9–10), jadi **tidak pernah dibeli ulang otomatis**.
6. Stok tinggal **1** (kolom 8). Peluang habis **94%** (kolom 45).
7. Simulasi: supaya aman 99%, butuh minimal **47** (kolom 39–42).
8. **Rekomendasi: REORDER 65 buah, dan ubah statusnya jadi Stock Item dengan Min–Max 47/66.**
