# ============================================
# Script 1 (FINAL / v6 REAL STUDY): Sample 1000 English README software repos and download:
# - repo metadata
# - README
# - recursive tree
# - selected config/manifests
# Google Colab standalone
#
# Methodological goals:
# - reproducible, auditable, and English-only
# - stratified candidate construction to reduce popularity-only bias
# - early README/language filtering before tree/config collection
# - explicit software-project screening using repository structure
# - SAME downstream output filenames/schema as earlier pipeline versions
# ============================================

!pip -q install requests pandas

import os
import re
import time
import math
import base64
import random
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from google.colab import files

# -----------------------------
# USER CONFIG
# -----------------------------
GITHUB_TOKEN = input("Paste your GitHub token: ").strip()

LANGUAGES = ["Python"]
TARGET_REPOS = 1000
RANDOM_SEED = 42

# Candidate-pool construction.
# GitHub search is segmented to avoid convenience-sampling only the very top starred repos.
# You can widen/narrow these later without changing downstream outputs.
STAR_BANDS = [
    (10, 99),
    (100, 499),
    (500, 1999),
    (2000, 1000000),
]
PUSH_WINDOWS = [
    (0, 180),    # active in last 6 months
    (181, 730),  # active in last 6–24 months
]
PER_PAGE = 100
PAGES_PER_QUERY = 3   # keep moderate; many segmented queries already diversify the pool

# Hard scope controls
MIN_README_WORDS = 40
MIN_ALPHA_TOKENS_FOR_ENGLISH = 25
MIN_RECENT_PUSH_DAYS = 730
MAX_CANDIDATES_PER_STRATUM = 250

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28"
}

WHITELIST_CONFIG_BASENAMES = {
    "package.json",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    "makefile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "cargo.toml",
    "go.mod",
    "requirements.txt",
    "environment.yml",
    "environment.yaml",
    "pipfile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

SOURCE_DIR_HINTS = {"src", "app", "lib", "cmd", "server", "client", "package", "packages"}
TEST_DIR_HINTS = {"tests", "test", "spec", "specs"}
DOC_DIR_HINTS = {"docs", "doc", "images", "assets", ".github"}
MANIFEST_BASENAMES = {
    "package.json", "pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini", "makefile",
    "pom.xml", "build.gradle", "build.gradle.kts", "cargo.toml", "go.mod", "requirements.txt",
    "environment.yml", "environment.yaml", "pipfile", "dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yml", "compose.yaml"
}
PYTHON_FILE_RE = re.compile(r"\.py$", re.I)
NOTEBOOK_RE = re.compile(r"\.ipynb$", re.I)

EXCLUDE_NAME_PATTERNS = [
    r"\bawesome\b",
    r"\bprimer\b",
    r"\bbooks?\b",
    r"\bresources?\b",
    r"\btutorial\b",
    r"\binterview\b",
    r"\broadmap\b",
    r"\bpublic[- ]?apis\b",
    r"\bcurated\b",
    r"\blist\b",
    r"\bcheatsheet\b",
    r"\bcheat[- ]?sheet\b",
    r"\bboilerplate\b",
    r"\btemplate\b",
]

EXCLUDE_DESC_PATTERNS = [
    r"\ba curated list\b",
    r"\bcollection of\b",
    r"\blist of\b",
    r"\bfree programming books\b",
    r"\binterview questions\b",
    r"\blearning resource\b",
    r"\bawesome\b",
    r"\broadmap\b",
    r"\btutorial\b",
    r"\bguide\b",
    r"\bboilerplate\b",
    r"\btemplate\b",
    r"\bstarter\b",
]

CURATED_README_PATTERNS = [
    r"(?im)^\s*[-*+]\s*\[[^\]]+\]\([^\)]+\)",
    r"(?im)^\s*\d+\.\s*\[[^\]]+\]\([^\)]+\)",
    r"(?i)curated list",
    r"(?i)awesome list",
    r"(?i)collection of resources",
    r"(?i)learning resources",
    r"(?i)free .* books",
]

COMMON_ENGLISH_FUNCTION_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "you", "your", "are", "is", "to",
    "of", "in", "on", "as", "by", "or", "an", "be", "can", "will", "use", "using", "install",
    "run", "build", "test", "project", "application", "example", "examples", "quick", "start",
    "getting", "started", "requirements", "setup", "deployment", "development", "usage", "command",
    "commands", "python", "repository", "clone", "configure", "docker", "service", "server", "client",
    "how", "installing", "running", "testing", "module", "package", "library", "framework", "api"
}

session = requests.Session()
session.headers.update(HEADERS)
random.seed(RANDOM_SEED)

# -----------------------------
# API helpers
# -----------------------------

def github_get(url, params=None, retries=4):
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=45)
        except requests.RequestException:
            time.sleep(2 + attempt * 2)
            continue

        if r.status_code == 403:
            remaining = r.headers.get("X-RateLimit-Remaining")
            reset = r.headers.get("X-RateLimit-Reset")
            if remaining == "0" and reset:
                wait = max(1, int(reset) - int(time.time()) + 2)
                print(f"Rate limit hit. Sleeping {wait} seconds...")
                time.sleep(wait)
                continue
            retry_after = r.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else (4 + attempt * 4)
            print(f"GitHub temporary throttle. Sleeping {wait} seconds...")
            time.sleep(wait)
            continue

        if r.status_code >= 500:
            time.sleep(2 + attempt * 2)
            continue

        if r.status_code >= 400:
            return None

        return r

    return None


def fmt_date(dt):
    return dt.strftime("%Y-%m-%d")


def build_search_queries(language):
    now = datetime.now(timezone.utc)
    queries = []
    for smin, smax in STAR_BANDS:
        for newer_days, older_days in PUSH_WINDOWS:
            end_dt = now - timedelta(days=newer_days)
            start_dt = now - timedelta(days=older_days)
            # pushed:YYYY-MM-DD..YYYY-MM-DD is inclusive and helps reduce search-cap bias.
            q = (
                f"language:{language} fork:false archived:false stars:{smin}..{smax} "
                f"pushed:{fmt_date(start_dt)}..{fmt_date(end_dt)}"
            )
            queries.append({
                "language": language,
                "star_band": f"{smin}_{smax}",
                "push_band": f"{newer_days}_{older_days}",
                "q": q,
                "stratum": f"{language}|stars:{smin}-{smax}|pushed:{newer_days}-{older_days}d"
            })
    return queries


def search_repositories(query, per_page=100, page=1):
    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "updated",
        "order": "desc",
        "per_page": per_page,
        "page": page
    }
    r = github_get(url, params=params)
    if r is None:
        return []
    return r.json().get("items", [])


def get_readme(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    r = github_get(url)
    if r is None:
        return None, None
    data = r.json()
    content = data.get("content")
    path = data.get("path")
    if content and data.get("encoding") == "base64":
        try:
            text = base64.b64decode(content).decode("utf-8", errors="replace")
            return text, path
        except Exception:
            return None, path
    return None, path


def get_recursive_tree(owner, repo, branch):
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
    r = github_get(url, params={"recursive": 1})
    if r is None:
        return []
    return r.json().get("tree", [])


def get_file_content(owner, repo, path):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    r = github_get(url)
    if r is None:
        return None
    data = r.json()
    content = data.get("content")
    if content and data.get("encoding") == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None
    return None

# -----------------------------
# Text / README helpers
# -----------------------------

def strip_markdown_for_language_signal(text):
    t = str(text or "")
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`[^`\n]+`", " ", t)
    t = re.sub(r"!\[[^\]]*\]\([^\)]+\)", " ", t)
    t = re.sub(r"\[[^\]]+\]\([^\)]+\)", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[#>*_\-~=|]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def readme_word_count(text):
    return len(re.findall(r"\b\w+\b", str(text or "")))


def english_readme_ok(text):
    prose = strip_markdown_for_language_signal(text)
    tokens = re.findall(r"[A-Za-z][A-Za-z\-']+", prose)
    alpha_tokens = [t.lower() for t in tokens if re.search(r"[A-Za-z]", t)]

    if len(alpha_tokens) < MIN_ALPHA_TOKENS_FOR_ENGLISH:
        return False, "insufficient_natural_language_for_english_check"

    ascii_chars = sum(1 for ch in prose if ord(ch) < 128)
    ascii_ratio = ascii_chars / max(1, len(prose))
    if ascii_ratio < 0.85:
        return False, "non_english_readme_low_ascii_ratio"

    function_hits = sum(1 for t in alpha_tokens if t in COMMON_ENGLISH_FUNCTION_WORDS)
    function_ratio = function_hits / max(1, len(alpha_tokens))
    if function_ratio < 0.06:
        return False, "weak_english_function_word_signal"

    alpha_ratio = len(alpha_tokens) / max(1, len(re.findall(r"\S+", prose)))
    if alpha_ratio < 0.45:
        return False, "readme_too_code_or_markup_heavy"

    return True, "english_ok"


def repo_name_or_desc_excluded(full_name, description):
    hay = f"{full_name} {description or ''}".lower()
    for pat in EXCLUDE_NAME_PATTERNS + EXCLUDE_DESC_PATTERNS:
        if re.search(pat, hay, flags=re.I):
            return True
    return False


def looks_like_curated_list(readme_text):
    t = str(readme_text or "")
    if any(re.search(p, t) for p in CURATED_README_PATTERNS):
        bullet_link_lines = len(re.findall(r"(?im)^\s*[-*+]\s*\[[^\]]+\]\([^\)]+\)", t))
        numbered_link_lines = len(re.findall(r"(?im)^\s*\d+\.\s*\[[^\]]+\]\([^\)]+\)", t))
        if bullet_link_lines + numbered_link_lines >= 8:
            return True
    return False

# -----------------------------
# Tree summarization / screening
# -----------------------------

def summarize_tree(tree):
    file_paths = []
    dir_paths = []
    basenames = []
    top_dirs = set()

    for node in tree:
        p = str(node.get("path") or "")
        t = str(node.get("type") or "")
        if not p:
            continue
        lower_p = p.lower().replace("\\", "/")
        if t == "blob":
            file_paths.append(lower_p)
            basenames.append(os.path.basename(lower_p))
            if "/" in lower_p:
                top_dirs.add(lower_p.split("/")[0])
        elif t == "tree":
            dir_paths.append(lower_p)
            top_dirs.add(lower_p.split("/")[0] if "/" in lower_p else lower_p)

    basenames_set = set(basenames)
    top_dirs_set = set(top_dirs)
    dir_paths_set = set(dir_paths)
    file_paths_set = set(file_paths)

    has_manifest = int(any(b in MANIFEST_BASENAMES for b in basenames_set))
    has_container = int(any(b in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"} for b in basenames_set))
    has_makefile = int("makefile" in basenames_set)
    has_workflow = int(any(p.startswith(".github/workflows/") for p in file_paths_set))
    has_source_dir = int(any(d in top_dirs_set or d in dir_paths_set for d in SOURCE_DIR_HINTS))
    has_test_dir = int(any(d in top_dirs_set or d in dir_paths_set for d in TEST_DIR_HINTS))
    doc_dir_count = sum(1 for d in DOC_DIR_HINTS if d in top_dirs_set or d in dir_paths_set)

    py_files = [p for p in file_paths_set if PYTHON_FILE_RE.search(p)]
    notebook_files = [p for p in file_paths_set if NOTEBOOK_RE.search(p)]
    has_python_files = int(len(py_files) > 0)
    has_notebook_only = int(len(notebook_files) > 0 and len(py_files) == 0)

    return {
        "file_paths": file_paths_set,
        "dir_paths": dir_paths_set,
        "top_dirs": top_dirs_set,
        "basenames": basenames_set,
        "file_count": len(file_paths_set),
        "dir_count": len(dir_paths_set),
        "py_file_count": len(py_files),
        "notebook_count": len(notebook_files),
        "has_manifest": has_manifest,
        "has_container": has_container,
        "has_makefile": has_makefile,
        "has_workflow": has_workflow,
        "has_source_dir": has_source_dir,
        "has_test_dir": has_test_dir,
        "has_python_files": has_python_files,
        "has_notebook_only": has_notebook_only,
        "doc_dir_count": doc_dir_count,
    }


def repo_looks_like_software_project(full_name, description, readme_text, tree_info, pushed_at):
    desc = str(description or "")
    name_desc = f"{full_name} {desc}".lower()

    if pushed_at:
        try:
            pushed_dt = datetime.fromisoformat(str(pushed_at).replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - pushed_dt).days
            if age_days > MIN_RECENT_PUSH_DAYS:
                return False, "inactive_repo"
        except Exception:
            pass

    if repo_name_or_desc_excluded(full_name, description):
        return False, "excluded_by_name_or_description"

    if readme_word_count(readme_text) < MIN_README_WORDS:
        return False, "readme_too_short"

    if looks_like_curated_list(readme_text):
        return False, "curated_list_heuristic"

    if re.search(r"\b(dataset|benchmark data|paper list|reading list|syllabus|course notes)\b", name_desc, flags=re.I):
        return False, "non_project_repo_semantics"

    if tree_info["has_notebook_only"]:
        return False, "notebook_only_repo"

    if not tree_info["has_python_files"]:
        return False, "no_python_files"

    # Transparent structural score to operationalize "software project".
    structural_score = (
        tree_info["has_source_dir"] +
        tree_info["has_test_dir"] +
        tree_info["has_manifest"] +
        tree_info["has_workflow"] +
        tree_info["has_container"] +
        tree_info["has_makefile"]
    )

    if tree_info["py_file_count"] < 3 and structural_score < 2:
        return False, "insufficient_substantive_code"

    if structural_score < 2:
        return False, "insufficient_software_structure"

    if tree_info["doc_dir_count"] >= 2 and structural_score < 3:
        return False, "doc_heavy_structure"

    return True, "accepted"

# -----------------------------
# Candidate collection
# -----------------------------

def collect_candidate_pools():
    pools = {}
    seen_global = set()
    for language in LANGUAGES:
        for qinfo in build_search_queries(language):
            stratum = qinfo["stratum"]
            pools[stratum] = []
            seen_local = set()
            for page in range(1, PAGES_PER_QUERY + 1):
                items = search_repositories(qinfo["q"], per_page=PER_PAGE, page=page)
                if not items:
                    break
                for item in items:
                    fn = item.get("full_name")
                    if not fn:
                        continue
                    if fn in seen_local:
                        continue
                    seen_local.add(fn)
                    if fn in seen_global:
                        continue
                    # Keep cross-stratum deduplication global.
                    seen_global.add(fn)
                    enriched = dict(item)
                    enriched["_stratum"] = stratum
                    pools[stratum].append(enriched)
                    if len(pools[stratum]) >= MAX_CANDIDATES_PER_STRATUM:
                        break
                if len(pools[stratum]) >= MAX_CANDIDATES_PER_STRATUM:
                    break
            random.Random(RANDOM_SEED).shuffle(pools[stratum])
            print(f"Collected {len(pools[stratum])} candidates for {stratum}")
    return pools


def candidate_stream_round_robin(pools):
    keys = sorted(pools.keys())
    indices = {k: 0 for k in keys}
    remaining = True
    while remaining:
        remaining = False
        for k in keys:
            i = indices[k]
            if i < len(pools[k]):
                remaining = True
                yield pools[k][i]
                indices[k] += 1

# -----------------------------
# Main collection
# -----------------------------
selected = []
readmes = []
trees = []
configs = []
skip_log = []
accepted_seen = set()

candidate_pools = collect_candidate_pools()
total_candidates = sum(len(v) for v in candidate_pools.values())
print(f"Collected {total_candidates} unique candidates across {len(candidate_pools)} strata.")

for item in candidate_stream_round_robin(candidate_pools):
    if len(selected) >= TARGET_REPOS:
        break

    full_name = item["full_name"]
    if full_name in accepted_seen:
        continue

    owner, repo = full_name.split("/", 1)
    description = item.get("description")
    pushed_at = item.get("pushed_at")
    print(f"Checking [{len(selected)+1}/{TARGET_REPOS} target]: {full_name}")

    if repo_name_or_desc_excluded(full_name, description):
        skip_log.append((full_name, "excluded_by_name_or_description"))
        continue

    readme_text, readme_path = get_readme(owner, repo)
    if not readme_text:
        skip_log.append((full_name, "missing_or_unreadable_readme"))
        continue

    english_ok, english_reason = english_readme_ok(readme_text)
    if not english_ok:
        skip_log.append((full_name, english_reason))
        continue

    if looks_like_curated_list(readme_text):
        skip_log.append((full_name, "curated_list_heuristic"))
        continue

    branch = item.get("default_branch") or "main"
    tree = get_recursive_tree(owner, repo, branch)
    if not tree and branch != "master":
        tree = get_recursive_tree(owner, repo, "master")
        if tree:
            branch = "master"
    if not tree:
        skip_log.append((full_name, "tree_unavailable"))
        continue

    tree_info = summarize_tree(tree)
    ok, reason = repo_looks_like_software_project(full_name, description, readme_text, tree_info, pushed_at)
    if not ok:
        skip_log.append((full_name, reason))
        continue

    accepted_seen.add(full_name)
    print(f"Accepted: {full_name}")

    selected.append({
        "full_name": full_name,
        "language": item.get("language"),
        "description": description,
        "stars": item.get("stargazers_count"),
        "forks": item.get("forks_count"),
        "open_issues": item.get("open_issues_count"),
        "default_branch": branch,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "pushed_at": item.get("pushed_at"),
        "archived": item.get("archived"),
        "readme_path": readme_path,
        "readme_word_count": readme_word_count(readme_text),
        "curated_list_heuristic": looks_like_curated_list(readme_text),
        "has_manifest": tree_info["has_manifest"],
        "has_container": tree_info["has_container"],
        "has_makefile": tree_info["has_makefile"],
        "has_workflow": tree_info["has_workflow"],
        "has_source_dir": tree_info["has_source_dir"],
        "has_test_dir": tree_info["has_test_dir"],
        "selection_reason": reason
    })

    readmes.append({
        "full_name": full_name,
        "readme_path": readme_path,
        "readme_text": readme_text,
    })

    repo_tree_paths = []
    for node in tree:
        path = node.get("path")
        node_type = node.get("type")
        trees.append({
            "full_name": full_name,
            "path": path,
            "type": node_type,
            "size": node.get("size"),
            "sha": node.get("sha")
        })
        if node_type == "blob" and path:
            repo_tree_paths.append(path)

    for p in repo_tree_paths:
        base = os.path.basename(p).lower()
        lower_p = p.lower()
        if base in WHITELIST_CONFIG_BASENAMES or lower_p.startswith(".github/workflows/"):
            content = get_file_content(owner, repo, p)
            configs.append({
                "full_name": full_name,
                "path": p,
                "basename": os.path.basename(p),
                "content": content
            })

    if len(selected) % 50 == 0:
        print(f"Checkpoint: accepted {len(selected)} repos so far.")

# -----------------------------
# Save outputs
# -----------------------------
repos_df = pd.DataFrame(selected)
readmes_df = pd.DataFrame(readmes)
trees_df = pd.DataFrame(trees)
configs_df = pd.DataFrame(configs)
skip_df = pd.DataFrame(skip_log, columns=["full_name", "skip_reason"])

repos_df.to_csv("repos_pilot_v3.csv", index=False)
readmes_df.to_csv("readmes_pilot_v3.csv", index=False)
trees_df.to_csv("trees_pilot_v3.csv", index=False)
configs_df.to_csv("configs_pilot_v3.csv", index=False)
skip_df.to_csv("repo_skip_log_pilot_v3.csv", index=False)

print("\n=== Collection complete ===")
print("Accepted repos:", len(repos_df))
print("README rows:", len(readmes_df))
print("Tree rows:", len(trees_df))
print("Config rows:", len(configs_df))
print("\nAccepted repos preview:")
if not repos_df.empty:
    print(repos_df[[
        "full_name", "stars", "pushed_at", "has_manifest", "has_workflow",
        "has_source_dir", "has_test_dir", "selection_reason"
    ]].head(20))

print("\nSkip reason counts:")
if not skip_df.empty:
    print(skip_df["skip_reason"].value_counts())

files.download("repos_pilot_v3.csv")
files.download("readmes_pilot_v3.csv")
files.download("trees_pilot_v3.csv")
files.download("configs_pilot_v3.csv")
files.download("repo_skip_log_pilot_v3.csv")
