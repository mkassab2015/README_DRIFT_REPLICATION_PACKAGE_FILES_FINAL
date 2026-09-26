# ============================================
# Script 5 (FIXED / v3): Layered README drift detector
# Labels:
# - drifted_high
# - drifted_medium
# - supported
# - uncertain
# Aligned with Script 3 (v6) and Script 4 (v3)
# ============================================

!pip -q install pandas

import os
import re
import pandas as pd
from google.colab import files

print("Upload claims_pilot_v6.csv and artifact_index_pilot_v3.csv")
uploaded = files.upload()

claims_file = None
artifact_file = None
for fn in uploaded.keys():
    lower = fn.lower()
    if "claims" in lower:
        claims_file = fn
    elif "artifact_index" in lower:
        artifact_file = fn

if claims_file is None or artifact_file is None:
    raise ValueError("Please upload both claims_pilot_v6.csv and artifact_index_pilot_v3.csv")

claims_df = pd.read_csv(claims_file)
artifact_df = pd.read_csv(artifact_file)

def split_field(s):
    s = "" if pd.isna(s) else str(s)
    return [x.strip() for x in re.split(r"\|\|", s) if x.strip()]

def norm(s):
    return str(s or "").strip().replace("\\", "/").lower()

lookup = {}
for _, row in artifact_df.iterrows():
    lookup[row["full_name"]] = {
        "file_paths": set(norm(x) for x in split_field(row.get("all_file_paths", ""))),
        "file_basenames": set(norm(x) for x in split_field(row.get("all_file_basenames", ""))),
        "dir_paths": set(norm(x) for x in split_field(row.get("all_dir_paths", ""))),
        "top_dirs": set(norm(x) for x in split_field(row.get("top_level_dirs", ""))),
        "workflow_files": set(norm(x) for x in split_field(row.get("workflow_files", ""))),
        "make_targets": set(norm(x) for x in split_field(row.get("make_targets", ""))),
        "has_requirements_txt": int(row.get("has_requirements_txt", 0)),
        "has_package_json": int(row.get("has_package_json", 0)),
        "has_dockerfile": int(row.get("has_dockerfile", 0)),
        "has_docker_compose": int(row.get("has_docker_compose", 0)),
        "has_makefile": int(row.get("has_makefile", 0)),
        "has_pom_xml": int(row.get("has_pom_xml", 0)),
        "has_build_gradle": int(row.get("has_build_gradle", 0)),
        "has_cargo_toml": int(row.get("has_cargo_toml", 0)),
        "has_go_mod": int(row.get("has_go_mod", 0)),
        "has_pyproject_toml": int(row.get("has_pyproject_toml", 0)),
        "has_setup_cfg": int(row.get("has_setup_cfg", 0)),
        "has_tox_ini": int(row.get("has_tox_ini", 0)),
        "has_pytest_ini": int(row.get("has_pytest_ini", 0)),
        "has_tests_dir": int(row.get("has_tests_dir", 0)),
        "has_py_test_files": int(row.get("has_py_test_files", 0)),
        "has_go_test_files": int(row.get("has_go_test_files", 0)),
        "npm_has_test_script": int(row.get("npm_has_test_script", 0)),
    }

def exists_file_or_basename(artifact, repo):
    a = norm(artifact)
    if not a:
        return False
    return a in repo["file_paths"] or os.path.basename(a) in repo["file_basenames"]

def exists_dir(path, repo):
    p = norm(path).rstrip("/")
    return p in repo["dir_paths"] or p in repo["top_dirs"]

def classify_drift(row, repo):
    ctype = str(row["claim_type"])
    artifact = row.get("artifact_or_path")
    snippet = str(row.get("snippet", ""))

    label = "supported"
    family = "unknown"
    reason = "Artifact/structure support found."

    if ctype == "pip_requirements":
        family = "D1_dependency_file_drift"
        if not repo["has_requirements_txt"]:
            return "drifted_high", family, "README requires requirements.txt but file is missing"
        return label, family, reason

    if ctype == "docker_build":
        family = "D1_dependency_file_drift"
        if artifact:
            if not exists_file_or_basename(artifact, repo):
                return "drifted_high", family, f"docker build references missing file: {artifact}"
        elif not repo["has_dockerfile"]:
            return "drifted_high", family, "README uses docker build but Dockerfile is missing"
        return label, family, reason

    if ctype in {"python_script"}:
        family = "D2_entrypoint_drift"
        if not exists_file_or_basename(artifact, repo):
            return "drifted_high", family, f"Referenced entrypoint missing: {artifact}"
        return label, family, reason

    if ctype == "cd_dir":
        family = "D3_path_directory_drift"
        target = str(artifact or "").strip()
        if target not in {".", ".."} and not exists_dir(target, repo):
            return "drifted_high", family, f"Referenced directory missing: {target}"
        return label, family, reason

    if ctype in {"artifact_ref", "local_link_ref"}:
        family = "D8_local_example_or_artifact_drift"
        if artifact and not exists_file_or_basename(artifact, repo):
            return "drifted_high", family, f"Referenced local artifact/path missing: {artifact}"
        return label, family, reason

    if ctype == "make_cmd":
        family = "D5_build_or_test_drift"
        m = re.match(r"^\s*make(?:\s+([A-Za-z0-9_.-]+))?\s*$", snippet.strip())
        target = m.group(1).lower() if m and m.group(1) else None
        if not repo["has_makefile"]:
            return "drifted_high", family, "README uses make but Makefile is missing"
        if target and repo["make_targets"] and target not in repo["make_targets"]:
            return "drifted_medium", family, f"Make target '{target}' not found in Makefile"
        return label, family, reason

    if ctype == "pytest_cmd":
        family = "D6_test_command_drift"
        support = (
            repo["has_tests_dir"] or repo["has_py_test_files"] or
            repo["has_pyproject_toml"] or repo["has_setup_cfg"] or
            repo["has_tox_ini"] or repo["has_pytest_ini"]
        )
        if not support:
            return "drifted_medium", family, "README uses pytest but no test/config evidence found"
        return label, family, reason

    if ctype == "docker_compose_up":
        family = "D7_container_deployment_drift"
        if not repo["has_docker_compose"]:
            return "drifted_high", family, "README uses docker compose but no compose file found"
        return label, family, reason

    if ctype == "poetry_install":
        family = "D1_dependency_file_drift"
        if not repo["has_pyproject_toml"]:
            return "drifted_high", family, "README uses poetry install but pyproject.toml is missing"
        return label, family, reason

    if ctype == "python_module":
        family = "D2_entrypoint_drift"
        return "uncertain", family, "Python module execution needs package-level semantic resolution beyond current static rules"

    return label, family, reason

rows = []
for _, row in claims_df.iterrows():
    full_name = row["full_name"]
    if full_name not in lookup:
        continue
    label, family, reason = classify_drift(row, lookup[full_name])
    rows.append({
        "full_name": full_name,
        "line_no": row.get("line_no"),
        "heading": row.get("heading"),
        "section_class": row.get("section_class"),
        "context_type": row.get("context_type"),
        "claim_type": row.get("claim_type"),
        "claim_family": row.get("claim_family"),
        "artifact_or_path": row.get("artifact_or_path"),
        "snippet": row.get("snippet"),
        "repo_curated_heuristic": row.get("repo_curated_heuristic"),
        "drift_family": family,
        "label": label,
        "reason": reason,
    })

results_df = pd.DataFrame(rows)
results_df.to_csv("drift_results_pilot_v3_detailed.csv", index=False)

summary_df = (
    results_df.groupby(["full_name", "label"])
    .size()
    .reset_index(name="count")
    .pivot(index="full_name", columns="label", values="count")
    .fillna(0)
    .reset_index()
)

for col in ["drifted_high", "drifted_medium", "supported", "uncertain"]:
    if col not in summary_df.columns:
        summary_df[col] = 0

summary_df["total_claims"] = summary_df[["drifted_high", "drifted_medium", "supported", "uncertain"]].sum(axis=1)
summary_df["has_any_high_drift"] = (summary_df["drifted_high"] > 0).astype(int)
summary_df["has_any_drift"] = ((summary_df["drifted_high"] + summary_df["drifted_medium"]) > 0).astype(int)
summary_df.to_csv("drift_results_pilot_v3_summary.csv", index=False)

print("Saved drift_results_pilot_v3_detailed.csv and drift_results_pilot_v3_summary.csv")
files.download("drift_results_pilot_v3_detailed.csv")
files.download("drift_results_pilot_v3_summary.csv")
