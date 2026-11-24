#!/usr/bin/env python3
"""Rebuild the public board from GitHub Issues/PRs and the verdict ledger."""
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "maunzec/riemann-swarm")


def gh_json(*args):
    return json.loads(subprocess.check_output(["gh", *args], text=True))


registry = json.loads(Path("tasks/index.json").read_text(encoding="utf-8"))
verdicts = []
ledger = Path("data/verdicts.jsonl")
if ledger.exists():
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                verdicts.append(json.loads(line))
            except ValueError:
                pass

issues = gh_json("issue", "list", "--state", "all", "--limit", "200",
                 "--json", "number,title,state,labels,assignees,html_url")
first_by_task = {}
for v in sorted(verdicts, key=lambda x: (x.get("run_id", 0), x.get("run_attempt", 1))):
    if v.get("verdict") == "ACCEPTED" and v.get("task") and v["task"] not in first_by_task:
        first_by_task[v["task"]] = {"author": v.get("author", ""), "pr": v.get("pr"), "url": v.get("pr_url")}

rows = []
for t in registry["tasks"]:
    issue = next((i for i in issues if t["id"] in i["title"]), None)
    accepted = first_by_task.get(t["id"])
    labels = [l["name"] for l in issue.get("labels", [])] if issue else []
    status = "done" if accepted else (
        "in-review" if "status:in-review" in labels else (
            "claimed" if "status:claimed" in labels else (
                "blocked" if "status:blocked" in labels else "available")))
    history = [v for v in verdicts if v.get("task") == t["id"]]
    rows.append({
        "id": t["id"], "title": t["title"], "type": t["type"], "milestone": t["milestone"],
        "status": status, "parallel": t["parallel"],
        "assignees": [a["login"] for a in (issue or {}).get("assignees", [])],
        "issue_url": (issue or {}).get("html_url"),
        "winner": accepted,
        "verdicts": [{"verdict": v["verdict"], "run_url": v.get("run_url"),
                      "pr": v.get("pr"), "checked_at": v.get("checked_at")} for v in history[-10:]],
    })

leaders = {}
for task_id, info in first_by_task.items():
    name = info["author"].casefold()
    entry = leaders.setdefault(name, {"login": info["author"], "tasks": []})
    entry["tasks"].append(task_id)
leaderboard = sorted(leaders.values(), key=lambda x: -len(x["tasks"]))

board = {
    "project": "riemann-swarm",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "disclaimer": registry["disclaimer"],
    "summary": {
        "tasks": len(rows),
        "done": sum(r["status"] == "done" for r in rows),
        "claimed": sum(r["status"] == "claimed" for r in rows),
        "verdicts": len(verdicts),
    },
    "tasks": rows,
    "leaderboard": leaderboard,
    "repo_url": f"https://github.com/{REPO}",
}
out = Path("data/board.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}: {board['summary']}")
