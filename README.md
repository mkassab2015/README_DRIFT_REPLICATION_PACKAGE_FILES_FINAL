# README Drift: Prevalence, Structure, and Persistence of Inconsistencies in Executable Repository Documentation

Replication package for the article of the same title (Empirical Software Engineering).
Everything reported in the article can be regenerated from this repository: the corpus,
the extracted claims, the verification labels, all metrics, tables and figures, the two
manual validation sets, the persistence analysis and the repository-level models.

## Layout

```
pipeline/                 numbered scripts, run in order (Python 3). Scripts 01 to 05 and 10 were run in
                          Google Colab and read/write a Google Drive folder; Scripts 06 to 09 and 11 run
                          locally from the repository root.
  01_corpus_sampling.py                  stratified GitHub search, 13 filters, exclusion log            -> data/01_corpus/
  02_readme_parsing.py                   headings, fenced blocks, inline code, links, prose lines        -> data/02_claims/readme_structure
  03_claim_extraction.py                 37 a priori claim types, 4 surface contexts                     -> data/02_claims/candidate_claims
  04_artifact_indexing.py                files, directories, base names, Makefile targets, manifests     -> data/01_corpus/artifact_index
  05a_verification_context_free_baseline.py   per-claim lookup without sequence context (sensitivity baseline, Section 4.4)
  05b_verification_sequence_aware.py     final detector: hygiene filters H1-H9, working-directory tracking,
                                         artifacts created by earlier steps, run-time lexicon, rules per type -> data/03_labels/
  06_validation_sampling.py              sampling design of the two coded samples (the coded draws are the released files)
  07_metrics.py                          prevalence, cluster-bootstrap CIs, robustness, per-group tables, entropies -> data/04_metrics/
  08_figures.py                          Figures 2 to 8                                                  -> figures/
  09_validation_scoring.py               coder agreement, detector precision/recall, precision-adjusted prevalence -> data/05_validation/
  10_persistence.py                      random cohort, 300-commit history walk, Kaplan-Meier with Greenwood bands -> data/06_persistence/
  11_repository_models.py                logistic and negative binomial models, VIF                      -> data/07_models/

data/
  01_corpus/        repos_pilot_v3.csv (905 accepted repositories), repo_skip_log_pilot_v3.csv (1,095 exclusions
                    with the filter responsible), readmes_pilot_v3.csv, configs_pilot_v3.csv,
                    trees_pilot_v3.csv.gz (1.30 M tree entries), artifact_index_pilot_v3.csv.gz
  02_claims/        readme_structure_pilot_v3.csv (parsed READMEs), candidate_claims_pilot_v3.csv (7,992 candidates)
  03_labels/        drift_results_detailed.csv   one row per candidate: status (kept, or excluded with filter), label
                                                 (supported, drifted_high, drifted_medium, uncertain), drift family,
                                                 verification mode (verified, sequence, external, uncertain), reason
                    drift_results_summary.csv    per-repository totals
                    drifted_claims_v6.csv        the 246 drifted claims with the kind of artifact named
                    baseline_context_free_*.csv  labels of the context-free baseline (Script 05a)
                    reclassification_audit.csv   every claim whose label differs between 05a and 05b, with the rule responsible
  04_metrics/       metrics.json and the per-type, family, context and section tables (Tables 4 to 8 of the article)
  05_validation/    development set and evaluation set: both coders' files, consensus, sampling key, merged file, scores
  06_persistence/   random cohort (100 cases; sampling frame: the 183 repositories with a trackable drifted claim under the
                    intermediate detector version current at sampling time, 136 under the final detector; see
                    persistence_cohort_README.txt), history walk of all cases, the 47 usable cases with their codebook
                    adjudication (persistence_cohort_adjudication.csv: 6 confirmed drifted), KM curve, summaries
  07_models/        repository-level dataset (763 rows) and model output
figures/            Figure 1 (pipeline_v2) and Figures 2 to 8 (fig_rq*_v2) in PDF, PNG and JPG
docs/               codebook given to the coders (Appendix B of the article)
```

## Reproducing the article

Scripts 06 to 09 and 11 are deterministic given `data/03_labels/` and finish in minutes
(Script 07 runs 2,000 bootstrap replicates, about three minutes). Scripts 01 to 05 and 10
query the GitHub API and depend on its state at run time (corpus snapshot: March 2026;
persistence walk: September 2026); their outputs are included so that every downstream
number can be checked without a token. Script 05b is deterministic given the outputs of
Scripts 03 and 04 and reproduces `data/03_labels/` exactly.

The two Google Drive scripts expect a folder `README_Drift_Revision` containing
`drift_results_pilot_v3_detailed.csv` (output of 05a), `artifact_index_pilot_v3.csv`,
`readme_structure_pilot_v3.csv` and `repos_pilot_v3.csv` (Script 05b) and, for Script 10,
a GitHub token; see the header of each script.

## Licence

Code under MIT, data and figures under CC BY 4.0 (see LICENSE); retrieved README texts and trees keep their original licences.

## Requirements

Python 3.10 or later; pandas, numpy, matplotlib, statsmodels, scikit-learn, openpyxl, Pillow.

## Citing

Please cite the article and this package (Zenodo DOI given in the article's data availability statement; CITATION.cff).
