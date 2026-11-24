#!/usr/bin/env python3
"""Verify one submitted file against a frozen task. Never executes PR-supplied code.

The pull request is read through the GitHub API. Only the bytes of the single
allow-listed blob are downloaded; the fork is never checked out. The frozen
statement always comes from the default branch of this repository.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TASK_ID = re.compile(r"^RH-\d{3}$")


class Refused(Exception):
    pass


def gh(*args, timeout=30):
    return subprocess.check_output(["gh", *args], text=True, timeout=timeout).strip()


def api(path, repo):
    return json.loads(gh("api", f"repos/{repo}{path}"))


def blob_sha1(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode() + b"\0")
    h.update(data)
    return h.hexdigest()


def run_checker(task, target: Path):
    kind = task["checker"]
    if kind == "pytest":
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", str(target.parent)],
                              capture_output=True, text=True, timeout=600)
        ok = proc.returncode == 0
        return ok, (proc.stdout + proc.stderr)[-12000:], "pytest"
    if kind == "json":
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception as e:
            return False, str(e), "json"
        needed = {"source_task", "error_term", "quantifiers", "target_task"}
        missing = sorted(needed - set(data))
        return not missing, f"missing keys: {missing}" if missing else "schema ok", "json"
    if kind == "markdown":
        text = target.read_text(encoding="utf-8")
        headings = len(re.findall(r"^#{1,4} ", text, re.M))
        links = len(re.findall(r"https?://", text))
        ok = headings >= 6 and links >= 6 and task["statement"][:20] in text
        return ok, f"headings={headings} links={links}", "markdown"
    if kind == "lean":
        lean = shutil.which("lean")
        if not lean:
            return None, "Lean toolchain unavailable on this runner; use a self-hosted runner with Lean 4 + Mathlib.", "lean"
        proc = subprocess.run([lean, str(target)], capture_output=True, text=True, timeout=900)
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-12000:], "lean"
    return None, f"unknown checker: {kind}", "none"


def build(args):
    repo = args.repo
    pr = int(args.pr)
    if not 1 <= pr <= 9_999_999:
        raise Refused("invalid PR number")

    if args.body:
        m = re.fullmatch(r"/verify\s+(RH-\d{3})", args.body.strip())
        if not m:
            raise Refused("use /verify RH-001")
        task_id = m.group(1)
    else:
        task_id = args.task
    if not TASK_ID.fullmatch(task_id or ""):
        raise Refused("task id must look like RH-001")

    pull = api(f"/pulls/{pr}", repo)
    author = pull["user"]["login"]
    if pull["state"] != "open":
        raise Refused("pull request is closed")
    if args.commenter and args.commenter.casefold() != author.casefold():
        raise Refused("only the PR author can request verification")
    if pull["base"]["ref"] != args.default_branch:
        raise Refused(f"PR must target {args.default_branch}")
    if pull["changed_files"] != 1:
        raise Refused("PR must change exactly one file")
    head = pull["head"]["sha"]

    files = api(f"/pulls/{pr}/files?per_page=100", repo)
    if len(files) != 1 or files[0]["status"] != "added":
        raise Refused("PR must add exactly one new file")
    rel = files[0]["filename"]
    blob = files[0]["sha"]

    registry = json.loads(Path("tasks/index.json").read_text(encoding="utf-8"))
    task = next((t for t in registry["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise Refused(f"unknown task {task_id}")
    if rel != task["file"]:
        raise Refused(f"file must be {task['file']}")
    statement_sha = hashlib.sha256(task["statement"].encode("utf-8")).hexdigest()
    if statement_sha != task["statement_sha256"]:
        raise Refused("frozen statement hash mismatch in the registry")

    tree = api(f"/git/trees/{head}?recursive=1", repo)
    node = next((n for n in tree.get("tree", []) if n["path"] == rel), None)
    if not node or node.get("type") != "blob" or node.get("mode") not in ("100644", "100755"):
        raise Refused("submitted path is not a regular file")

    content = base64.b64decode(api(f"/git/blobs/{blob}", repo)["content"])
    if len(content) > 512 * 1024:
        raise Refused("file exceeds 512 KiB")
    if blob_sha1(content) != blob:
        raise Refused("downloaded bytes do not match the PR blob")
    target = Path("verify_work") / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    text = content.decode("utf-8", "replace")
    if task["statement"].strip() not in re.sub(r"\s+", " ", text):
        return task, head, statement_sha, "REJECTED", "冻结命题原文未逐字出现在提交文件中。", rel, blob, author

    ok, detail, kind = run_checker(task, target)
    if ok is None:
        verdict = "FAULT"
    else:
        verdict = "ACCEPTED" if ok else "REJECTED"
    return task, head, statement_sha, verdict, f"checker={kind}\n{detail}", rel, blob, author


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pr", required=True)
    p.add_argument("--task", default="")
    p.add_argument("--body", default="")
    p.add_argument("--commenter", default="")
    p.add_argument("--repo", required=True)
    p.add_argument("--default-branch", default="main")
    p.add_argument("--out", default="verdict.json")
    args = p.parse_args()

    run_id = os.environ.get("GITHUB_RUN_ID", "0")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    repo_url = f"https://github.com/{args.repo}"
    base = {
        "pr": int(args.pr), "run_id": int(run_id), "run_attempt": int(run_attempt),
        "run_url": f"{repo_url}/actions/runs/{run_id}",
        "pr_url": f"{repo_url}/pull/{args.pr}",
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "task": "", "head": "", "statement_sha256": "", "file": "", "file_sha256": "",
        "author": "", "verdict": "FAULT", "detail": "",
    }
    try:
        task, head, ssha, verdict, detail, rel, blob, author = build(args)
        base.update(task=task["id"], head=head, statement_sha256=ssha,
                    verdict=verdict, detail=detail, file=rel, file_sha256=blob, author=author)
    except Refused as e:
        base.update(verdict="REFUSED", detail=str(e))
    except Exception as e:  # infrastructure failure, never a statement about the proof
        base.update(verdict="FAULT", detail=f"{type(e).__name__}: {e}")
    Path(args.out).write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: {base['verdict']} task={base['task']} pr={base['pr']}")
    print(base["detail"][:4000])
    return 0 if base["verdict"] == "ACCEPTED" else (1 if base["verdict"] == "REJECTED" else 2)


if __name__ == "__main__":
    sys.exit(main())
