Persistence cohort metadata

Sampling frame: repositories containing at least one actively verified drifted claim of a trackable type
(artifact_ref, local_link_ref, cd_dir, python_script, make_target, pip_requirements, run_shell_script,
bash_script) under the intermediate, sequence-aware detector version current at sampling time
(hygiene filters H1-H7, before H8-H9 and the final rule refinements): 183 repositories.
Under the final detector (data/03_labels/drift_results_detailed.csv) the same condition holds for 136
repositories.

Sample: 100 repositories drawn at random from the 183 (seed 20260905), one drifted claim drawn at random
per repository -> persistence_cohort_random100.csv (label_v4 column = label under the intermediate version).

History walk (Script 10): 300 most recent commits per case, coarse grid of 12 commits then linear refinement
-> persistence_cases_all_v5walk.csv (all 100 cases).

Final cases: the 64 cases still labelled drifted by the final detector, of which 47 have a usable onset
(17: claim text not found within the 300-commit window) -> persistence_cases_v6.csv; Kaplan-Meier curve
with Greenwood bands -> kaplan_meier_curve_v6.csv; summary -> persistence_v6.json.

Adjudication: every one of the 47 cases carries a codebook label (persistence_cohort_adjudication.csv).
24 cases also fall in the held-out evaluation set and carry the two coders' consensus label (label_source =
coders_consensus, with the evaluation id); the other 23 were labelled by the author from the README passage and
the repository tree (label_source = author), with the justification recorded. Result: 6 drifted, 6 supported,
18 uncertain, 17 not-a-claim. The article reports the six confirmed cases separately (one corrected, P077, after
1,705 days; five censored at 151 to 1,344 days) and the Kaplan-Meier analysis over all 47 detector-labelled cases
as a sensitivity analysis -> persistence_adjudicated_summary.json.
