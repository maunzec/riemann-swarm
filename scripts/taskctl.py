#!/usr/bin/env python3
"""Claim, hand off, release and submit research tasks using only the GitHub CLI."""
import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TASK_ID = re.compile(r"^RH-\d{3}$")


def gh(*args, check=True):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and p.returncode:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def login():
    return gh("api", "user", "--jq", ".login")


def lease_path():
    git_dir = subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], text=True).strip()
    return Path(git_dir) / "task-lease.json"


def load_lease():
    path = lease_path()
    if not path.exists():
        raise SystemExit("no lease in this checkout; run `taskctl.py claim` first")
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, state):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".task-lease-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def available_issues():
    return json.loads(gh("issue", "list", "--state", "open", "--limit", "100",
                         "--label", "status:available",
                         "--json", "number,title,labels,assignees"))


def registry():
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    return json.loads(subprocess.check_output(
        ["git", "show", f"{base}:tasks/index.json"], text=True)), base


def claim(task_id=None):
    path = lease_path()
    if path.exists():
        raise SystemExit("this checkout already holds a task; finish or release it first")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], text=True).strip():
        raise SystemExit("use a clean dedicated checkout")
    if task_id and not TASK_ID.fullmatch(task_id):
        raise SystemExit("task id must look like RH-001")

    issues = [i for i in available_issues() if not i.get("assignees")]
    if task_id:
        issues = [i for i in issues if task_id in i["title"]]
    if not issues:
        raise SystemExit("no available task matches the request")
    issue = issues[0]

    gh("issue", "comment", str(issue["number"]),
       "--body", f"/claim {task_id}" if task_id else "/claim")
    handle = login()
    deadline = time.time() + 120
    assigned = False
    while time.time() < deadline:
        view = json.loads(gh("issue", "view", str(issue["number"]),
                             "--json", "assignees,labels"))
        names = {a["login"].casefold() for a in view.get("assignees", [])}
        labels = {l["name"] for l in view.get("labels", [])}
        if handle.casefold() in names and "status:claimed" in labels:
            assigned = True
            break
        time.sleep(3)
    if not assigned:
        raise SystemExit("claim did not complete; check the issue comments and Actions run")

    tasks, base = registry()
    match = re.search(r"RH-\d{3}", issue["title"])
    if not match:
        raise SystemExit("task issue has no RH id in its title")
    real_id = match.group(0)
    task = next((t for t in tasks["tasks"] if t["id"] == real_id), None)
    if not task:
        raise SystemExit("task missing from tasks/index.json")
    sha = hashlib.sha256(task["statement"].encode("utf-8")).hexdigest()
    if sha != task["statement_sha256"]:
        raise SystemExit("frozen statement hash mismatch; refresh the checkout")

    branch = f"task/{real_id.lower()}-{secrets.token_hex(4)}"
    state = {
        "task": real_id, "issue": issue["number"], "handle": handle,
        "branch": branch, "base": base, "file": task["file"],
        "claimed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    save(path, state)
    subprocess.run(["git", "switch", "-c", branch], check=True)
    print(json.dumps({"task": real_id, "issue_url": issue.get("html_url"),
                      "branch": branch, "file": task["file"],
                      "statement": task["statement"]}, ensure_ascii=False, indent=2))


def issue_comment_from_lease(args):
    lease = load_lease()
    body = {"beat": "/beat", "release": "/release " + (args.reason or "abandoned")}.get(
        args.action, "")
    if args.action == "handoff":
        target = (args.target or "").lstrip("@")
        if not target or (args.task and args.task != lease["task"]):
            raise SystemExit("usage: handoff <TASK_ID> @handle")
        body = f"/handoff @{target}"
    gh("issue", "comment", str(lease["issue"]), "--body", body)
    print(f"{args.action}: {body}")


def submit(pr):
    lease = load_lease()
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    if branch != lease["branch"]:
        raise SystemExit(f"switch to task branch {lease['branch']} first")
    if login().casefold() != lease["handle"].casefold():
        raise SystemExit("use the same GitHub account that claimed the task")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], text=True).strip():
        raise SystemExit("commit the submission file and leave the checkout clean")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    diff = subprocess.check_output(["git", "diff", "--name-status", "-z", lease["base"], head], text=True)
    if diff != "A\0" + lease["file"] + "\0":
        raise SystemExit(f"branch must add exactly {lease['file']}")

    pull = json.loads(gh("api", f"pulls/{pr}"))
    if (pull["state"] != "open"
            or pull["user"]["login"].casefold() != lease["handle"].casefold()
            or pull["head"]["sha"] != head
            or pull["changed_files"] != 1
            or pull["base"]["ref"] != pull["base"]["repo"]["default_branch"]):
        raise SystemExit("PR must be yours, open, based on default branch, and match your head")
    gh("pr", "comment", str(pr), "--body", f"/verify {lease['task']}")
    print(f"requested verification for {lease['task']} on PR #{pr}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    c = sub.add_parser("claim", help="claim an available task")
    c.add_argument("task", nargs="?")
    sub.add_parser("beat", help="renew the lease")
    r = sub.add_parser("release", help="return the task")
    r.add_argument("reason", nargs="?", default="abandoned")
    h = sub.add_parser("handoff", help="hand the task to another account")
    h.add_argument("task")
    h.add_argument("target")
    s = sub.add_parser("submit", help="register PR and request verification")
    s.add_argument("pr", type=int)
    args = p.parse_args()
    if args.action == "claim":
        claim(args.task)
    elif args.action == "submit":
        submit(args.pr)
    else:
        issue_comment_from_lease(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
