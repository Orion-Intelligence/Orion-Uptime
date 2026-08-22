#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

REPO = "Orion-Intelligence/Orion-Uptime"
KEEP = {"Agentlinter", "Bandit", "CodeQL", "Eslint-8", "Jacksonlinter", "Markdownlint", "Opengrep", "Pmd", "Prospector", "Pylintpython3", "Scorecard", "Shellcheck", "Stylelint", "Trivy"}
TOKEN = os.environ.get("GITHUB_TOKEN") or sys.exit("set GITHUB_TOKEN (classic PAT with repo scope, or fine-grained with code scanning alerts: read/write)")
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"


def call(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def tool_name(analysis):
    return analysis["tool"]["name"].replace(" (reported by Codacy)", "")


analyses = []
page = 1
while True:
    batch = call(f"https://api.github.com/repos/{REPO}/code-scanning/analyses?per_page=100&page={page}")
    if not batch:
        break
    analyses.extend(batch)
    page += 1

by_category = {}
for analysis in analyses:
    if tool_name(analysis) in KEEP:
        continue
    by_category.setdefault((tool_name(analysis), analysis["category"]), []).append(analysis)

print(f"{len(analyses)} analyses total; {sum(len(v) for v in by_category.values())} belong to {len(by_category)} unwanted tool/category pairs")
for (tool, category), items in sorted(by_category.items()):
    print(f"  {tool:14} {category:40} {len(items)} analyses")

if DRY_RUN:
    print("\nDRY_RUN=1: nothing deleted. Re-run with DRY_RUN=0 to delete.")
    sys.exit(0)

for (tool, category), items in sorted(by_category.items()):
    latest = max(items, key=lambda a: a["created_at"])
    url = f"https://api.github.com/repos/{REPO}/code-scanning/analyses/{latest['id']}?confirm_delete"
    deleted = 0
    while url:
        result = call(url, method="DELETE")
        deleted += 1
        url = result.get("confirm_delete_url")
    print(f"deleted {deleted} analyses for {tool} / {category}")
