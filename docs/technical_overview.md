# Documentazione tecnica — organoid-mea-foundation

> Documento di riferimento per chiunque debba capire, spiegare o continuare
> questo progetto senza aver seguito lo sviluppo passo passo. Scritto per
> essere letto in ordine, dall'alto verso il basso.

---

## 1. Panoramica del progetto

### 1.1 Scopo

Il progetto costruisce l'infrastruttura per classificare l'**identità regionale**
di organoidi cerebrali (corticale, midbrain, striatale, ippocampale, ecc.) a
partire da registrazioni elettrofisiologiche multi-elettrodo (**MEA**,
Micro-Electrode Array). Questa è la **fase fondativa** del progetto più ampio:
lavora solo su dati **corticali** (nessuna classificazione regionale ancora
possibile, per definizione — servirebbero più tipi a confronto) e ha tre
obiettivi:

1. **Misurare e neutralizzare l'effetto laboratorio/piattaforma hardware** —
   dati dallo stesso tipo di tessuto ma acquisiti con hardware diverso (MaxOne
   vs MaxTwo) o in laboratori diversi non devono sembrare "diversi
   biologicamente" solo per differenze tecniche.
2. **Validare la pipeline di analisi** contro un ground truth reale (dati già
   analizzati e pubblicati da altri laboratori).
3. **Definire una firma di riferimento corticale** riutilizzabile, così che
   quando arriveranno i dati reali del laboratorio (organoidi corticali e
   spinali, hardware 3Brain) si inseriscano in un'infrastruttura già
   testata, non in un progetto partito da zero.

### 1.2 I dati usati finora

| Dataset | Tipo | Piattaforma | Ruolo |
|---|---|---|---|
| `DANDI:001603` | Organoidi corticali umani | MaxWell **MaxOne** (20kHz) | Ancora di ground-truth: alcuni soggetti hanno sia dati grezzi sia spike già ordinati e pubblicati da altri |
| `DANDI:001872` | Organoidi corticali umani | MaxWell **MaxTwo** (10kHz) | Replica indipendente, solo dati grezzi |

`DANDI` è un archivio pubblico di dati di neuroscienze; i file sono in
formato **NWB** (Neurodata Without Borders), uno standard che impacchetta
segnali grezzi, metadati del soggetto, ed eventuali analisi già fatte in un
unico file HDF5.

**Il futuro (non ancora iniziato):** dati reali del laboratorio, hardware
**3Brain BrainWave5** (formato `.brw`, diverso sia da NWB che da MaxWell) —
per questo esiste già un modulo dedicato (§3.6).

### 1.3 Architettura generale: pipeline a stadi

Il progetto segue un piano a **stadi sequenziali**, ciascuno con un
"checkpoint" in cui il lavoro si ferma per revisione umana prima di
proseguire (definito nel documento originale `docs/handoff_foundation_phase.md`):

```
Stage 0  → inventario dei dati (quanti soggetti, che impostazioni hardware)
Stage 0.5 → download mirato dei file grezzi prioritari
Stage 1  → validazione: il nostro metodo di rilevamento spike funziona?
Stage 2  → estrazione di feature elettrofisiologiche (IN CORSO ORA)
Stage 3  → quanto le feature dipendono dal laboratorio vs dalla biologia?
Stage 4  → correzione statistica dell'effetto laboratorio
Stage 5  → firma di riferimento corticale finale
```

Lo stato attuale è documentato in dettaglio al §7.

### 1.4 Moduli principali e responsabilità (`src/`)

| Modulo | Responsabilità |
|---|---|
| `config.py` | Carica `config/params.yaml` e impone la regola "fallisci rumorosamente se manca un parametro" — nessun default nascosto nel codice |
| `io_dandi.py` | Scarica/streamma metadati e file da DANDI |
| `inventory.py` | Costruisce l'inventario dei dataset (Stage 0) |
| `mirror_priority.py` | Script una-tantum per scaricare il sottoinsieme prioritario di file grezzi |
| `validate_pipeline.py` | Confronta rilevamento spike "fatto da noi" contro le Units già depositate (Stage 1) |
| `self_derived_sorting.py` | Esegue sorting + curazione di qualità quando NON esistono Units depositate |
| `io_brainwave.py` | Legge/converte file 3Brain `.brw` per il laboratorio |
| `features/spike_train.py` | Feature per singola unità: tasso di scarica, ISI, burst |
| `features/network.py` | Feature di rete: connettività STTC, metriche di grafo |
| `features/spectral.py` | Feature spettrali: LFP, PSD, esponente aperiodico (FOOOF) |
| `features/complexity.py` | Feature di criticità: avalanche, entropia, complessità di Lempel-Ziv |
| `build_feature_matrix.py` | Orchestratore: assembla tutte le feature per `DANDI:001603` |
| `build_feature_matrix_001872.py` | Come sopra, per `DANDI:001872` (percorso più lento, serve sorting) |
| `batch_effect.py`, `harmonize.py`, `reference.py` | Stage 3-5, non ancora implementati |

---

## 2. Ambiente e dipendenze

### 2.1 Cos'è Conda e perché lo usiamo

**Conda** è un gestore di pacchetti e ambienti virtuali. Il problema che
risolve: due progetti Python sulla stessa macchina possono avere bisogno di
versioni diverse (a volte incompatibili) delle stesse librerie. Conda crea
**ambienti isolati** — cartelle separate, ciascuna con la propria versione di
Python e delle librerie — così installare/aggiornare qualcosa in un progetto
non rompe gli altri.

In questo progetto:
- L'ambiente si chiama **`organoid-mea-foundation`** (Python 3.11)
- È definito nel file `environment.yml` (la "ricetta": quali pacchetti,
  quali versioni)
- Va **attivato** prima di ogni comando: `conda activate organoid-mea-foundation`
  — da quel momento, `python`, `pip`, ecc. puntano tutti a questo ambiente
  specifico, non all'installazione globale del sistema

**Nota pratica su questa macchina:** esisteva già un'installazione Anaconda
(più completa di Miniconda, che invece non era ancora in uso) non attiva nel
PATH di sistema — va richiamata con il percorso completo se `conda` non è
riconosciuto direttamente:
```
C:\Users\franc\anaconda3\Scripts\conda.exe activate organoid-mea-foundation
```

### 2.2 Le librerie principali, spiegate

**Accesso ai dati (DANDI / NWB):**
| Libreria | A cosa serve |
|---|---|
| `dandi` | Client Python per cercare, elencare e scaricare file dall'archivio DANDI |
| `pynwb` | Legge/scrive file NWB (il formato standard dei dati grezzi) |
| `remfile`, `h5py`, `fsspec` | Permettono di leggere *solo i metadati* di un file NWB via streaming, senza scaricarlo tutto — essenziale quando i file pesano gigabyte |

**Elettrofisiologia:**
| Libreria | A cosa serve |
|---|---|
| `spikeinterface` | Il "coltellino svizzero" per dati di elettrofisiologia: legge decine di formati proprietari (incluso 3Brain), fornisce sorter di spike pronti all'uso, calcola metriche di qualità |
| `neo`, `elephant`, `quantities` | Strutture dati e statistiche standard di neuroscienze (es. entropia, correlazioni tra treni di spike) |
| `probeinterface` | Descrive la geometria fisica degli elettrodi (posizioni x/y) |
| `hdbscan` | Algoritmo di clustering usato internamente dai sorter di spike CPU (es. `lupin`) |

**Analisi spettrale e di complessità:**
| Libreria | A cosa serve |
|---|---|
| `fooof` | Scompone uno spettro di potenza in componente "aperiodica" (rumore di fondo 1/f, legata alla maturazione/eccitazione-inibizione del tessuto) e picchi oscillatori |
| `antropy` | Calcola entropia campionaria e complessità di Lempel-Ziv su segnali |
| `powerlaw` | Verifica se una distribuzione (es. dimensioni delle "avalanche" neuronali) segue una legge di potenza, e con quale esponente |

**Grafo e rete:**
| Libreria | A cosa serve |
|---|---|
| `networkx`, `bctpy` | Calcolano metriche di teoria dei grafi (grado, efficienza, clustering) sulla rete di connettività funzionale |

**Statistica e machine learning:**
| Libreria | A cosa serve |
|---|---|
| `scikit-learn`, `statsmodels` | Modelli statistici generali (usati soprattutto negli Stage 3-5, non ancora iniziati) |
| `umap-learn` | Riduzione dimensionale per visualizzare pattern nelle feature |
| `neuroCombat`, `scikit-bio` | Correzione dell'effetto batch/laboratorio (Stage 4) |

**MEA-NAP** (non su PyPI, clonato manualmente in `external/MEA-NAP/`, escluso
da git): toolkit specifico per analisi di reti neuronali su MEA, con
un'implementazione Python validata contro l'originale MATLAB. Usato per
rilevamento spike, statistiche di burst, connettività STTC, metriche di
grafo — **riusato direttamente invece di essere riscritto da zero**, perché
già testato e validato dalla comunità scientifica.

### 2.3 File che descrivono l'ambiente

- `environment.yml` — la "ricetta" (cosa installare)
- `outputs/reports/env_lock.txt` — le versioni *effettivamente risolte* la
  prima volta che l'ambiente è stato creato su questa macchina
- `outputs/reports/pip_freeze.txt` — elenco completo e preciso di ogni
  pacchetto Python installato, con versione esatta (utile per riprodurre
  l'ambiente altrove)

---

## 3. Architettura della pipeline — flusso dati

### 3.1 Stage 0 — Inventario

```
DANDI (remoto) --[streaming metadati, NO download]--> src/inventory.py
                                                              |
                                                              v
                                    outputs/manifests/manifest_*.csv
                                    outputs/reports/stage0_inventory.md
                                    outputs/reports/settings_audit.csv
```

Legge solo i **metadati** di ogni file (quanti elettrodi, frequenza di
campionamento, se contiene dati grezzi o solo spike già ordinati) senza
scaricare i dati veri e propri. Ha rivelato fatti non ovvi: `001603` mescola
soggetti umani e animali (esclusi), `001872` ha una chiave di
identificazione degli organoidi più complessa del previsto.

### 3.2 Stage 0.5 — Download mirato

```
manifest_*.csv --> src/mirror_priority.py --[download selettivo]--> data/raw/*.nwb
```

Scarica solo un **sottoinsieme rappresentativo** (non tutto: `001872` da solo
pesa 261GB, più dello spazio disco disponibile).

### 3.3 Stage 1 — Validazione della pipeline

```
data/raw/*.nwb (grezzo)  ┐
                          ├──> src/validate_pipeline.py / self_derived_sorting.py
data/raw/*.nwb (Units    ┘         |
depositate, ground truth)          v
                        confronto statistico (correlazione, tasso di burst)
                                    |
                                    v
                    outputs/reports/stage1_validation.md
```

Ha testato 4 approcci diversi per "trovare gli spike" nei dati grezzi
(soglia semplice, wavelet, sorter CPU non curato, sorter CPU curato),
confrontandoli contro dati già analizzati e pubblicati. **Nessuno ha
raggiunto il criterio di accettazione originale** (correlazione elettrodo-
per-elettrodo) — motivo più probabile: i file grezzi e quelli con gli spike
già ordinati non sono la stessa sessione di registrazione. La curazione di
qualità ha però sistemato le statistiche aggregate. Decisione presa
(2026-07-10): procedere comunque, usando gli spike già depositati dove
esistono, e il sorting curato dove no — politica congelata in
`config/params.yaml`.

### 3.4 Stage 2 — Estrazione feature (stage attuale)

Questo è il cuore del progetto. Per **ogni registrazione**, calcola 4
categorie di feature:

```
                    spike_times (da Units depositate O da sorting self-derived)
                                    |
        ┌───────────────┬──────────┼──────────┬───────────────┐
        v               v          v           v               
  spike_train.py   network.py  spectral.py  complexity.py
  (per unità)       (grafo di   (serve il    (avalanche,
                    connettività) dato grezzo) entropia)
        |               |          |               |
        └───────────────┴──────────┴───────────────┘
                                |
                                v
              build_feature_matrix.py (001603) /
              build_feature_matrix_001872.py (001872)
                                |
                                v
              outputs/features/feature_matrix_*.parquet
```

**Due percorsi diversi per i due dataset:**
- `001603`: usa le Units **già depositate** (veloce, nessun calcolo pesante)
- `001872`: nessuna Units depositata → deve fare **sorting da zero** (lento,
  ore per file) tramite `self_derived_sorting.py`, poi le stesse 4 categorie
  di feature

### 3.5 Stage 3-5 (non ancora iniziati)

`batch_effect.py` → quanto le feature dipendono dal laboratorio vs
dall'età/maturazione dell'organoide (PCA, PERMANOVA, modelli misti).
`harmonize.py` → corregge statisticamente l'effetto laboratorio (ComBat).
`reference.py` → firma di riferimento corticale finale + mappa di
maturazione (UMAP).

### 3.6 Modulo separato: supporto al laboratorio (BrainWave5/3Brain)

Non fa parte della pipeline DANDI — è **infrastruttura preparata in
anticipo** per quando arriveranno i dati reali del laboratorio (hardware
3Brain, non MaxWell):

```
file .brw (3Brain) --> src/io_brainwave.py --> stesse funzioni MEA-NAP
                                                (rilevamento, feature)
                                                        |
                                                        v
                                    notebooks/run_meanap_on_brainwave.py
                                    (script pronto all'uso per il laboratorio)
```

Guida completa: `docs/brainwave5_usage.md`.

---

## 4. Esecuzione e utilizzo

**Prerequisito per ogni comando:**
```powershell
conda activate organoid-mea-foundation
cd "C:\Users\franc\MEA project"
```

### 4.1 Ricostruire l'inventario dei dataset (Stage 0)
```powershell
python -m src.inventory
```
Interroga DANDI via streaming (richiede connessione internet, nessun
download di dati grezzi). Output: `outputs/manifests/*.csv`,
`outputs/reports/stage0_inventory.md`.

### 4.2 Validazione Stage 1 (confronto con ground truth)
```powershell
# Metodo a soglia o wavelet (veloce, minuti)
python notebooks\run_stage1_validation.py --subjects HO1,HO2,HO3,HO4

# Sorter CPU vero (lento, ore) — soggetto singolo
python notebooks\run_sorter_validation.py --subjects HO1 --sorter lupin

# Applica curazione di qualità a un sorting già fatto
python notebooks\run_sorter_curation.py
```
Il flag `--subjects` accetta una lista separata da virgole. `--sorter`
accetta `lupin`, `spykingcircus2`, o `tridesclous2`.

### 4.3 Costruire la matrice di feature — Stage 2

```powershell
# DANDI:001603 (veloce, usa Units depositate)
python -m src.build_feature_matrix

# DANDI:001872 (lento, richiede sorting — ore/giorni)
python -m src.build_feature_matrix_001872
```

**Entrambi sono riavviabili**: se interrotti (chiusura del terminale,
sospensione del PC, errore), rilanciando lo stesso comando riprendono da
dove si erano fermati, senza ricalcolare quanto già fatto. Il progresso è
salvato in `outputs/features/_checkpoint_*.json` dopo ogni registrazione
completata.

### 4.4 Elaborare un file del laboratorio (BrainWave5)
```powershell
python notebooks\run_meanap_on_brainwave.py percorso\al\file.brw --method threshold --workers 6
```
`--method` accetta `threshold` (veloce) o `wavelet` (più lento, non
necessariamente migliore — vedi Stage 1). `--workers` controlla quanti
processi paralleli usare (default 6, adatto a questa macchina).

### 4.5 Eseguire i test automatici
```powershell
python -m pytest tests\ -v
```
Verifica che le funzioni di calcolo delle feature diano risultati corretti
su dati sintetici a statistiche note (non richiede dati scaricati).

---

## 5. Risultati e output — cosa viene generato, e dove

### 5.1 Struttura delle cartelle di output

```
outputs/
├── manifests/     → inventario dei dataset (CSV)
├── features/      → LE MATRICI DI FEATURE FINALI (Parquet) + checkpoint (JSON)
├── figures/       → grafici (attualmente vuota, verrà popolata negli Stage 3-5)
└── reports/       → un file .md o .log per ogni fase importante, con
                     conclusioni, tabelle di risultati, log grezzi di
                     esecuzione
```

### 5.2 Tabella completa: cosa genera ciascuno script

| Script | Genera | Formato |
|---|---|---|
| `src/inventory.py` | `manifest_001603.csv`, `manifest_001872.csv`, `manifest_all.csv`, `manifest_in_scope.csv` (solo umani), `stage0_inventory.md`, `settings_audit.csv` | CSV + Markdown |
| `src/mirror_priority.py` | File `.nwb` grezzi | dati binari, in `data/raw/` (esclusi da git) |
| `notebooks/run_stage1_validation.py` | `stage1_validation_results*.json` | JSON |
| `notebooks/run_sorter_validation.py` | `stage1_sorter_validation_results.json` | JSON |
| `notebooks/run_sorter_curation.py` | `stage1_sorter_curated_validation_results.json`, `stage1_sorter_lupin_quality_metrics.csv` | JSON + CSV |
| `src/build_feature_matrix.py` | **`feature_matrix_001603.parquet`** (14 righe × 78 colonne) | Parquet |
| `src/build_feature_matrix_001872.py` | **`feature_matrix_001872.parquet`** (in costruzione, 15 righe attese) | Parquet |
| `src/io_brainwave.py` (funzione `export_to_meanap_mat`) | File `.mat` per la GUI di MEA-NAP | HDF5/.mat |
| `notebooks/run_meanap_on_brainwave.py` | `summary.json`, `firing_rates_per_channel.csv`, `firing_rate_heatmap.png` | JSON + CSV + PNG |

### 5.3 Cos'è un file `.parquet` e come si legge

**Parquet** è un formato di file colonnare, compresso, molto più efficiente
di un CSV per tabelle con molte colonne numeriche (il nostro caso: fino a 78
colonne di feature). Si legge in Python con `pandas`:

```python
import pandas as pd
df = pd.read_parquet("outputs/features/feature_matrix_001603.parquet")
df.columns          # elenco di tutte le feature disponibili
df.head()            # prime righe
df.to_csv("export.csv")  # se serve un CSV per Excel/altri strumenti
```

### 5.4 Anatomia di una riga della matrice di feature

Ogni riga = **una registrazione**. Le colonne sono raggruppate per prefisso:

| Prefisso colonna | Categoria | Esempio |
|---|---|---|
| (nessuno) | Metadati | `organoid_id`, `age`, `duration_s`, `spike_source` |
| `spike_train__` | Per singola unità (aggregato: media + deviazione standard) | `spike_train__mfr_hz_mean` (tasso di scarica medio) |
| `network__` | Rete/connettività | `network__mean_degree_15ms`, `network__density_15ms` |
| `spectral__` | Spettrale (solo se esiste il dato grezzo) | `spectral__aperiodic_exponent_mean` |
| `complexity__` | Criticità/complessità | `complexity__branching_ratio`, `complexity__sample_entropy` |

Il campo **`spike_source`** dice se le feature vengono da spike già
pubblicati (`deposited`) o calcolati da noi (`self_derived_lupin_curated`) —
distinzione importante da non perdere mai nelle analisi successive.

### 5.5 File di log — a cosa servono

Ogni esecuzione lunga scrive un file `.log` in `outputs/reports/` con
l'output grezzo del terminale (utile per diagnosticare errori dopo che il
processo è finito, specialmente per job durati ore). Non sono pensati per
essere letti riga per riga in condizioni normali — solo in caso di problemi.

---

## 6. Glossario dei termini tecnici chiave

| Termine | Significato |
|---|---|
| **MEA** | Micro-Electrode Array: griglia di elettrodi che registra l'attività elettrica di un tessuto (qui, un organoide) |
| **Spike** | Un potenziale d'azione — l'evento elettrico base con cui un neurone comunica |
| **Spike detection** | Trovare *quando* c'è stato uno spike in un segnale grezzo (soglia, wavelet, ecc.) |
| **Spike sorting** | Trovare *quale specifico neurone* ha generato ogni spike — molto più difficile della sola detection, richiede analisi della forma d'onda |
| **MUA** (Multi-Unit Activity) | Attività registrata "grezza": ogni evento sopra soglia, senza distinguere i singoli neuroni |
| **SUA** (Single-Unit Activity) | Attività di un singolo neurone identificato tramite spike sorting |
| **Curation** | Filtro di qualità applicato dopo il sorting: elimina "unità" probabilmente non reali (troppo rumorose, troppo poco attive, troppe violazioni del periodo refrattario) |
| **NWB** | Formato file standard per dati di neuroscienze |
| **LFP** (Local Field Potential) | Segnale a bassa frequenza (sotto ~300Hz), riflette attività di popolazione più che spike singoli |
| **PSD** (Power Spectral Density) | Quanta "energia" del segnale sta a ciascuna frequenza |
| **Esponente aperiodico** | Pendenza della componente 1/f dello spettro — proxy usato in letteratura per maturazione/bilancio eccitazione-inibizione |
| **STTC** (Spike Time Tiling Coefficient) | Misura statistica di quanto due elettrodi sparano in modo sincronizzato |
| **Avalanche neuronale** | Sequenza contigua di attività di popolazione sopra il livello basale — usata per studiare se il sistema è vicino a un punto critico |
| **Branching ratio** | Rapporto tra attività "figlia" e "madre" in bin temporali successivi — vicino a 1 indica dinamica critica |
| **Ground truth** | Dati di riferimento già validati (qui: spike già ordinati e pubblicati da altri laboratori) usati per verificare se il nostro metodo funziona |

---

## 7. Stato attuale del progetto (aggiornato a questa sessione)

- ✅ **Stage 0-1**: completi. Ambiente, inventario dati, validazione pipeline
  (con esito negativo sul criterio originale, ma decisione umana di
  procedere comunque con una politica congelata).
- 🔄 **Stage 2**: `DANDI:001603` completo (14 registrazioni × 78 colonne di
  feature). `DANDI:001872` **in corso** — richiede sorting self-derived su
  15 file, stima iniziale ~30 ore di calcolo totale, in esecuzione in
  background su più sessioni.
- ⏳ **Stage 3-5**: non ancora iniziati.
- ⏳ **Modulo BrainWave5/3Brain**: infrastruttura pronta e testata (con un
  file di esempio pubblico), in attesa dei dati reali del laboratorio.

### 7.1 Decisioni architetturali chiave da ricordare

1. **MEA-NAP invece di codice scritto da zero** per rilevamento spike/burst/
   rete — già validato dalla comunità, non reinventare la ruota.
2. **`lupin` come sorter CPU scelto** tra 3 opzioni testate (più veloce, più
   unità trovate in un test di fattibilità).
3. **Politica "spike source" per Stage 2**: Units depositate dove esistono,
   sorting curato altrove — mai mischiare senza etichettare (`spike_source`).
4. **`config/params.yaml` come unica fonte di verità** per ogni soglia/parametro
   — il codice si rifiuta di girare se manca un valore, invece di usare un
   default nascosto.
5. **Ogni scelta di parametro non ovvia è documentata nel commento YAML
   accanto**, con la fonte (letteratura scientifica citata, o convenzione di
   MEA-NAP) — nessun "numero magico" senza spiegazione.
