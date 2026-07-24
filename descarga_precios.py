# -*- coding: utf-8 -*-
"""Genera oro_diario.csv y oro_1h.csv: precio del futuro GC=F (COMEX) via yfinance.

  - oro_diario.csv: OHLC + volumen diario, historico maximo disponible (~2000-presente)
  - oro_1h.csv: OHLC + volumen en velas de 1 hora (UTC), ventana rodante de 30 dias,
    con columna gap_apertura (apertura menos cierre de la vela anterior) que deja
    medidos los huecos de fin de semana y del cierre diario de COMEX

Pensado para correr en GitHub Actions cada madrugada. Valida el resultado antes de
guardar y termina con exit code 1 sin tocar los ficheros si algo no cuadra (asi el
workflow conserva la version previa y no commitea datos rotos).

Uso:  python descarga_precios.py
"""
import sys
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO = Path(__file__).resolve().parent
OUT_DIARIO = REPO / "oro_diario.csv"
OUT_1H = REPO / "oro_1h.csv"

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


def preparar(df, descripcion):
    """Aplana el MultiIndex de yf.download, renombra a espanol y redondea precios."""
    if df is None or df.empty:
        raise SystemExit(f"yfinance devolvio vacio para {descripcion}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "apertura", "High": "maximo",
                            "Low": "minimo", "Close": "cierre", "Volume": "volumen"})
    df = df[["apertura", "maximo", "minimo", "cierre", "volumen"]]
    df = df.dropna(subset=["cierre"]).sort_index()
    for c in ("apertura", "maximo", "minimo", "cierre"):
        df[c] = df[c].round(2)
    df["volumen"] = df["volumen"].fillna(0).astype("int64")
    return df


# ---------- 1. Diario (historico maximo) ----------
print("Descargando GC=F diario (period=max)...", flush=True)
diario = preparar(
    reintentar(lambda: yf.download("GC=F", period="max", interval="1d", progress=False),
               "descarga GC=F diario"),
    "GC=F diario")
out_d = diario.reset_index(drop=True)
out_d.insert(0, "fecha", [d.date() for d in pd.to_datetime(diario.index)])
print(f"  Diario: {len(out_d):,} filas ({out_d.fecha.iloc[0]} a {out_d.fecha.iloc[-1]})",
      flush=True)

# ---------- 2. Horario (ventana rodante de 30 dias) ----------
print("Descargando GC=F horario (period=30d, interval=1h)...", flush=True)
hora = preparar(
    reintentar(lambda: yf.download("GC=F", period="30d", interval="1h", progress=False),
               "descarga GC=F horario"),
    "GC=F horario")
idx = pd.to_datetime(hora.index)
idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
out_h = hora.reset_index(drop=True)
out_h.insert(0, "fecha_hora", idx.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
# gap entre velas: mide los huecos del cierre diario COMEX (22:00-23:00 UTC) y del finde
out_h["gap_apertura"] = (out_h["apertura"] - out_h["cierre"].shift(1)).round(2)
print(f"  Horario: {len(out_h):,} velas ({out_h.fecha_hora.iloc[0]} a "
      f"{out_h.fecha_hora.iloc[-1]})", flush=True)

# ---------- 3. Validacion (falla visible en el workflow, sin tocar ficheros) ----------
errores = []
if len(out_d) <= 5000:
    errores.append(f"oro_diario: solo {len(out_d)} filas (<=5000: historico incompleto)")
edad_d = (date.today() - out_d.fecha.iloc[-1]).days
if edad_d > 5:
    errores.append(f"oro_diario: ultima fecha ({out_d.fecha.iloc[-1]}) tiene {edad_d} dias (>5)")
if len(out_h) <= 300:
    errores.append(f"oro_1h: solo {len(out_h)} velas (<=300: descarga intradia incompleta)")
edad_h = (datetime.now(timezone.utc) - idx.max()).total_seconds() / 3600
if edad_h > 72:
    errores.append(f"oro_1h: ultima vela ({idx.max()}) tiene {edad_h:.0f} horas (>72)")

if errores:
    print("VALIDACION FALLIDA (se conservan los ficheros previos):", flush=True)
    for e in errores:
        print(f"  - {e}", flush=True)
    sys.exit(1)

out_d.to_csv(OUT_DIARIO, index=False, encoding="utf-8")
out_h.to_csv(OUT_1H, index=False, encoding="utf-8")
print(f"OK -> {OUT_DIARIO}  ({len(out_d):,} filas)", flush=True)
print(f"OK -> {OUT_1H}  ({len(out_h):,} velas)", flush=True)
