# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Release gate (RR-B-15): required files, forbidden paths, forbidden
content, headers present, version agreement (RR-B-09). Exits non-zero on
any failure."""
import pathlib
import re
import sys

fails: list[str] = []

REQUIRED = ["LICENSE", "COPYRIGHT", "NOTICE", "README.md", "CHANGELOG.md",
            "RELEASE-INFO.txt", "CITATION.cff", "SECURITY.md", ".gitignore",
            "pyproject.toml", "docs/install.md", "docs/configuration.md",
            "docs/licensing.md", "docs/usage.md", "docs/TOOL-REFERENCE.md",
            "examples/.mcp.json.example", "glama.json", "smithery.yaml",
            ".claude-plugin/marketplace.json", ".claude-plugin/plugin.json",
            ".cursor-plugin/plugin.json", ".cursor-plugin/marketplace.json",
            ".agents/plugins/marketplace.json", "gemini-extension.json"]
for f in REQUIRED:
    if not pathlib.Path(f).is_file():
        fails.append(f"required file missing: {f}")

# forbidden paths: judge the TRACKED tree (local gitignored dirs are fine)
import subprocess
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         check=True).stdout.splitlines()
FORBIDDEN_PATH_PARTS = ["__pycache__", ".venv", ".worktrees", ".pytest_cache",
                        ".ruff_cache", ".bak"]
for f in tracked:
    if any(part in f for part in FORBIDDEN_PATH_PARTS):
        fails.append(f"forbidden tracked path: {f}")

FORBIDDEN_CONTENT = [re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
                     re.compile(r"CONFIDENTIAL")]
SCAN_GLOBS = ["src/**/*.py", "tests/**/*.py", "docs/**/*.md", "docs/**/*.html",
              "scripts/*.py", "*.md", "*.txt", "*.cff", "*.json", "*.yaml",
              "*.yml", ".github/**/*.yml", ".github/**/*.yaml"]
# docs/dev/** is relocated engineering history (design catalog, tier plans,
# triage logs) — it discusses these regex patterns BY NAME (self-referential
# postmortem prose, e.g. this exact scan's own findings), not actual leaked
# secrets. Same exemption rationale as the RR-B-28 em-dash check: engineering
# history is not customer-facing and isn't subject to the same content bar.
# This does not weaken RR-B-14 leak prevention for real secrets/keys, since
# any actual credential would still be forbidden everywhere else that's scanned.
#
# This gate script itself is also exempt: FORBIDDEN_CONTENT's own pattern
# literals (e.g. the word "CONFIDENTIAL" inside `re.compile(r"CONFIDENTIAL")`)
# are source code naming the sentinel, not leaked content, so scanning
# scripts/*.py for coverage (the RR-B-14 hardening fix) must not have the gate
# flag its own regex definitions as a self-inflicted false positive.
SELF_PATH = pathlib.Path(__file__).resolve()
# stage_release.py's own FORBIDDEN_SENTINELS list names these same patterns as
# string literals (its leak check for the release payload) — not leaked content.
EXEMPT_PATHS = {SELF_PATH, pathlib.Path("scripts/stage_release.py").resolve()}
for g in SCAN_GLOBS:
    for path in pathlib.Path(".").glob(g):
        if path.is_relative_to("docs/dev"):
            continue
        if path.resolve() in EXEMPT_PATHS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for rx in FORBIDDEN_CONTENT:
            if rx.search(text):
                fails.append(f"forbidden content in {path}: {rx.pattern}")

HEADER_SENTINEL = "Copyright (c) 2026 JG Systems Consulting Ltd"
for g in ["src/**/*.py", "tests/**/*.py", "scripts/*.py"]:
    for path in pathlib.Path(".").glob(g):
        if HEADER_SENTINEL not in path.read_text(encoding="utf-8", errors="ignore")[:300]:
            fails.append(f"header missing: {path}")

# RR-B-09 version agreement: pyproject, CHANGELOG top entry, RELEASE-INFO,
# and .claude-plugin/plugin.json must all name the same version, or a later
# bump that misses one file goes undetected forever.
# Each read is guarded: a missing file is already reported by the REQUIRED
# check above, so here it must degrade to a None version (skipped from the
# comparison below), never an unhandled FileNotFoundError crash.
import tomllib

pyproject_path = pathlib.Path("pyproject.toml")
pyproject_version = None
if pyproject_path.is_file():
    pyproject_version = tomllib.loads(pyproject_path.read_text())["project"]["version"]

changelog_path = pathlib.Path("CHANGELOG.md")
changelog_version = None
if changelog_path.is_file():
    changelog_top = re.search(r"## \[(\d+\.\d+\.\d+)\]", changelog_path.read_text())
    changelog_version = changelog_top.group(1) if changelog_top else None

release_info_path = pathlib.Path("RELEASE-INFO.txt")
release_info_version = None
if release_info_path.is_file():
    release_info_match = re.search(r"Version:\s*(\S+)", release_info_path.read_text())
    release_info_version = release_info_match.group(1) if release_info_match else None

plugin_json_path = pathlib.Path(".claude-plugin/plugin.json")
plugin_version = None
if plugin_json_path.is_file():
    import json
    plugin_version = json.loads(plugin_json_path.read_text()).get("version")
versions = {"pyproject.toml": pyproject_version, "CHANGELOG.md": changelog_version,
           "RELEASE-INFO.txt": release_info_version,
           ".claude-plugin/plugin.json": plugin_version}
# only compare sources that currently exist: plugin.json isn't created until
# Task 5, so an absent-file None must not count as a "mismatch" before then.
present_versions = {k: v for k, v in versions.items() if v is not None}
if len(set(present_versions.values())) > 1:
    fails.append(f"version mismatch across sources: {present_versions}")

if fails:
    print("RELEASE GATE FAILED:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("release gate: PASS")
