"""Script 07: prevalence, CIs, robustness, per-group tables and entropies on the v6 labels.
Input : data/03_labels/drift_results_detailed.csv
Output: data/04_metrics/metrics.json, data/04_metrics/by_*.csv, data/04_metrics/drift_families.csv
"""
import pandas as pd, numpy as np, json
o = pd.read_csv("data/03_labels/drift_results_detailed.csv")
k = o[o.status == "kept"].copy()
k["drifted"] = k.label_v4.isin(["drifted_high", "drifted_medium"])
k["supported"] = k.label_v4 == "supported"
k["uncertain"] = k.label_v4 == "uncertain"
rng = np.random.default_rng(42)
repos = k.full_name.unique()

def boot_ci(stat, B=2000):
    vals = []
    groups = {r: g for r, g in k.groupby("full_name")}
    for _ in range(B):
        samp = rng.choice(repos, size=len(repos), replace=True)
        df = pd.concat([groups[r] for r in samp])
        vals.append(stat(df))
    return np.percentile(vals, [2.5, 97.5])

res = {}
res["n_claims"] = len(k); res["n_repos"] = len(repos)
res["drift_rate"] = k.drifted.mean(); res["support_rate"] = k.supported.mean(); res["uncertain_rate"] = k.uncertain.mean()
res["DRI"] = res["support_rate"] - res["drift_rate"]
res["drift_rate_ci95_cluster_boot"] = list(boot_ci(lambda d: d.drifted.mean()))
rep = k.groupby("full_name").agg(n=("drifted", "size"), d=("drifted", "sum"), s=("supported", "sum"), u=("uncertain", "sum"))
rep["drift_rate"] = rep.d / rep.n; rep["support_rate"] = rep.s / rep.n; rep["DRI"] = rep.support_rate - rep.drift_rate
res["repo_any_drift"] = (rep.d > 0).mean(); res["repo_any_drift_n"] = int((rep.d > 0).sum())
res["repo_any_drift_ci95"] = list(boot_ci(lambda d: (d.groupby("full_name").drifted.sum() > 0).mean()))
res["repo_drift_rate_mean"] = rep.drift_rate.mean(); res["repo_drift_rate_sd"] = rep.drift_rate.std(); res["repo_drift_rate_median"] = rep.drift_rate.median()
res["repo_zero_drift_share"] = (rep.d == 0).mean(); res["repo_DRI_1_share"] = (rep.DRI == 1).mean()
res["repo_drift_gt50"] = int((rep.drift_rate > 0.5).sum()); res["repo_drift_100"] = int((rep.drift_rate == 1).sum())
x = np.sort(rep.support_rate.values); n = len(x)
res["gini_support_rate"] = float((2 * np.sum((np.arange(1, n + 1)) * x) / (n * x.sum())) - (n + 1) / n)
mu = x.mean(); xp = x[x > 0]; res["theil_support_rate"] = float(np.mean((xp / mu) * np.log(xp / mu)) * len(xp) / n)
# robustness
strict = (k.label_v4 == "drifted_high"); lenient = k.drifted | k.uncertain
res["robust"] = {
    "strict_claim": strict.mean(), "strict_repo": (k.assign(x=strict).groupby("full_name").x.sum() > 0).mean(),
    "primary_claim": k.drifted.mean(), "primary_repo": res["repo_any_drift"],
    "lenient_claim": lenient.mean(), "lenient_repo": (k.assign(x=lenient).groupby("full_name").x.sum() > 0).mean(),
}
# family / type / context / section tables
def tab(col):
    t = k.groupby(col).agg(n=("drifted", "size"), drifted=("drifted", "sum"), uncertain=("uncertain", "sum"), supported=("supported", "sum"),
                           verified=("verification", lambda s: (s != "external").sum()))
    t["drift_rate"] = (100 * t.drifted / t.n).round(1); t["DRI"] = ((t.supported - t.drifted) / t.n).round(3)
    return t.sort_values("n", ascending=False)
tab("claim_family").to_csv("data/04_metrics/by_claim_family.csv")
ct = tab("claim_type"); ct.to_csv("data/04_metrics/by_claim_type.csv")
tab("context_type").to_csv("data/04_metrics/by_context_type.csv")
tab("section_class").to_csv("data/04_metrics/by_section_class.csv")
fam = k[k.drifted].drift_family_v4.value_counts(); (100 * fam / fam.sum()).round(1)
pd.DataFrame({"drifted": fam, "share_pct": (100 * fam / fam.sum()).round(1)}).to_csv("data/04_metrics/drift_families.csv")
# command family excluding cd_dir
c = k[(k.claim_family == "command") & (k.claim_type != "cd_dir")]
res["command_excl_cd_drift"] = c.drifted.mean(); res["command_excl_cd_n"] = len(c)
res["artifact_family_drift"] = k[k.claim_family == "artifact_reference"].drifted.mean()
res["command_family_drift"] = k[k.claim_family == "command"].drifted.mean()
res["share_actively_verified"] = (k.verification != "external").mean()
res["share_sequence_supported"] = (k.verification == "sequence").mean()
# entropy
p = ct.n / ct.n.sum(); res["claim_type_entropy_bits"] = float(-(p * np.log2(p)).sum()); res["n_types"] = len(ct)
pf = fam / fam.sum(); res["drift_family_entropy_bits"] = float(-(pf * np.log2(pf)).sum())
# original-vs-refined comparison on same claims
res["original_drift_rate_all7992"] = 1377 / 7992
res["original_drift_on_kept"] = float(k.drifted_v3.mean())
res["excluded_noise"] = int((o.status == "excluded").sum())
json.dump(res, open("data/04_metrics/metrics.json", "w"), indent=2, default=float)
print(json.dumps(res, indent=2, default=float))
print(tab("claim_family")); print(fam); print(tab("context_type")); print(tab("section_class"))
