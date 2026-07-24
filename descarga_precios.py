# -*- coding: utf-8 -*-
"""Genera las series de precio del repo via yfinance, un par de ficheros por ticker:

  - ORO  (futuro GC=F, COMEX):        oro_diario.csv  + oro_1h.csv
  - DXY  (indice dolar ICE DX-Y.NYB): dxy_diario.csv  + dxy_1h.csv

Por cada ticker:
  - *_diario.csv: OHLC + volumen diario, historico maximo disponible
  - *_1h.csv: OHLC + volumen en velas de 1 hora (UTC), ventana rodante de 30 dias,
    con columna gap_apertura (apertura menos cierre de la vela anterior) que deja
    medidos los huecos de fin de semana y del cierre diario de la sesion

Pensado para correr en GitHub Actions cada madrugada. Valida cada par antes de
guardarlo; si la validacion del ORO falla, termina con exit code 1 sin tocar nada
(el workflow conserva la version previa y no commitea datos rotos). Si falla solo
el DXY, guarda el oro, reporta el fallo del DXY como warning y sale con exit 0
para no bloquear el resto del pipeline.

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

# (ticker, prefijo de fichero, etiqueta, decimales de precio)
# El DXY se redondea a 3 decimales: el indice cotiza con mas precision que GC=F.
SERIES = [
    ("GC=F", "oro", "oro GC=F", 2),
    ("DX-Y.NYB", "dxy", "DXY DX-Y.NYB", 3),
]

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


def preparar(df, descripcion, decimales):
    """Aplana el MultiIndex de yf.download, renombra a espanol y redondea precios."""
    if df is None or df.empty:
        raise RuntimeError(f"yfinance devolvio vacio para {descripcion}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "apertura", "High": "maximo",
                            "Low": "minimo", "Close": "cierre", "Volume": "volumen"})
    df = df[["apertura", "maximo", "minimo", "cierre", "volumen"]]
    df = df.dropna(subset=["cierre"]).sort_index()
    for c in ("apertura", "maximo", "minimo", "cierre"):
        df[c] = df[c].round(decimales)
    df["volumen"] = df["volumen"].fillna(0).astype("int64")
    return df


def generar_par(ticker, etiqueta, decimales):
    """Descarga diario (historico maximo) + 1h (30 dias) de un ticker.

    Devuelve (out_diario, out_1h, errores): los dos DataFrames listos para CSV y la
    lista de errores de validacion (vacia si el par es valido). No escribe a disco.
    """
    print(f"Descargando {etiqueta} diario (period=max)...", flush=True)
    diario = preparar(
        reintentar(lambda: yf.download(ticker, period="max", interval="1d", progress=False),
                   f"descarga {etiqueta} diario"),
        f"{etiqueta} diario", decimales)
    out_d = diario.reset_index(drop=True)
    out_d.insert(0, "fecha", [d.date() for d in pd.to_datetime(diario.index)])
    print(f"  Diario: {len(out_d):,} filas ({out_d.fecha.iloc[0]} a {out_d.fecha.iloc[-1]})",
          flush=True)

    print(f"Descargando {etiqueta} horario (period=30d, interval=1h)...", flush=True)
    hora = preparar(
        reintentar(lambda: yf.download(ticker, period="30d", interval="1h", progress=False),
                   f"descarga {etiqueta} horario"),
        f"{etiqueta} horario", decimales)
    idx = pd.to_datetime(hora.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    out_h = hora.reset_index(drop=True)
    out_h.insert(0, "fecha_hora", idx.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
    # gap entre velas: mide los huecos del cierre diario de la sesion y del finde
    out_h["gap_apertura"] = (out_h["apertura"] - out_h["cierre"].shift(1)).round(decimales)
    print(f"  Horario: {len(out_h):,} velas ({out_h.fecha_hora.iloc[0]} a "
          f"{out_h.fecha_hora.iloc[-1]})", flush=True)

    errores = []
    if len(out_d) <= 5000:
        errores.append(f"{etiqueta} diario: solo {len(out_d)} filas (<=5000: historico incompleto)")
    edad_d = (date.today() - out_d.fecha.iloc[-1]).days
    if edad_d > 5:
        errores.append(f"{etiqueta} diario: ultima fecha ({out_d.fecha.iloc[-1]}) "
                       f"tiene {edad_d} dias (>5)")
    if len(out_h) <= 300:
        errores.append(f"{etiqueta} 1h: solo {len(out_h)} velas (<=300: descarga intradia incompleta)")
    edad_h = (datetime.now(timezone.utc) - idx.max()).total_seconds() / 3600
    if edad_h > 72:
        errores.append(f"{etiqueta} 1h: ultima vela ({idx.max()}) tiene {edad_h:.0f} horas (>72)")
    return out_d, out_h, errores


def guardar_par(prefijo, out_d, out_h):
    ruta_d = REPO / f"{prefijo}_diario.csv"
    ruta_h = REPO / f"{prefijo}_1h.csv"
    out_d.to_csv(ruta_d, index=False, encoding="utf-8")
    out_h.to_csv(ruta_h, index=False, encoding="utf-8")
    print(f"OK -> {ruta_d}  ({len(out_d):,} filas)", flush=True)
    print(f"OK -> {ruta_h}  ({len(out_h):,} velas)", flush=True)


resultados = {}
for ticker, prefijo, etiqueta, decimales in SERIES:
    try:
        resultados[prefijo] = generar_par(ticker, etiqueta, decimales)
    except Exception as e:
        resultados[prefijo] = (None, None, [f"{etiqueta}: descarga fallida ({e})"])

# El oro es la serie primaria: si falla, no se escribe nada y el job termina en rojo.
out_d_oro, out_h_oro, errores_oro = resultados["oro"]
if errores_oro:
    print("VALIDACION FALLIDA del oro (se conservan los ficheros previos):", flush=True)
    for e in errores_oro:
        print(f"  - {e}", flush=True)
    sys.exit(1)
guardar_par("oro", out_d_oro, out_h_oro)

# El DXY es secundario: si falla su validacion, se reporta como warning visible en
# Actions y se sale con exit 0 para que el commit del oro siga adelante.
out_d_dxy, out_h_dxy, errores_dxy = resultados["dxy"]
if errores_dxy:
    print("VALIDACION FALLIDA del DXY (se conservan sus ficheros previos; el oro si se guarda):",
          flush=True)
    for e in errores_dxy:
        print(f"  - {e}", flush=True)
        print(f"::warning title=DXY no actualizado::{e}", flush=True)
    sys.exit(0)
guardar_par("dxy", out_d_dxy, out_h_dxy)
