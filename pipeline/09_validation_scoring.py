"""Script 09: scoring of the two validation sets and the precision-adjusted prevalence.
Inputs : data/05_validation/development_set_consensus.xlsx, data/05_validation/evaluation_set_coder_A.xlsx, _B.xlsx,
         data/05_validation/evaluation_set_consensus.xlsx, data/05_validation/evaluation_set_sampling_key.csv,
         data/03_labels/drift_results_detailed.csv
Outputs: data/05_validation/validation_scores.txt, data/05_validation/evaluation_set_merged_v6.csv
"""
import pandas as pd, numpy as np
from sklearn.metrics import cohen_kappa_score
out = []
o = pd.read_csv("data/03_labels/drift_results_detailed.csv")
def fin(r):  # final-detector outcome incl. hygiene exclusion
    return "not-a-claim" if r.status == "excluded" else ("drifted" if str(r.label_v4).startswith("drifted") else r.label_v4)
def ini(x): return "drifted" if str(x).startswith("drifted") else x
def score(name, df, det):
    tp = ((df[det]=="drifted")&(df.gold=="drifted")).sum(); fp=((df[det]=="drifted")&(df.gold!="drifted")).sum(); fn=((df[det]!="drifted")&(df.gold=="drifted")).sum()
    out.append(f"[{name}] accuracy={(df[det]==df.gold).mean():.3f} kappa={cohen_kappa_score(df[det],df.gold):.3f} "
               f"drift P={tp/(tp+fp):.3f} ({tp}/{tp+fp}) R={tp/(tp+fn):.3f} ({tp}/{tp+fn}) F1={2*tp/(2*tp+fp+fn):.3f}")
    out.append(pd.crosstab(df[det], df.gold).to_string()); out.append("")
# ---- development set ----
c = pd.read_excel("data/05_validation/development_set_consensus.xlsx")
c["full_name"] = c.repository_url.str.replace("https://github.com/", "", regex=False)
d = c.merge(o[["full_name","line_no","claim_type","artifact_or_path","label","status","label_v4"]], on=["full_name","line_no","claim_type","artifact_or_path"], how="left").drop_duplicates("validation_id")
d["gold"] = d.consensus_label; d["final"] = d.apply(fin, axis=1); d["init"] = d.label.map(ini)
out.append(f"DEVELOPMENT SET n={len(d)} coder agreement={(d.coder_A_label==d.coder_B_label).mean():.3f} kappa={cohen_kappa_score(d.coder_A_label,d.coder_B_label):.3f}")
score("development / final detector", d, "final"); score("development / initial detector", d, "init")
# ---- evaluation set ----
A = pd.read_excel("data/05_validation/evaluation_set_coder_A.xlsx"); B = pd.read_excel("data/05_validation/evaluation_set_coder_B.xlsx")
C = pd.read_excel("data/05_validation/evaluation_set_consensus.xlsx"); K = pd.read_csv("data/05_validation/evaluation_set_sampling_key.csv")
m = A[["eval_id","claim_type","artifact_or_path","coder_label","coder_justification"]].rename(columns={"coder_label":"A","coder_justification":"jA"}) \
     .merge(B[["eval_id","coder_label","coder_justification"]].rename(columns={"coder_label":"B","coder_justification":"jB"}), on="eval_id") \
     .merge(K[["eval_id","full_name","stratum","status","label_v4"]], on="eval_id") \
     .merge(C[["eval_id","consensus_label","consensus_note"]], on="eval_id", how="left")
m["gold"] = np.where(m.A == m.B, m.A, m.consensus_label); assert m.gold.notna().all()
m["final"] = m.apply(fin, axis=1)
m = m.merge(o[["full_name","claim_type","artifact_or_path","label"]].drop_duplicates(), on=["full_name","claim_type","artifact_or_path"], how="left"); m["init"] = m.label.map(ini)
out.append(f"EVALUATION SET n={len(m)} coder agreement={(m.A==m.B).mean():.3f} kappa={cohen_kappa_score(m.A,m.B):.3f} "
           f"binary-drift kappa={cohen_kappa_score(m.A=='drifted', m.B=='drifted'):.3f}; gold={m.gold.value_counts().to_dict()}")
score("evaluation / final detector", m, "final"); score("evaluation / initial detector", m, "init")
out.append(pd.crosstab(m.stratum, m.gold).to_string()); out.append("")
# ---- precision-adjusted prevalence (stratified) ----
k = o[o.status == "kept"]
N = {"drifted": int(k.label_v4.str.startswith("drifted").sum()), "supported": int(((k.label_v4=="supported")&(k.verification=="verified")).sum()),
     "supported_sequence": int((k.verification=="sequence").sum()), "supported_external": int((k.verification=="external").sum()), "uncertain": int((k.label_v4=="uncertain").sum())}
def est(df):
    num = sum(n*(df[df.stratum==s].gold=="drifted").mean() for s,n in N.items()); den = sum(n*(df[df.stratum==s].gold!="not-a-claim").mean() for s,n in N.items()); return num, den, num/den
num, den, p = est(m); rng = np.random.default_rng(1)
boot = [est(pd.concat([m[m.stratum==s].sample(frac=1, replace=True, random_state=rng.integers(1e9)) for s in N]))[2] for _ in range(5000)]
out.append(f"PRECISION-ADJUSTED PREVALENCE: strata sizes {N}; estimated drifted claims {num:.1f} of {den:.0f} genuine = {100*p:.2f}% ; bootstrap 95% CI {100*np.percentile(boot,2.5):.2f}-{100*np.percentile(boot,97.5):.2f}%")
out.append(f"confirmed among detector-drifted: {N['drifted']*(m[m.stratum=='drifted'].gold=='drifted').mean():.1f} claims = {100*N['drifted']*(m[m.stratum=='drifted'].gold=='drifted').mean()/len(k):.2f}% of corpus")
m.to_csv("data/05_validation/evaluation_set_merged_v6.csv", index=False)
open("data/05_validation/validation_scores.txt", "w").write("\n".join(out)); print("\n".join(out))
