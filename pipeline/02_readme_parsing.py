# ============================================
# Script 2 (FIXED / v5): Parse README structure with expanded, research-grounded taxonomy
# - aligned with Script 1 (v3)
# - reads readmes_pilot_v3.csv
# - preserves all section lines
# - strengthens English heading taxonomy substantially
# - supports numbered imperative headings (e.g., "1. Clone the repository")
# - keeps output schema compatible with Script 3
# Google Colab standalone
# ============================================

!pip -q install pandas

import re
import pandas as pd
from google.colab import files

print("Upload readmes_pilot_v3.csv")
uploaded = files.upload()
input_file = next(iter(uploaded.keys()))

readmes_df = pd.read_csv(input_file)

# ----------------------------------
# Methodologically grounded taxonomy
# ----------------------------------
# Design rationale:
# 1) README studies show that repositories commonly document "what" and "how" content,
#    and that section-level labeling is feasible and useful for information discovery.
# 2) Installation-oriented README work distinguishes pre-installation, installation,
#    and post-installation/help content.
# 3) GitHub's own guidance highlights project purpose, getting started, help, and
#    contribution/maintenance information as central README functions.
#
# To stay compatible with Script 3, we operationalize these ideas into the same
# downstream labels already consumed there:
#   installation, usage, run, test, build, development, deployment, ci, documentation, other
#
# The patterns below are intentionally broad, but remain English-only and are organized
# around functional documentation intent rather than arbitrary lexical expansion.

SECTION_PATTERNS = [
    ("installation", [
        # canonical install/setup language
        r"\binstall(?:ation|ing|ed)?\b",
        r"\bsetup\b",
        r"\bset\s*up\b",
        r"\bprerequisites?\b",
        r"\brequirements?\b",
        r"\bdependencies?\b",
        r"\bdependency\s+installation\b",
        r"\benvironment\s+setup\b",
        r"\bvirtual\s+environment\b",
        r"\bvenv\b",
        r"\bconda\b",
        r"\bpip\s+install\b",
        r"\bnpm\s+install\b",
        r"\byarn\s+install\b",
        r"\bpnpm\s+install\b",
        r"\bpoetry\s+install\b",
        r"\bdownload\b",
        r"\bdownloads\b",
        r"\bclone\b",
        r"\bcloning\b",
        r"\bcheckout\b",
        r"\bget\s+started\b",
        r"\bgetting\s+started\b",
        r"\bquick\s*start\b",
        r"\bquickstart\b",
        r"\bfirst\s+steps?\b",
        r"\bbootstr(?:ap|apping)\b",
        r"\binit(?:ialize|ialization)?\b",
        r"\bconfiguration\s+setup\b",
        r"\blocal\s+setup\b",
        r"\bfrom\s+source\b",
        r"\bbuild\s+from\s+source\b",
        r"\bmanual\s+installation\b",
        r"\binstall\s+guide\b",
        r"\bsetup\s+guide\b",
        r"\bpre[- ]?install(?:ation)?\b",
    ]),
    ("usage", [
        # how to use / interact / examples / tutorials
        r"\busage\b",
        r"\bhow\s+to\s+use\b",
        r"\busing\b",
        r"\buser\s+guide\b",
        r"\bguide\b",
        r"\bguides\b",
        r"\btutorial\b",
        r"\btutorials\b",
        r"\bwalkthrough\b",
        r"\bwalk[- ]?through\b",
        r"\bexamples?\b",
        r"\bexample\s+usage\b",
        r"\bdemo\b",
        r"\bdemonstration\b",
        r"\bshowcase\b",
        r"\bcli\b",
        r"\bcommand\s+line\b",
        r"\bweb\s+app(?:lication)?\b",
        r"\bapi\s+usage\b",
        r"\bhow\s+it\s+works\b",
        r"\binteract(?:ion|ing)?\b",
        r"\buse\s+cases?\b",
        r"\bscenario\b",
        r"\bscenarios\b",
        r"\bnotebook\s+example\b",
        r"\btry\s+it\b",
        r"\bplayground\b",
        r"\bhelp\b",
        r"\bfaq\b",
    ]),
    ("run", [
        # post-install execution / launch / service startup
        r"\brun(?:ning)?\b",
        r"\bexecute\b",
        r"\bexecution\b",
        r"\bstart\b",
        r"\bstarting\b",
        r"\blaunch\b",
        r"\blaunching\b",
        r"\bserve\b",
        r"\bserving\b",
        r"\bstartup\b",
        r"\bstart\s+server\b",
        r"\brun\s+server\b",
        r"\binference\b",
        r"\binfer\b",
        r"\bprediction\b",
        r"\bpredict\b",
        r"\btraining\b",
        r"\btrain\b",
        r"\bevaluate\s+the\s+model\b",
        r"\blaunch\s+the\s+app\b",
        r"\brun\s+the\s+app\b",
        r"\brun\s+locally\b",
        r"\blive\s+demo\b",
        r"\bstart\s+here\b",
        r"\bexecution\s+example\b",
    ]),
    ("test", [
        # validation / test / benchmark / quality checks
        r"\btest(?:ing|s|ed)?\b",
        r"\brun\s+tests?\b",
        r"\bunit\s+tests?\b",
        r"\bintegration\s+tests?\b",
        r"\be2e\b",
        r"\bend[- ]to[- ]end\b",
        r"\bvalidation\b",
        r"\bverify\b",
        r"\bverification\b",
        r"\bchecks?\b",
        r"\bquality\s+checks?\b",
        r"\bbenchmark(?:s|ing)?\b",
        r"\bevaluation\b",
        r"\bsmoke\s+test\b",
        r"\bregression\s+test\b",
        r"\btest\s+suite\b",
        r"\bcoverage\b",
        r"\blint(?:ing)?\b",
        r"\bstatic\s+analysis\b",
    ]),
    ("build", [
        # compiling / packaging / release engineering
        r"\bbuild(?:ing)?\b",
        r"\bcompile\b",
        r"\bcompilation\b",
        r"\bpackage(?:d|ing)?\b",
        r"\bpackaging\b",
        r"\brelease\b",
        r"\breleases\b",
        r"\bdistribution\b",
        r"\bartifact\s+build\b",
        r"\bbundle\b",
        r"\bbundling\b",
        r"\bmake\b",
        r"\bbuild\s+artifacts?\b",
        r"\bbuild\s+steps?\b",
        r"\bcompile\s+from\s+source\b",
    ]),
    ("development", [
        # contributor/developer/local hacking workflows
        r"\bdevelopment\b",
        r"\bdeveloper\b",
        r"\bdevelopers\b",
        r"\bdev\b",
        r"\bcontribut(?:e|ing|ion|ors?)\b",
        r"\bfor\s+developers\b",
        r"\bdevelopment\s+setup\b",
        r"\blocal\s+development\b",
        r"\bhacking\b",
        r"\bhacker\s+guide\b",
        r"\barchitecture\s+for\s+developers\b",
        r"\bcode\s+style\b",
        r"\bstyle\s+guide\b",
        r"\bdev\s+workflow\b",
        r"\bworkflow\s+for\s+contributors\b",
        r"\bextending\b",
        r"\bplugin\s+development\b",
        r"\bdevelopment\s+guide\b",
    ]),
    ("deployment", [
        # deployment / hosting / operations
        r"\bdeploy(?:ment|ing)?\b",
        r"\bproduction\b",
        r"\bself[- ]?hosting\b",
        r"\bhost(?:ing|ed)?\b",
        r"\bcontainer(?:s|ization)?\b",
        r"\bdocker\b",
        r"\bdocker\s+compose\b",
        r"\bkubernetes\b",
        r"\bk8s\b",
        r"\bhelm\b",
        r"\bterraform\b",
        r"\bansible\b",
        r"\bcloud\b",
        r"\baws\b",
        r"\bazure\b",
        r"\bgcp\b",
        r"\binfrastructure\b",
        r"\bops\b",
        r"\boperat(?:e|ions?)\b",
        r"\bserving\s+in\s+production\b",
        r"\bruntime\s+environment\b",
        r"\bdeployment\s+guide\b",
    ]),
    ("ci", [
        # automation pipelines / CI/CD workflows
        r"\bci\b",
        r"\bcd\b",
        r"\bci/cd\b",
        r"\bcontinuous\s+integration\b",
        r"\bcontinuous\s+delivery\b",
        r"\bcontinuous\s+deployment\b",
        r"\bgithub\s+actions\b",
        r"\bactions\s+workflow\b",
        r"\bworkflow(?:s)?\b",
        r"\bpipeline(?:s)?\b",
        r"\bbuildkite\b",
        r"\bjenkins\b",
        r"\bgitlab\s+ci\b",
        r"\bcircleci\b",
        r"\btravis\b",
        r"\bautomation\b",
        r"\brelease\s+pipeline\b",
    ]),
    ("documentation", [
        # explicit docs/reference/API/reference-manual style sections
        r"\bdocumentation\b",
        r"\bdocs?\b",
        r"\breference\b",
        r"\breferences\b",
        r"\bapi\b",
        r"\bapi\s+reference\b",
        r"\bmanual\b",
        r"\bread\s+more\b",
        r"\bfurther\s+reading\b",
        r"\bresources?\b",
        r"\brelated\s+work\b",
        r"\bpaper\b",
        r"\bcitation\b",
    ]),
]

# Additional imperative heading rules for numbered/procedural headings.
# These are only applied when no direct section match is found.
IMPERATIVE_RULES = [
    ("installation", [
        r"^(?:clone|download|get|fetch|install|set\s*up|setup|configure|create\s+(?:a\s+)?(?:virtual\s+)?environment|prepare|bootstrap|initialize|init|checkout)\b",
        r"^(?:step\s*\d+\s*[:.-]?\s*)?(?:clone|download|install|configure|setup|set\s*up)\b",
    ]),
    ("usage", [
        r"^(?:open|use|try|follow|see|explore)\b",
        r"^(?:command\s+line\s+interface|cli|web\s+application|web\s+app|example|tutorial)\b",
    ]),
    ("run", [
        r"^(?:run|start|launch|serve|execute|train|infer|predict)\b",
    ]),
    ("test", [
        r"^(?:test|verify|validate|benchmark|lint|check)\b",
    ]),
    ("build", [
        r"^(?:build|compile|package|bundle|release)\b",
    ]),
    ("development", [
        r"^(?:contribute|contributing|develop|extend|hack)\b",
    ]),
    ("deployment", [
        r"^(?:deploy|host|self[- ]?host|containerize)\b",
    ]),
    ("ci", [
        r"^(?:configure\s+ci|set\s*up\s+ci|github\s+actions|pipeline|workflow)\b",
    ]),
]

OPER_HINT_PATTERNS = [
    # broad operational signals; documentation-only sections are intentionally omitted
    r"\binstall(?:ation|ing|ed)?\b",
    r"\bsetup\b",
    r"\bset\s*up\b",
    r"\bprerequisites?\b",
    r"\brequirements?\b",
    r"\bdependencies?\b",
    r"\bdownload\b",
    r"\bclone\b",
    r"\bgetting\s+started\b",
    r"\bquick\s*start\b",
    r"\busage\b",
    r"\bexamples?\b",
    r"\btutorial\b",
    r"\bcli\b",
    r"\bcommand\s+line\b",
    r"\brun(?:ning)?\b",
    r"\bexecute\b",
    r"\bstart(?:ing)?\b",
    r"\blaunch(?:ing)?\b",
    r"\bserve\b",
    r"\bserving\b",
    r"\btrain(?:ing)?\b",
    r"\binfer(?:ence)?\b",
    r"\bpredict(?:ion)?\b",
    r"\btest(?:ing|s)?\b",
    r"\bverify\b",
    r"\bvalidation\b",
    r"\bbenchmark(?:s|ing)?\b",
    r"\blint(?:ing)?\b",
    r"\bbuild(?:ing)?\b",
    r"\bcompile\b",
    r"\bpackage(?:d|ing)?\b",
    r"\bdevelopment\b",
    r"\bcontribut(?:e|ing|ion)?\b",
    r"\blocal\s+development\b",
    r"\bdeploy(?:ment|ing)?\b",
    r"\bproduction\b",
    r"\bdocker\b",
    r"\bkubernetes\b",
    r"\bhelm\b",
    r"\bterraform\b",
    r"\bci\b",
    r"\bci/cd\b",
    r"\bcontinuous\s+integration\b",
    r"\bworkflow(?:s)?\b",
    r"\bpipeline(?:s)?\b",
    r"\bgithub\s+actions\b",
]

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
DOC_EXTS = {".md", ".rst", ".adoc", ".txt"}
ARTIFACT_EXTS = {".py", ".js", ".go", ".jar", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".json", ".xml", ".ipynb"}

ARTIFACT_NAMES = {
    "requirements.txt", "package.json", "dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
    "compose.yml", "compose.yaml",
    "makefile", "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "go.mod", "pyproject.toml", "setup.cfg",
    "tox.ini", "pytest.ini", "environment.yml", "environment.yaml", "pipfile"
}

# ----------------------------------
# Helpers
# ----------------------------------
def normalize_heading(text):
    text = str(text or "").strip().lower()
    # remove markdown/images/html-ish wrappers that commonly appear in headings
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[^\]]+\]\([^)]*\)", " ", text)
    text = re.sub(r"[`*_:#>|]+", " ", text)
    text = re.sub(r"^[\W_]*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_leading_enumerator(text):
    text = str(text or "").strip()
    # examples handled:
    # 1. Clone the repository
    # 2) Install dependencies
    # Step 3: Run tests
    # Phase II - Build
    # I. Setup
    text = re.sub(r"^(?:step|phase)\s+[ivxlcdm0-9]+\s*[:.)-]\s*", "", text, flags=re.I)
    text = re.sub(r"^[ivxlcdm]+\s*[:.)-]\s*", "", text, flags=re.I)
    text = re.sub(r"^\d+\s*[:.)-]\s*", "", text)
    return text.strip()


def is_setext_heading(lines, idx):
    if idx + 1 >= len(lines):
        return False
    line = lines[idx].rstrip()
    underline = lines[idx + 1].rstrip()
    if not line.strip():
        return False
    if re.match(r"^\s*=\s*=+\s*$", underline):
        return True
    if re.match(r"^\s*-\s*-+\s*$", underline):
        return True
    if re.match(r"^\s*[=-]{3,}\s*$", underline):
        return True
    return False


def normalize_for_classification(heading_text):
    h = normalize_heading(heading_text)
    h = strip_leading_enumerator(h)
    return h


def classify_section(heading_text):
    h = normalize_for_classification(heading_text)

    # direct lexical/function match first
    for section_name, patterns in SECTION_PATTERNS:
        for pat in patterns:
            if re.search(pat, h, flags=re.I):
                return section_name

    # fallback: imperative/procedural numbered headings
    for section_name, patterns in IMPERATIVE_RULES:
        for pat in patterns:
            if re.search(pat, h, flags=re.I):
                return section_name

    return "other"


def has_operational_hint(heading_text):
    h = normalize_for_classification(heading_text)
    return int(any(re.search(p, h, flags=re.I) for p in OPER_HINT_PATTERNS))


def is_external_target(target):
    t = str(target or "").strip().lower()
    return (
        t.startswith("http://") or
        t.startswith("https://") or
        t.startswith("www.") or
        "://" in t
    )


def classify_link_target(target):
    t = str(target or "").strip()
    tl = t.lower()

    if not t:
        return "unknown"
    if is_external_target(t):
        return "external"
    if tl.startswith("#"):
        return "anchor"

    base = re.split(r"[?#]", tl)[0]

    for ext in IMAGE_EXTS:
        if base.endswith(ext):
            return "image"
    for ext in DOC_EXTS:
        if base.endswith(ext):
            return "local_doc"
    for ext in ARTIFACT_EXTS:
        if base.endswith(ext):
            return "local_artifact"

    if base.endswith("/"):
        return "local_dir"

    name = base.split("/")[-1] if "/" in base else base
    if name in ARTIFACT_NAMES:
        return "local_artifact"
    if name in {"docs", "doc", "documentation", "examples", "example"}:
        return "local_doc"
    if "/" in base:
        return "local_path_other"
    return "local_other"


# ----------------------------------
# Parser
# ----------------------------------
def parse_readme(text):
    text = "" if pd.isna(text) else str(text)
    lines = text.splitlines()

    rows = []
    current_heading = "ROOT"
    current_heading_norm = "root"
    current_section = "other"
    current_oper_hint = 0

    in_fence = False
    fence_lang = None
    fence_start = None
    fence_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]
        line_no = i + 1

        # ATX headings: ## Heading
        m_head = re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if not in_fence and m_head:
            current_heading = m_head.group(2).strip()
            current_heading_norm = normalize_for_classification(current_heading)
            current_section = classify_section(current_heading)
            current_oper_hint = has_operational_hint(current_heading)

            rows.append({
                "elem_type": "heading",
                "line_no": line_no,
                "heading": current_heading,
                "heading_norm": current_heading_norm,
                "section_class": current_section,
                "operational_hint": current_oper_hint,
                "content": line,
                "code_lang": None,
                "link_text": None,
                "link_target": None,
                "link_target_type": None,
            })
            i += 1
            continue

        # Setext headings:
        # Heading text
        # ----------
        if not in_fence and is_setext_heading(lines, i):
            current_heading = line.strip()
            current_heading_norm = normalize_for_classification(current_heading)
            current_section = classify_section(current_heading)
            current_oper_hint = has_operational_hint(current_heading)

            rows.append({
                "elem_type": "heading",
                "line_no": line_no,
                "heading": current_heading,
                "heading_norm": current_heading_norm,
                "section_class": current_section,
                "operational_hint": current_oper_hint,
                "content": line,
                "code_lang": None,
                "link_text": None,
                "link_target": None,
                "link_target_type": None,
            })
            i += 2
            continue

        m_fence = re.match(r"^\s*```([A-Za-z0-9_+\-#. ]*)\s*$", line)
        if m_fence:
            if not in_fence:
                in_fence = True
                fence_lang = (m_fence.group(1) or "").strip().lower()
                fence_start = line_no
                fence_lines = []
            else:
                rows.append({
                    "elem_type": "fenced_code",
                    "line_no": fence_start,
                    "heading": current_heading,
                    "heading_norm": current_heading_norm,
                    "section_class": current_section,
                    "operational_hint": current_oper_hint,
                    "content": "\n".join(fence_lines),
                    "code_lang": fence_lang,
                    "link_text": None,
                    "link_target": None,
                    "link_target_type": None,
                })
                in_fence = False
                fence_lang = None
                fence_start = None
                fence_lines = []
            i += 1
            continue

        if in_fence:
            fence_lines.append(line)
            i += 1
            continue

        for match in re.finditer(r"`([^`\n]+)`", line):
            rows.append({
                "elem_type": "inline_code",
                "line_no": line_no,
                "heading": current_heading,
                "heading_norm": current_heading_norm,
                "section_class": current_section,
                "operational_hint": current_oper_hint,
                "content": match.group(1),
                "code_lang": None,
                "link_text": None,
                "link_target": None,
                "link_target_type": None,
            })

        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
            target = match.group(2)
            rows.append({
                "elem_type": "markdown_link",
                "line_no": line_no,
                "heading": current_heading,
                "heading_norm": current_heading_norm,
                "section_class": current_section,
                "operational_hint": current_oper_hint,
                "content": line.strip(),
                "code_lang": None,
                "link_text": match.group(1),
                "link_target": target,
                "link_target_type": classify_link_target(target),
            })

        rows.append({
            "elem_type": "section_line",
            "line_no": line_no,
            "heading": current_heading,
            "heading_norm": current_heading_norm,
            "section_class": current_section,
            "operational_hint": current_oper_hint,
            "content": line,
            "code_lang": None,
            "link_text": None,
            "link_target": None,
            "link_target_type": None,
        })

        i += 1

    return rows


# ----------------------------------
# Run
# ----------------------------------
all_rows = []
for _, row in readmes_df.iterrows():
    full_name = row["full_name"]
    parsed = parse_readme(row["readme_text"])
    for r in parsed:
        r["full_name"] = full_name
        all_rows.append(r)

parsed_df = pd.DataFrame(all_rows)
parsed_df.to_csv("readme_structure_pilot_v3.csv", index=False)

print("Saved readme_structure_pilot_v3.csv")
print("Shape:", parsed_df.shape)
print("\nElement type counts:")
print(parsed_df["elem_type"].value_counts(dropna=False))
print("\nSection class counts:")
print(parsed_df["section_class"].value_counts(dropna=False).head(20))
print("\nOperational hint counts:")
print(parsed_df["operational_hint"].value_counts(dropna=False))
print("\nLink target type counts:")
if "link_target_type" in parsed_df.columns:
    print(parsed_df["link_target_type"].value_counts(dropna=False).head(20))

files.download("readme_structure_pilot_v3.csv")
