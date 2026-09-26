# ============================================
# Script 4 (FIXED / v4): Build rich artifact/config index
# - aligned with Script 1 (v3/v5 English-filtered)
# - reads trees_pilot_v3.csv and configs_pilot_v3.csv
# - file paths, dirs, manifests, make targets, workflow files
# - improved Makefile parsing and broader test support
# Google Colab standalone
# ============================================

!pip -q install pandas toml

import os
import re
import json
import toml  # retained for compatibility / future extension
import pandas as pd
from google.colab import files

print("Upload trees_pilot_v3.csv and configs_pilot_v3.csv")
uploaded = files.upload()

trees_file = None
configs_file = None
for fn in uploaded.keys():
    lower = fn.lower()
    if "trees" in lower:
        trees_file = fn
    elif "configs" in lower:
        configs_file = fn

if trees_file is None or configs_file is None:
    raise ValueError("Please upload both trees_pilot_v3.csv and configs_pilot_v3.csv")

trees_df = pd.read_csv(trees_file)
configs_df = pd.read_csv(configs_file)


def norm(s):
    return str(s or "").strip().replace("\\", "/").lower()


def split_path_parts(p):
    p = norm(p).strip("/")
    return [x for x in p.split("/") if x]


SPECIAL_MAKE_TARGETS = {
    ".phony", ".default", ".suffixes", ".precious", ".intermediate",
    ".secondary", ".seconexpansion", ".delete_on_error", ".ignore",
    ".low_resolution_time", ".silent", ".export_all_variables",
    ".notparallel", ".oneshell", ".posix"
}


def parse_make_targets(text):
    """
    Extract likely executable Make targets while excluding special directives,
    pattern rules, variable assignments, and multi-target lines.
    """
    targets = set()
    if not text:
        return targets

    for raw_line in str(text).splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("\t") or line.startswith(" "):
            continue
        if line.lstrip().startswith("#"):
            continue

        # skip variable assignments such as VAR := x or VAR = x
        if re.match(r"^[A-Za-z0-9_.-]+\s*[:+?]?=", line):
            continue

        m = re.match(r"^([^:#=]+?)\s*:(?![=])", line)
        if not m:
            continue

        lhs = m.group(1).strip()
        if not lhs:
            continue

        # Multiple targets may share a rule; keep only concrete single targets.
        for tgt in lhs.split():
            t = tgt.strip().lower()
            if not t:
                continue
            if t in SPECIAL_MAKE_TARGETS:
                continue
            if "%" in t:
                continue  # pattern rule, not concrete target
            if "/" in t:
                continue  # often path-like prerequisites/phony groups, not target names for our purpose
            if not re.match(r"^[a-z0-9_.-]+$", t):
                continue
            targets.add(t)

    return targets


PLACEHOLDER_NPM_TEST_VALUES = {
    "echo \"error: no test specified\" && exit 1",
    "echo 'error: no test specified' && exit 1",
    "exit 0",
    "true"
}


def parse_package_json_test_script(text):
    """
    Return 1 only when package.json has a non-placeholder test script.
    """
    if not text:
        return 0
    try:
        obj = json.loads(text)
        scripts = obj.get("scripts", {})
        if not isinstance(scripts, dict) or "test" not in scripts:
            return 0
        value = str(scripts.get("test", "")).strip().lower()
        if not value or value in PLACEHOLDER_NPM_TEST_VALUES:
            return 0
        return 1
    except Exception:
        return 0


TEST_DIR_NAMES = {
    "test", "tests", "spec", "specs", "__tests__", "integration", "integration_tests",
    "e2e", "e2e_tests", "unittests", "unit_tests"
}


def has_test_directory(dir_paths_set, top_dirs_set):
    all_dirs = set(dir_paths_set) | set(top_dirs_set)
    for d in all_dirs:
        parts = split_path_parts(d)
        if any(part in TEST_DIR_NAMES for part in parts):
            return 1
    return 0


PY_TEST_PATTERNS = [
    re.compile(r"(^|/)test_.*\.py$"),
    re.compile(r"(^|/).*_test\.py$"),
]

JS_TS_TEST_PATTERNS = [
    re.compile(r"(^|/).*\.(test|spec)\.(js|jsx|ts|tsx)$"),
]

JAVA_TEST_PATTERNS = [
    re.compile(r"(^|/).*test\.java$"),
]


def has_matching_file(file_paths_set, patterns):
    for p in file_paths_set:
        for pat in patterns:
            if pat.search(p):
                return 1
    return 0


records = []

for full_name, g in trees_df.groupby("full_name"):
    file_paths = []
    dir_paths = []
    basenames = []
    top_dirs = set()

    for _, row in g.iterrows():
        p = norm(row.get("path", ""))
        t = norm(row.get("type", ""))
        if not p:
            continue
        if t == "blob":
            file_paths.append(p)
            basenames.append(os.path.basename(p))
            parts = split_path_parts(p)
            if len(parts) >= 2:
                top_dirs.add(parts[0])
        elif t == "tree":
            dir_paths.append(p)
            parts = split_path_parts(p)
            if parts:
                top_dirs.add(parts[0])

    file_paths_set = set(file_paths)
    basenames_set = set(basenames)
    dir_paths_set = set(dir_paths)
    top_dirs_set = set(top_dirs)

    cfg = configs_df[configs_df["full_name"] == full_name]

    make_targets = set()
    npm_has_test_script = 0
    workflow_files = []
    has_pyproject = 0
    has_setup_cfg = 0
    has_tox_ini = 0
    has_pytest_ini = 0

    for _, crow in cfg.iterrows():
        p = norm(crow.get("path", ""))
        b = norm(crow.get("basename", ""))
        content = crow.get("content")

        if b == "makefile":
            make_targets |= parse_make_targets(content)
        elif b == "package.json":
            npm_has_test_script = max(npm_has_test_script, parse_package_json_test_script(content))
        elif p.startswith(".github/workflows/"):
            workflow_files.append(p)
        elif b == "pyproject.toml":
            has_pyproject = 1
        elif b == "setup.cfg":
            has_setup_cfg = 1
        elif b == "tox.ini":
            has_tox_ini = 1
        elif b == "pytest.ini":
            has_pytest_ini = 1

    has_tests_dir = has_test_directory(dir_paths_set, top_dirs_set)
    has_py_test_files = has_matching_file(file_paths_set, PY_TEST_PATTERNS)
    has_go_test_files = int(any(p.endswith("_test.go") for p in file_paths_set))
    has_js_ts_test_files = has_matching_file(file_paths_set, JS_TS_TEST_PATTERNS)
    has_java_test_files = has_matching_file(file_paths_set, JAVA_TEST_PATTERNS)

    records.append({
        "full_name": full_name,
        "file_count": len(file_paths_set),
        "dir_count": len(dir_paths_set),
        "all_file_paths": " || ".join(sorted(file_paths_set)),
        "all_file_basenames": " || ".join(sorted(basenames_set)),
        "all_dir_paths": " || ".join(sorted(dir_paths_set)),
        "top_level_dirs": " || ".join(sorted(top_dirs_set)),
        "workflow_files": " || ".join(sorted(set(workflow_files))),
        "make_targets": " || ".join(sorted(make_targets)),
        "has_requirements_txt": int("requirements.txt" in basenames_set),
        "has_package_json": int("package.json" in basenames_set),
        "has_dockerfile": int("dockerfile" in basenames_set),
        "has_docker_compose": int(any(x in basenames_set for x in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"})),
        "has_makefile": int("makefile" in basenames_set),
        "has_pom_xml": int("pom.xml" in basenames_set),
        "has_build_gradle": int(any(x in basenames_set for x in {"build.gradle", "build.gradle.kts"})),
        "has_cargo_toml": int("cargo.toml" in basenames_set),
        "has_go_mod": int("go.mod" in basenames_set),
        "has_pyproject_toml": has_pyproject,
        "has_setup_cfg": has_setup_cfg,
        "has_tox_ini": has_tox_ini,
        "has_pytest_ini": has_pytest_ini,
        "has_tests_dir": has_tests_dir,
        "has_py_test_files": has_py_test_files,
        "has_go_test_files": has_go_test_files,
        "has_js_ts_test_files": has_js_ts_test_files,
        "has_java_test_files": has_java_test_files,
        "npm_has_test_script": npm_has_test_script,
    })

artifact_df = pd.DataFrame(records)
artifact_df.to_csv("artifact_index_pilot_v3.csv", index=False)

print("Saved artifact_index_pilot_v3.csv")
print("Shape:", artifact_df.shape)
print("\nPreview:")
print(artifact_df.head())
files.download("artifact_index_pilot_v3.csv")
