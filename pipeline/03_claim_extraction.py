# ============================================
# Script 3 (FINAL-FINAL / v11): Robust executable claim extraction
# - aligned with Script 1 (v3+) and Script 2 (v5)
# - reads readme_structure_pilot_v3.csv and repos_pilot_v3.csv
# - fixes residual false positives from v10
# - suppresses natural-language "Go to ..."
# - suppresses python -m pip as a spurious python_module claim
# - avoids capturing pip flags as install targets
# - de-duplicates parsing byproducts from same line
# - keeps output schema compatible with downstream Script 5
# Google Colab standalone
# ============================================

!pip -q install pandas

import os
import re
import pandas as pd
from google.colab import files

print("Upload readme_structure_pilot_v3.csv and repos_pilot_v3.csv")
uploaded = files.upload()

structure_file = None
repos_file = None

for fn in uploaded.keys():
    lower = fn.lower()
    if "structure" in lower:
        structure_file = fn
    elif "repos" in lower:
        repos_file = fn

if structure_file is None or repos_file is None:
    raise ValueError("Please upload both readme_structure_pilot_v3.csv and repos_pilot_v3.csv")

structure_df = pd.read_csv(structure_file)
repos_df = pd.read_csv(repos_file)
repo_meta = repos_df.set_index("full_name").to_dict(orient="index")

RELEVANT_SECTIONS = {
    "installation", "usage", "run", "test", "build",
    "development", "deployment", "ci"
}

SHELL_LANGS = {"bash", "shell", "sh", "zsh", "console", "terminal", "powershell", "pwsh"}

LOCAL_ARTIFACT_WHITELIST = {
    "requirements.txt", "package.json", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "makefile", "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "go.mod", "pyproject.toml", "setup.cfg",
    "tox.ini", "pytest.ini", "environment.yml", "environment.yaml", "pipfile",
    "contributing.md", "contributing.rst", "contributing.adoc",
    "install.md", "installation.md", "setup.md",
    "manage.py", "main.py", "app.py", "run.py"
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
DOC_EXTS = {".md", ".rst", ".adoc", ".txt", ".pdf"}
BADGE_HINTS = ("badge", "img.shields.io", "github/workflows", "build status", "coverage status")

STRONGLY_NEGATIVE_HEADINGS = {
    "screenshots", "screenshot", "gallery", "roadmap", "acknowledgements",
    "acknowledgments", "citation", "cite", "license", "authors", "references"
}

SOFT_NEGATIVE_HEADINGS = {
    "prompt", "prompts", "sample prompts", "example prompts"
}

def norm(s):
    return str(s or "").strip().lower()

def likely_curated_repo(full_name):
    return int(repo_meta.get(full_name, {}).get("curated_list_heuristic", 0)) == 1

def is_external_target(s):
    s = str(s or "").strip()
    if not s:
        return False
    sl = s.lower()
    return (
        sl.startswith("http://") or
        sl.startswith("https://") or
        sl.startswith("ftp://") or
        sl.startswith("www.") or
        sl.startswith("mailto:") or
        bool(re.match(r"^[a-z][a-z0-9+.-]*://", sl))
    )

def looks_like_domain(token):
    token = norm(token)
    if not token or "/" in token or " " in token:
        return False
    return bool(re.match(r"^[a-z0-9.-]+\.(com|org|net|io|dev|ai|edu|gov|co|app|cloud|tech|xyz)$", token))

def is_image_path(token):
    t = str(token or "").strip().lower()
    base = re.split(r"[?#]", t)[0]
    return any(base.endswith(ext) for ext in IMAGE_EXTS)

def is_doc_path(token):
    t = str(token or "").strip().lower()
    base = re.split(r"[?#]", t)[0]
    return any(base.endswith(ext) for ext in DOC_EXTS)

def canonicalize_artifact_or_path(token):
    if token is None:
        return None
    t = str(token).strip()
    if not t:
        return None
    t = t.replace("\\", "/")
    t = t.strip("`'\"()[]{}<>.,;:")
    if not t:
        return None
    if t.startswith("./"):
        t = t[2:]
    if not is_external_target(t):
        t = re.sub(r"/+", "/", t)
    return t

def heading_is_strongly_negative(heading):
    h = norm(heading)
    return any(tok in h for tok in STRONGLY_NEGATIVE_HEADINGS)

def heading_is_soft_negative(heading):
    h = norm(heading)
    return any(tok in h for tok in SOFT_NEGATIVE_HEADINGS)

def is_relevant_or_hint(section_class, operational_hint):
    return norm(section_class) in RELEVANT_SECTIONS or int(operational_hint) == 1

def looks_like_badge_or_status(text):
    s = norm(text)
    return any(h in s for h in BADGE_HINTS)

def looks_link_heavy(line):
    s = str(line or "")
    url_count = len(re.findall(r"https?://|www\.", s, flags=re.I))
    md_link_count = len(re.findall(r"\[([^\]]+)\]\(([^)]+)\)", s))
    return (url_count + md_link_count) >= 2

def looks_like_list_bullet(line):
    return bool(re.match(r"^\s*[-*+]\s+", str(line or "")))

def normalize_artifact_key(artifact_path):
    if artifact_path is None:
        return ""
    p = canonicalize_artifact_or_path(artifact_path)
    if not p:
        return ""
    return os.path.basename(p).lower()

PROMPT_PREFIX_RE = re.compile(r"^\s*(?:\$|>|>>|PS [^>]*>)\s*")
ENV_PREFIX_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|[^\s]+)\s+)+")
COMMAND_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;)\s*")
PLACEHOLDER_DIR_RE = re.compile(
    r"(?:^|/)(?:path/to|your[-_/ ]project|your_project|project_name|repo_name|your-repo)(?:$|/)",
    flags=re.I
)

COMMAND_STARTERS = (
    "python", "python3", "pip", "pip3", "uv", "pytest", "py.test", "tox", "coverage",
    "make", "docker", "docker-compose", "poetry", "npm", "pnpm", "yarn", "node",
    "bash", "sh", "source", "conda", "mamba",
    "go", "cargo", "mvn", "gradle", "./gradlew", "java",
    "kubectl", "helm", "terraform",
    "streamlit", "flask", "gunicorn", "uvicorn",
    "jupyter", "nohup", "curl", "wget",
    "git", "cd", "cp", "mv", "chmod", "export", "set"
)

COMMAND_START_RE = re.compile(
    r"^(?:" + "|".join(re.escape(x) for x in COMMAND_STARTERS) + r")\b",
    flags=re.I
)

def clean_command_line(line):
    s = str(line or "").strip()
    s = PROMPT_PREFIX_RE.sub("", s).strip()
    s = ENV_PREFIX_RE.sub("", s).strip()
    return s

def split_compound_commands(line):
    parts = COMMAND_SPLIT_RE.split(str(line or "").strip())
    return [p.strip() for p in parts if p.strip()]

def looks_natural_language_make_sentence(raw):
    s = norm(raw)
    return bool(re.match(r"^make\s+(?:a|an|the|your|this|that|these|those)\b", s))

def looks_natural_language_run_sentence(raw):
    s = norm(raw)
    return bool(re.match(r"^run\s+(?:the|this|that|these|those|a|an|your)\b", s))

def looks_natural_language_go_sentence(raw):
    s = norm(raw)
    return bool(re.match(r"^go\s+to\b", s))

def shell_like_line(line, heading="", code_lang=None):
    s = str(line or "").strip()
    if not s:
        return False

    if len(s) > 250 and not PROMPT_PREFIX_RE.match(s):
        return False

    cleaned = clean_command_line(s)
    if not cleaned:
        return False

    first = split_compound_commands(cleaned)[0] if split_compound_commands(cleaned) else cleaned

    if looks_natural_language_make_sentence(first) or looks_natural_language_run_sentence(first) or looks_natural_language_go_sentence(first):
        return False

    if code_lang and str(code_lang).lower() in SHELL_LANGS:
        return bool(COMMAND_START_RE.match(first))

    return bool(COMMAND_START_RE.match(first))

def is_valid_pip_target(token):
    t = canonicalize_artifact_or_path(token)
    if not t:
        return False
    tl = t.lower()
    if tl.startswith("-"):
        return False
    if is_external_target(tl):
        return True
    return True

def is_valid_module_target(token):
    t = canonicalize_artifact_or_path(token)
    if not t:
        return False
    tl = t.lower()
    if tl in {"pip", "pip3"}:
        return False
    if tl.startswith("-"):
        return False
    return True

COMMAND_PATTERNS = [
    ("pip_requirements", re.compile(r"\bpip(?:3)?\s+install\s+-r\s+([^\s`]+)", re.I), 1),
    ("pip_install_editable", re.compile(r"\bpip(?:3)?\s+install\s+-e\s+([^\s`]+)", re.I), 1),
    ("pip_install_pkg", re.compile(r"\bpip(?:3)?\s+install\s+(?!-[A-Za-z-])([^\s`]+)", re.I), 1),
    ("poetry_install", re.compile(r"\bpoetry\s+install\b", re.I), None),
    ("conda_env_create", re.compile(r"\bconda\s+env\s+create\s+-f\s+([^\s`]+)", re.I), 1),
    ("python_script", re.compile(r"\bpython(?:3)?\s+([A-Za-z0-9_./*-]+\.py)\b", re.I), 1),
    ("python_module", re.compile(r"\bpython(?:3)?\s+-m\s+([A-Za-z0-9_.-]+)\b", re.I), 1),
    ("node_script", re.compile(r"\bnode\s+([A-Za-z0-9_./*-]+\.(?:js|mjs|cjs|ts))\b", re.I), 1),
    ("bash_script", re.compile(r"\b(?:bash|sh)\s+([A-Za-z0-9_./*-]+\.(?:sh|bash))\b", re.I), 1),
    ("run_shell_script", re.compile(r"\b([./A-Za-z0-9_-]+/(?:[A-Za-z0-9_.-]+)?|[A-Za-z0-9_.-]+)\.(?:sh|bash)\b", re.I), 0),
    ("streamlit_run", re.compile(r"\bstreamlit\s+run\s+([A-Za-z0-9_./*-]+\.py)\b", re.I), 1),
    ("flask_run", re.compile(r"\bflask\s+run\b", re.I), None),
    ("uvicorn_run", re.compile(r"\buvicorn\s+([A-Za-z0-9_:.]+)\b", re.I), 1),
    ("gunicorn_run", re.compile(r"\bgunicorn\s+([A-Za-z0-9_:.]+)\b", re.I), 1),
    ("jupyter_notebook", re.compile(r"\bjupyter\s+(?:notebook|lab)\b", re.I), None),
    ("pytest_cmd", re.compile(r"\b(?:pytest|py\.test)\b", re.I), None),
    ("tox_cmd", re.compile(r"\btox\b", re.I), None),
    ("coverage_cmd", re.compile(r"\bcoverage\s+run\b", re.I), None),
    ("make_target", re.compile(r"\bmake\s+([A-Za-z0-9_.-]+)\b", re.I), 1),
    ("make_cmd", re.compile(r"\bmake\b", re.I), None),
    ("npm_install", re.compile(r"\bnpm\s+(?:ci|install)\b", re.I), None),
    ("npm_run", re.compile(r"\bnpm\s+run\s+([A-Za-z0-9:_-]+)\b", re.I), 1),
    ("npm_test", re.compile(r"\bnpm\s+test\b", re.I), None),
    ("yarn_cmd", re.compile(r"\byarn\s+(?:install|test|start|dev|build)\b", re.I), None),
    ("pnpm_cmd", re.compile(r"\bpnpm\s+(?:install|test|start|dev|build)\b", re.I), None),
    ("docker_build", re.compile(r"\bdocker\s+build(?:\s+-f\s+([^\s`]+))?", re.I), 1),
    ("docker_run", re.compile(r"\bdocker\s+run\b", re.I), None),
    ("docker_compose_up", re.compile(r"\bdocker(?:\s+compose|-compose)\s+up\b", re.I), None),
    ("docker_compose_build", re.compile(r"\bdocker(?:\s+compose|-compose)\s+build\b", re.I), None),
    ("kubectl_apply", re.compile(r"\bkubectl\s+apply\s+-f\s+([^\s`]+)", re.I), 1),
    ("helm_install", re.compile(r"\bhelm\s+install\b", re.I), None),
    ("terraform_apply", re.compile(r"\bterraform\s+apply\b", re.I), None),
    ("go_run", re.compile(r"\bgo\s+run\s+([A-Za-z0-9_./*-]+\.go)\b", re.I), 1),
    ("go_test", re.compile(r"\bgo\s+test\b", re.I), None),
    ("cargo_build", re.compile(r"\bcargo\s+build\b", re.I), None),
    ("cargo_run", re.compile(r"\bcargo\s+run\b", re.I), None),
    ("cargo_test", re.compile(r"\bcargo\s+test\b", re.I), None),
    ("mvn_test", re.compile(r"\bmvn\s+test\b", re.I), None),
    ("mvn_package", re.compile(r"\bmvn\s+package\b", re.I), None),
    ("gradle_build", re.compile(r"\b(?:gradle|\./gradlew)\s+build\b", re.I), None),
    ("java_jar", re.compile(r"\bjava\s+-jar\s+([A-Za-z0-9_./*-]+\.jar)\b", re.I), 1),
    ("git_clone", re.compile(r"\bgit\s+clone\s+([^\s`]+)", re.I), 1),
    ("cd_dir", re.compile(r"\bcd\s+([A-Za-z0-9_./*-]+)\b", re.I), 1),
]

def dedupe_same_part_claims(part_claims):
    if not part_claims:
        return part_claims

    claim_types = {c[0] for c in part_claims}

    # Remove python_module=pip when pip install is already captured
    filtered = []
    for ctype, snippet, artifact, fam in part_claims:
        if ctype == "python_module" and artifact and artifact.lower() in {"pip", "pip3"}:
            if any(x in claim_types for x in {"pip_requirements", "pip_install_editable", "pip_install_pkg"}):
                continue
        filtered.append((ctype, snippet, artifact, fam))

    claim_types = {c[0] for c in filtered}
    filtered2 = []
    for ctype, snippet, artifact, fam in filtered:
        # If make_target exists, drop bare make_cmd from same part
        if ctype == "make_cmd" and "make_target" in claim_types:
            continue
        filtered2.append((ctype, snippet, artifact, fam))

    # exact dedupe within same part
    seen = set()
    final = []
    for c in filtered2:
        key = (c[0], c[1].strip().lower(), canonicalize_artifact_or_path(c[2]) or "", c[3])
        if key not in seen:
            seen.add(key)
            final.append(c)

    return final

def extract_from_shell_text(text, heading="", code_lang=None):
    claims = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not shell_like_line(line, heading=heading, code_lang=code_lang):
            continue

        cleaned = clean_command_line(line)

        for part in split_compound_commands(cleaned):
            if not part:
                continue
            if not shell_like_line(part, heading=heading, code_lang=code_lang):
                continue

            part_claims = []
            matched_any = False

            for ctype, pat, group_idx in COMMAND_PATTERNS:
                for m in pat.finditer(part):
                    artifact = None
                    if group_idx is not None:
                        if group_idx == 0:
                            artifact = m.group(0)
                        elif m.lastindex and m.lastindex >= group_idx:
                            artifact = m.group(group_idx)

                    artifact = canonicalize_artifact_or_path(artifact)

                    if ctype == "cd_dir" and artifact and PLACEHOLDER_DIR_RE.search(artifact):
                        continue

                    if ctype == "pip_install_pkg" and artifact and not is_valid_pip_target(artifact):
                        continue

                    if ctype == "python_module" and artifact and not is_valid_module_target(artifact):
                        continue

                    if artifact and is_external_target(artifact):
                        if ctype != "git_clone":
                            artifact = None

                    part_claims.append((ctype, part, artifact, "command"))
                    matched_any = True

            if not matched_any:
                part_claims.append(("generic_command", part, None, "command"))

            part_claims = dedupe_same_part_claims(part_claims)
            claims.extend(part_claims)

    return claims

ARTIFACT_PATTERNS = [
    r"\brequirements\.txt\b",
    r"\bpackage\.json\b",
    r"\bDockerfile\b",
    r"\bdocker-compose\.ya?ml\b",
    r"\bcompose\.ya?ml\b",
    r"\bMakefile\b",
    r"\bpom\.xml\b",
    r"\bbuild\.gradle(?:\.kts)?\b",
    r"\bCargo\.toml\b",
    r"\bgo\.mod\b",
    r"\bpyproject\.toml\b",
    r"\bsetup\.cfg\b",
    r"\btox\.ini\b",
    r"\bpytest\.ini\b",
    r"\benvironment\.ya?ml\b",
    r"\bPipfile\b",
    r"\bmanage\.py\b",
    r"\bapp\.py\b",
    r"\bmain\.py\b",
    r"\brun\.py\b",
    r"(?:\./|\.\./|/)?[A-Za-z0-9_.-]+/[A-Za-z0-9_./*-]+\.(?:py|js|ts|go|ya?ml|toml|cfg|ini|json|xml|ipynb|sh|bash|jar)\b",
    r"\b[A-Za-z0-9_.-]+\.(?:py|js|ts|go|ya?ml|toml|cfg|ini|json|xml|ipynb|sh|bash|jar)\b",
]

def is_probably_local_path(token):
    token = str(token or "").strip()
    if not token:
        return False

    t = canonicalize_artifact_or_path(token)
    if not t:
        return False

    tl = t.lower()

    if is_external_target(tl) or looks_like_domain(tl) or is_image_path(tl) or is_doc_path(tl):
        return False

    if tl in LOCAL_ARTIFACT_WHITELIST:
        return True
    if tl.startswith("../") or tl.startswith("./"):
        return True
    if "/" in tl:
        return True
    if re.match(r"^[A-Za-z0-9_.-]+\.(py|js|ts|go|ya?ml|toml|cfg|ini|json|xml|ipynb|sh|bash|jar)$", tl):
        return True

    return False

def extract_artifacts_from_text(text):
    text = str(text or "")
    found = []

    for pat in ARTIFACT_PATTERNS:
        for m in re.finditer(pat, text, flags=re.I):
            token = canonicalize_artifact_or_path(m.group(0))
            if not token:
                continue
            if is_external_target(token) or looks_like_domain(token) or is_image_path(token) or is_doc_path(token):
                continue
            if is_probably_local_path(token):
                found.append(token)

    seen = set()
    ordered = []
    for x in found:
        xl = x.lower()
        key = xl if "/" in xl else os.path.basename(xl)
        if key not in seen:
            seen.add(key)
            ordered.append(x)

    return ordered

def extract_inline_artifact(token):
    t = canonicalize_artifact_or_path(token)
    if not t:
        return None
    if is_external_target(t) or looks_like_domain(t) or is_image_path(t) or is_doc_path(t):
        return None
    if is_probably_local_path(t):
        return t
    return None

OPERATIONAL_DOC_HINTS = {
    "contributing", "install", "installation", "setup", "usage", "getting-started",
    "quickstart", "quick-start", "run", "deploy", "deployment", "examples", "example",
    "tutorial", "guide", "docs"
}

def is_actionable_local_link(target, target_type, heading="", link_text=""):
    t = canonicalize_artifact_or_path(target)
    tt = norm(target_type)
    lt = norm(link_text)

    if not t:
        return False
    if is_external_target(t):
        return False
    if tt in {"external", "image", "anchor", "unknown"}:
        return False
    if looks_like_badge_or_status(t) or looks_like_badge_or_status(lt):
        return False

    base = os.path.basename(norm(t))
    base_no_ext = re.sub(r"\.[a-z0-9]+$", "", base)

    if tt == "local_artifact":
        return True

    if tt in {"local_path_other", "local_other", "local_doc"}:
        if base in LOCAL_ARTIFACT_WHITELIST:
            return True
        if base_no_ext in OPERATIONAL_DOC_HINTS:
            return True
        if "/" in norm(t) and any(h in norm(t) for h in OPERATIONAL_DOC_HINTS):
            return True

    return False

claims = []

for _, row in structure_df.iterrows():
    full_name = row["full_name"]
    line_no = row.get("line_no")
    heading = str(row.get("heading", "") or "")
    section_class = str(row.get("section_class", "") or "other")
    operational_hint = int(row.get("operational_hint", 0) or 0)
    elem_type = str(row.get("elem_type", "") or "")
    content = "" if pd.isna(row.get("content")) else str(row.get("content"))
    code_lang = str(row.get("code_lang", "") or "")
    curated = likely_curated_repo(full_name)

    if not content.strip():
        continue
    if looks_like_badge_or_status(content):
        continue

    relevant_context = is_relevant_or_hint(section_class, operational_hint)

    if elem_type == "fenced_code":
        if heading_is_strongly_negative(heading) and str(code_lang).lower() not in SHELL_LANGS:
            pass
        else:
            extracted = extract_from_shell_text(content, heading=heading, code_lang=code_lang)
            for ctype, snippet, artifact, fam in extracted:
                claims.append({
                    "full_name": full_name,
                    "line_no": line_no,
                    "heading": heading,
                    "section_class": section_class,
                    "operational_hint": operational_hint,
                    "context_type": "fenced_code",
                    "claim_type": ctype,
                    "claim_family": fam,
                    "artifact_or_path": artifact,
                    "snippet": snippet,
                    "repo_curated_heuristic": curated,
                    "evidence_level": "high",
                })

            if relevant_context and not extracted:
                for artifact in extract_artifacts_from_text(content):
                    claims.append({
                        "full_name": full_name,
                        "line_no": line_no,
                        "heading": heading,
                        "section_class": section_class,
                        "operational_hint": operational_hint,
                        "context_type": "fenced_code_artifact",
                        "claim_type": "artifact_ref",
                        "claim_family": "artifact_reference",
                        "artifact_or_path": artifact,
                        "snippet": artifact,
                        "repo_curated_heuristic": curated,
                        "evidence_level": "medium",
                    })

    elif elem_type == "inline_code":
        token = content.strip()
        if not token:
            continue

        if shell_like_line(token, heading=heading, code_lang=None):
            for ctype, snippet, artifact, fam in extract_from_shell_text(token, heading=heading, code_lang=None):
                claims.append({
                    "full_name": full_name,
                    "line_no": line_no,
                    "heading": heading,
                    "section_class": section_class,
                    "operational_hint": operational_hint,
                    "context_type": "inline_code_command",
                    "claim_type": ctype,
                    "claim_family": fam,
                    "artifact_or_path": artifact,
                    "snippet": snippet,
                    "repo_curated_heuristic": curated,
                    "evidence_level": "medium",
                })
        else:
            if relevant_context and not heading_is_strongly_negative(heading) and not heading_is_soft_negative(heading):
                artifact = extract_inline_artifact(token)
                if artifact is not None:
                    claims.append({
                        "full_name": full_name,
                        "line_no": line_no,
                        "heading": heading,
                        "section_class": section_class,
                        "operational_hint": operational_hint,
                        "context_type": "inline_code_artifact",
                        "claim_type": "artifact_ref",
                        "claim_family": "artifact_reference",
                        "artifact_or_path": artifact,
                        "snippet": token,
                        "repo_curated_heuristic": curated,
                        "evidence_level": "medium",
                    })

    elif elem_type == "markdown_link":
        target = str(row.get("link_target", "") or "").strip()
        target_type = str(row.get("link_target_type", "") or "").strip()
        link_text = str(row.get("link_text", "") or "")

        if relevant_context and not heading_is_strongly_negative(heading):
            if is_actionable_local_link(target, target_type, heading=heading, link_text=link_text):
                claims.append({
                    "full_name": full_name,
                    "line_no": line_no,
                    "heading": heading,
                    "section_class": section_class,
                    "operational_hint": operational_hint,
                    "context_type": "markdown_link",
                    "claim_type": "local_link_ref",
                    "claim_family": "artifact_reference",
                    "artifact_or_path": canonicalize_artifact_or_path(target),
                    "snippet": content,
                    "repo_curated_heuristic": curated,
                    "evidence_level": "low",
                })

    elif elem_type == "section_line":
        line = content.strip()
        if not line:
            continue

        if curated and looks_like_list_bullet(line) and not shell_like_line(line, heading=heading):
            continue

        if shell_like_line(line, heading=heading):
            for ctype, snippet, artifact, fam in extract_from_shell_text(line, heading=heading, code_lang=None):
                claims.append({
                    "full_name": full_name,
                    "line_no": line_no,
                    "heading": heading,
                    "section_class": section_class,
                    "operational_hint": operational_hint,
                    "context_type": "section_line_command",
                    "claim_type": ctype,
                    "claim_family": fam,
                    "artifact_or_path": artifact,
                    "snippet": snippet,
                    "repo_curated_heuristic": curated,
                    "evidence_level": "medium",
                })

        if relevant_context and not heading_is_strongly_negative(heading):
            if not is_external_target(line) and not looks_link_heavy(line):
                for artifact in extract_artifacts_from_text(line):
                    claims.append({
                        "full_name": full_name,
                        "line_no": line_no,
                        "heading": heading,
                        "section_class": section_class,
                        "operational_hint": operational_hint,
                        "context_type": "section_line_artifact",
                        "claim_type": "artifact_ref",
                        "claim_family": "artifact_reference",
                        "artifact_or_path": artifact,
                        "snippet": line,
                        "repo_curated_heuristic": curated,
                        "evidence_level": "low",
                    })

claims_df = pd.DataFrame(claims)

if not claims_df.empty:
    claims_df["artifact_or_path"] = claims_df["artifact_or_path"].apply(canonicalize_artifact_or_path)
    claims_df["snippet_norm"] = claims_df["snippet"].fillna("").astype(str).str.strip().str.lower()
    claims_df["artifact_key"] = claims_df["artifact_or_path"].apply(normalize_artifact_key)

    claims_df = claims_df.drop_duplicates(
        subset=[
            "full_name", "line_no", "heading", "section_class",
            "context_type", "claim_type", "artifact_key", "snippet_norm"
        ]
    ).reset_index(drop=True)

    ref_mask = claims_df["claim_type"].isin({"artifact_ref", "local_link_ref"}) & claims_df["artifact_key"].ne("")
    ref_df = claims_df[ref_mask].copy()
    non_ref_df = claims_df[~ref_mask].copy()

    if not ref_df.empty:
        evidence_rank = {"high": 3, "medium": 2, "low": 1}
        context_rank = {
            "inline_code_artifact": 4,
            "fenced_code_artifact": 3,
            "markdown_link": 2,
            "section_line_artifact": 1,
        }

        ref_df["_evidence_rank"] = ref_df["evidence_level"].map(evidence_rank).fillna(0)
        ref_df["_context_rank"] = ref_df["context_type"].map(context_rank).fillna(0)

        ref_df = ref_df.sort_values(
            ["full_name", "artifact_key", "_evidence_rank", "_context_rank", "line_no"],
            ascending=[True, True, False, False, True],
        )

        ref_df = ref_df.drop_duplicates(subset=["full_name", "artifact_key"], keep="first")
        ref_df = ref_df.drop(columns=["_evidence_rank", "_context_rank"])

    claims_df = pd.concat([non_ref_df, ref_df], ignore_index=True)
    claims_df = claims_df.sort_values(["full_name", "line_no", "heading", "claim_type"]).reset_index(drop=True)
    claims_df = claims_df.drop(columns=["snippet_norm", "artifact_key"])

output_file = "claims_pilot_v11.csv"
claims_df.to_csv(output_file, index=False)

print(f"Saved {output_file}")
print("Extracted claims:", len(claims_df))

if not claims_df.empty:
    print("\nClaim type counts:")
    print(claims_df["claim_type"].value_counts(dropna=False).head(40))

    print("\nClaim family counts:")
    print(claims_df["claim_family"].value_counts(dropna=False))

    print("\nContext type counts:")
    print(claims_df["context_type"].value_counts(dropna=False))

    print("\nEvidence level counts:")
    print(claims_df["evidence_level"].value_counts(dropna=False))

    print("\nRepos with claims:")
    print(claims_df["full_name"].nunique())

    print("\nTop repos by claim count:")
    print(claims_df["full_name"].value_counts(dropna=False).head(25))

    print("\nPreview:")
    print(claims_df.head(25))
else:
    print("No claims extracted. Re-check README sample and structure output.")

files.download(output_file)