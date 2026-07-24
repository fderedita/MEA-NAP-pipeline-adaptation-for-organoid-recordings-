# Documentazione tecnica — organoid-mea-foundation

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

Il progetto segue un piano a **stadi sequenziali**:

```
Stage 0  → inventario dei dati (quanti soggetti, che impostazioni hardware)
Stage 0.5 → download mirato dei file grezzi prioritari
Stage 1  → validazione: il nostro metodo di rilevamento spike funziona?
Stage 2  → estrazione di feature elettrofisiologiche 
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
| `validate_pipeline.py` | Confronta rilevamento spike "fatto da noi" contro le Units già depositate (Stage 1); contiene anche `detect_spikes_full_recording()`, usato da Stage 1 e dal percorso ora superato (vedi sotto) |
| `self_derived_sorting.py` | Sorting + curazione di qualità via `spikeinterface`/`lupin` — metodo **superato** dal pivot MEA-NAP del 2026-07-13, mantenuto solo per il confronto già calcolato su 001872 |
| `io_brainwave.py` | Legge/converte file 3Brain `.brw` per il laboratorio; contiene anche `export_to_meanap_mat()`, il convertitore BRW→formato MEA-NAP |
| `io_nwb_convert.py` | Convertitore NWB→formato MEA-NAP: `nwb_to_meanap_mat()` (un file) + `convert_all_recordings()` (tutti i raw in scope), equivalente NWB di `io_brainwave.py`'s `export_to_meanap_mat` |
| `build_meanap_spreadsheet.py` | Scrive il CSV "spreadsheet" che MEA-NAP richiede per sapere quali registrazioni processare — lo stesso passaggio che ogni utente MEA-NAP prepara a mano, qui automatizzato |
| `run_meanap_pipeline.py` | **Percorso attuale per Stage 2**: costruisce l'oggetto `Params` da `config/params.yaml` e fa girare `meanap.pipeline.runner.run_pipeline()` (Step 1-4 completi di MEA-NAP) — usa gli altri due moduli per la conversione e il CSV, non li reimplementa — vedi §3.4 |
| `features/spike_train.py`, `features/network.py` | **Superati come percorso primario** dal pivot a `run_pipeline()` (2026-07-13) — contengono comunque `detect_bursts_meanap_isin_batch`/wrapper diretti a MEA-NAP, mantenuti per compatibilità con `build_feature_matrix.py` (ora anch'esso secondario, vedi sotto) |
| `features/spectral.py` | Feature spettrali: LFP, PSD, esponente aperiodico (FOOOF) — **non fanno parte di MEA-NAP**, supplementari, non nel set primario per Stage 3-5 |
| `features/complexity.py` | Feature di criticità: avalanche, entropia, complessità di Lempel-Ziv — **non fanno parte di MEA-NAP**, supplementari, non nel set primario per Stage 3-5 |
| `build_feature_matrix.py` | **Attivo solo per HO5-8** (eccezione forzata, Units depositate); il resto del file (percorso MEA-NAP a pezzi) è superato, output storico tenuto — vedi §3.4 |
| `build_feature_matrix_001872.py` | **Percorso superato** (self-derived sorting `lupin`); tenuto solo perché `io_nwb_convert.py` importa `_RAW_FILES`/`_parse_filename` da qui — output storico tenuto, non ricalcolato — vedi §3.4 |
| `batch_effect.py`, `harmonize.py`, `reference.py` | Stage 3-5, non ancora implementati — leggeranno i CSV nativi di MEA-NAP direttamente (vedi §3.4), non un file Parquet consolidato |

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
- È definito nel file `environment.yml` (quali pacchetti,
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

### 2.2.1 Setup di MEA-NAP da zero (necessario dopo un clone nuovo)

`external/` è **completamente escluso da git** — chi clona questo repo NON
riceve MEA-NAP insieme al resto. Passi per ricostruirlo (fatti a mano su
questa macchina, da rifare identici altrove):

```powershell
git clone https://github.com/SAND-Lab/MEA-NAP.git "external\MEA-NAP"
conda activate organoid-mea-foundation
pip install -e "external\MEA-NAP"
```

**Patch locale necessaria, non presente upstream** (2026-07-14): il repo
ufficiale ha un bug in `src/meanap/pipeline/step2.py` — il calcolo di
`duration_s` (letto dalla shape del file `.mat` grezzo) usa un controllo
hardcoded `if n_samples == 64` per capire se l'array è trasposto, invece del
controllo robusto `if n_samples == n_channels` già usato correttamente in
`step3.py`/`step4.py`. Per qualunque registrazione con un numero di canali
diverso da 64 (il nostro caso: 130-1020 canali, mai 64), la correzione non
scatta mai e `duration_s` viene calcolato come `n_channels / fs` invece di
`n_samples / fs` — un valore migliaia di volte troppo piccolo, che gonfia
tutte le statistiche dipendenti dalla durata nel CSV `NeuronalActivity_*`
(FRmean, NBurstRate, ecc.) di un fattore enorme. **Non influenza** Step 3
(connettività STTC) né la maggior parte di Step 4 (metriche di rete
topologiche), che usano già il controllo corretto.

Fix applicato manualmente in questo clone locale (`external/MEA-NAP/src/
meanap/pipeline/step2.py`, riga ~136): sostituire `if n_samples == 64:` con
`if n_samples == n_channels:`. **Va riapplicato a mano dopo ogni clone
nuovo** di MEA-NAP, dato che `external/` non è tracciato da git — non c'è
modo di farlo ereditare automaticamente. Scoperto verificando manualmente i
numeri nel CSV di output (FRmean ~24000 Hz, biologicamente impossibile) e
rintracciando la causa nel codice sorgente, non assunto.

### 2.2.2 Patch di performance/correttezza aggiuntive (2026-07-20/22)

Come per `step2.py` sopra, **tutte queste patch vivono solo nel clone locale
di `external/MEA-NAP`** (gitignored) e vanno riapplicate a mano dopo ogni
clone nuovo, su ogni macchina (workstation e locale sono state tenute
allineate a mano, non c'è un meccanismo automatico). Nate processando
HO1-4/001872 su HD-MEA a 130-1020 canali — scala mai raggiunta prima nel
ciclo di sviluppo/test di MEA-NAP, che assume tipicamente MEA standard a
~60 elettrodi. Tutte verificate su dati reali (non solo sintetici) prima
del deploy.

1. **`network_metrics.py::participation_coef_norm`** — le 100 randomizzazioni
   per normalizzare il participation coefficient erano seriali; il costo
   scala con n² tramite `null_model_und_sign`, dominando lo Step 4 (ore per
   lag) su registrazioni a 1000+ canali. Ora girano in parallelo via
   `joblib.Parallel` (processi worker separati, non thread — ogni
   iterazione è indipendente, nessun rischio di correttezza).
2. **`nmf.py::cal_nmf`** — due bug distinti nella ricerca del numero di
   componenti NMF: (a) il ciclo di sweep per la varianza spiegata al 95%
   mancava l'uscita anticipata nonostante il `break` fosse l'intento
   dichiarato nel codice; (b) anche corretto, il punto di arresto può
   richiedere centinaia di fit NMF seriali a rango crescente. Entrambi i
   cicli ora calcolano un blocco di ranghi candidati in parallelo e
   scorrono i risultati in ordine per trovare lo stesso identico punto di
   arresto che troverebbe una ricerca seriale (verificato: corrispondenza
   esatta con un riferimento seriale su dati di controllo).
3. **`network_metrics.py::effective_rank`** — costruiva una matrice densa
   di spike a piena frequenza di campionamento (`n_samples × n_channels`)
   prima di ridurla; per 1014 canali × 600s × 10kHz, ~49 GB — più della RAM
   disponibile. Ora costruita e ridotta a blocchi di canali (~512MB l'uno);
   risultato numericamente identico (`resample_poly` filtra ogni canale
   indipendentemente, quindi processarli a blocchi non cambia nulla).
4. **`probabilistic_threshold.py::adjm_thr`** (Step 3) — le 200 ripetizioni
   surrogate per la soglia di significatività erano seriali, ciascuna
   ricalcolando l'intera matrice STTC O(n²). Parallelizzate con lo stesso
   schema del punto 1.
5. **`plotting_step2.py::plot_burst_detection_info`** — due cicli Python
   annidati O(spike totali × burst totali) per verificare se uno spike
   cade dentro un burst di rete. Sostituiti con una ricerca vettorializzata
   (`np.searchsorted`), sfruttando che i burst di rete non si sovrappongono
   per costruzione — fino a 1236× più veloce, risultato identico.
6. **`network_metrics.py`: `NULL_MODEL_DENSITY_LIMIT = 0.5`** — la scoperta
   più importante: su registrazioni con connettività STTC molto densa
   (osservato: 97.3% su HO2 — segnale biologico reale di sincronizzazione
   diffusa, non un bug di soglia; verificato che `tail=0.05` è il default
   standard di MEA-NAP), la randomizzazione a preservazione di grado usata
   sia per `participation_coef_norm` sia per la small-worldness
   (`latmio_und_v2`/`randmio_und_v2` in `step4.py`) diventa
   algoritmicamente impraticabile: il campionamento per rigetto cerca
   quartetti di nodi con un arco presente e uno assente, evento
   sempre più raro quanto più il grafo è denso. Separatamente,
   `step4.py::compute_network_metrics`'s local efficiency
   (`efficiency_wei_local`) richiama un intero calcolo di cammini minimi
   *per ogni nodo*, un'esplosione O(n²) equivalente alla stessa densità.
   Sopra questa soglia (conservativa, non un confine misurato con
   precisione), queste tre metriche vengono saltate e segnalate
   esplicitamente nei dati (`PCNormalized`,
   `SmallWorldnessSkippedHighDensity`, `ElocSkippedHighDensity`) invece di
   bloccarsi in silenzio — il gap resta visibile, non nascosto.
7. **`step3.py`/`step4.py`** — l'eccezione generica attorno alla lettura del
   file raw per calcolare la durata veniva inghiottita senza dettagli
   (`except Exception: log("could not read raw file...")`); ora include il
   messaggio d'errore reale e se il percorso esiste, per non restare senza
   indizi se ricapita.
8. **`src/run_meanap_pipeline.py`** (file nostro, tracciato da git — non
   serve riapplicare a mano) — chiusura esplicita del pool di processi di
   `joblib` dopo ogni registrazione (`get_reusable_executor().shutdown()`),
   dato che una singola registrazione può fare 10+ chiamate separate a
   `joblib.Parallel()` nello Step 4; sospettato (non confermato con
   certezza) causa di un arresto del processo dopo ~5.8h di esecuzione
   continua su HO2, con swap quasi pieno e warning di risorse "leaked" da
   `joblib`.

### 2.3 File che descrivono l'ambiente

- `environment.yml` — cosa installare
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
per-elettrodo) — spiegazione: i file grezzi e quelli con
gli spike già ordinati non sono la stessa sessione di registrazione. Il gap temporale reale tra le due sessioni è stato
misurato per tutti e 4 i soggetti (~57 min per HO1/HO4, ~4 giorni per
HO2/HO3) e **l'ordine del gap coincide esattamente con l'ordine della
correlazione ottenuta** (gap corto → rho più alto) — vedi l'addendum del
2026-07-13 in `stage1_validation.md`. La curazione di qualità ha però
sistemato le statistiche aggregate. Decisione presa il 2026-07-10:
procedere comunque, usando gli spike già depositati dove esistono, e il
sorting curato dove no.

**Pivot successivo (2026-07-13):** proprio perché il gap temporale
spiegava la mancata correlazione meglio della qualità del metodo, mescolare
Units depositate (sessione diversa) e sorting self-derived (metodo diverso)
tra dataset è stato giudicato un confound peggiore che usare un solo
metodo, non perfetto ma uniforme, ovunque. Vedi §3.4 per la policy attuale.

### 3.4 Stage 2 — Estrazione feature (stage attuale)

Questo è il cuore del progetto. Ha attraversato **tre revisioni nella
stessa giornata (2026-07-13)**, ciascuna motivata da quanto emerso dalla
precedente — riassunte qui in ordine, perché capire il percorso aiuta a
capire perché l'architettura finale è così.

**Revisione 1 — un solo metodo di rilevamento spike, non due diversi.**
All'inizio si usavano le Units già depositate per `001603` e sorting
self-derived (`lupin`) per `001872` — due metodi diversi su due dataset
diversi. Dato che l'addendum a Stage 1 (§3.3) aveva mostrato che le
correlazioni fallite erano spiegate meglio dal gap temporale tra sessioni
che dalla qualità del metodo, usare metodi di misura diversi tra dataset è
stato giudicato un confound peggiore di un solo metodo imperfetto ma
uniforme. Scelto il rilevatore a soglia di MEA-NAP ("thr4") su entrambi i
dataset.

**Revisione 2 — MEA-NAP calcola molto più di quanto stessimo usando.**
Il codice iniziale chiamava singole funzioni di MEA-NAP una per una
(`detect_spikes_full_recording`, `single_channel_burst_detection`,
`firing_rates_bursts`, `adjm_thr`, un sottoinsieme di `network_metrics.py`).
Verificato nel port Python completo
(`external/MEA-NAP/python/PIPELINE_PORT_STATUS.md`) che MEA-NAP calcola,
di suo, molto di più: modularità (Louvain), node cartography (6 ruoli
hub/non-hub), participation coefficient, small-worldness, rich club — non
solo il sottoinsieme deterministico base (grado, densità, clustering, path
length, efficienza) che stavamo usando.

**Revisione 3 — usare la pipeline `run_pipeline()` di MEA-NAP per intero,
non le sue funzioni a pezzi.** MEA-NAP ha il proprio orchestratore completo
(`meanap.pipeline.runner.run_pipeline()`, port di `MEApipeline.m`) che fa
girare tutti e 4 gli step (detection → attività neuronale → connettività →
metriche di rete) e scrive i propri file di output — CSV/JSON puliti, non
serve riscrivere la logica di aggregazione. **Unico vincolo tecnico reale**:
MEA-NAP non sa leggere NWB, solo file `.mat` (HDF5/v7.3) del formato usato
da Axion/Multichannel Systems — serve una conversione preliminare.

Tre file separati, uno per ciascun passaggio del "rituale di setup" che
MEA-NAP stesso richiede a qualunque utente (vedi il suo README: dati
convertiti in `.mat` + un CSV "spreadsheet" preparato prima di poter
lanciare l'analisi):

```
data/raw/*.nwb (grezzo)
        |
        v
src/io_nwb_convert.py
  - nwb_to_meanap_mat(): converte un file NWB in .mat
  - convert_all_recordings(): lo fa per tutti i raw in scope
    (001603 HO1-4, tutto 001872)
        |
        v
data/meanap_mat/*.mat        (formato che MEA-NAP sa leggere)
        |
        v
src/build_meanap_spreadsheet.py::build_spreadsheet()
  - scrive il CSV che elenca ogni registrazione (nome file, gruppo, età)
        |
        v
outputs/meanap_pipeline/recordings.csv
        |
        v
src/run_meanap_pipeline.py
  - build_params(): traduce config/params.yaml nell'oggetto Params
    che meanap.pipeline.runner.run_pipeline() si aspetta
  - main(): chiama run_pipeline() -- questa riga è MEA-NAP, non nostra
        |
        v
meanap.pipeline.runner.run_pipeline()   (Step 1-4 completi di MEA-NAP)
        |
        v
outputs/meanap_pipeline/OutputData/
  2_NeuronalActivity/NeuronalActivity_RecordingLevel.csv
  2_NeuronalActivity/NeuronalActivity_NodeLevel.csv
  4_NetworkActivity/NetworkActivity_RecordingLevel.csv
  4_NetworkActivity/NetworkActivity_NodeLevel.csv
  (+ ephys_results.json, netmet_results.json, grafici di controllo)
```

**HO5-HO8 di 001603 restano fuori da questo flusso** — nessun file raw
depositato su DANDI per questi 4 soggetti, MEA-NAP non può girare senza
raw. Continuano a passare per `build_feature_matrix.py`'s
`process_deposited_recording()` (percorso separato, Units depositate),
producendo `spike_source: deposited` come eccezione forzata, non scelta.

**`channel_layout` (coordinate elettrodi) non serve per risultati
corretti** — verificato nel codice (`step4.py`): è usato solo per i grafici
spaziali, dentro un blocco che salta silenziosamente il plot se il layout
non è riconosciuto, senza toccare nessuna metrica numerica.

**`fs` (frequenza di campionamento) è letta per-registrazione** dal file
`.mat` stesso, non da un valore globale unico — permette di far girare
`001603` (20kHz) e `001872` (10kHz) nella stessa chiamata a
`run_pipeline()`.

Dato che MEA-NAP scrive già CSV puliti e pronti, uno script di merge extra sarebbe solo un sovraccarico. Stage 3-5 leggerà questi CSV direttamente (con un
pivot long→wide per le metriche di rete, che sono una riga per
registrazione×lag, più il join con le righe HO5-8 da
`build_feature_matrix.py`) quando verrà costruito — vedi §3.5.

**Migrazione alla workstation e ottimizzazione (2026-07-16/22).** Il
`run_pipeline()` completo, testato su un file piccolo, mostrava un
problema reale solo a scala piena: su registrazioni HD-MEA a 1000+ canali
(HO1-4, molte di 001872), lo Step 4 poteva richiedere ore o non completare
mai, contro pochi minuti sulle registrazioni piccole. Trasferito il
progetto su una workstation del laboratorio (24 core, 30GB RAM — poi
scoperta essere una WSL2, non Linux nativo) per avere più margine di
calcolo, e investigato a fondo la causa: non un singolo bug, ma **sette
colli di bottiglia distinti** nel codice vendored di MEA-NAP, mai emersi
prima perché mai testato a questa scala di canali/densità — dettagliati in
§2.2.2. Il più significativo: registrazioni con connettività STTC
molto densa (fino al 97% osservato, segnale reale di sincronizzazione di
rete negli organoidi) rendono alcuni algoritmi di randomizzazione
statisticamente impraticabili, non solo lenti — richiede di saltare
esplicitamente quelle metriche sopra una soglia di densità, non di
parallelizzare ulteriormente. **Primo completamento riuscito end-to-end di
una registrazione a 1000+ canali (HO2)**: 22 luglio 2026, dopo tutte le
correzioni.


### 3.5 Stage 3-5 (non ancora iniziati)

`batch_effect.py` → quanto le feature dipendono dal laboratorio vs
dall'età/maturazione dell'organoide (PCA, PERMANOVA, modelli misti).
`harmonize.py` → corregge statisticamente l'effetto laboratorio (ComBat).
`reference.py` → firma di riferimento corticale finale + mappa di
maturazione (UMAP).

**Input dati**: leggeranno direttamente i CSV nativi di MEA-NAP sotto
`outputs/meanap_pipeline/OutputData/` (vedi §3.4) — non un Parquet
consolidato. Compiti da gestire in quel momento, non prima: pivot
long→wide di `NetworkActivity_RecordingLevel.csv` (una riga per
registrazione×lag, serve una riga per registrazione), join con le righe
HO5-8 (percorso `deposited` separato), ed eventualmente ISI mean/CV/skew/Lv
e le feature spettrali/di complessità se si decide di includerle (nessun
equivalente MEA-NAP per queste, andrebbero calcolate a parte).

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

### 4.3 Estrazione feature — Stage 2 (percorso attuale)

```powershell
# HO1-4 di 001603 + tutte le registrazioni di 001872: converte i raw in
# .mat e fa girare l'intera pipeline MEA-NAP (Step 1-4)
python -m src.run_meanap_pipeline

# HO5-8 di 001603 (nessun raw disponibile, eccezione forzata su Units depositate)
python -m src.build_feature_matrix
```

Il primo comando è quello pesante (converte ogni file raw in `.mat`, poi
fa girare detection + attività neuronale + connettività + metriche di rete
su tutte le registrazioni in un'unica chiamata a `run_pipeline()`).
Output sotto `outputs/meanap_pipeline/OutputData/` — vedi §3.4 per la
struttura esatta.

**Percorso superato** (2026-07-13, mantenuto solo per confronto storico,
non serve rilanciarlo — l'output esistente resta valido così com'è; il
file stesso resta in `src/` solo perché `io_nwb_convert.py` importa la
lista dei raw file da lì, non perché vada eseguito):
```powershell
python -m src.build_feature_matrix_001872           # self-derived sorting lupin (Revisione 1)
```
(Il percorso "chiamate MEA-NAP a pezzi" — Revisione 2, che usava
`build_feature_matrix_001872_meanap.py` — è stato rimosso dal repository
il 2026-07-13: nessun file lo importava più, codice morto in senso
stretto. Il suo output storico, se presente, resta comunque su disco in
`outputs/features/`.)

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
├── manifests/         → inventario dei dataset (CSV)
├── meanap_pipeline/    → OUTPUT PRINCIPALE DI STAGE 2 (percorso attuale, 2026-07-13+)
│                         struttura nativa di MEA-NAP, vedi §5.2
├── features/           → output storico (Parquet) dei percorsi superati
│                         (chiamate MEA-NAP a pezzi, self-derived sorting,
│                         Units depositate per HO5-8) + checkpoint (JSON)
├── figures/            → grafici (attualmente vuota, verrà popolata negli Stage 3-5)
└── reports/             → un file .md o .log per ogni fase importante, con
                          conclusioni, tabelle di risultati, log grezzi di
                          esecuzione
```

### 5.2 Struttura di `outputs/meanap_pipeline/` (percorso attuale)

```
outputs/meanap_pipeline/
├── recordings.csv                → lo "spreadsheet" che elenca ogni registrazione
│                                   (filename, gruppo/soggetto, DIV/età)
└── OutputData/
    ├── ExperimentMatFiles/         → matrici di adiacenza STTC per lag (.npz)
    ├── 1_SpikeDetection/
    │   └── 1A_SpikeDetectedData/    → tempi degli spike per canale (.npz)
    ├── 2_NeuronalActivity/
    │   ├── ephys_results.json           → tasso di scarica + burst, tutto
    │   ├── NeuronalActivity_RecordingLevel.csv   → 1 riga per registrazione
    │   └── NeuronalActivity_NodeLevel.csv        → 1 riga per (registrazione, canale)
    └── 4_NetworkActivity/
        ├── netmet_results.json
        ├── NetworkActivity_RecordingLevel.csv    → 1 riga per (registrazione, lag)
        │     colonne: Dens, NDmean, nMod, Q, PL, Eglob, SW, SWw,
        │     node cartography (NCpn1..6), participation coefficient, ecc.
        └── NetworkActivity_NodeLevel.csv         → 1 riga per (registrazione, lag, canale)
```

Questi sono file nativi di MEA-NAP (stessa struttura del suo output MATLAB),
letti direttamente con `pandas.read_csv` — non serve nessuna conversione
per usarli in Stage 3-5 (vedi §3.4/§3.5).

### 5.3 Tabella: cosa genera ciascuno script (per stage)

| Script | Genera | Formato |
|---|---|---|
| `src/inventory.py` | `manifest_001603.csv`, `manifest_001872.csv`, `manifest_all.csv`, `manifest_in_scope.csv` (solo umani), `stage0_inventory.md`, `settings_audit.csv` | CSV + Markdown |
| `src/mirror_priority.py` | File `.nwb` grezzi | dati binari, in `data/raw/` (esclusi da git) |
| `notebooks/run_stage1_validation.py` | `stage1_validation_results*.json` | JSON |
| `notebooks/run_sorter_validation.py` | `stage1_sorter_validation_results.json` | JSON |
| `notebooks/run_sorter_curation.py` | `stage1_sorter_curated_validation_results.json`, `stage1_sorter_lupin_quality_metrics.csv` | JSON + CSV |
| `src/run_meanap_pipeline.py` **(Stage 2, percorso attuale)** | `outputs/meanap_pipeline/OutputData/` — vedi §5.2 | CSV + JSON |
| `src/build_feature_matrix.py` (solo HO5-8) | Righe `deposited` unite manualmente a valle, non in un file separato | — |
| `src/build_feature_matrix.py`, `_001872_meanap.py`, `_001872.py` (superati) | `feature_matrix_*.parquet` in `outputs/features/` — storico, non ricalcolato | Parquet |
| `src/io_brainwave.py`/`io_nwb_convert.py` | File `.mat` per MEA-NAP (GUI o `run_meanap_pipeline.py`) | HDF5/.mat |
| `notebooks/run_meanap_on_brainwave.py` | `summary.json`, `firing_rates_per_channel.csv`, `firing_rate_heatmap.png` | JSON + CSV + PNG |

### 5.4 Come leggere i CSV di MEA-NAP

```python
import pandas as pd
df = pd.read_csv("outputs/meanap_pipeline/OutputData/4_NetworkActivity/NetworkActivity_RecordingLevel.csv")
df.columns          # elenco di tutte le metriche di rete disponibili
df[df["Lag"] == "15mslag"]   # solo il lag 15ms (formato long: 1 riga per registrazione x lag)
```

Il file `feature_matrix_*.parquet` in `outputs/features/` esiste ancora
(output storico dei percorsi superati, spiegato in §3.4) e si legge allo
stesso modo con `pd.read_parquet(...)`, ma **non è più l'output primario di
Stage 2** — resta solo come confronto storico, non viene più prodotto o
aggiornato.

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

## 7. Stato attuale del progetto

- ✅ **Stage 0-1**: completi. Ambiente, inventario dati, validazione pipeline
  (con esito negativo sul criterio originale, ma decisione umana di
  procedere comunque; rafforzato e in parte reinterpretato dall'addendum e
  dal pivot del 2026-07-13, vedi §3.3-3.4).
- 🔄 **Stage 2**: architettura definitiva (terza revisione, 2026-07-13) —
  `src/run_meanap_pipeline.py` converte i raw NWB e fa girare l'intera
  pipeline `run_pipeline()` di MEA-NAP (Step 1-4) su HO1-4 (001603) e tutte
  le 15 registrazioni di 001872. Testato end-to-end su un file piccolo
  prima di lanciare su scala piena (disciplina già seguita per gli altri
  passaggi pesanti di questo progetto). HO5-8 restano sul percorso
  separato `deposited` (`build_feature_matrix.py`). I tre percorsi
  precedenti (chiamate MEA-NAP a pezzi, self-derived sorting, Units
  depositate ovunque) sono superati e tenuti solo come confronto storico.
  In esecuzione sulla workstation del laboratorio dopo sette correzioni di
  performance/correttezza nel codice vendored (§2.2.2) — HO2 (1014 canali)
  completato con successo il 22 luglio 2026, primo caso a questa scala;
  registrazioni restanti in corso.
- ⏳ **Stage 3-5**: non ancora iniziati. Leggeranno i CSV nativi di
  MEA-NAP sotto `outputs/meanap_pipeline/OutputData/` direttamente
  (nessun Parquet consolidato, decisione 2026-07-13) — pivot long→wide
  per le metriche di rete, join con le righe HO5-8, tutto da fare in
  quella fase, non prima.
- ⏳ **Modulo BrainWave5/3Brain**: infrastruttura pronta e testata (con un
  file di esempio pubblico), in attesa dei dati reali del laboratorio.

### 7.1 Decisioni architetturali chiave da ricordare

1. **MEA-NAP invece di codice scritto da zero** per rilevamento spike/burst/
   rete — già validato dalla comunità, non reinventare la ruota.
2. **Usare la pipeline `run_pipeline()` completa di MEA-NAP, non le sue
   funzioni una per una** (decisione finale, 2026-07-13, terza revisione
   di Stage 2) — dà accesso a tutto il set di metriche di default di
   MATLAB (modularità, node cartography, small-worldness, ecc.), non solo
   al sottoinsieme che avremmo ricordato di richiamare a mano. Unico costo:
   serve convertire NWB in `.mat` prima (`src/io_nwb_convert.py`), perché
   MEA-NAP non sa leggere NWB nativamente.
3. **`lupin` come sorter CPU** — usato solo nel percorso self-derived ora
   superato (prima revisione di Stage 2), non nella policy attuale.
4. **Politica "spike source" per Stage 2 (finale, 2026-07-13)**: un solo
   metodo (MEA-NAP a soglia, via `run_pipeline()`) uniforme su entrambi i
   dataset, per non introdurre "metodo di misura diverso" come confound
   aggiuntivo rispetto a "laboratorio/piattaforma diverso" — obiettivo
   centrale del progetto. Eccezione forzata (non scelta) solo per HO5-8,
   che non hanno alcun raw depositato. Mai mischiare senza etichettare
   (`spike_source`).
5. **Niente Parquet consolidato per Stage 2** (2026-07-13) — MEA-NAP scrive
   già CSV puliti; un merge/pivot extra è compito di Stage 3-5, non di
   Stage 2, per evitare uno strato di trasformazione che nessuno usa finché
   non serve davvero.
6. **`config/params.yaml` come unica fonte di verità** per ogni soglia/parametro
   — il codice si rifiuta di girare se manca un valore, invece di usare un
   default nascosto. `run_meanap_pipeline.py::build_params()` traduce questi
   valori nell'oggetto `Params` che MEA-NAP si aspetta, non li duplica.
7. **Ogni scelta di parametro non ovvia è documentata nel commento YAML
   accanto**, con la fonte (letteratura scientifica citata, o convenzione di
   MEA-NAP) — nessun "numero magico" senza spiegazione.
8. **Risultati superati non vengono cancellati**, solo affiancati da una
   versione aggiornata con un nome file chiaro (es. `_deposited_only`,
   `_meanap`) — permette confronti futuri senza dover ricalcolare da zero.
9. **Sopra una certa densità di connettività, alcune metriche si saltano
   esplicitamente invece di parallelizzare all'infinito** (2026-07-22,
   `NULL_MODEL_DENSITY_LIMIT` — vedi §2.2.2 punto 6). Non tutti i problemi
   di performance sono risolvibili con più core: alcuni algoritmi di
   randomizzazione diventano statisticamente impraticabili su grafi quasi
   completi, indipendentemente da quanto lavoro venga distribuito in
   parallelo. Quando succede, il gap va segnalato nei dati (colonna
   booleana dedicata), mai nascosto in un valore silenziosamente sbagliato
   o in un processo che non finisce mai.
