# -*- coding: utf-8 -*-
"""Genera cot_gold_historico.csv: historico COT del oro COMEX (1986-presente).

Combina tres fuentes publicas:
  - COT Legacy futures-only (CFTC): noncomm/comm/nonrep + concentracion Net 4/8 + traders
  - COT Disaggregated futures-only (CFTC, desde jun-2006): managed money / swap / producer / other
  - Cierre del martes: fix PM LBMA (spot, hasta ago-2000) + GC=F via yfinance (futuro, despues)

Pensado para correr en GitHub Actions (full rebuild semanal). Valida el resultado
antes de guardar y termina con exit code 1 si algo no cuadra.

Uso:  python build_cot_gold_csv.py [salida.csv]
"""
import re
import sys
import time
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import cot_reports as cot

GOLD_CODE = "088691"  # GOLD - COMMODITY EXCHANGE INC. (el Micro Gold es otro codigo)
REPO = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "cot_gold_historico.csv"

warnings.filterwarnings("ignore")


def reintentar(fn, descripcion, intentos=3):
    """Ejecuta fn() con reintentos y backoff (los runners de CI sufren 429 esporadicos)."""
    for i in range(1, intentos + 1):
        try:
            return fn()
        except Exception as e:
            if i == intentos:
                raise
            espera = 15 * i
            print(f"  AVISO: {descripcion} fallo (intento {i}/{intentos}): {e}. "
                  f"Reintento en {espera}s...", flush=True)
            time.sleep(espera)


def norm(s):
    # los nombres de la CFTC tienen espaciado inconsistente ("LT = 4" vs "LT =4")
    return re.sub(r"\s+", "", str(s)).lower()


def pick(df, mapping):
    """Selecciona/renombra columnas casando nombres con espaciado normalizado."""
    lookup = {norm(c): c for c in df.columns}
    selected, faltan = {}, []
    for original, limpio in mapping.items():
        real = lookup.get(norm(original))
        (faltan.append(original) if real is None else selected.setdefault(real, limpio))
    if faltan:
        raise SystemExit(f"Columnas no encontradas: {faltan}")
    return df[list(selected)].rename(columns=selected)


# ---------- 1. Legacy (1986-presente) ----------
print("Descargando COT Legacy futures-only (1986-presente)...", flush=True)
leg = reintentar(lambda: cot.cot_all(cot_report_type="legacy_fut", store_txt=False, verbose=False),
                 "descarga COT Legacy")
code_col = next(c for c in leg.columns if "Contract Market Code" in c)
leg = leg[leg[code_col].astype(str).str.strip() == GOLD_CODE].copy()
date_col = next(c for c in leg.columns if "YYYY-MM-DD" in c)
leg[date_col] = pd.to_datetime(leg[date_col])
print(f"  Legacy oro: {len(leg):,} filas", flush=True)

legacy = pick(leg, {
    date_col: "fecha",
    "Open Interest (All)": "open_interest",
    "Noncommercial Positions-Long (All)": "noncomm_long",
    "Noncommercial Positions-Short (All)": "noncomm_short",
    "Noncommercial Positions-Spreading (All)": "noncomm_spreads",
    "Commercial Positions-Long (All)": "comm_long",
    "Commercial Positions-Short (All)": "comm_short",
    "Nonreportable Positions-Long (All)": "nonrep_long",
    "Nonreportable Positions-Short (All)": "nonrep_short",
    "Concentration-Net LT =4 TDR-Long (All)": "conc_4_long",
    "Concentration-Net LT =4 TDR-Short (All)": "conc_4_short",
    "Concentration-Net LT =8 TDR-Long (All)": "conc_8_long",
    "Concentration-Net LT =8 TDR-Short (All)": "conc_8_short",
    "Traders-Total (All)": "traders_total",
    "Traders-Noncommercial-Long (All)": "traders_noncomm_long",
    "Traders-Noncommercial-Short (All)": "traders_noncomm_short",
}).sort_values("fecha")

# ---------- 2. Disaggregated (jun-2006-presente) ----------
print("Descargando COT Disaggregated futures-only (2006-presente)...", flush=True)
dis = reintentar(lambda: cot.cot_all(cot_report_type="disaggregated_fut", store_txt=False, verbose=False),
                 "descarga COT Disaggregated")
dcode = next(c for c in dis.columns if norm(c) == norm("CFTC_Contract_Market_Code"))
dis = dis[dis[dcode].astype(str).str.strip() == GOLD_CODE].copy()
ddate = next(c for c in dis.columns if "YYYY-MM-DD" in c)
dis[ddate] = pd.to_datetime(dis[ddate])
print(f"  Disaggregated oro: {len(dis):,} filas", flush=True)

disagg = pick(dis, {
    ddate: "fecha",
    "M_Money_Positions_Long_All": "mm_long",
    "M_Money_Positions_Short_All": "mm_short",
    "M_Money_Positions_Spread_All": "mm_spreads",
    "Swap_Positions_Long_All": "swap_long",
    "Swap__Positions_Short_All": "swap_short",
    "Swap__Positions_Spread_All": "swap_spreads",
    "Prod_Merc_Positions_Long_All": "prod_long",
    "Prod_Merc_Positions_Short_All": "prod_short",
    "Other_Rept_Positions_Long_All": "other_long",
    "Other_Rept_Positions_Short_All": "other_short",
    "Other_Rept_Positions_Spread_All": "other_spreads",
}).sort_values("fecha")

# ---------- 3. Cierre del martes: LBMA (spot) + GC=F (futuro) ----------
print("Descargando cierres: GC=F (yfinance) + fix PM LBMA...", flush=True)
import yfinance as yf

gc = reintentar(lambda: yf.Ticker("GC=F").history(period="max", interval="1d")["Close"],
                "descarga GC=F (yfinance)")
if gc.empty:
    raise SystemExit("yfinance devolvio una serie vacia para GC=F")
gc.index = pd.to_datetime(gc.index.date)

lbma_raw = reintentar(
    lambda: requests.get("https://prices.lbma.org.uk/json/gold_pm.json",
                         timeout=60, headers={"User-Agent": "curl/8.0"}).json(),
    "descarga fix PM LBMA")
lbma = pd.Series(
    {pd.Timestamp(row["d"]): row["v"][0] for row in lbma_raw if row.get("v") and row["v"][0]},
).sort_index()

gc_start = gc.index.min()
px = pd.concat([
    pd.DataFrame({"fecha": lbma.index, "cierre_martes": lbma.values,
                  "fuente_precio": "spot"})[lbma.index < gc_start],
    pd.DataFrame({"fecha": gc.index, "cierre_martes": gc.values,
                  "fuente_precio": "gc_futuro"}),
]).drop_duplicates(subset="fecha", keep="last").sort_values("fecha")
print(f"  Precios: {px.fecha.min().date()} a {px.fecha.max().date()} "
      f"(spot LBMA hasta {gc_start.date()}, GC=F despues)", flush=True)

# ---------- 4. Ensamblado ----------
df = legacy.merge(disagg, on="fecha", how="left")
# asof hacia atras: si el martes fue festivo sin cotizacion, usa el ultimo cierre anterior
df = pd.merge_asof(df.sort_values("fecha"), px, on="fecha", direction="backward")
df["cierre_martes"] = df["cierre_martes"].round(2)

int_cols = [c for c in df.columns if c.startswith(("open_", "noncomm", "comm", "nonrep",
            "mm_", "swap_", "prod_", "other_", "traders"))]
for c in int_cols:
    df[c] = df[c].astype("Int64")

ORDEN = ["fecha", "cierre_martes", "fuente_precio", "open_interest",
         "noncomm_long", "noncomm_short", "noncomm_spreads",
         "comm_long", "comm_short", "nonrep_long", "nonrep_short",
         "mm_long", "mm_short", "mm_spreads",
         "swap_long", "swap_short", "swap_spreads",
         "prod_long", "prod_short",
         "other_long", "other_short", "other_spreads",
         "conc_4_long", "conc_4_short", "conc_8_long", "conc_8_short",
         "traders_total", "traders_noncomm_long", "traders_noncomm_short"]
df = df[ORDEN].sort_values("fecha").reset_index(drop=True)

# ---------- 5. Validacion (falla visible en el workflow) ----------
errores = []
ultima = df.fecha.iloc[-1]
if ultima.weekday() != 1:
    errores.append(f"la ultima fecha ({ultima.date()}) no es martes")
antiguedad = (date.today() - ultima.date()).days
if antiguedad > 12:
    errores.append(f"la ultima fecha ({ultima.date()}) tiene {antiguedad} dias "
                   "(>12: falta el informe reciente de la CFTC)")
cola = df.tail(5)
for col in ("open_interest", "noncomm_long", "noncomm_short", "cierre_martes"):
    if cola[col].isna().any():
        errores.append(f"valores vacios en '{col}' en las ultimas filas")
if len(df) < 1900:
    errores.append(f"solo {len(df)} filas (<1900: historico incompleto)")
if df.fecha.duplicated().any():
    errores.append("fechas duplicadas")

if errores:
    print("VALIDACION FALLIDA:", flush=True)
    for e in errores:
        print(f"  - {e}", flush=True)
    sys.exit(1)

df["fecha"] = df["fecha"].dt.strftime("%Y-%m-%d")
df.to_csv(OUT, index=False, encoding="utf-8")
print(f"OK -> {OUT}  ({len(df):,} filas, {df['fecha'].iloc[0]} a {df['fecha'].iloc[-1]})", flush=True)
