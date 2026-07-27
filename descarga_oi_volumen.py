# -*- coding: utf-8 -*-
"""Genera oi_volumen.csv: volumen y open interest DIARIOS agregados del futuro GC (COMEX).

Fuente: API interna de Barchart (core-api, EOD por contrato), sumando TODOS los
vencimientos vivos del GC: 12 codigos de mes (F,G,H,J,K,M,N,Q,U,V,X,Z) x anos.
Es la unica forma de reproducir el total que publica cmegroup.com (el front-month
solo es ~70-80% del total). Portado del colector de Botzilla validado contra CME.
Por construccion la serie es de futuros puros: la raiz "GC" excluye opciones y
el Micro Gold (raiz MGC).

Ventana rodante de 12 meses, full rebuild en cada ejecucion. SIN fallback: si
Barchart no responde, exit 1 sin escribir (una fila ausente es mejor que el OI
de un solo contrato contaminando la serie).

La serie replica el "Total Volume" FINAL de CME (Globex + PNT/ClearPort, es
decir incluye bloques/EFP/EFR ex-pit). Validado al contrato: 23-jul-2026
Globex 221,587 + PNT 7,349 = 228,936 = nuestra fila.

Estado por fila:
  - "final": CME ya publico el dato definitivo de la sesion (T+1 habil ~10:10 CT)
  - "preliminar": la ULTIMA sesion, siempre — su volumen y su OI aun pueden
    revisarse (el volumen final incorpora el ex-pit, tipicamente +5-10% sobre
    el preliminar que sirve Barchart). Si el OI aun no esta publicado la celda
    va VACIA (no se arrastra el del dia anterior)

La sesion EN CURSO (fecha de hoy) se excluye siempre: su volumen aun es parcial
(la sesion COMEX del dia arranca a las 22:00 UTC de la vispera).

Validaciones antes de guardar (exit 1 sin escribir si alguna falla):
  - los MARTES el OI agregado debe cuadrar con open_interest de
    cot_gold_historico.csv (CFTC, fuente oficial independiente)
  - minimo de filas, frescura de la ultima sesion, sin fechas duplicadas,
    recuento no muy inferior al del fichero previo

Uso:  python descarga_oi_volumen.py [salida.csv]
"""
import csv
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "oi_volumen.csv"
COT_CSV = REPO / "cot_gold_historico.csv"

MESES = "FGHJKMNQUVXZ"          # los 12 codigos, incluidos los seriales con OI minusculo
ANOS_FUTURO = 6                  # CME lista GC hasta ~6 anos vista
VENTANA_DIAS = 365               # ventana rodante de 12 meses
TOLERANCIA_COT = 5               # contratos de margen en el cuadre del martes
MIN_FILAS = 235                  # ~251 sesiones/ano menos festivos de margen
MAX_ANTIGUEDAD_DIAS = 6          # la ultima sesion no puede ser mas vieja (cubre festivos largos)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def reintentar(fn, descripcion, intentos=3):
    for i in range(1, intentos + 1):
        try:
            return fn()
        except Exception as e:
            if i == intentos:
                raise
            espera = 10 * i
            print(f"  AVISO: {descripcion} fallo (intento {i}/{intentos}): {e}. "
                  f"Reintento en {espera}s...", flush=True)
            time.sleep(espera)


def sesion_barchart():
    """Sesion con cookies + header X-XSRF-TOKEN listos para la core-api."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    r = s.get("https://www.barchart.com/futures/quotes/GCZ26/overview", timeout=30)
    r.raise_for_status()
    tok = s.cookies.get("XSRF-TOKEN")
    if not tok:
        raise RuntimeError("Barchart no devolvio la cookie XSRF-TOKEN")
    s.headers.update({"X-XSRF-TOKEN": urllib.parse.unquote(tok)})
    return s


def num(x):
    try:
        return int(float(str(x).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def eod_contrato(s, simbolo, inicio, fin):
    """Filas EOD {fecha, volumen, oi} de un contrato. Lanza excepcion si HTTP falla."""
    def _get():
        r = s.get("https://www.barchart.com/proxies/core-api/v1/historical/get",
                  params={"symbol": simbolo,
                          "fields": "tradeTime.format(Y-m-d),lastPrice,volume,openInterest",
                          "type": "eod", "startDate": inicio, "endDate": fin,
                          "orderBy": "tradeTime", "orderDir": "asc"},
                  timeout=30)
        r.raise_for_status()
        return r.json().get("data") or []
    filas = []
    for d in reintentar(_get, f"EOD {simbolo}"):
        fecha = (d.get("tradeTime") or "").strip()
        vol, oi = num(d.get("volume")), num(d.get("openInterest"))
        if not RE_FECHA.match(fecha) or (vol is None and oi is None):
            continue  # Barchart devuelve filas 'N/A' en contratos sin negociar
        filas.append({"fecha": fecha, "vol": vol or 0, "oi": oi or 0})
    return filas


# ---------- 1. Descarga y agregado (suma estilo cmegroup.com) ----------
hoy = date.today()
inicio = (hoy - timedelta(days=VENTANA_DIAS)).isoformat()
fin = hoy.isoformat()
print(f"Descargando EOD Barchart de todos los meses GC ({inicio} a {fin})...", flush=True)

s = reintentar(sesion_barchart, "sesion Barchart")
agg = defaultdict(lambda: {"volumen": 0, "oi": 0, "_vol_activo": -1, "contrato": ""})
n_contratos = 0
for ano in range(hoy.year - 1, hoy.year + ANOS_FUTURO + 1):
    ano_con_datos = False
    for c in MESES:
        simbolo = f"GC{c}{ano % 100:02d}"
        filas = eod_contrato(s, simbolo, inicio, fin)
        if filas:
            ano_con_datos = True
            n_contratos += 1
            for f in filas:
                a = agg[f["fecha"]]
                a["volumen"] += f["vol"]
                a["oi"] += f["oi"]
                if f["vol"] > a["_vol_activo"]:
                    a["_vol_activo"], a["contrato"] = f["vol"], simbolo
        time.sleep(0.5)  # Barchart devuelve 429 con rafagas mas agresivas
    if not ano_con_datos and ano >= hoy.year:
        break  # ano futuro entero sin datos: no hay vencimientos mas lejanos
print(f"  {n_contratos} contratos con datos, {len(agg)} sesiones", flush=True)

# ---------- 2. Filas + estado final/preliminar ----------
# la sesion en curso (hoy) se descarta: volumen parcial intradia
fechas = sorted(f for f in agg if f < fin)
# cola sin OI liquidado (Barchart da 0, o un parcial muy bajo si pilla la
# liquidacion a medias): su OI va vacio, no se arrastra el previo
sin_liquidar = 0
while sin_liquidar < len(fechas) and agg[fechas[-1 - sin_liquidar]]["oi"] == 0:
    sin_liquidar += 1
filas_csv = []
for i, fecha in enumerate(fechas):
    a = agg[fecha]
    oi_previo = agg[fechas[i - 1]]["oi"] if i else None
    # la ultima sesion es SIEMPRE preliminar: CME no publica su dato final
    # (volumen con ex-pit + OI liquidado) hasta el dia habil siguiente
    preliminar = (i == len(fechas) - 1 or
                  (i >= len(fechas) - sin_liquidar - 1 and
                   (a["oi"] == 0 or (oi_previo and a["oi"] < 0.9 * oi_previo))))
    filas_csv.append({
        "fecha": fecha,
        "volumen": a["volumen"],
        "open_interest": "" if (preliminar and a["oi"] == 0) else a["oi"],
        "estado": "preliminar" if preliminar else "final",
        "contrato_activo": a["contrato"],
    })

# ---------- 3. Validacion (falla visible en el workflow, sin escribir) ----------
errores = []

if len(filas_csv) < MIN_FILAS:
    errores.append(f"solo {len(filas_csv)} sesiones (<{MIN_FILAS}: ventana incompleta)")
if len(fechas) != len(set(fechas)):
    errores.append("fechas duplicadas")
if fechas:
    antiguedad = (hoy - date.fromisoformat(fechas[-1])).days
    if antiguedad > MAX_ANTIGUEDAD_DIAS:
        errores.append(f"la ultima sesion ({fechas[-1]}) tiene {antiguedad} dias "
                       f"(>{MAX_ANTIGUEDAD_DIAS}: datos rancios)")

# cuadre de los martes contra la CFTC (detecta que Barchart cambie o degrade el endpoint)
oi_cot = {}
with open(COT_CSV, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if row.get("open_interest"):
            oi_cot[row["fecha"]] = int(row["open_interest"])
martes_ok, desvio_max = 0, 0
for fila in filas_csv:
    if fila["estado"] != "final" or fila["fecha"] not in oi_cot:
        continue
    if date.fromisoformat(fila["fecha"]).weekday() != 1:
        continue
    desvio = abs(fila["open_interest"] - oi_cot[fila["fecha"]])
    desvio_max = max(desvio_max, desvio)
    if desvio > TOLERANCIA_COT:
        errores.append(f"martes {fila['fecha']}: OI Barchart {fila['open_interest']:,} "
                       f"vs COT {oi_cot[fila['fecha']]:,} (desvio {desvio})")
    else:
        martes_ok += 1
if martes_ok < 30:
    errores.append(f"solo {martes_ok} martes cuadrados contra el COT (<30: el chequeo no cubre)")
print(f"  Cuadre COT: {martes_ok} martes OK, desvio maximo {desvio_max} contratos", flush=True)

# el full rebuild no puede encoger mucho respecto al fichero previo (mismo criterio que el COT)
if OUT.exists():
    with open(OUT, newline="", encoding="utf-8-sig") as f:
        previas = sum(1 for _ in csv.DictReader(f))
    if len(filas_csv) < previas - 10:
        errores.append(f"{len(filas_csv)} filas vs {previas} previas: el rebuild encoge demasiado")

if errores:
    print("VALIDACION FALLIDA (no se escribe el CSV):", flush=True)
    for e in errores:
        print(f"  - {e}", flush=True)
    sys.exit(1)

# ---------- 4. Escritura ----------
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["fecha", "volumen", "open_interest",
                                      "estado", "contrato_activo"])
    w.writeheader()
    w.writerows(filas_csv)
ult = filas_csv[-1]
print(f"OK -> {OUT}  ({len(filas_csv):,} filas, {filas_csv[0]['fecha']} a {ult['fecha']}; "
      f"ultima sesion {ult['estado']})", flush=True)
