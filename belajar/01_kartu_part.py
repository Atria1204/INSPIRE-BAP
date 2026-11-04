# LATIHAN 1: membaca SATU part dari database dalam bentuk "kartu".
#     cd "D:\ITS\sem 7\CALIBER\HACKATHON\aether-spare"
#     python belajar/01_kartu_part.py
#
# Ganti NOMOR_PART di bawah dengan nomor part lain (kolom "material" di DB Browser).

import sqlite3

NOMOR_PART = "4100000142"

db = sqlite3.connect("data/aether_spare.db")
db.row_factory = sqlite3.Row            # supaya kolom bisa dipanggil pakai nama, misalnya p["stock"]

# Ini SQL: "ambil semua kolom (*) dari tabel materials yang material-nya = NOMOR_PART"
p = db.execute("SELECT * FROM materials WHERE material = ?", (NOMOR_PART,)).fetchone()

if p is None:
    print("Part tidak ditemukan:", NOMOR_PART)
    raise SystemExit

def rp(x):
    return "-" if x is None else f"Rp {x:,.0f}".replace(",", ".")

print(f"""
==================== KARTU PART {p['material']} ====================
{p['description']}

IDENTITAS
  Satuan            : {p['unit']}
  Status di sistem  : {p['mrp_type']}
  Tingkat kritis    : {p['criticality']}   (S paling kritis, lalu A, B, C)
  Dipasang di       : {p['n_funcloc']} lokasi, total {p['installed_qty']:g} buah

STOK SEKARANG
  Stok              : {p['stock']:g}
  Min / Max sistem  : {p['min_qty']:g} / {p['max_qty']:g}

RIWAYAT PEMAKAIAN (17 bulan)
  Diambil           : {p['n_issues']} kali, total {p['total_qty']:g} {p['unit']}
  12 bulan terakhir : {p['issues_12m']} kali, total {p['qty_12m']:g} {p['unit']}
  Terakhir dipakai  : {p['last_issue'] or 'tidak pernah'}
  Bulan ada pemakaian: {p['months_with_demand']} dari 17
  Pola pemakaian    : {p['demand_class']}

FORECAST
  Metode            : {p['forecast_method']}
  Perkiraan         : {p['forecast_monthly']} {p['unit']} per bulan

SINYAL DARI PERALATAN
  Kerusakan darurat : {p['breakdowns_on_equipment']}
  Jadwal PM 12 bulan: {p['pm_events_12m']}

PEMBELIAN
  Lead time         : {p['lead_time_days']:g} hari (sumber: {p['lead_time_source']})
  Supplier telat    : {'-' if p['late_share'] is None else f"{p['late_share']:.0%} pesanan"}
  Supplier utama    : {p['main_supplier'] or '-'}
  Harga per unit    : {rp(p['unit_price_idr'])} (sumber: {p['price_source']})

HITUNGAN STOK BARU (simulasi PEMSI)
  Target service lvl: {p['service_level']:.1%}
  Terpakai selama menunggu (rata-rata): {p['lead_time_demand_mean']:g}
  Reorder point     : {p['reorder_point']:g}
  Min / Max BARU    : {p['rec_min']} / {p['rec_max']}

HASIL
  Peluang habis     : {p['p_stockout']:.0%}
  Risiko            : {p['stockout_risk']}
  Kesehatan stok    : {p['health']}
  REKOMENDASI       : {p['action']} {p['action_qty']:g}
  Alasan            : {p['action_reason']}
""")
