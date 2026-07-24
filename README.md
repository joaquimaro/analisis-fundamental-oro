# analisis-fundamental-oro

Datos para el análisis fundamental del oro en CSVs listos para analizar: histórico semanal del informe **COT (Commitments of Traders) del oro COMEX** (código CFTC `088691`, contratos de 100 onzas troy) desde enero de 1986, más dos series de precio del futuro **GC=F** y otras dos del **índice dólar DXY** (`DX-Y.NYB`): velas diarias (histórico completo) y velas de 1 hora (últimos 30 días) de cada uno.

> Este repo se llamaba **cot-oro** hasta el 24-07-2026; GitHub redirige las URLs antiguas, pero la fuente canónica es la nueva.

**URLs raw de los datasets (fuente canónica):**

```
https://raw.githubusercontent.com/joaquimaro/analisis-fundamental-oro/main/cot_gold_historico.csv
https://raw.githubusercontent.com/joaquimaro/analisis-fundamental-oro/main/oro_diario.csv
https://raw.githubusercontent.com/joaquimaro/analisis-fundamental-oro/main/oro_1h.csv
https://raw.githubusercontent.com/joaquimaro/analisis-fundamental-oro/main/dxy_diario.csv
https://raw.githubusercontent.com/joaquimaro/analisis-fundamental-oro/main/dxy_1h.csv
https://raw.githubusercontent.com/joaquimaro/analisis-fundamental-oro/main/tipos.csv
```

## Qué contiene

Cada fila es un informe semanal de la CFTC (snapshot del **martes** al cierre, publicado el **viernes siguiente a las 15:30 ET**). Se combinan tres fuentes públicas:

- **COT Legacy futures-only** (CFTC): categorías Non-Commercial / Commercial / Non-Reportable, concentración neta de los mayores traders y número de traders. Desde 1986.
- **COT Disaggregated futures-only** (CFTC): desglose Managed Money / Swap Dealers / Producer-Merchant / Other Reportables. **Solo existe desde el 13-06-2006** — antes esas columnas van vacías.
- **Cierre del martes**: precio del oro al cierre del día del snapshot.

## Columnas

| Columna | Descripción |
|---|---|
| `fecha` | Martes del snapshot (YYYY-MM-DD) |
| `cierre_martes` | Cierre del oro ese martes (USD/oz); si fue festivo, último cierre anterior |
| `fuente_precio` | `spot` (fix PM LBMA) o `gc_futuro` (futuro GC=F) — ver empalme abajo |
| `open_interest` | Interés abierto total |
| `noncomm_long / noncomm_short / noncomm_spreads` | Posiciones Non-Commercial (especuladores) |
| `comm_long / comm_short` | Posiciones Commercial (coberturas) |
| `nonrep_long / nonrep_short` | Posiciones Non-Reportable (pequeños) |
| `mm_long / mm_short / mm_spreads` | Managed Money (fondos) — desde jun-2006 |
| `swap_long / swap_short / swap_spreads` | Swap Dealers — desde jun-2006 |
| `prod_long / prod_short` | Producer/Merchant/Processor/User — desde jun-2006 |
| `other_long / other_short / other_spreads` | Other Reportables — desde jun-2006 |
| `conc_4_long / conc_4_short` | % del OI en manos de los 4 mayores traders (posición **neta**) |
| `conc_8_long / conc_8_short` | Ídem, 8 mayores traders |
| `traders_total` | Número total de traders reportables |
| `traders_noncomm_long / traders_noncomm_short` | Traders Non-Commercial por lado |

## Empalme del precio (columna `fuente_precio`)

- **1986 → 29-08-2000**: fix **PM de la LBMA** (precio spot de Londres, USD/oz) → `fuente_precio = spot`. Yahoo Finance no tiene el futuro GC=F antes de esa fecha.
- **30-08-2000 → hoy**: cierre diario del futuro **GC=F (COMEX)** vía yfinance → `fuente_precio = gc_futuro`, coherente con el mercado sobre el que se reporta el COT.

Entre spot y futuro existe una pequeña base (contango), así que al comparar precios a caballo del empalme conviene tener en cuenta la columna `fuente_precio`.

## Series de precio GC=F (`oro_diario.csv` y `oro_1h.csv`)

Dos ficheros con el precio del **futuro de oro GC=F (COMEX)** descargado de yfinance, regenerados **cada madrugada a las 05:30 UTC** (redondeo a 2 decimales):

### `oro_diario.csv` — velas diarias, histórico máximo disponible (~ago-2000 → hoy)

| Columna | Descripción |
|---|---|
| `fecha` | Día de la vela (YYYY-MM-DD) |
| `apertura` / `maximo` / `minimo` / `cierre` | OHLC en USD/oz, 2 decimales |
| `volumen` | Volumen negociado del contrato frontal según Yahoo Finance |

> yfinance no publica el **open interest** de GC=F, por eso el fichero no lo incluye. Para OI está la columna `open_interest` (semanal) del CSV del COT.

### `oro_1h.csv` — velas de 1 hora, ventana rodante de 30 días

| Columna | Descripción |
|---|---|
| `fecha_hora` | Inicio de la vela en **UTC**, con sufijo explícito de zona (`2026-07-24T13:00:00+00:00`) |
| `apertura` / `maximo` / `minimo` / `cierre` | OHLC en USD/oz, 2 decimales |
| `volumen` | Volumen de la vela |
| `gap_apertura` | Apertura de la vela menos cierre de la vela anterior: deja medidos en el propio fichero los huecos del cierre diario de COMEX (~1 h entre las 21:00 y las 22:00 UTC según horario de verano de EE. UU.) y del fin de semana. Vacío en la primera fila |

> ⚠️ **GC=F es el futuro COMEX, no el spot XAUUSD**: los niveles difieren ligeramente (base/contango, normalmente unos pocos dólares) y el futuro tiene huecos de negociación (cierre diario + fin de semana) que el spot OTC casi no tiene. Para casar niveles exactos con un broker de XAUUSD hay que contar con ese desfase.

## Series de precio del DXY (`dxy_diario.csv` y `dxy_1h.csv`)

Mismo tratamiento que el oro, aplicado al **índice dólar DXY** con el ticker **`DX-Y.NYB`** de Yahoo Finance: el **US Dollar Index de ICE al contado** (el índice en sí, no el futuro DX). Se regeneran en el mismo cron diario de las 05:30 UTC.

- **`dxy_diario.csv`** — velas diarias, histórico máximo disponible (**ene-1971 → hoy**, >14.000 filas). Mismas columnas que `oro_diario.csv` (`fecha`, `apertura`, `maximo`, `minimo`, `cierre`, `volumen`).
- **`dxy_1h.csv`** — velas de 1 hora en UTC, ventana rodante de 30 días. Mismas columnas que `oro_1h.csv`, incluida `gap_apertura` (apertura menos cierre de la vela anterior), que aquí mide los huecos del cierre de la sesión ICE y del fin de semana.

Diferencias respecto a los ficheros del oro:

- Los precios van redondeados a **3 decimales** (el índice cotiza con más precisión que el futuro del oro, que usa 2).
- La columna `volumen` existe para mantener el esquema idéntico, pero **siempre vale 0**: DX-Y.NYB es un índice calculado, no un instrumento negociado, y Yahoo no publica volumen para él. Para volumen real habría que mirar el futuro DX de ICE (no disponible en Yahoo, ver nota siguiente).
- Si la validación del DXY falla en el cron pero la del oro pasa, el workflow **commitea igualmente el oro** y deja el fallo del DXY anotado como *warning* en la ejecución de Actions, conservando la última versión buena de los ficheros del DXY.

> **Por qué `DX-Y.NYB` y no `DX=F`**: se probó el futuro `DX=F` como alternativa, pero Yahoo Finance ya no lo sirve (responde 404 / "possibly delisted" tanto en diario como en intradía, comprobado el 24-07-2026). `DX-Y.NYB` en cambio devuelve histórico diario desde 1971 e intradía 1h de forma fiable, así que es el ticker activo.

## Tipos de interés y crédito (`tipos.csv`)

Serie diaria de tipos y crédito descargada de **FRED** (St. Louis Fed) por URL pública (`fredgraph.csv?id=SERIE`, sin API key), regenerada en el mismo cron diario de las 05:30 UTC por `descarga_tipos.py`. FRED publica con **1-2 días hábiles de retraso**, así que el último dato normalmente es de anteayer.

| Columna | Serie FRED | Descripción |
|---|---|---|
| `fecha` | — | Día del dato (YYYY-MM-DD); solo días con dato publicado en alguna serie, sin interpolar fines de semana ni festivos |
| `nominal_10a` | `DGS10` | Treasury 10 años, rendimiento nominal (%). Desde 1962 |
| `real_10a` | `DFII10` | TIPS 10 años, rendimiento real (%). Desde 2003 |
| `breakeven_10a` | calculada | `nominal_10a − real_10a`: inflación implícita a 10 años. Solo en filas donde existen ambas patas |
| `spread_hy` | `BAMLH0A0HYM2` | Spread high yield ICE BofA (puntos porcentuales sobre Treasuries) |

Interpretación rápida de cara al oro:

- **`real_10a` alto (o subiendo) presiona al oro a la baja**: el tipo real es el coste de oportunidad de un activo sin rendimiento; es la correlación macro más fiable del XAUUSD.
- **`breakeven_10a` subiendo** = mercado descontando más inflación, viento a favor del oro como cobertura.
- **`spread_hy` estrechándose** = apetito por riesgo, viento en contra del oro refugio; **ampliándose** = estrés de crédito, viento a favor.

> ⚠️ **`spread_hy` solo cubre los últimos ~3 años**: `BAMLH0A0HYM2` es una serie licenciada de ICE BofA y FRED limita su descarga por URL pública a esa ventana (ignora el parámetro `cosd`, comprobado el 24-07-2026; el histórico completo desde 1996 solo está disponible con API key). Las celdas anteriores a esa ventana van vacías. Los huecos (`.` de FRED) se dejan como celda vacía, nunca como cero.

La validación previa al commit exige >5000 filas, último `real_10a` con dato a ≤7 días naturales y dentro del rango −3 a +5. Si falla, el paso queda en rojo **sin tocar `tipos.csv`** (se conserva la última versión buena) y el resto del pipeline (oro, DXY, COT) sigue commiteando con normalidad.

## Actualización

GitHub Actions ejecuta el pipeline con tres crons:

- **Diario, 05:30 UTC**: `descarga_precios.py` (los cuatro ficheros de precio: `oro_diario.csv`, `oro_1h.csv`, `dxy_diario.csv`, `dxy_1h.csv`) + `descarga_tipos.py` (`tipos.csv`).
- **Sábado y domingo, 06:00 UTC** (08:00 Madrid en horario de verano): los tres scripts — full rebuild del COT 1986→hoy tras la publicación del viernes de la CFTC (el domingo es reintento inocuo) + precios + tipos.

Ambos scripts validan la integridad del resultado antes de guardar (número de filas mínimo y frescura de la última fecha/vela); si la validación falla, el job termina en error **sin commitear**, conservando la versión previa de los ficheros. Si no hay datos nuevos no se crea commit. También puede lanzarse a mano desde la pestaña Actions (`workflow_dispatch`, ejecuta ambos scripts).

## Regenerar en local

```bash
pip install -r requirements.txt
python build_cot_gold_csv.py
python descarga_precios.py
python descarga_tipos.py
```
