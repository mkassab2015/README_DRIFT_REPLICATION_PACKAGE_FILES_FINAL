"""Script 08: all Section 4 figures from the v6 outputs.
Inputs: data/03_labels/, data/04_metrics/, data/06_persistence/. Output: figures/
"""
import pandas as pd, numpy as np, json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 200})
O = "figures/"; import os; os.makedirs(O, exist_ok=True)
BLUE, ORANGE, GREY, RED = "#1f5fa8", "#d97706", "#8a8f98", "#b42318"
o = pd.read_csv("data/03_labels/drift_results_detailed.csv"); k = o[o.status == "kept"].copy()
k["drifted"] = k.label_v4.isin(["drifted_high", "drifted_medium"]); k["supported"] = k.label_v4 == "supported"; k["uncertain"] = k.label_v4 == "uncertain"

# Fig 2a: claim-type Pareto (v5)
ct = k.claim_type.value_counts(); cum = ct.cumsum() / ct.sum() * 100
fig, ax = plt.subplots(figsize=(6.5, 3.2)); ax.bar(range(len(ct)), ct.values, color=BLUE); ax2 = ax.twinx(); ax2.plot(range(len(ct)), cum.values, color=ORANGE, lw=1.5)
ax.set_xticks(range(len(ct))); ax.set_xticklabels([t.replace("_", "\n") for t in ct.index], rotation=90, fontsize=5.5); ax.set_ylabel("Claims"); ax2.set_ylabel("Cumulative %"); ax2.set_ylim(0, 105); ax2.spines["top"].set_visible(False)
plt.tight_layout(); plt.savefig(O + "fig2a_claim_type_pareto.png"); plt.savefig(O + "fig2a_claim_type_pareto.pdf"); plt.close()

# Fig 2b: drift by context
cx = k.groupby("context_type").agg(n=("drifted", "size"), d=("drifted", "sum")); cx["rate"] = 100 * cx.d / cx.n; cx = cx.sort_values("rate")
fig, ax = plt.subplots(figsize=(5.2, 3)); ax.barh(cx.index, cx.rate, color=[ORANGE if "artifact" in i or i == "markdown_link" else BLUE for i in cx.index])
for i, (r, n) in enumerate(zip(cx.rate, cx.n)): ax.text(r + 0.5, i, f"{r:.1f}%  (n={n})", va="center", fontsize=7)
ax.set_xlabel("Drift rate (%)"); ax.set_xlim(0, max(cx.rate) + 15); plt.tight_layout(); plt.savefig(O + "fig2b_drift_by_context.png"); plt.savefig(O + "fig2b_drift_by_context.pdf"); plt.close()

# Fig 3: label distribution overall and by family
fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.8))
tot = k.label_v4.map(lambda x: "drifted" if x.startswith("drifted") else x).value_counts()
axes[0].pie([tot["supported"], tot["drifted"], tot["uncertain"]], labels=[f"supported {100*tot['supported']/len(k):.1f}%", f"drifted {100*tot['drifted']/len(k):.1f}%", f"uncertain {100*tot['uncertain']/len(k):.1f}%"], colors=[BLUE, RED, GREY], startangle=90, textprops={"fontsize": 7}, wedgeprops={"width": 0.45}); axes[0].set_title(f"All claims (N={len(k):,})", fontsize=8)
fam = k.groupby("claim_family").agg(s=("supported", "mean"), d=("drifted", "mean"), u=("uncertain", "mean"))
x = np.arange(2); axes[1].bar(x, fam.s * 100, color=BLUE, label="supported"); axes[1].bar(x, fam.d * 100, bottom=fam.s * 100, color=RED, label="drifted"); axes[1].bar(x, fam.u * 100, bottom=(fam.s + fam.d) * 100, color=GREY, label="uncertain")
axes[1].set_xticks(x); axes[1].set_xticklabels([f"artifact reference\n(n={int((k.claim_family=='artifact_reference').sum())})", f"command\n(n={int((k.claim_family=='command').sum())})"], fontsize=7); axes[1].set_ylabel("%"); axes[1].legend(fontsize=6, frameon=False, loc="lower right")
for i, f in enumerate(fam.index): axes[1].text(i, fam.s[f] * 100 + fam.d[f] * 50, f"{fam.d[f]*100:.1f}%", ha="center", fontsize=7, color="white")
plt.tight_layout(); plt.savefig(O + "fig3_labels_overall_family.png"); plt.savefig(O + "fig3_labels_overall_family.pdf"); plt.close()

# Fig 4: repo-level ECDF and DRI histogram
rep = k.groupby("full_name").agg(n=("drifted", "size"), d=("drifted", "sum"), s=("supported", "sum")); rep["rate"] = rep.d / rep.n; rep["DRI"] = (rep.s - rep.d) / rep.n
fig, axes = plt.subplots(1, 2, figsize=(6.5, 2.7)); xs = np.sort(rep.rate); axes[0].step(xs, np.arange(1, len(xs) + 1) / len(xs), where="post", color=BLUE); axes[0].set_xlabel("Repository drift rate"); axes[0].set_ylabel("Cumulative share of repositories"); axes[0].set_ylim(0, 1.02)
axes[0].annotate(f"{100*(rep.d==0).mean():.1f}% zero drift", xy=(0.02, (rep.d == 0).mean()), fontsize=7)
axes[1].hist(rep.DRI, bins=np.linspace(-1, 1, 21), color=BLUE); axes[1].set_xlabel("Repository DRI"); axes[1].set_ylabel("Repositories"); plt.tight_layout(); plt.savefig(O + "fig4_repo_distribution.png"); plt.savefig(O + "fig4_repo_distribution.pdf"); plt.close()

# Fig 5: drift rate by claim type (verified types only), bubble
t = k.groupby("claim_type").agg(n=("drifted", "size"), d=("drifted", "sum"), v=("verification", lambda s: (s != "external").sum())); t = t[(t.v > 0) & (t.n >= 10)]; t["rate"] = 100 * t.d / t.n; t = t.sort_values("rate")
fig, ax = plt.subplots(figsize=(6.5, 3.4)); ax.scatter(range(len(t)), t.rate, s=np.sqrt(t.n) * 12, color=[RED if r > 10 else (ORANGE if r > 3 else BLUE) for r in t.rate], alpha=0.8)
ax.set_xticks(range(len(t))); ax.set_xticklabels(t.index, rotation=60, ha="right", fontsize=7); ax.set_ylabel("Drift rate (%)"); ax.set_title("Actively verified claim types (n ≥ 10); area ∝ claims", fontsize=8); plt.tight_layout(); plt.savefig(O + "fig5_drift_by_type.png"); plt.savefig(O + "fig5_drift_by_type.pdf"); plt.close()

# Fig 6: drift families
names = {"D1": "D1 dependency manifest", "D2": "D2 entrypoint/script", "D3": "D3 directory navigation", "D4": "D4 build target", "D5": "D5 local install target", "D6": "D6 test-command support", "D7": "D7 container/deployment", "D8": "D8 local artifact reference"}
fam = k[k.drifted].drift_family_v4.value_counts().reindex(["D1","D2","D3","D4","D5","D6","D7","D8"]).fillna(0).astype(int).sort_values()
fig, ax = plt.subplots(figsize=(5.5, 2.8)); ax.barh([names[i] for i in fam.index], fam.values, color=BLUE)
for i, v in enumerate(fam.values): ax.text(v + 1, i, f"{v} ({100*v/fam.sum():.1f}%)" + (" (0 of 122 claims)" if v == 0 else ""), va="center", fontsize=7)
ax.set_xlabel("Drifted claims"); ax.set_xlim(0, fam.max() * 1.25); plt.tight_layout(); plt.savefig(O + "fig6_drift_families.png"); plt.savefig(O + "fig6_drift_families.pdf"); plt.close()

# Fig 7: robustness incl. naive vs sequence-aware
r = json.load(open("data/04_data/04_metrics/metrics.json"))["robust"]
labels = ["Initial detector,\nall candidates", "Initial detector,\nfiltered claims", "Final,\nstrict", "Final,\nprimary", "Final,\nlenient"]
claim = [17.23, 100 * json.load(open("data/04_data/04_metrics/metrics.json"))["original_drift_on_kept"], 100 * r["strict_claim"], 100 * r["primary_claim"], 100 * r["lenient_claim"]]
repo = [55.27, np.nan, 100 * r["strict_repo"], 100 * r["primary_repo"], 100 * r["lenient_repo"]]
fig, ax = plt.subplots(figsize=(6.5, 2.8)); x = np.arange(5); ax.bar(x - 0.18, claim, 0.36, color=BLUE, label="claim level"); ax.bar(x + 0.18, [0 if np.isnan(v) else v for v in repo], 0.36, color=ORANGE, label="repository level")
for i in range(5):
    ax.text(x[i] - 0.18, claim[i] + 1, f"{claim[i]:.1f}", ha="center", fontsize=6.5)
    if not np.isnan(repo[i]): ax.text(x[i] + 0.18, repo[i] + 1, f"{repo[i]:.1f}", ha="center", fontsize=6.5)
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7); ax.set_ylabel("Drift prevalence (%)"); ax.legend(fontsize=7, frameon=False); plt.tight_layout(); plt.savefig(O + "fig7_robustness.png"); plt.savefig(O + "fig7_robustness.pdf"); plt.close()

# Fig 8: KM v5
K = pd.read_csv("data/06_persistence/kaplan_meier_curve_v6.csv"); P = json.load(open("data/06_persistence/persistence_v6.json")); ok = pd.read_csv("data/06_persistence/persistence_cases_v6.csv")
fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.9))
axes[0].step(K.time_days, K.survival, where="post", color=BLUE, label=f"KM estimate (N={P['n_ok']})"); axes[0].fill_between(K.time_days, K.ci_low, K.ci_high, step="post", alpha=0.18, color=BLUE, label="95% CI (Greenwood)")
axes[0].scatter(ok[ok.event_fixed == 1].duration_days, [K[K.time_days <= d].survival.iloc[-1] for d in ok[ok.event_fixed == 1].duration_days], color=ORANGE, s=14, zorder=3, label=f"observed fixes (n={P['fixed']})")
axes[0].set_ylim(0, 1.02); axes[0].set_xlabel("Days since first detectable drift"); axes[0].set_ylabel("Probability drift remains unfixed"); axes[0].legend(fontsize=6.5, frameon=False, loc="lower left")
axes[1].hist(ok.duration_days, bins=20, color=GREY); axes[1].set_xlabel("Observed duration (days)"); axes[1].set_ylabel("Cases"); axes[1].set_title(f"{P['censored']} censored, {P['fixed']} fixed", fontsize=8)
plt.tight_layout(); plt.savefig(O + "fig8_km_persistence.png"); plt.savefig(O + "fig8_km_persistence.pdf"); plt.close()
print(os.listdir(O))


# ---- combined RQ1 figure (paper Figure 2) ----
import pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 200})
O = "figures/"
BLUE, ORANGE = "#1f5fa8", "#d97706"
o = pd.read_csv("data/03_labels/drift_results_detailed.csv"); k = o[o.status == "kept"].copy()
k["drifted"] = k.label_v4.isin(["drifted_high", "drifted_medium"])

fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.6), gridspec_kw={"width_ratios": [1.05, 1]})
# (a) claim types: top 20 + remainder, with cumulative share
ct = k.claim_type.value_counts(); TOP = 20
top = ct.iloc[:TOP]; rest = ct.iloc[TOP:]
labels = [t.replace("_", " ") for t in top.index] + [f"other {len(rest)} types"]
vals = list(top.values) + [rest.sum()]
cum = np.cumsum(vals) / ct.sum() * 100
fam = k.drop_duplicates("claim_type").set_index("claim_type").claim_family
cols = [ORANGE if fam.get(t) == "artifact_reference" else BLUE for t in top.index] + ["#8a8f98"]
y = np.arange(len(vals))[::-1]
ax = axes[0]; ax.barh(y, vals, color=cols)
for yi, v, c in zip(y, vals, cum): ax.text(v + 25, yi, f"{v:,}  ({c:.0f}%)", va="center", fontsize=6.2)
ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=6.8); ax.set_xlabel("Claims (cumulative share in parentheses)"); ax.set_xlim(0, max(vals) * 1.32)
ax.set_title("(a) Claim types (N = 7,034)", fontsize=8.5, loc="left")
# (b) drift rate by surface context
cx = k.groupby("context_type").agg(n=("drifted", "size"), d=("drifted", "sum")); cx["rate"] = 100 * cx.d / cx.n; cx = cx.sort_values("rate")
ax = axes[1]; NAME={"fenced_code":"fenced code (command)","inline_code_command":"inline code (command)","section_line_command":"prose line (command)","inline_code_artifact":"inline code (artifact)","markdown_link":"Markdown link (local file)","section_line_artifact":"prose line (artifact)","fenced_code_artifact":"fenced code (artifact)"}
ax.barh([NAME[i] for i in cx.index], cx.rate, color=[ORANGE if "artifact" in i or i == "markdown_link" else BLUE for i in cx.index])
for i, (r, n) in enumerate(zip(cx.rate, cx.n)): ax.text(r + 0.6, i, f"{r:.1f}%  (n={n:,})", va="center", fontsize=6.5)
ax.set_xlabel("Drift rate (%)"); ax.set_xlim(0, max(cx.rate) + 18); ax.tick_params(axis="y", labelsize=6.8)
ax.set_title("(b) Drift rate by surface context", fontsize=8.5, loc="left")
from matplotlib.patches import Patch
fig.legend(handles=[Patch(color=BLUE, label="command"), Patch(color=ORANGE, label="artifact reference"), Patch(color="#8a8f98", label="mixed")], loc="lower center", ncol=3, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.01))
plt.tight_layout(rect=(0, 0.04, 1, 1)); plt.savefig(O + "fig_rq1_landscape_v2.pdf"); plt.savefig(O + "fig_rq1_landscape_v2.png"); print("ok")

import shutil
for a,b in [("fig3_labels_overall_family","fig_rq2_prevalence_v2"),("fig4_repo_distribution","fig_rq2_repo_v2"),("fig5_drift_by_type","fig_rq3_claimtype_v2"),("fig6_drift_families","fig_rq3_families_v2"),("fig7_robustness","fig_rq4_robustness_v2"),("fig8_km_persistence","fig_rq5_persistence_v2")]:
    for ext in ("pdf","png"): shutil.copy(f"figures/{a}.{ext}", f"figures/{b}.{ext}")
