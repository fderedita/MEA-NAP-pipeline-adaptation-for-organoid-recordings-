# Stage 0 — Inventory report

- DANDI:001603 assets scanned: 111
- DANDI:001872 assets scanned: 120

## DANDI:001603 contains non-human subjects — must be excluded

This dataset is titled "Preconfigured neuronal firing sequences in human brain organoids" but its subject list is NOT all-human. Species breakdown by subject_id count: {'Homo sapiens': 8, 'Mus musculus': 24, 'Rattus norvegicus': 4}.

Only subjects with `species == Homo sapiens` (prefix `HO*`, 8 subjects) are in scope for this project. Subjects prefixed `M1S*`/`M2S*`/`M3S*`, `MO*` (Mus musculus / mouse) and `PR1-4` (Rattus norvegicus / rat), `PR5-8` (Mus musculus / mouse) are reference/comparison recordings and MUST NOT be included in any human-cortical-organoid manifest, feature matrix, or downstream analysis. All counts below are filtered to Homo sapiens only unless stated otherwise.

## DANDI:001603 — recorded vs sourced subjects, human-only (VERIFY item, Task 0.3)

- Distinct human (Homo sapiens) subjects: 8
- Recorded (>=1 asset with raw ElectricalSeries): 4
- Sourced (Units only, no raw): 4
- Neither raw nor Units present (excluded from both categories): 0

| subject_id   | species      |   n_assets |   n_with_raw |   n_with_units | subject_type   |
|:-------------|:-------------|-----------:|-------------:|---------------:|:---------------|
| HO1          | Homo sapiens |          2 |            1 |              1 | recorded       |
| HO2          | Homo sapiens |         18 |            9 |              9 | recorded       |
| HO3          | Homo sapiens |         18 |            9 |              9 | recorded       |
| HO4          | Homo sapiens |          2 |            1 |              1 | recorded       |
| HO5          | Homo sapiens |          1 |            0 |              1 | sourced        |
| HO6          | Homo sapiens |          1 |            0 |              1 | sourced        |
| HO7          | Homo sapiens |          1 |            0 |              1 | sourced        |
| HO8          | Homo sapiens |          1 |            0 |              1 | sourced        |

### Non-human subjects (excluded), for completeness

| subject_id   | species           |   n_assets |   n_with_raw |   n_with_units | subject_type    |
|:-------------|:------------------|-----------:|-------------:|---------------:|:----------------|
| M1S1         | Mus musculus      |          2 |            1 |              1 | recorded        |
| M1S2         | Mus musculus      |          2 |            1 |              1 | recorded        |
| M2S1         | Mus musculus      |          2 |            1 |              1 | recorded        |
| M2S2         | Mus musculus      |          2 |            1 |              1 | recorded        |
| M3S1         | Mus musculus      |          2 |            1 |              1 | recorded        |
| M3S2         | Mus musculus      |          2 |            1 |              1 | recorded        |
| MO1          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO10         | Mus musculus      |          6 |            3 |              3 | recorded        |
| MO11         | Mus musculus      |          6 |            3 |              3 | recorded        |
| MO12         | Mus musculus      |          5 |            3 |              2 | recorded        |
| MO13         | Mus musculus      |          6 |            3 |              3 | recorded        |
| MO14         | Mus musculus      |          6 |            3 |              3 | recorded        |
| MO2          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO3          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO4          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO5          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO6          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO7          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO8          | Mus musculus      |          2 |            1 |              0 | recorded        |
| MO9          | Mus musculus      |          2 |            1 |              0 | recorded        |
| PR1          | Rattus norvegicus |          1 |            0 |              0 | no_raw_no_units |
| PR2          | Rattus norvegicus |          1 |            0 |              0 | no_raw_no_units |
| PR3          | Rattus norvegicus |          1 |            0 |              0 | no_raw_no_units |
| PR4          | Rattus norvegicus |          1 |            0 |              0 | no_raw_no_units |
| PR5          | Mus musculus      |          1 |            0 |              1 | sourced         |
| PR6          | Mus musculus      |          1 |            0 |              1 | sourced         |
| PR7          | Mus musculus      |          1 |            0 |              1 | sourced         |
| PR8          | Mus musculus      |          1 |            0 |              1 | sourced         |

## DANDI:001872 — file -> well -> organoid mapping (VERIFY item, Task 0.3)

- Distinct well_id values found: 24 (NOT a unique organoid key on its own -- see below)
- Distinct batches/plates found: 2 (['sample', 'sample2'])
- Distinct subject_id values (batch+well = the correct distinct-organoid key): 48

**Important:** well_id (e.g. "well001") is reused across batches -- e.g. both the `sample` and `sample2` batches have their own well001..well023. `subject_id` (e.g. `sample_well001` vs `sample2_well001`) is the correct distinct-organoid grouping key, NOT well_id alone.

| subject_id      | batch   | well_id   |   n_sessions |   n_with_raw | ages                             |
|:----------------|:--------|:----------|-------------:|-------------:|:---------------------------------|
| sample2_well000 | sample2 | well000   |            1 |            1 | ['P41D']                         |
| sample2_well001 | sample2 | well001   |            1 |            1 | ['P41D']                         |
| sample2_well002 | sample2 | well002   |            1 |            1 | ['P41D']                         |
| sample2_well003 | sample2 | well003   |            1 |            1 | ['P41D']                         |
| sample2_well004 | sample2 | well004   |            1 |            1 | ['P41D']                         |
| sample2_well005 | sample2 | well005   |            1 |            1 | ['P41D']                         |
| sample2_well006 | sample2 | well006   |            1 |            1 | ['P41D']                         |
| sample2_well007 | sample2 | well007   |            1 |            1 | ['P41D']                         |
| sample2_well008 | sample2 | well008   |            1 |            1 | ['P41D']                         |
| sample2_well009 | sample2 | well009   |            1 |            1 | ['P41D']                         |
| sample2_well010 | sample2 | well010   |            1 |            1 | ['P41D']                         |
| sample2_well011 | sample2 | well011   |            1 |            1 | ['P41D']                         |
| sample2_well012 | sample2 | well012   |            1 |            1 | ['P41D']                         |
| sample2_well013 | sample2 | well013   |            1 |            1 | ['P41D']                         |
| sample2_well014 | sample2 | well014   |            1 |            1 | ['P41D']                         |
| sample2_well015 | sample2 | well015   |            1 |            1 | ['P41D']                         |
| sample2_well016 | sample2 | well016   |            1 |            1 | ['P41D']                         |
| sample2_well017 | sample2 | well017   |            1 |            1 | ['P41D']                         |
| sample2_well018 | sample2 | well018   |            1 |            1 | ['P41D']                         |
| sample2_well019 | sample2 | well019   |            1 |            1 | ['P41D']                         |
| sample2_well020 | sample2 | well020   |            1 |            1 | ['P41D']                         |
| sample2_well021 | sample2 | well021   |            1 |            1 | ['P41D']                         |
| sample2_well022 | sample2 | well022   |            1 |            1 | ['P41D']                         |
| sample2_well023 | sample2 | well023   |            1 |            1 | ['P41D']                         |
| sample_well000  | sample  | well000   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well001  | sample  | well001   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well002  | sample  | well002   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well003  | sample  | well003   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well004  | sample  | well004   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well005  | sample  | well005   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well006  | sample  | well006   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well007  | sample  | well007   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well008  | sample  | well008   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well009  | sample  | well009   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well010  | sample  | well010   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well011  | sample  | well011   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well012  | sample  | well012   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well013  | sample  | well013   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well014  | sample  | well014   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well015  | sample  | well015   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well016  | sample  | well016   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well017  | sample  | well017   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well018  | sample  | well018   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well019  | sample  | well019   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well020  | sample  | well020   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well021  | sample  | well021   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well022  | sample  | well022   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |
| sample_well023  | sample  | well023   |            4 |            4 | ['P52D', 'P57D', 'P71D', 'P75D'] |

## Settings audit — MaxOne (001603) vs MaxTwo (001872), human subjects only (VERIFY item, Task 0.4)

| platform        |   n_recordings_total_all_species |   n_recordings_total_human |   n_recordings_with_raw | sampling_rate_Hz_unique   | raw_dtype_unique   | n_electrodes_unique                                                                                                                                                                                                                                                                                                                                                                                                                                          |   electrode_pitch_raw_units_median | electrode_geometry_cols_unique   |
|:----------------|---------------------------------:|---------------------------:|------------------------:|:--------------------------|:-------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------:|:---------------------------------|
| MaxOne (001603) |                              111 |                         44 |                      20 | [20000.0]                 | ['uint16']         | [1014.0, 1020.0]                                                                                                                                                                                                                                                                                                                                                                                                                                             |                                 35 | ['rel_x,rel_y']                  |
| MaxTwo (001872) |                              120 |                        120 |                     120 | [10000.0]                 | ['uint16']         | [107, 114, 120, 130, 137, 144, 148, 149, 151, 158, 159, 162, 165, 166, 168, 169, 170, 173, 180, 183, 187, 192, 194, 196, 205, 210, 225, 251, 253, 256, 258, 259, 261, 271, 273, 276, 281, 295, 333, 337, 344, 357, 368, 369, 388, 400, 402, 452, 503, 523, 530, 540, 592, 608, 619, 644, 651, 667, 690, 697, 703, 723, 725, 731, 762, 778, 795, 808, 813, 850, 859, 870, 874, 916, 923, 951, 967, 990, 1006, 1008, 1009, 1015, 1016, 1017, 1018, 1019, 1020] |                                 35 | ['rel_x,rel_y']                  |

## Verified vs assumed

- VERIFIED: asset counts, per-asset raw/Units presence, sampling rate, dtype, electrode count and geometry columns, well/subject grouping — all read directly from each NWB file's own metadata via streaming (no download).
- ASSUMED: `electrode_pitch_raw_units` assumes the electrode table's x/y (or rel_x/rel_y) columns are in a consistent, comparable unit within each platform; the actual unit was not independently confirmed against device documentation and should be checked before using pitch for cross-platform decisions.
- ASSUMED: subject_type classification (recorded vs sourced) uses only presence of a raw ElectricalSeries in *this* dandiset's assets — a subject could in principle have raw data hosted elsewhere and only Units deposited here; not cross-checked against dandiset descriptions/publications beyond what's in NWB metadata.
- VERIFIED: species per subject, read directly from NWB Subject metadata — confirms 001603 mixes Homo sapiens subjects with Mus musculus / Rattus norvegicus reference subjects; 001872 subjects are all Homo sapiens.
- NOT YET VERIFIED: whether the 4 `PR1-4` (rat) / `PR5-8` (mouse) subjects that have neither raw nor Units data are empty/placeholder NWB files or contain some other data type (e.g. stimulus/protocol only) not captured by this manifest's columns — not investigated further since these are non-human and out of scope regardless.

## Open questions

- **Exclude non-human subjects going forward**: confirm it's fine to drop all `M1S*/M2S*/M3S*`, `MO*`, `PR*` subjects from 001603 for the rest of this project (28 of 36 subjects) — only `HO1-HO8` are human.
- Confirm the well -> organoid mapping for 001872: does each well_id correspond to one biological organoid across all its sessions, or could a well have been re-seeded between sessions (which would break the organoid-as-grouping-unit guardrail)? Note the `sample` batch has multiple sessions per well spanning different ages while `sample2` has one session per well — worth confirming these are genuinely longitudinal recordings of the same organoid within `sample`, not re-seeds.
- Any settings_audit.csv mismatches (sampling rate, dtype, pitch) must be resolved or explicitly flagged as platform-sensitive before Stage 2.
- 001872's `n_electrodes` varies a lot even within the `sample2` batch (107-608) recorded in the same session batch — worth confirming whether this reflects a per-well active-electrode selection step (expected) rather than a data-quality issue.