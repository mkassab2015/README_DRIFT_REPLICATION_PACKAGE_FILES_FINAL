"""
06_validation_sampling.py -- stratified sampling of claims for manual coding.

Two samples of 200 claims were coded (article, Section 3.7):

  development set  drawn from the labels of the initial, context-free detector
                   (output of 05a): 80 claims labelled drifted, 80 supported and
                   40 uncertain, stratified over claim type; used to diagnose that
                   detector and to refine the hygiene filters and sequence rules.

  evaluation set   drawn after the rules were frozen, from the labels of the
                   sequence-aware detector current at that time, stratified by
                   detector outcome: 80 drifted, 40 supported by active
                   verification, 15 supported only through sequence context,
                   10 externally grounded, 25 uncertain and 30 removed by the
                   hygiene filters. One claim sampled as drifted became supported
                   under the final rule refinements of 05b and is counted in the
                   supported row of Table 12.

The two draws that were actually coded are the files released in
data/05_validation/ (development_set_*.xlsx, evaluation_set_*.xlsx and
evaluation_set_sampling_key.csv); those files are the record of the samples
and every validation figure in the article is computed from them by
09_validation_scoring.py. This script documents the sampling design and
regenerates a draw of the same design from the released labels; because the
evaluation set was drawn from the detector labels current at sampling time,
re-running it against the final labels in data/03_labels/ produces a sample of
the same composition but not the identical rows.

Usage:  python pipeline/06_validation_sampling.py [--seed N] [--out DIR]
"""
import argparse, pandas as pd

SIZES_EVAL = {"drifted": 80, "supported": 40, "supported_sequence": 15,
              "supported_external": 10, "uncertain": 25, "excluded": 30}
SIZES_DEV  = {"drifted": 80, "supported": 80, "uncertain": 40}
COLS = ["full_name", "claim_type", "artifact_or_path", "snippet", "heading",
        "line_no", "context_type"]

def stratum_final(r):
    if r.status != "kept": return "excluded"
    if str(r.label_v4).startswith("drifted"): return "drifted"
    if r.label_v4 == "uncertain": return "uncertain"
    return {"verified": "supported", "sequence": "supported_sequence",
            "external": "supported_external"}[r.verification]

def blind(df, prefix):
    """Coder view: repository, claim, passage and artifact; no detector label."""
    out = df[COLS].copy()
    out.insert(0, "eval_id", [f"{prefix}_{i+1:03d}" for i in range(len(out))])
    out["coder_label"] = ""; out["coder_justification"] = ""; out["artifact_found"] = ""
    return out

def draw(df, sizes, seed, by_type=False):
    parts = []
    for s, n in sizes.items():
        pool = df[df.stratum == s]
        if by_type:   # proportional over claim type within the stratum
            sub = [g.sample(n=max(1, round(n * len(g) / len(pool))), random_state=seed)
                   for _, g in pool.groupby("claim_type")]
            parts.append(pd.concat(sub).sample(frac=1, random_state=seed).head(n))
        else:
            parts.append(pool.sample(n=n, random_state=seed))
    return pd.concat(parts).sample(frac=1, random_state=seed).reset_index(drop=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--out", default="data/05_validation/regenerated"); a = ap.parse_args()
    import os; os.makedirs(a.out, exist_ok=True)
    # evaluation-set design, from the final labels
    d = pd.read_csv("data/03_labels/drift_results_detailed.csv")
    d["stratum"] = d.apply(stratum_final, axis=1)
    ev = draw(d, SIZES_EVAL, a.seed)
    ev_key = ev[COLS + ["stratum", "status", "label_v4"]].copy()
    ev_key.insert(0, "eval_id", [f"EVAL_{i+1:03d}" for i in range(len(ev_key))])
    ev_key.to_csv(f"{a.out}/evaluation_set_sampling_key.csv", index=False)
    blind(ev, "EVAL").to_excel(f"{a.out}/evaluation_set_blank.xlsx", index=False)
    # development-set design, from the context-free baseline labels
    b = pd.read_csv("data/03_labels/baseline_context_free_detailed.csv")
    b["stratum"] = b.label.map(lambda l: "drifted" if str(l).startswith("drifted") else l)
    dv = draw(b[b.stratum.isin(SIZES_DEV)], SIZES_DEV, a.seed, by_type=True)
    blind(dv, "DEV").to_excel(f"{a.out}/development_set_blank.xlsx", index=False)
    print("evaluation design:", ev.stratum.value_counts().to_dict())
    print("development design:", dv.stratum.value_counts().to_dict())
    print("Note: the coded samples are the released files in data/05_validation/; see docstring.")
