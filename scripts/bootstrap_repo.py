#!/usr/bin/env python3
"""One-shot repository bootstrap: labels, milestones and task issues via gh CLI."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def gh(*args, check=True):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, cwd=ROOT)
    if check and p.returncode:
        print(f"warn: gh {' '.join(args[:3])} -> {p.stderr.strip()}", file=sys.stderr)
    return p.stdout.strip()


def parse_labels(text):
    out = []
    name = color = desc = None
    for line in text.splitlines() + ["- end"]:
        if line.startswith("- name:"):
            if name:
                out.append((name, color or "ededed", desc or ""))
            name, color, desc = line.split(":", 1)[1].strip(), None, None
        elif line.startswith("  color:"):
            color = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("  description:"):
            desc = line.split(":", 1)[1].strip()
    return out


labels_file = ROOT / ".github/labels.yml"
for name, color, desc in parse_labels(labels_file.read_text(encoding="utf-8")):
    gh("label", "create", name, "--color", color, "--description", desc, "--force")

repo = json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
registry = json.loads((ROOT / "tasks/index.json").read_text(encoding="utf-8"))

existing = json.loads(gh("issue", "list", "--state", "all", "--limit", "200", "--json", "title"))
titles = "\n".join(i["title"] for i in existing)

for key, title in registry["milestones"].items():
    gh("api", f"repos/{repo}/milestones", "-f", f"title={key} · {title}",
       "-f", "state=open", check=False)

for t in registry["tasks"]:
    if t["id"] in titles:
        print(f"skip existing issue {t['id']}")
        continue
    body = (
        f"**任务编号**：`{t['id']}`\n\n"
        f"**冻结命题**（逐字，SHA-256 `{t['statement_sha256']}`）：\n\n"
        f"```text\n{t['statement']}\n```\n\n"
        f"**指定文件**：`{t['file']}`\n\n"
        f"**验收**：{t['acceptance']}\n\n"
        f"**类型**：{t['type']} · **里程碑**：{t['milestone']} · "
        f"**并行**：{'是' if t['parallel'] else '否'}\n\n"
        f"**依赖**：{', '.join(t['depends_on']) or '无'}\n\n"
        "领取：在本 Issue 评论 `/claim`，或运行 `python scripts/taskctl.py claim "
        f"{t['id']}`。\n\n"
        "> 黎曼猜想尚未解决。本任务通过验证不代表 RH 成立。\n"
    )
    labels = ["status:available", f"type:{t['type']}"]
    if t["parallel"]:
        labels.append("parallel")
    gh("issue", "create", "--repo", repo, "--title", f"[{t['id']}] {t['title']}",
       "--body", body, "--label", ",".join(labels))
    print(f"created issue {t['id']}")
