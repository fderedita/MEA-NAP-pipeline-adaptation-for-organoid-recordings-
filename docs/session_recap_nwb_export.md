# Recap sessione — Caricamento ed esplorazione dati NWB (MEA organoidi)

## Contesto
Progetto: analisi di registrazioni elettrofisiologiche da organoidi cerebrali umani (HD-MEA),
soggetto `HO1`, University of California Santa Barbara (Tal Sharf lab).

File NWB coinvolti:
- `sub-HO1_ses-20250924T011900_ecephys.nwb` — dati grezzi (`ElectricalSeries`), shape `(3597600, 1020)`, `uint16`, 1020 elettrodi.
- `sub-HO1_ses-20250924T002125.nwb` — spike **già ordinati e curati** (Kilosort2, band-pass 300–6000 Hz, filtrati per ISI violation > 0.3, firing rate < 0.05 Hz, SNR < 5), raster a bin da 1ms, esposti come tabella `units`.

Notebook di lavoro: `MEA_analysis.ipynb` (root del progetto `C:\Users\franc\MEA project`).

## Cosa abbiamo fatto

### 1. Caricamento file NWB con pynwb
```python
from pynwb import NWBHDF5IO

with NWBHDF5IO("percorso/file.nwb", mode="r") as io:
    nwbfile = io.read()
    print(nwbfile)
```

### 2. Bug: `<Closed HDF5 dataset>`
Problema: accedere a `ts.data` **fuori** dal blocco `with` restituisce un dataset chiuso
(il file HDF5 viene chiuso all'uscita del `with`).

Soluzione adottata — non usare `with`, tenere `io` aperto e chiuderlo manualmente a fine lavoro:
```python
io = NWBHDF5IO("file.nwb", mode="r")
nwbfile = io.read()
ts = nwbfile.acquisition["ElectricalSeries"]
data = ts.data[:]   # carica in RAM come array numpy

# a fine lavoro:
# io.close()
```

### 3. Plot dei segnali grezzi
- Singolo canale nel tempo (`plt.plot(data[:10000, canale])`)
- Multi-canale sovrapposti con offset verticale (stile traccia MEA/EEG)
- Tentativo di heatmap spaziale per singolo istante temporale — **da correggere**: il
  `frame.reshape(-1, 1)` produce solo una colonna 1020×1, non una vera mappa spaziale.
  Serve estrarre le coordinate reali degli elettrodi da `nwbfile.electrodes`
  (tipicamente colonne `rel_x`/`rel_y` o `x`/`y` per HD-MEA) per uno scatter/heatmap corretto.

### 4. Esplorazione secondo file (spike curati)
Caricato `sub-HO1_ses-20250924T002125.nwb`, che contiene una `units` table con gli spike
già ordinati — non serve rifare spike sorting su questi dati.

## Da tenere a mente
- Due oggetti `io` restano aperti nel notebook attuale (mai chiusi esplicitamente) — da
  chiudere con `io.close()` a fine sessione.
- Con array così grandi (3.6M campioni × 1020 canali), evitare `data[:]` completo se non
  necessario: usare slicing su finestre temporali/canali per l'esplorazione.

## Strumenti open source consigliati (prossimi passi)
| Scopo | Libreria | Note |
|---|---|---|
| Analisi statistica spike già curati | [Elephant](https://github.com/NeuralEnsemble/elephant) | firing rate, ISI, sincronia, cross-correlazioni; lavora con NWB via Neo |
| Esplorazione rapida spike in notebook | [pynapple](https://github.com/pynapple-org/pynapple) | integrazione diretta e leggera con NWB |
| Analisi di rete/burst per organoidi HD-MEA | [MEA-NAP](https://github.com/SAND-Lab/MEA-NAP) | pensato specificamente per organoidi cerebrali su MEA; è MATLAB, non Python |
| Validare/rifare spike sorting su dati grezzi | [SpikeInterface](https://spikeinterface.github.io/) | `NwbRecordingExtractor` per caricare direttamente il file ecephys NWB |

**Scelta suggerita per continuare:** partire da **pynapple** sul file `_small` (spike curati)
per un primo raster plot e statistiche di base; poi, se serve analisi di rete/burst tipica
degli organoidi, passare a MEA-NAP.

## Prossimo step proposto
Script di esempio con pynapple che carica `nwbfile_small` (units curati) e produce un
raster plot iniziale.

## Consolidamento con la repo formale organoid-mea-foundation (2026-07-08)

Questa cartella (`C:\Users\franc\MEA project`, non sincronizzata con OneDrive) è stata
resa la repo canonica per l'intero progetto (vedi `docs/handoff_foundation_phase.md`).
Una copia gemella sotto OneDrive è stata dismessa per evitare drift e problemi di
sync/lock su file HDF5 di grandi dimensioni.

Cambiamenti applicati:
- `MEA_analysis.ipynb` spostato in `notebooks/`.
- I 3 file NWB scaricati in precedenza in `Downloads/` sono stati spostati in
  `data/raw/` (percorso già escluso da git). Due di essi (`sub-HO1_..._ecephys.nwb`
  raw e `sub-HO1_..._002125.nwb` curato) erano bloccati da handle HDF5 mai chiusi
  nel notebook — vedi cella di cleanup aggiunta in fondo al notebook.
- Kernel Jupyter consolidato: l'ambiente frozen `organoid-mea-foundation`
  (da `environment.yml`, non il precedente env ad-hoc `nwb`) è ora registrato come
  kernel e impostato come kernel del notebook.
- Terzo file scaricato, non ancora esplorato nel notebook:
  `sub-sample-well000_ses-20260622T175109_ecephys.nwb` (4.27 GB) — naming "well000"
  compatibile con il chip 24-well MaxTwo di DANDI:001872, utile per Stage 0/1.

Fatti concreti emersi da questa esplorazione, rilevanti per lo Stage 0 formale
(`docs/handoff_foundation_phase.md`, Task 0.3/0.4 — da confermare sistematicamente,
non ancora "settled"):
- Soggetto **HO1** (Tal Sharf lab, UCSB) ha sia un file raw (`ElectricalSeries`,
  shape (3597600, 1020), dtype uint16, 1020 elettrodi) sia un file di spike già
  ordinati/curati separato → è un candidato soggetto "recorded" (non "sourced-only")
  in DANDI:001603.
- Sorter usato per la curation: **Kilosort2** (non 2.5/3) — risponde parzialmente
  alla open question #5 dell'handoff, almeno per questo soggetto/lab.
- Preprocessing per la curation: band-pass **300–6000 Hz**, che combacia esattamente
  con il default già congelato in `config/params.yaml` (`preprocessing.bandpass_hz`).
- Esclusione unità: ISI violation > 0.3, firing rate < 0.05 Hz, SNR < 5.
- Pubblicazione collegata: doi:10.1038/s41467-022-32115-4.
- `age`/`age__reference` nel campo Subject usa una durata ISO8601 riferita a
  "birth" (qui `P7M`) — da verificare come si mappa a DIV nello Stage 0, non è
  detto sia direttamente equivalente.

Questi punti sono osservazioni preliminari da un solo soggetto, non sostituiscono
l'inventory sistematico dello Stage 0 (Checkpoint B), ma lo orientano.
