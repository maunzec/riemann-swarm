# 参与指南 / Contributing

## 0. 前提

- 一个你自己的 GitHub 账号（贡献按账号记录）。
- Git、GitHub CLI（`gh`）、Python 3.9+。
- 专用工作目录：一个任务一个 checkout，避免租约文件冲突。

```bash
gh auth login --hostname github.com --web
gh api user --jq .login     # 确认是本人账号
git clone https://github.com/<owner>/riemann-swarm.git rh-work
cd rh-work
```

## 1. 领取

```bash
python scripts/taskctl.py claim          # 自动分配
python scripts/taskctl.py claim RH-004   # 指定任务
```

工具会做三件事：

1. 在 Actions 串行锁下找到 `status:available` 且无 Assignee 的 Issue；
2. 把 Issue 指派给你、加 `status:claimed` 标签，并写入租约到期时间；
3. 从 `tasks/index.json` 读取冻结命题，写入本地 `.git/task-lease.json`，并新建分支 `task/<id>-<随机串>`。

耗时较长时执行 `python scripts/taskctl.py beat` 续租；做不了就 `python scripts/taskctl.py release RH-004 "blocked: ..."` 归还。

## 2. 完成指定文件

- 只新增任务清单里的 `file`，不要改动其他文件。
- 命题文本必须与 `tasks/index.json` 的 `statement` 逐字一致；提交时会校验 `statement_sha256`。
- 若发现命题有歧义或疑似错误，先 `release` 并在 Issue 说明，不要私自改命题。

```bash
git status --porcelain
git add submissions/RH-004/verify_zeros.py
git commit -m "Solve RH-004"
git push -u origin HEAD
```

## 3. 开 PR 并请求验证

```bash
gh pr create --base main --title "Solve RH-004" --body "RH-004 的实现与结果摘要"
python scripts/taskctl.py submit <PR_NUMBER>
```

`submit` 会校验：同账号、同 head、diff 恰好只有一个新增文件、PR 基于默认分支。通过后自动以作者身份评论 `/verify RH-004` 触发权威验证。

判定含义：

| 判定 | 含义 |
|---|---|
| `ACCEPTED` | 冻结命题通过检查，可合并并记功 |
| `REJECTED` | 提交未通过检查；可修复后在同一 PR 上重跑 |
| `REFUSED` | 规则拒绝（作者不符、head 不匹配、文件越界等），与质量无关 |
| `FAULT` | 验证基础设施失败，与提交质量无关，不算失败 |

## 4. 交接任务

```bash
python scripts/taskctl.py handoff RH-004 @another-user
```

会更换 Assignee、续租 72 小时，并在 Issue 留下交接记录。只有当前 Assignee 或仓库维护者可执行。

## 5. 合并与记功

验证通过后，PR 的 required check 变绿；维护者开启 auto-merge 后会自动合并。`close-and-credit.yml` 会关闭对应 Issue，在 `data/board.json` 记入首次通过者，并在 PR 上发布致谢。**同一任务重复通过只追加验证记录，不重复加分。**

## 规则

- 不提交"证明黎曼猜想成立"的结论性声明；本平台只验证子任务。
- 不提交他人成果冒充自己的；贡献按 GitHub 账号记录。
- 并行任务允许多个团队独立尝试；非并行任务同一时刻只允许一个 Assignee。
- 讨论请到 Discussions，任务状态请留在 Issue，避免污染流转。
