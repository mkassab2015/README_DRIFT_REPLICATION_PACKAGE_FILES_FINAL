# ============================================
# Script 11b (REVISION): Longitudinal persistence analysis on a RANDOM cohort of
# CONFIRMED drift cases, with corrected history checks.
#
# Differences from Script 11 (submitted version):
#   1. Input is the corrected claim table from Script 5b (drift_results_v4_detailed.csv),
#      restricted to kept, actively-verified, drifted claims of trackable types.
#   2. The cohort is a RANDOM sample (fixed seed) of repositories, one random case per
#      repository -- not the first 80 repositories in alphabetical order.
#   3. Optional manual confirmation: if you upload a CSV with a column
#      `confirmed` (yes/no) for the sampled cohort (produced by this script in
#      "cohort-only" mode), only confirmed cases are analysed.
#   4. History checks use directories as well as files (tree entries of type "tree"),
#      never strip leading dots, and verify `make <target>` against the Makefile at
#      that commit.
#   5. Deeper history (default 300 commits) and an explicit LEFT-TRUNCATION flag:
#      if the drift is already present at the oldest commit in the window, the
#      recorded onset is a lower bound, and the case is flagged (report separately).
#   6. Kaplan-Meier with Greenwood 95% confidence band.
#   7. Rate-limit aware GitHub client (waits for reset instead of aborting).
#
# Usage (Google Colab, Google Drive):
#   Reads <Drive>/<DRIVE_DIR>/outputs_script5b/drift_results_v4_detailed.csv (from Script 5b).
#   MODE = "cohort"  -> only writes the random cohort for manual confirmation
#   MODE = "analyse" -> analyses; uses persistence_cohort_v4_confirmed.csv if present in outputs_script11b/
#   MODE = "both"    -> skips the manual step and analyses the random cohort directly (default)
# ============================================

!pip -q install pandas numpy requests matplotlib

import os
import re
import time
import zipfile
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from google.colab import files

# -------------------------------------------------
# Controls
# -------------------------------------------------
MODE = "both"                  # "cohort" | "analyse" | "both"
RANDOM_SEED = 20260905
N_REPOS = 100                  # repositories to sample (one case each)
COMMITS_PER_REPO = 300         # history depth (most recent commits on default branch)
COARSE_GRID_POINTS = 12
SLEEP_BETWEEN_REQUESTS = 0.05

# Claim types whose support can be approximated from file/directory presence in a historical tree
ELIGIBLE_TYPES = {
    "artifact_ref", "local_link_ref", "cd_dir", "python_script",
    "pip_requirements", "run_shell_script", "bash_script", "make_target",
}

# -------------------------------------------------
# Inputs
# -------------------------------------------------
# -------------------------------------------------
# WHERE THE FILES ARE (Google Drive). Uses the outputs of Script 5b.
# -------------------------------------------------
DRIVE_DIR = "README_Drift_Revision"     # same folder you used for Script 5b

from google.colab import drive
drive.mount("/content/drive")
BASE = os.path.join("/content/drive/MyDrive", DRIVE_DIR)
detailed_file = os.path.join(BASE, "outputs_script5b", "drift_results_v4_detailed.csv")
if not os.path.exists(detailed_file):
    raise FileNotFoundError(f"Not found: {detailed_file}. Run Script 5b first.")
OUT_DIR = os.path.join(BASE, "outputs_script11b")
FIG_DIR = os.path.join(OUT_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)
confirmed_file = os.path.join(OUT_DIR, "persistence_cohort_v4_confirmed.csv")
confirmed_file = confirmed_file if os.path.exists(confirmed_file) else None

df = pd.read_csv(detailed_file)
for c in df.columns:
    if df[c].dtype == object:
        df[c] = df[c].fillna("").astype(str).str.strip()

# -------------------------------------------------
# Cohort construction (random, one case per repository)
# -------------------------------------------------
pool = df[
    (df["status"] == "kept")
    & df["label_v4"].isin(["drifted_high", "drifted_medium"])
    & (df["verification"] == "verified")
    & df["claim_type"].isin(ELIGIBLE_TYPES)
    & (df["artifact_or_path"] != "")
].copy()
print(f"Eligible confirmed-by-rule drift cases: {len(pool)} in {pool['full_name'].nunique()} repositories")

rng = np.random.default_rng(RANDOM_SEED)
repos = sorted(pool["full_name"].unique())
sampled_repos = list(rng.choice(repos, size=min(N_REPOS, len(repos)), replace=False))
cohort = (
    pool[pool["full_name"].isin(sampled_repos)]
    .groupby("full_name", group_keys=False)
    .apply(lambda g: g.sample(1, random_state=int(rng.integers(0, 2**31 - 1))))
    .reset_index(drop=True)
)
cohort.insert(0, "case_id", [f"P{str(i+1).zfill(3)}" for i in range(len(cohort))])
cohort["confirmed"] = ""      # fill in manually: yes / no
cohort["confirmation_note"] = ""
cohort_path = os.path.join(OUT_DIR, "persistence_cohort_v4.csv")
cohort[["case_id", "full_name", "claim_type", "artifact_or_path", "snippet", "context_type",
        "section_class", "line_no", "label_v4", "reason_v4", "confirmed", "confirmation_note"]].to_csv(cohort_path, index=False)
print(f"Random cohort: {len(cohort)} cases, one per repository (seed {RANDOM_SEED}). Saved to {cohort_path}")

if MODE == "cohort":
    raise SystemExit(f"Cohort written to {cohort_path}. Copy it to persistence_cohort_v4_confirmed.csv in the same folder, fill the 'confirmed' column (yes/no), then re-run with MODE='analyse'.")

if confirmed_file is not None:
    conf = pd.read_csv(confirmed_file)
    conf["confirmed"] = conf["confirmed"].fillna("").astype(str).str.strip().str.lower()
    keep_ids = set(conf.loc[conf["confirmed"].isin({"yes", "y", "true", "1"}), "case_id"])
    work = cohort[cohort["case_id"].isin(keep_ids)].reset_index(drop=True)
    print(f"Using {len(work)} manually confirmed cases.")
else:
    work = cohort.copy()
    print("No confirmation file supplied: analysing the full random cohort (rule-confirmed only).")

# -------------------------------------------------
# GitHub client
# -------------------------------------------------
token = input("Enter GitHub token: ").strip()
headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if token:
    headers["Authorization"] = f"Bearer {token}"

def gh_get(url, params=None, retries=5):
    for attempt in range(retries):
        r = requests.get(url, headers=headers, params=params, timeout=45)
        if r.status_code in (403, 429):
            reset = r.headers.get("X-RateLimit-Reset")
            remaining = r.headers.get("X-RateLimit-Remaining")
            if remaining == "0" and reset:
                wait = max(1, int(reset) - int(time.time()) + 2)
                print(f"Rate limit reached; sleeping {wait}s")
                time.sleep(wait)
                continue
            time.sleep(5 + 5 * attempt)
            continue
        if r.status_code >= 500:
            time.sleep(2 + 2 * attempt)
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        return r.json()
    raise RuntimeError(f"GitHub API failed after retries: {url}")

def raw_get(url):
    r = requests.get(url, headers=headers, timeout=45)
    time.sleep(SLEEP_BETWEEN_REQUESTS)
    return r.text if r.status_code == 200 else None

commit_cache, tree_cache, readme_cache, makefile_cache = {}, {}, {}, {}

def get_commits(full_name, max_commits=COMMITS_PER_REPO):
    if full_name in commit_cache:
        return commit_cache[full_name]
    owner, repo = full_name.split("/", 1)
    commits, page = [], 1
    while len(commits) < max_commits:
        data = gh_get(f"https://api.github.com/repos/{owner}/{repo}/commits",
                      params={"per_page": 100, "page": page})
        if not data:
            break
        for x in data:
            commits.append({"sha": x["sha"], "date": x["commit"]["committer"]["date"]})
            if len(commits) >= max_commits:
                break
        if len(data) < 100:
            break
        page += 1
    cdf = pd.DataFrame(commits)
    if len(cdf):
        cdf["date"] = pd.to_datetime(cdf["date"], errors="coerce", utc=True)
        cdf = cdf.dropna().sort_values("date").reset_index(drop=True)
    commit_cache[full_name] = cdf
    return cdf

def get_tree(full_name, sha):
    """returns (file_paths, dir_paths) lower-cased; None if unavailable"""
    key = (full_name, sha)
    if key in tree_cache:
        return tree_cache[key]
    owner, repo = full_name.split("/", 1)
    tree = gh_get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}", params={"recursive": "1"})
    if not tree or "tree" not in tree:
        tree_cache[key] = None
        return None
    files_ = set(); dirs_ = set()
    for item in tree["tree"]:
        p = str(item.get("path", "")).lower()
        if item.get("type") == "blob":
            files_.add(p)
            if "/" in p:
                dirs_.add(p.rsplit("/", 1)[0])
        elif item.get("type") == "tree":
            dirs_.add(p)
    # add all directory prefixes
    for d in list(dirs_):
        parts = d.split("/")
        for i in range(1, len(parts)):
            dirs_.add("/".join(parts[:i]))
    tree_cache[key] = (files_, dirs_)
    return tree_cache[key]

def get_readme_text(full_name, sha):
    key = (full_name, sha)
    if key in readme_cache:
        return readme_cache[key]
    txt = None
    for path in ["README.md", "readme.md", "README.rst", "README.txt", "Readme.md", "README"]:
        txt = raw_get(f"https://raw.githubusercontent.com/{full_name}/{sha}/{path}")
        if txt:
            break
    readme_cache[key] = txt
    return txt

def get_make_targets(full_name, sha):
    key = (full_name, sha)
    if key in makefile_cache:
        return makefile_cache[key]
    tree = get_tree(full_name, sha)
    targets = set(); has_makefile = False
    if tree:
        for p in tree[0]:
            if os.path.basename(p) in {"makefile", "gnumakefile"}:
                has_makefile = True
                txt = raw_get(f"https://raw.githubusercontent.com/{full_name}/{sha}/{p}")
                if txt:
                    for line in txt.splitlines():
                        m = re.match(r"^([A-Za-z0-9_.\-/ ]+?)\s*::?(?!=)", line)
                        if m and not line.startswith(("\t", " ", ".PHONY", "#")):
                            for t in m.group(1).split():
                                if "%" not in t and "$" not in t:
                                    targets.add(t.lower())
    makefile_cache[key] = (has_makefile, targets)
    return makefile_cache[key]

def snippet_present(full_name, sha, snippet):
    txt = get_readme_text(full_name, sha)
    if txt is None:
        return None
    s = " ".join(str(snippet).split())[:80].lower()
    return bool(s) and s in " ".join(txt.split()).lower()

def norm_path(a):
    a = str(a).strip().replace("\\", "/").lower()
    a = re.sub(r"^\./", "", a).strip("/")
    return a

def artifact_supported(full_name, sha, claim_type, artifact):
    a = norm_path(artifact)
    tree = get_tree(full_name, sha)
    if tree is None:
        return None
    files_, dirs_ = tree
    if claim_type == "make_target":
        has_mk, targets = get_make_targets(full_name, sha)
        if not has_mk:
            return False
        return (a in targets) if targets else True
    base = os.path.basename(a)
    if a in files_ or a in dirs_:
        return True
    if base and (base in {os.path.basename(p) for p in files_} or base in {os.path.basename(d) for d in dirs_}):
        return True
    return False

def evaluate_state(full_name, sha, claim_type, artifact, snippet):
    present = snippet_present(full_name, sha, snippet)
    if present is None:
        return "unknown"
    if present is False:
        return "no_claim"
    sup = artifact_supported(full_name, sha, claim_type, artifact)
    if sup is None:
        return "unknown"
    return "supported" if sup else "drift"

def coarse_indices(n, points=COARSE_GRID_POINTS):
    if n <= points:
        return list(range(n))
    return sorted(set(np.linspace(0, n - 1, points, dtype=int).tolist()))

def first_index_with_state(cdf, full_name, ct, art, snip, target, start=0):
    """first index >= start whose state is in `target` (coarse scan, then linear refinement)"""
    sub = cdf.iloc[start:]
    n = len(sub)
    if n == 0:
        return None
    cand = None
    for j in coarse_indices(n):
        if evaluate_state(full_name, sub.iloc[j]["sha"], ct, art, snip) in target:
            cand = j
            break
    if cand is None:
        return None
    lo = 0
    # find the previous coarse point before cand
    pts = coarse_indices(n)
    prev = [p for p in pts if p < cand]
    lo = prev[-1] + 1 if prev else 0
    for j in range(lo, cand + 1):
        if evaluate_state(full_name, sub.iloc[j]["sha"], ct, art, snip) in target:
            return start + j
    return start + cand

# -------------------------------------------------
# Main loop
# -------------------------------------------------
results = []
for i, row in work.iterrows():
    fn, ct = row["full_name"], row["claim_type"]
    art, snip = row["artifact_or_path"], row["snippet"]
    rec = {"case_id": row["case_id"], "full_name": fn, "claim_type": ct, "artifact_or_path": art, "snippet": snip[:200]}
    try:
        cdf = get_commits(fn)
        if len(cdf) < 2:
            results.append({**rec, "status": "too_few_commits"}); continue
        onset = first_index_with_state(cdf, fn, ct, art, snip, {"drift"})
        if onset is None:
            results.append({**rec, "status": "no_detectable_drift_in_checked_history", "n_commits_checked": len(cdf)}); continue
        # left truncation: drift already present at the oldest commit of the window
        left_truncated = int(onset == 0 and evaluate_state(fn, cdf.iloc[0]["sha"], ct, art, snip) == "drift")
        fix = first_index_with_state(cdf, fn, ct, art, snip, {"supported", "no_claim"}, start=onset + 1)
        onset_date = cdf.iloc[onset]["date"]
        if fix is not None:
            fix_date = cdf.iloc[fix]["date"]
            fix_state = evaluate_state(fn, cdf.iloc[fix]["sha"], ct, art, snip)
            dur, event = int((fix_date - onset_date).days), 1
        else:
            fix_date, fix_state = pd.NaT, ""
            dur, event = int((cdf.iloc[-1]["date"] - onset_date).days), 0
        results.append({**rec, "first_drift_date": onset_date, "first_fix_date": fix_date,
                        "fix_mode": fix_state, "duration_days": dur, "event_fixed": event,
                        "left_truncated": left_truncated, "window_start": cdf.iloc[0]["date"],
                        "window_end": cdf.iloc[-1]["date"], "n_commits_checked": len(cdf), "status": "ok"})
    except Exception as e:
        results.append({**rec, "status": f"analysis_failed: {e}"})
    if (i + 1) % 10 == 0:
        print(f"Processed {i + 1}/{len(work)} cases")

res = pd.DataFrame(results)
cases_path = os.path.join(OUT_DIR, "persistence_cases_v4.csv")
res.to_csv(cases_path, index=False)
ok = res[res["status"] == "ok"].copy()

# -------------------------------------------------
# Kaplan-Meier with Greenwood 95% band
# -------------------------------------------------
def km_curve(durations, events):
    d = pd.DataFrame({"t": durations, "e": events}).dropna().sort_values("t")
    surv, var_sum, rows = 1.0, 0.0, []
    for t in sorted(d["t"].unique()):
        at_risk = int((d["t"] >= t).sum())
        occ = int(((d["t"] == t) & (d["e"] == 1)).sum())
        if at_risk > 0 and occ > 0:
            surv *= 1 - occ / at_risk
            if at_risk - occ > 0:
                var_sum += occ / (at_risk * (at_risk - occ))
        se = surv * np.sqrt(var_sum)
        rows.append({"time_days": int(t), "at_risk": at_risk, "events": occ, "survival": surv,
                     "ci_low": max(0.0, surv - 1.96 * se), "ci_high": min(1.0, surv + 1.96 * se)})
    return pd.DataFrame(rows)

lines = ["PERSISTENCE ANALYSIS REPORT (v4 random cohort)", "=" * 60,
         f"Random seed: {RANDOM_SEED}; repositories sampled: {len(sampled_repos)}; cases analysed: {len(work)}",
         f"History depth: up to {COMMITS_PER_REPO} most recent commits per repository",
         f"Successful persistence estimates: {len(ok)}"]
if len(ok):
    km = km_curve(ok["duration_days"].values, ok["event_fixed"].values)
    km.to_csv(os.path.join(OUT_DIR, "kaplan_meier_curve_v4.csv"), index=False)
    plt.figure(figsize=(6, 4))
    plt.step(km["time_days"], km["survival"], where="post", label="KM estimate")
    plt.fill_between(km["time_days"], km["ci_low"], km["ci_high"], step="post", alpha=0.2, label="95% CI (Greenwood)")
    plt.ylim(0, 1.02); plt.xlabel("Days since first detectable drift"); plt.ylabel("Probability drift remains unfixed")
    plt.legend(); plt.tight_layout(); plt.savefig(os.path.join(FIG_DIR, "figure_km_persistence_v4.png"), dpi=200); plt.close()
    n_fixed = int(ok["event_fixed"].sum()); n_cens = len(ok) - n_fixed
    lt = int(ok["left_truncated"].sum())
    med = km.loc[km["survival"] <= 0.5, "time_days"].min() if (km["survival"] <= 0.5).any() else np.nan
    lines += [f"Fixed within window: {n_fixed} ({100*n_fixed/len(ok):.1f}%)", f"Right-censored: {n_cens}",
              f"Left-truncated (drift already present at oldest checked commit): {lt} ({100*lt/len(ok):.1f}%)",
              f"Fix modes: {ok['fix_mode'].value_counts().to_dict()}",
              f"KM survival at end of follow-up: {km['survival'].iloc[-1]:.3f}",
              f"KM median time to fix (days): {med if not np.isnan(med) else 'not reached'}",
              f"Observed duration median/mean (days): {ok['duration_days'].median():.0f} / {ok['duration_days'].mean():.1f}",
              f"Max follow-up (days): {ok['duration_days'].max()}"]
    # sensitivity: exclude left-truncated cases
    ok2 = ok[ok["left_truncated"] == 0]
    if len(ok2):
        km2 = km_curve(ok2["duration_days"].values, ok2["event_fixed"].values)
        lines.append(f"Sensitivity (non-left-truncated only, n={len(ok2)}): fixed {int(ok2['event_fixed'].sum())}, KM at end {km2['survival'].iloc[-1]:.3f}")
    pd.DataFrame([{"n_cases_attempted": len(res), "n_cases_ok": len(ok), "n_fixed": n_fixed, "n_censored": n_cens,
                   "n_left_truncated": lt, "km_end": float(km["survival"].iloc[-1]),
                   "median_observed_duration_days": float(ok["duration_days"].median()),
                   "mean_observed_duration_days": float(ok["duration_days"].mean())}]).to_csv(
        os.path.join(OUT_DIR, "persistence_summary_v4.csv"), index=False)
lines.append(f"Status counts: {res['status'].str.split(':').str[0].value_counts().to_dict()}")
with open(os.path.join(OUT_DIR, "persistence_report_v4.txt"), "w") as f:
    f.write("\n".join(lines))
print("\n".join(lines))

zip_path = os.path.join(OUT_DIR, "persistence_results_v4.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, fs in os.walk(OUT_DIR):
        for f_ in fs:
            if not f_.endswith(".zip"):
                z.write(os.path.join(root, f_), arcname=os.path.relpath(os.path.join(root, f_), OUT_DIR))
print(f"\nAll outputs saved to your Drive folder: {OUT_DIR}")
