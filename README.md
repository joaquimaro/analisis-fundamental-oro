# cot-oro

Histórico semanal del informe **COT (Commitments of Traders) del oro COMEX** (código CFTC `088691`, contratos de 100 onzas troy), desde enero de 1986 hasta la actualidad, en un único CSV listo para analizar.

**URL raw del dataset (fuente canónica):**

```
https://raw.githubusercontent.com/joaquimaro/cot-oro/main/cot_gold_historico.csv
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

## Actualización

GitHub Actions regenera el CSV completo (full rebuild 1986→hoy, con validación de integridad) **cada sábado a las 06:00 UTC** (08:00 Madrid en horario de verano), tras la publicación del viernes de la CFTC, con **reintento el domingo** a la misma hora. Si no hay datos nuevos no se crea commit. También puede lanzarse a mano desde la pestaña Actions (`workflow_dispatch`).

## Regenerar en local

```bash
pip install -r requirements.txt
python build_cot_gold_csv.py
```
