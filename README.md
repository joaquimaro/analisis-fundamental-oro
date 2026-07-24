# cot-oro

Histórico semanal del informe **COT (Commitments of Traders) del oro COMEX** (código CFTC `088691`, contratos de 100 onzas troy), desde enero de 1986 hasta la actualidad, en un único CSV listo para analizar. Además, dos series de precio del futuro **GC=F** para análisis técnico: velas diarias (histórico completo) y velas de 1 hora (últimos 30 días).

**URLs raw de los datasets (fuente canónica):**

```
https://raw.githubusercontent.com/joaquimaro/cot-oro/main/cot_gold_historico.csv
https://raw.githubusercontent.com/joaquimaro/cot-oro/main/oro_diario.csv
https://raw.githubusercontent.com/joaquimaro/cot-oro/main/oro_1h.csv
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

Dos ficheros con el precio del **futuro de oro GC=F (COMEX)** descargado de yfinance, regenerados **cada madrugada a las 05:30 UTC**:

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

## Actualización

GitHub Actions ejecuta el pipeline con tres crons:

- **Diario, 05:30 UTC**: solo `descarga_precios.py` → refresca `oro_diario.csv` y `oro_1h.csv`.
- **Sábado y domingo, 06:00 UTC** (08:00 Madrid en horario de verano): ambos scripts — full rebuild del COT 1986→hoy tras la publicación del viernes de la CFTC (el domingo es reintento inocuo) + precios.

Ambos scripts validan la integridad del resultado antes de guardar (número de filas mínimo y frescura de la última fecha/vela); si la validación falla, el job termina en error **sin commitear**, conservando la versión previa de los ficheros. Si no hay datos nuevos no se crea commit. También puede lanzarse a mano desde la pestaña Actions (`workflow_dispatch`, ejecuta ambos scripts).

## Regenerar en local

```bash
pip install -r requirements.txt
python build_cot_gold_csv.py
python descarga_precios.py
```
