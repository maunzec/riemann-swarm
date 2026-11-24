# Riemann Swarm · 黎曼猜想协作研究台

> **黎曼猜想尚未解决。** 本仓库把可独立审查的子命题拆成任务，用 GitHub 自带能力完成分发、领取、流转、提交、验证与记功。任何 `ACCEPTED` 只代表对应子任务的冻结命题通过检查，**不代表 RH 成立**。

[设计方案 docs/DESIGN.md](docs/DESIGN.md) · [参与指南 CONTRIBUTING.md](CONTRIBUTING.md) · [任务清单 tasks/index.json](tasks/index.json) · [公开看板（Pages）](index.html)

## 三步加入

```bash
# 1. 授权（用你自己的 GitHub 账号）
gh auth login --hostname github.com --web
gh auth status

# 2. 领取任务（自动选一条可领取任务，也可 claim RH-001）
python scripts/taskctl.py claim

# 3. 完成指定文件 → 开单文件 PR → 登记并请求验证
python scripts/taskctl.py submit <PR_NUMBER>
```

把 `join-zh.txt` 的内容粘贴给 Codex / Claude Code / Cursor，Agent 会按同样流程领取并提交。

## 机制一览

| 环节 | GitHub 载体 |
|---|---|
| 任务与状态 | Issue + Label（`status:available → claimed → in-review → done`） |
| 领取与租约 | `/claim` 评论 → Actions 全局串行锁 → Assignee + 到期评论 |
| 交接 / 归还 | `/handoff @user`、`/release <reason>`，超时自动回收 |
| 提交 | 只新增 `submissions/<task-id>/<file>` 的 Pull Request |
| 权威验证 | PR 作者评论 `/verify <task-id>` → `verify.yml`，判定 ACCEPTED / REJECTED / REFUSED / FAULT |
| 合并与记功 | required check 通过 → auto-merge → 关单 + 更新榜单 |
| 公开记录 | GitHub Pages（`index.html` + `data/board.json`）+ Actions 日志 + Git 历史 |

## 首个任务集

RH-001 形式化命题冻结 · RH-002 函数方程与对称性 · RH-003 显式公式接口 · RH-004 前 N 个零点数值复核 · RH-005 RH→素数对接口梳理 · RH-006 ψ(x) 误差界接口 · RH-007 与 Goldbach 研究台对接。

详见 [tasks/index.json](tasks/index.json)。

## 参考

- 强哥德巴赫猜想众包研究台：<https://www.movan.tech/goldbach/?lang=zh#records>
- 其开源实现：`CGandGameEngineLearner/goldbach-proofs`（本地副本 `goldbach-proofs-main`）
- Lean 上游：<https://github.com/leanprover-community/riemann-hypothesis>

Apache-2.0。
