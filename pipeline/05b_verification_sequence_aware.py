# ============================================
# Script 5d (REVISION, final): Sequence-aware, hygiene-filtered README drift re-classification
# Google Colab standalone. Replaces Script 5 for the revised paper.
#
# Reads FOUR files that you already have (from your Zenodo/GitHub package) from a Google Drive folder:
#   1. drift_results_pilot_v3_detailed.csv   (Script 5 Output folder)
#   2. artifact_index_pilot_v3.csv           (Script 4 Output folder)
#   3. readme_structure_pilot_v3.csv         (Script 2 Output folder)
#   4. repos_pilot_v3.csv                    (Script 1 Output folder)
# It writes to <that folder>/outputs_script5d/:
#   - drift_results_v4_detailed.csv   (every original claim, with the corrected label and the reason)
#   - drift_results_v4_summary.csv    (one row per repository)
#   - reclassification_audit.csv      (only the claims whose label changed, with the rule responsible)
#   - script5b_console.txt            (the printed summary)
# ============================================

!pip -q install pandas

import os, re, sys
import pandas as pd
from google.colab import files

# -------------------------------------------------
# WHERE THE FILES ARE: put the four input files in ONE folder in your Google Drive
# and write that folder's path below (path as seen from "My Drive").
# -------------------------------------------------
DRIVE_DIR = "README_Drift_Revision"     # e.g. "README_Drift_Revision" or "Research/README drift/revision"

from google.colab import drive
drive.mount("/content/drive")
BASE = os.path.join("/content/drive/MyDrive", DRIVE_DIR)
if not os.path.isdir(BASE):
    raise FileNotFoundError(f"Folder not found in your Drive: {BASE}. Create it and put the four input files inside.")

def _find(keyword):
    for root, _, fs in os.walk(BASE):
        for fn in fs:
            if keyword in fn.lower() and fn.lower().endswith(".csv") and "v4" not in fn.lower():
                return os.path.join(root, fn)
    raise FileNotFoundError(f"No file containing '{keyword}' found under {BASE}")

print("Reading inputs from Drive ...")
detailed = pd.read_csv(_find("drift_results_pilot_v3_detailed"))
index_df = pd.read_csv(_find("artifact_index"))
struct_df = pd.read_csv(_find("readme_structure"), low_memory=False)
repos_df = pd.read_csv(_find("repos_pilot"))
OUT = os.path.join(BASE, "outputs_script5d")
os.makedirs(OUT, exist_ok=True)

def split_field(s):
    s = "" if pd.isna(s) else str(s)
    return [x.strip() for x in re.split(r"\|\|", s) if x.strip()]

def norm(s):
    return str(s or "").strip().replace("\\", "/").lower()

# ---------- artifact index ----------
IDX = {}
for _, row in index_df.iterrows():
    fp = set(norm(x) for x in split_field(row.get("all_file_paths", "")))
    dp = set(norm(x) for x in split_field(row.get("all_dir_paths", "")))
    IDX[row["full_name"]] = {
        "file_paths": fp,
        "file_basenames": set(norm(x) for x in split_field(row.get("all_file_basenames", ""))),
        "dir_paths": dp,
        "top_dirs": set(norm(x) for x in split_field(row.get("top_level_dirs", ""))),
        "dir_basenames": set(os.path.basename(d) for d in dp),
        "make_targets": set(norm(x) for x in split_field(row.get("make_targets", ""))),
        **{k: int(row.get(k, 0) or 0) for k in [
            "has_requirements_txt", "has_dockerfile", "has_docker_compose", "has_makefile",
            "has_pyproject_toml", "has_setup_cfg", "has_tox_ini", "has_pytest_ini",
            "has_tests_dir", "has_py_test_files"]},
    }
REPO_NAME = {fn: fn.split("/", 1)[1].lower() for fn in repos_df["full_name"]}

# ---------- helpers ----------
USER_FS_PREFIX = re.compile(r"^(?:~|\$?(?:pwd|home)/|/(?:home|users?|usr|etc|opt|tmp|var|mnt|dev|root|path|srv|sdcard|proc|sys|boot|lib|bin|sbin|media|run)(?:/|$)|[a-z]:(?:/|$)|[a-z]$)", re.I)
TOOL_NAME_TOKENS = {"node.js", "next.js", "vue.js", "react.js", "nuxt.js", "express.js", "three.js", "d3.js",
                    "angular.js", "ember.js", "socket.io", "coverage.py", "python.org", "pypi.org", "github.com",
                    "astral.sh", "docs.astral.sh", "deno.land", "bun.sh", "nodejs.org", "npmjs.com", "p5.js",
                    "chart.js", "alpine.js", "backbone.js", "knockout.js", "gulp.js", "grunt.js", "electron.js"}
DOMAIN_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|sh|dev|ai|edu|gov|co|app|cloud|tech|xyz|land|rs)$")
PLACEHOLDER_RE = re.compile(r"[<>{}$^\\]|\[[^\]]+\]|(?:^|/)(?:path/to|your[-_]?[a-z]+|my[-_][a-z_-]+|dummy[-_]?[a-z]*|project/directory|project[-_]name|repo[-_]name|username|user_name|xxx+|foo|bar|example[-_]?name|some[-_][a-z]+|sample[-_][a-z]+)(?:$|/|\.)", re.I)
NL_MAKE_WORDS = {"sure", "a", "an", "the", "it", "this", "that", "these", "those", "your", "changes", "use", "them",
                 "sense", "them.", "yourself", "any", "some", "and", "or", "of", "sure,", "certain"}
RUNTIME_LEXICON = {"output", "outputs", "out", "checkpoints", "checkpoint", "ckpt", "ckpts", "logs", "log", "results",
                   "result", "data", "dataset", "datasets", "models", "model", "weights", "cache", ".cache", "build",
                   "dist", "tmp", "temp", "runs", "artifacts", "downloads", "download", "saved", "save", "pretrained",
                   "venv", ".venv", "env", ".env", "node_modules", "__pycache__", "outputs/", "workdir", "work_dir",
                   "experiments", "exp", "generated", "target", "bin", "obj", "egg-info", "htmlcov", "coverage",
                   ".coverage", "site", "_build", "public", "static/build", "uploads", "media", "storage", "backups",
                   "snapshots", "embeddings", "index", "vectorstore", "chroma", "chroma_db", "db", "database"}

def strip_lead(p):
    p = norm(p)
    p = re.sub(r"^\./", "", p)
    return p.rstrip("/")

def file_exists(repo, a):
    a = strip_lead(a)
    if not a:
        return False
    cands = {a, a.lstrip("/"), "." + a} if not a.startswith(".") else {a, a.lstrip("/")}
    for c in cands:
        if c in repo["file_paths"] or os.path.basename(c) in repo["file_basenames"]:
            return True
    return False

def dir_exists(repo, a):
    a = strip_lead(a)
    if not a:
        return False
    cands = {a, a.lstrip("/"), "." + a} if not a.startswith(".") else {a, a.lstrip("/")}
    for c in cands:
        if c in repo["dir_paths"] or c in repo["top_dirs"] or os.path.basename(c) in repo["dir_basenames"]:
            return True
    return False

def is_url_residue(artifact, snippet):
    a = strip_lead(artifact).lstrip("/")
    if not a:
        return False
    return bool(re.search(r"https?://\S*" + re.escape(a), str(snippet), re.I)) or \
           bool(DOMAIN_RE.match(a.split("/")[0]))

CAPS_PLACEHOLDER_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]{2,})+\b")
USER_SUPPLIED_RE = re.compile(r"(secret|credential|token|api[-_]?key|\.env$|/env$|bin/activate$|scripts/activate$|\.pem$|\.key$|license\.txt$)", re.I)

def runtime_like(a):
    a = strip_lead(a).lstrip("/")
    parts = [p for p in a.split("/") if p]
    if not parts:
        return False
    return parts[0] in RUNTIME_LEXICON or parts[-1] in RUNTIME_LEXICON or a.endswith(".egg-info")

# ---------- ordering of claims inside fenced blocks ----------
block_content = {}
for _, r in struct_df[struct_df.elem_type == "fenced_code"].iterrows():
    block_content[(r["full_name"], int(r["line_no"]))] = str(r["content"] or "")

def within_block_pos(row):
    key = (row["full_name"], int(row["line_no"]))
    c = block_content.get(key)
    if c is None:
        return 0
    s = str(row["snippet"] or "").strip()
    i = c.lower().find(s.lower())
    return i if i >= 0 else 10**6

detailed["_pos"] = detailed.apply(within_block_pos, axis=1)
detailed = detailed.sort_values(["full_name", "line_no", "_pos"]).reset_index(drop=True)

# ---------- sequence context: artifacts created by earlier commands ----------
CREATE_PATTERNS = [
    re.compile(r"\bmkdir\s+(?:-p\s+)?([^\s;&|]+)", re.I),
    re.compile(r"\b(?:cp|mv)\s+(?:-[a-z]+\s+)*\S+\s+([^\s;&|]+)", re.I),
    re.compile(r"\btouch\s+([^\s;&|]+)", re.I),
    re.compile(r"\bcurl\b[^;&|]*?\s-o\s+([^\s;&|]+)", re.I),
    re.compile(r"\bwget\b[^;&|]*?\s-O\s+([^\s;&|]+)", re.I),
    re.compile(r"\bgit\s+clone\s+(?:-[-a-z]+\s+\S+\s+)*\S+\s+([^\s;&|]+)", re.I),
    re.compile(r"\bpython(?:3)?\s+-m\s+venv\s+([^\s;&|]+)", re.I),
    re.compile(r"\bvirtualenv\s+([^\s;&|]+)", re.I),
    re.compile(r"\bconda\s+create\s+(?:-n|--name)\s+([^\s;&|]+)", re.I),
    re.compile(r"\bunzip\b[^;&|]*?\s-d\s+([^\s;&|]+)", re.I),
]
CLONE_URL_RE = re.compile(r"\bgit\s+clone\s+(?:-[-a-z]+\s+\S+\s+)*(\S+)", re.I)


def created_targets(snippet):
    out = set()
    s = str(snippet or "")
    for pat in CREATE_PATTERNS:
        for m in pat.finditer(s):
            out.add(strip_lead(m.group(1)))
    m = CLONE_URL_RE.search(s)
    if m:
        url = m.group(1).rstrip("/")
        out.add(re.sub(r"\.git$", "", os.path.basename(norm(url))))
    return out

PROSE_CREATE_PATTERNS = [
    re.compile(r"\b(?:saved|stored|named|called)\s+(?:as|to|in)?\s*`([^`\s]+\.[a-z0-9]{1,5})`", re.I),
    re.compile(r"\b(?:copy|rename|move)\s+`?[^`\s]+`?\s+(?:to|as|into)\s+`?([^`\s,;]+?)`?[.,;]?(?:\s|$)", re.I),
    re.compile(r"\b(?:save|store)\s+(?:it|this|them|the\s+\w+|the\s+following(?:\s+\w+)?|(?:the\s+)?(?:code|script|snippet)(?:\s+\w+)?)\s+(?:as|to|in)\s+(?:a\s+file\s+(?:named|called)\s+)?`?([^`\s,;]+?)`?[.,;]?(?:\s|$)", re.I),
    re.compile(r"\bcreate\s+(?:a|an|the|your)?\s*(?:new\s+)?(?:file|folder|directory|config(?:uration)?(?:\s+file)?)\s+(?:named|called)?\s*`?([^`\s,;]+?)`?[.,;]?(?:\s|$)", re.I),
    re.compile(r"\b(?:generates?|creates?|produces?|writes?|will\s+create|will\s+generate)\s+(?:a|an|the)?\s*`?([^`\s,.;]+\.[a-z0-9]{1,5})`?", re.I),
]
README_CREATED = {}
for _fn, _g in struct_df.groupby("full_name"):
    _acc = set()
    for _c in _g["content"].fillna("").astype(str):
        for _line in _c.splitlines():
            _acc |= created_targets(_line)
            for _p in PROSE_CREATE_PATTERNS:
                for _m in _p.finditer(_line):
                    _acc.add(strip_lead(_m.group(1)))
    README_CREATED[_fn] = _acc

# ---------- classification ----------
def classify(row, repo, created, cwd, repo_name):
    """returns (status, label, family, verification, reason, new_cwd)
    status: 'kept' | 'excluded'   verification: 'verified' | 'sequence' | 'external' | 'uncertain'"""
    ct = str(row["claim_type"]); art = row.get("artifact_or_path"); art = "" if pd.isna(art) else str(art)
    snip = str(row.get("snippet") or "")
    a = strip_lead(art)

    # ---- hygiene: extraction noise (removed from corpus, reported separately) ----
    if ct in {"artifact_ref", "local_link_ref"}:
        if not a or a.strip("/") == "" or re.fullmatch(r"[./]+", a):
            return "excluded", None, None, None, "H1 empty/punctuation-only artifact", cwd
        if is_url_residue(art, snip) or a in TOOL_NAME_TOKENS or os.path.basename(a) in TOOL_NAME_TOKENS:
            return "excluded", None, None, None, "H2 URL residue or tool/product name, not a repository artifact", cwd
        if USER_FS_PREFIX.match(a) or a.startswith("~"):
            return "excluded", None, None, None, "H3 user-filesystem path (outside repository)", cwd
        if PLACEHOLDER_RE.search(a) or CAPS_PLACEHOLDER_RE.search(art):
            return "excluded", None, None, None, "H4 placeholder / templated path", cwd
        if ":" in a or " " in a.strip() or "=" in a or "(" in a or a.startswith("_.") or "/_." in a:
            return "excluded", None, None, None, "H7 not a path (contains ':' or whitespace: CLI verb, config key, or command)", cwd
        _seg = [p for p in a.strip("/").split("/") if p]
        _noext = (not re.search(r"\.[a-z][a-z0-9]{0,5}$", _seg[-1])) if _seg else True
        if art.strip().startswith("/") and _noext and not (file_exists(repo, a) or dir_exists(repo, a)):
            return "excluded", None, None, None, "H8 root-anchored extensionless token (API route or slash-command), not a repository path", cwd
        if len(_seg) == 2 and _noext and not (file_exists(repo, a) or dir_exists(repo, a)) and not dir_exists(repo, _seg[0]) and not a.startswith("."):
            return "excluded", None, None, None, "H9 two-segment extensionless identifier without parent directory (model/namespace id), not verifiable", cwd
        if False:
            return "excluded", None, None, None, "H7 not a path (contains ':' or whitespace: CLI verb, config key, or command)", cwd
        if re.fullmatch(r"compose\.ya?ml", a) and re.search(r"docker-compose\.ya?ml", snip, re.I):
            return "excluded", None, None, None, "H5 duplicate token from docker-compose.yml match", cwd
    if a and ct not in {"pip_install_pkg", "git_clone", "docker_run", "python_module"} and (USER_FS_PREFIX.match(a) or a.startswith("~")):
        return "excluded", None, None, None, "H3 user-filesystem path (outside repository)", cwd
    if ct == "make_cmd" and re.match(r"^\s*make-[a-z]", snip, re.I):
        return "excluded", None, None, None, "H6 natural-language 'make ...' sentence", cwd
    if ct == "make_target" and (a in NL_MAKE_WORDS or a.startswith("-")):
        return "excluded", None, None, None, "H6 natural-language 'make ...' sentence", cwd
    if ct in {"bash_script", "run_shell_script"} and is_url_residue(art, snip):
        return "excluded", None, None, None, "H2 URL residue (piped installer), not a repository artifact", cwd
    if ct == "cd_dir" and (USER_FS_PREFIX.match(a) or a.startswith("~") or PLACEHOLDER_RE.search(a) or re.fullmatch(r"[a-z]", a)):
        return "excluded", None, None, None, "H3/H4 cd to user-filesystem or placeholder path", cwd

    # ---- D1 dependency manifests ----
    if ct == "pip_requirements":
        ok = repo["has_requirements_txt"] or file_exists(repo, a) if a else repo["has_requirements_txt"]
        return ("kept", "supported" if ok else "drifted_high", "D1", "verified",
                "requirements manifest present" if ok else f"requirements file missing: {a or 'requirements.txt'}", cwd)
    if ct == "poetry_install":
        ok = repo["has_pyproject_toml"]
        return "kept", "supported" if ok else "drifted_high", "D1", "verified", "pyproject.toml present" if ok else "poetry install but no pyproject.toml", cwd
    if ct == "conda_env_create":
        ok = file_exists(repo, a) or a in created
        return "kept", "supported" if ok else "drifted_high", "D1", "verified", f"env file {'present' if ok else 'missing'}: {a}", cwd
    if ct == "docker_build":
        m = re.search(r"(?:-f|--file)[\s=]+([^\s`\"']+)", snip)
        if m:
            a = strip_lead(m.group(1)); ok = file_exists(repo, a)
        else:
            ok = repo["has_dockerfile"]
        return "kept", "supported" if ok else "drifted_high", "D7", "verified", "Dockerfile present" if ok else f"Dockerfile missing {a}", cwd
    if ct in {"docker_compose_up", "docker_compose_build"}:
        ok = repo["has_docker_compose"] or any(re.fullmatch(r"(docker-)?compose\.ya?ml", c) for c in created)
        return "kept", "supported" if ok else "drifted_high", "D7", "verified", "compose file present" if ok else "compose file missing", cwd
    if ct == "kubectl_apply":
        ok = file_exists(repo, a) or a in created
        return "kept", "supported" if ok else "drifted_high", "D7", "verified", f"manifest {'present' if ok else 'missing'}: {a}", cwd

    # ---- D2 entrypoints / scripts ----
    if ct in {"python_script", "streamlit_run", "bash_script", "run_shell_script", "java_jar", "go_run", "node_script"}:
        if not a:
            return "kept", "supported", "D2", "external", "no local artifact captured", cwd
        if PLACEHOLDER_RE.search(a):
            return "kept", "uncertain", "D2", "uncertain", "placeholder in script path", cwd
        if file_exists(repo, a):
            return "kept", "supported", "D2", "verified", "script present", cwd
        if cwd and file_exists(repo, cwd + "/" + a.lstrip("/")):
            return "kept", "supported", "D2", "sequence", f"script present relative to cwd '{cwd}'", cwd
        if a in created or os.path.basename(a) in created:
            return "kept", "supported", "D2", "sequence", "script created by an earlier documented step", cwd
        return "kept", "drifted_high", "D2", "verified", f"script missing: {a}", cwd
    if ct == "python_module":
        return "kept", "uncertain", "D2", "uncertain", "module resolution depends on installation state", cwd

    # ---- D3 directory navigation (sequence-aware) ----
    if ct == "cd_dir":
        t = a.lstrip("/")
        if t in {"", ".", ".."} or t.startswith(".."):
            return "kept", "supported", "D3", "verified", "relative navigation", ("" if t in {"", "..", "."} else cwd)
        if t == repo_name or t.endswith("/" + repo_name) or t in created:
            return "kept", "supported", "D3", "sequence", "navigation into the freshly cloned repository (clone context)", ""
        if dir_exists(repo, t):
            return "kept", "supported", "D3", "verified", "directory present", t
        if cwd and dir_exists(repo, cwd + "/" + t):
            return "kept", "supported", "D3", "sequence", f"directory present relative to cwd '{cwd}'", cwd + "/" + t
        if runtime_like(t):
            return "kept", "uncertain", "D3", "uncertain", f"directory absent but runtime/generated-style name: {t}", cwd
        return "kept", "drifted_high", "D3", "verified", f"directory missing: {t}", cwd

    # ---- D4 build targets / D5 build-test support ----
    if ct == "make_target":
        if not repo["has_makefile"]:
            return "kept", "drifted_high", "D4", "verified", "make target used but no Makefile", cwd
        if repo["make_targets"] and a not in repo["make_targets"]:
            return "kept", "drifted_medium", "D4", "verified", f"target '{a}' not in parsed Makefile targets", cwd
        return "kept", "supported", "D4", "verified", "Makefile and target present", cwd
    if ct == "make_cmd":
        ok = repo["has_makefile"] or "cmakelists.txt" in repo["file_basenames"]
        return "kept", "supported" if ok else "drifted_high", "D4", "verified", "Makefile present" if ok else "make used but no Makefile", cwd
    if ct == "pip_install_editable":
        m = re.search(r"pip(?:3)?\s+install\s+(?:-[-a-z]+\s+)*-e\s+([^\s`]+)", snip, re.I)
        tgt = strip_lead(re.sub(r"\[.*?\]", "", m.group(1)).strip("\"'")) if m else "."
        if tgt in {"", "."}:
            ok = repo["has_pyproject_toml"] or repo["has_setup_cfg"] or "setup.py" in repo["file_basenames"]
            return "kept", "supported" if ok else "drifted_medium", "D5", "verified", "packaging manifest present" if ok else "editable install but no pyproject/setup", cwd
        ok = dir_exists(repo, tgt) or file_exists(repo, tgt)
        return "kept", "supported" if ok else "drifted_high", "D5", "verified", f"editable target {'present' if ok else 'missing'}: {tgt}", cwd
    if ct == "pip_install_pkg":
        if a in {".", ""} or a.endswith((".whl", ".tar.gz")) or ("/" in a and not re.match(r"^[a-z][a-z0-9+.-]*://", a)):
            if a in {".", ""}:
                ok = repo["has_pyproject_toml"] or repo["has_setup_cfg"] or "setup.py" in repo["file_basenames"]
            else:
                ok = file_exists(repo, a) or dir_exists(repo, a) or a in created
            return "kept", "supported" if ok else "drifted_medium", "D5", "verified", "local install target " + ("present" if ok else "missing"), cwd
        return "kept", "supported", None, "external", "package registry install (externally grounded)", cwd

    # ---- D6 test commands ----
    if ct == "pytest_cmd":
        _mf = re.search(r"pytest\s+(?:-[-a-z]+\s+)*([A-Za-z0-9_./-]+\.py)", snip)
        if _mf and file_exists(repo, _mf.group(1)):
            return "kept", "supported", "D6", "verified", "named test file present", cwd
        ok = (repo["has_tests_dir"] or repo["has_py_test_files"] or repo["has_pyproject_toml"] or
              repo["has_setup_cfg"] or repo["has_tox_ini"] or repo["has_pytest_ini"])
        return "kept", "supported" if ok else "drifted_medium", "D6", "verified", "test evidence present" if ok else "pytest but no test evidence", cwd
    if ct == "tox_cmd":
        ok = repo["has_tox_ini"] or repo["has_pyproject_toml"]
        return "kept", "supported" if ok else "drifted_medium", "D6", "verified", "tox config present" if ok else "tox but no tox.ini/pyproject", cwd

    # ---- D8 local artifact references ----
    if ct in {"artifact_ref", "local_link_ref"}:
        if file_exists(repo, a) or dir_exists(repo, a):
            return "kept", "supported", "D8", "verified", "artifact present", cwd
        if a in created or os.path.basename(a) in created:
            return "kept", "supported", "D8", "sequence", "artifact created by an earlier documented step", cwd
        if "*" in a:
            return "kept", "uncertain", "D8", "uncertain", "glob pattern", cwd
        if runtime_like(a) or USER_SUPPLIED_RE.search(a):
            return "kept", "uncertain", "D8", "uncertain", f"absent but runtime-generated or user-supplied style path: {a}", cwd
        return "kept", "drifted_high", "D8", "verified", f"local artifact missing: {a}", cwd

    # ---- everything else: externally grounded / non-verifiable ----
    return "kept", "supported", None, "external", "externally grounded command; no repository artifact asserted", cwd

rows = []
for fn, g in detailed.groupby("full_name", sort=False):
    repo = IDX.get(fn)
    if repo is None:
        continue
    rname = REPO_NAME.get(fn, fn.split("/")[1].lower())
    created = set(README_CREATED.get(fn, set()))
    cwd = ""
    last_block = None
    for _, row in g.iterrows():
        blk = (row["line_no"], row["context_type"])
        if blk != last_block:
            cwd = ""  # reset working directory at each new block/line
            last_block = blk
        created |= created_targets(row["snippet"])
        status, label, fam, ver, reason, cwd = classify(row, repo, created, cwd, rname)
        rows.append({**row.drop(labels=["_pos"]).to_dict(), "status": status, "label_v4": label,
                     "drift_family_v4": fam, "verification": ver, "reason_v4": reason})

out = pd.DataFrame(rows)
out["drifted_v3"] = out["label"].isin(["drifted_high", "drifted_medium"])
out["drifted_v4"] = out["label_v4"].isin(["drifted_high", "drifted_medium"])
out["changed"] = (out["status"] == "excluded") | (out["label"] != out["label_v4"])
out.to_csv(os.path.join(OUT, "drift_results_v4_detailed.csv"), index=False)
out[out["changed"]].to_csv(os.path.join(OUT, "reclassification_audit.csv"), index=False)

kept = out[out.status == "kept"]
summ = kept.groupby(["full_name", "label_v4"]).size().unstack(fill_value=0).reset_index()
for c in ["drifted_high", "drifted_medium", "supported", "uncertain"]:
    if c not in summ: summ[c] = 0
summ["total_claims"] = summ[["drifted_high", "drifted_medium", "supported", "uncertain"]].sum(axis=1)
summ["has_any_drift"] = ((summ.drifted_high + summ.drifted_medium) > 0).astype(int)
summ.to_csv(os.path.join(OUT, "drift_results_v4_summary.csv"), index=False)

import io, contextlib
_buf = io.StringIO()
_stdout = sys.stdout
sys.stdout = _Tee = type("T", (), {"write": lambda self, x: (_buf.write(x), _stdout.write(x)), "flush": lambda self: _stdout.flush()})()
print("Original claims:", len(out), "| excluded as extraction noise:", (out.status == "excluded").sum(), "| kept:", len(kept))
print(out[out.status == "excluded"].reason_v4.value_counts().to_string())
print("\nORIGINAL labels:\n", out.label.value_counts().to_string())
print("\nREFINED labels (kept):\n", kept.label_v4.value_counts().to_string())
n = len(kept); dr = kept.drifted_v4.sum()
print(f"\nclaim-level drift v4: {dr}/{n} = {100*dr/n:.2f}%  support {100*(kept.label_v4=='supported').mean():.2f}%  uncertain {100*(kept.label_v4=='uncertain').mean():.2f}%")
print(f"repo-level: {summ.has_any_drift.sum()}/{len(summ)} = {100*summ.has_any_drift.mean():.2f}%")
print("\nverification status (kept):\n", kept.verification.value_counts().to_string())
print("\nby claim family:")
print(kept.groupby("claim_family").agg(n=("label_v4", "size"), drifted=("drifted_v4", "sum")).assign(rate=lambda x: (100*x.drifted/x.n).round(2)))
print("\ncommand family excluding cd_dir:")
c = kept[(kept.claim_family == "command") & (kept.claim_type != "cd_dir")]; print(len(c), c.drifted_v4.sum(), round(100*c.drifted_v4.mean(), 2))
print("\ndrift family v4 (drifted only):\n", kept[kept.drifted_v4].drift_family_v4.value_counts().to_string())
print("\ntransition matrix (original label -> refined):")
print(pd.crosstab(out.label, out.label_v4.fillna("EXCLUDED")))
print("\ncd_dir detail:\n", kept[kept.claim_type == "cd_dir"].groupby(["label_v4", "verification"]).size())
print("\nper claim type v4:")
t = kept.groupby("claim_type").agg(n=("label_v4", "size"), drifted=("drifted_v4", "sum"), uncertain=("label_v4", lambda s: (s == "uncertain").sum()), verified=("verification", lambda s: (s != "external").sum()))
t["rate"] = (100 * t.drifted / t.n).round(1)
print(t.sort_values("n", ascending=False).to_string())

sys.stdout = _stdout
open(os.path.join(OUT, "script5b_console.txt"), "w").write(_buf.getvalue())
print(f"\nAll outputs saved to your Drive folder: {OUT}")
