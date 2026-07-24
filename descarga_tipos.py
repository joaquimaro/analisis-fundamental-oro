# -*- coding: utf-8 -*-
"""Genera tipos.csv: tipos de interes y credito desde FRED via URL publica (sin API key).

Series (https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIE):
  - DGS10        -> nominal_10a   Treasury 10 anos, rendimiento nominal (desde 1962)
  - DFII10       -> real_10a      TIPS 10 anos, rendimiento real (desde 2003)
  - BAMLH0A0HYM2 -> spread_hy     Spread high yield ICE BofA (FRED solo sirve los
                                  ultimos ~3 anos por URL publica: serie licenciada)
  - breakeven_10a = nominal_10a - real_10a, solo donde existen ambas

Union por fecha con outer join: cada fila es un dia con dato publicado en al menos
una serie; los huecos ('.' de FRED, fines de semana, festivos) quedan como celda
vacia, nunca como cero ni interpolados. FRED publica con 1-2 dias habiles de retraso.

Valida antes de guardar y termina con exit code 1 sin tocar tipos.csv si algo no
cuadra (el workflow marca el paso en rojo pero el resto del pipeline sigue).

Uso:  python descarga_tipos.py
"""
import io
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parent
OUT = REPO / "tipos.csv"

# (id FRED, nombre de columna) — los nombres son contrato con los consumidores: NO renombrar
SERIES = [
    ("DGS10", "nominal_10a"),
    ("DFII10", "real_10a"),
    ("BAMLH0A0HYM2", "spread_hy"),
]

# FRED responde con challenge/cuelgue a algunos User-Agent; el de curl funciona estable
CABECERAS = {"User-Agent": "curl/8.0"}


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


def descargar_serie(serie_id, columna):
    """Descarga una serie de fredgraph.csv y la devuelve como DataFrame fecha/valor."""
    # cosd fija el inicio del rango: sin el, algunas series recortan el historico
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie_id}&cosd=1960-01-01"

    def _get():
        r = requests.get(url, headers=CABECERAS, timeout=60)
        r.raise_for_status()
        return r.text

    texto = reintentar(_get, f"descarga FRED {serie_id}")
    df = pd.read_csv(io.StringIO(texto))
    if df.shape[1] != 2 or df.empty:
        raise SystemExit(f"FRED devolvio un CSV inesperado para {serie_id}: "
                         f"{df.shape[1]} columnas, {len(df)} filas")
    # primera columna = fecha (FRED la llama observation_date; antes era DATE)
    df.columns = ["fecha", columna]
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    # los '.' de dias sin dato se convierten a NaN, nunca a cero
    df[columna] = pd.to_numeric(df[columna], errors="coerce")
    print(f"  {serie_id} -> {columna}: {len(df):,} filas "
          f"({df.fecha.iloc[0]} a {df.fecha.iloc[-1]})", flush=True)
    return df


print("Descargando series de FRED...", flush=True)
tipos = None
for serie_id, columna in SERIES:
    df = descargar_serie(serie_id, columna)
    tipos = df if tipos is None else tipos.merge(df, on="fecha", how="outer")

tipos = tipos.sort_values("fecha").reset_index(drop=True)
# breakeven solo donde existen ambas patas (la resta con NaN ya propaga NaN)
tipos["breakeven_10a"] = (tipos["nominal_10a"] - tipos["real_10a"]).round(2)
tipos = tipos[["fecha", "nominal_10a", "real_10a", "breakeven_10a", "spread_hy"]]
print(f"Union: {len(tipos):,} filas ({tipos.fecha.iloc[0]} a {tipos.fecha.iloc[-1]})",
      flush=True)

# ---------- Validacion (falla visible en el workflow, sin tocar tipos.csv) ----------
errores = []
if len(tipos) <= 5000:
    errores.append(f"tipos: solo {len(tipos)} filas (<=5000: historico incompleto)")
con_real = tipos.dropna(subset=["real_10a"])
if con_real.empty:
    errores.append("tipos: real_10a no tiene ningun dato")
else:
    ultima_fecha = con_real.fecha.iloc[-1]
    ultimo_real = con_real.real_10a.iloc[-1]
    edad = (date.today() - ultima_fecha).days
    if edad > 7:
        errores.append(f"tipos: ultimo real_10a con dato ({ultima_fecha}) "
                       f"tiene {edad} dias naturales (>7)")
    if not (-3 <= ultimo_real <= 5):
        errores.append(f"tipos: ultimo real_10a ({ultimo_real}) fuera del rango [-3, +5]")

if errores:
    print("VALIDACION FALLIDA (se conserva el tipos.csv previo):", flush=True)
    for e in errores:
        print(f"  - {e}", flush=True)
    sys.exit(1)

tipos.to_csv(OUT, index=False, encoding="utf-8")
ult = tipos.ffill().iloc[-1]
print(f"OK -> {OUT}  ({len(tipos):,} filas)", flush=True)
print(f"  Ultimos valores: nominal_10a={ult.nominal_10a}  real_10a={ult.real_10a}  "
      f"breakeven_10a={ult.breakeven_10a}  spread_hy={ult.spread_hy}", flush=True)
