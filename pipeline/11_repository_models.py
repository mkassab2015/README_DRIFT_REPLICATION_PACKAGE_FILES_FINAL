"""Script 11: repository-level models on the v6 dataset.
Input : data/07_models/repo_modeling_dataset_v6.csv
Output: data/07_models/regression_v6.txt (logistic any-drift; NB2 count with log(claims) offset; VIF)
"""
import pandas as pd, numpy as np, statsmodels.api as sm, statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
d = pd.read_csv("data/07_models/repo_modeling_dataset_v6.csv")
X = d[["log_stars","age_y","days_since_push","log_words","log_claims"]]
out = []
logit = smf.logit("any ~ log_stars + age_y + days_since_push + log_words + log_claims", d).fit(disp=0)
t = logit.summary2().tables[1].round(3); t["OR"] = np.exp(logit.params).round(3)
out += ["LOGISTIC any-drift", t.to_string(), f"pseudo-R2 {logit.prsquared:.3f} n={int(logit.nobs)}", ""]
nb = sm.NegativeBinomial(d["drifted"], sm.add_constant(d[["log_stars","age_y","days_since_push","log_words"]]), offset=d["log_claims"]).fit(disp=0, maxiter=200)
t2 = nb.summary2().tables[1].round(3); t2["IRR"] = np.exp(nb.params).round(3)
out += ["NEGATIVE BINOMIAL drifted count, offset log(claims)", t2.to_string(), ""]
Xc = sm.add_constant(X); vif = {c: variance_inflation_factor(Xc.values, i) for i, c in enumerate(Xc.columns) if c != "const"}
out += ["VIF: " + ", ".join(f"{k}={v:.2f}" for k, v in vif.items())]
open("data/07_models/regression_v6_reproduced.txt", "w").write("\n".join(out)); print("\n".join(out))
