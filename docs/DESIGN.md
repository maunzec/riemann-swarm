# 基于 GitHub 原生的分布式研究任务协作平台

> 参考对象：[强哥德巴赫猜想众包研究台](https://www.movan.tech/goldbach/?lang=zh#records) 与本地 `goldbach-proofs-main` 源码。
> 本文目标：总结一套**尽量只依赖 GitHub 自带能力**的任务分发 / 接取 / 流转 / 交接 / 验证 / 合并 / 记功体系，并以**黎曼猜想**作为首个落地任务集。

---

## 0. 结论先行

参考站的本质不是"一个漂亮网页"，而是五层结构：

| 层 | 哥德巴赫项目里的实现 | GitHub 原生等价物（本方案） |
|---|---|---|
| 任务清单 | `research/gaps.json`：冻结命题、指定文件、模块名、依赖、来源 | `tasks/index.json` + `tasks/<id>.md`，提交时校验 SHA-256 |
| 任务台 | `deploy/desk.py` + SQLite + `/api/desk/*`：租约、领取、续租、归还、登记 | **Issue + Label + Assignee + Issue Comment 命令**；Actions 执行状态变更 |
| 参与者 CLI | `tools/goldbach.py claim/beat/release/submit` | `scripts/taskctl.py claim/handoff/release/submit`（仅依赖 `gh` CLI） |
| 权威验证 | `.github/workflows/authoritative.yml`：只取 PR 中一个 Lean 文件的字节，隔离编译，返回 ACCEPTED/REJECTED/REFUSED/FAULT | `.github/workflows/verify.yml`：同样只取白名单文件字节，跑项目自带 checker，结果写入 PR 评论 + `data/verdicts.jsonl` |
| 公开层 | 站点 + 贡献榜 + Actions 日志 + HMAC 回传 | **GitHub Pages**（`index.html` + `data/board.json`）+ Actions 日志 + Issue/PR 历史；无需自建服务器 |

一句话：**把"任务台"换成 Issue，把"租约"换成 Assignee + 时限评论，把"权威验证"换成带并发锁和最小权限的 Actions，把"公开记录"换成 Pages + 不可变的 Git 历史。**

---

## 1. 参考项目到底怎么跑的（拆解）

从 `goldbach-proofs-main` 读到的关键事实：

1. **领取有租约**：`tools/goldbach.py claim` 调用研究台 `/api/desk/claim`，返回 `gap`（冻结命题）+ `lease`（含 token、到期时间）。本地写入 `.git/goldbach-lease.json`，并新建 `goldbach/<gap-id>/<随机串>` 分支。`beat` 续租，`release` 归还。
2. **命题是冻结的**：领取后本地会逐字段比对 `id/file/module/statement/imports` 与仓库 `research/gaps.json`；不一致立即释放租约并报错。这是防止"任务描述被偷偷改掉"的关键。
3. **提交只 accept 一个文件**：`submit` 校验分支相对 base 的 diff 必须恰好是 `A <指定文件>`，PR 必须属于领取账号、基于默认分支、只改 1 个文件。
4. **验证由 PR 作者触发**：作者评论 `/goldbach-check <gap-id>`，`authoritative.yml` 校验评论者 == PR 作者，才调用研究台 `/authorize` 做租约授权（HMAC-SHA256 签名，绑定 PR/head/handle/gap/statement hash）。
5. **验证是敌意输入处理**：workflow 不 checkout fork；通过 API 按 blob hash 下载**那一个文件**的字节；语句来自 base 分支的清单而非 PR；编译在受限账号、无网络、内存/时间上限、`outsider` 用户下运行；信任文件前后做 SHA-256 比对，防篡改。判定有四种：`ACCEPTED / REJECTED / REFUSED / FAULT`，只有前两者代表对证明的结论。
6. **队列补偿**：`desk-queue.yml` 每 5 分钟轮询研究台 `/pending`，复核 PR 当前 head、作者、评论后再派发同一个验证 workflow，避免评论事件丢失导致任务卡住。
7. **可并行**：普通账号同时 1 条租约；持团队凭证的 controller 可同时持 128 条，每个助手独立 checkout、独立 PR。难题支持多团队并行尝试。
8. **记功**：结果由 Actions 签名回传研究台，SQLite 按 run_id/run_attempt 去重；榜单只统计"绑定到 GitHub 账号 + 首次通过的不同引理"。

**可复用的设计原则**（比具体代码更重要）：冻结命题 → 租约 → 单文件提交 → 作者触发 → 沙箱验证 → 幂等回传 → 首次通过记功。

---

## 2. GitHub 原生方案：对象映射与状态机

### 2.1 对象映射

| 概念 | GitHub 载体 | 说明 |
|---|---|---|
| 研究问题 | **Milestone** | 如 `RH · 零点与显式公式` |
| 研究路线 | **Label** `route/*` | 对应哥德巴赫的四条路线 |
| 一条任务 | **Issue** + `tasks/index.json` | Issue 是协作入口；JSON 是冻结命题的唯一真源 |
| 任务状态 | **Label** `status:available / claimed / in-review / done / blocked` | 看板按 label 分列 |
| 任务领取 | **Assignee** + 评论 `/claim` | Assignee 显示"谁在做"，评论留痕 |
| 租约到期 | 领取时自动评论 `LEASE ... expires_at` | 由 Actions 检查并自动 `/release` 超时任务 |
| 提交物 | **Pull Request** | 只新增 `submissions/<task-id>/<file>` |
| 权威验证 | **Issue Comment 命令** + `verify.yml` | `/verify <task-id>` 仅 PR 作者有效 |
| 判定记录 | PR 评论 + `data/verdicts.jsonl` | JSONL 追加，Git 历史即审计日志 |
| 任务交接 | 评论 `/handoff @user` | 自动改 Assignee、续租、留交接说明 |
| 流转 / 合并 | `verify.yml` 通过后 required check 变绿 → auto-merge | 合并后 `close-and-credit.yml` 关闭 Issue、更新榜单 |
| 公开看板 | **GitHub Pages** | `index.html` 读取 Actions 生成的 `data/board.json` |
| 讨论答疑 | **Discussions** | 与 Issue 分离，避免污染任务流 |
| 版本发布 | **Release** | 每个阶段（如"RH 数值零点复核完成"）打 tag |

### 2.2 状态机

```text
                 /claim (Actions 全局串行锁)
[available] ───────────────────────────▶ [claimed] (Assignee=领取人, 租约 72h)
     ▲                                      │
     │ /release 或超时自动回收                │ /handoff @user
     │                                      ▼
     └──────────────────────────── [claimed] (新 Assignee, 续租)
                                            │ 提交单文件 PR + /verify <id>
                                            ▼
                                      [in-review]
                                            │ ACCEPTED / REJECTED
                          ┌─────────────────┴─────────────────┐
                          ▼                                   ▼
                    [done] + auto-merge                  [available] 重开
                    记功 / 榜单                          （附失败评论与运行链接）
```

关键约束：

- **一个任务同一时刻只能有一个 Assignee**（独占任务）；标注 `parallel: true` 的任务允许多个团队独立尝试，用 `parallel/<task-id>/<handle>` 分支区分。
- **验证触发者必须是 PR 作者**，避免他人替不合格提交"刷验证"。
- **判定绑定到 head SHA + 冻结命题哈希**；PR head 变化后旧判定自动作废。
- **首次通过才记功**，重复通过只追加验证记录，不重复加分。

---

## 3. 为什么"自动领取"在 GitHub 上需要特别处理

GitHub 没有原生的原子 `pop()` 操作。两个 Agent 同时评论 `/claim` 时，可能都读到同一个 `status:available` Issue。本方案用三层防护：

1. **Actions 全局串行锁**：`claim.yml` 设置 `concurrency: group: task-claims, cancel-in-progress: false`。GitHub 会保证同一 group 同一时刻只跑一个 job，等价于分布式互斥锁。
2. **job 内二次校验**：拿到锁后重新读取 Issue 列表，只选 `status:available` 且**无 Assignee** 的最早 Issue；若已被领取则重新挑选。
3. **写回即声明**：先 `gh issue edit --add-assignee` 与 `--add-label status:claimed`，再写租约评论；任一步失败则回滚 label 并释放。

> 局限：`concurrency` 是 workflow 级别的，跨 fork / 跨仓库不共享。若允许任意 fork 触发领取，需要把领取入口固定在本仓库的 `workflow_dispatch` 或 `issue_comment`，并限制 `permissions: issues: write, contents: read`。

---

## 4. 参与者路径（人 / Agent 通用）

```bash
# 0) 一次性授权（参与者自己的 GitHub 账号）
gh auth login --hostname github.com --web
gh auth status

# 1) 领取（自动选一条可领取任务，也可指定 RH-001）
python scripts/taskctl.py claim            # 或 claim RH-001

# 2) 在指定文件里完成工作，只提交该文件
git add submissions/RH-001/statement.lean
git commit -m "Solve RH-001"

# 3) 推分支、开 PR（只改一个文件、基于默认分支）
git push -u origin HEAD
gh pr create --base main --title "Solve RH-001" --body "任务 RH-001 的证明/实现"

# 4) 登记并请求验证：校验账号、head、diff 后自动评论 /verify RH-001
python scripts/taskctl.py submit <PR_NUMBER>

# 5) 等待判定：PR 评论 + Actions 日志 + Pages 看板
gh run watch <RUN_ID> --exit-status
```

交接与放弃：

```bash
python scripts/taskctl.py handoff RH-001 @another-user
python scripts/taskctl.py release RH-001 "blocked: need functional equation"
```

给 Agent 的一行提示词见 `join-zh.txt`。

---

## 5. 验证工作流设计要点（借鉴权威验证的安全模型）

`verify.yml` 的最小安全集合：

- **不 checkout PR 分支的任意代码**：用 API 读取 PR 元数据和 `git/trees/<head>?recursive=1`，只下载白名单文件的 blob 字节。
- **输入校验**：PR number 必须纯数字；task id 必须匹配 `^RH-[0-9]{3}$`；目标文件必须在冻结清单里；文件大小上限（如 512 KiB）。
- **只信任 base 分支的命题**：`tasks/index.json` 从 `GITHUB_SHA`（默认分支）读取，计算 `statement_sha256`，与登记值比对。
- **最小权限**：`permissions: contents: read, pull-requests: read, issues: read`；需要评论时用单独 job 且只给 `issues: write`。
- **判定四态**：`ACCEPTED / REJECTED / REFUSED / FAULT`。`FAULT` 明确表示"验证基础设施失败，与提交质量无关"，不记功也不扣分。
- **幂等回传**：以 `run_id + run_attempt + head_sha` 为唯一键写 JSONL，重复运行不重复计榜。
- **超时与隔离**：给 checker 设 `timeout-minutes`；若任务类型需要执行不可信代码，参考权威验证用独立低权限用户 + 无网络 + 内存上限。
- **required check**：在 Branch protection 里把 `verify` 设为必需，配合 `allow_auto_merge`，才能做到"验证通过即合并"。

---

## 6. 仓库骨架

```text
riemann-swarm/
├── README.md                     项目首页 / 参与入口
├── CONTRIBUTING.md               完整参与指南
├── join-zh.txt                   复制给 Agent 的提示词
├── tasks/index.json              冻结任务清单（唯一真源）
├── submissions/                  参与者提交（按任务分目录）
├── data/
│   ├── board.json                Pages 看板数据（Actions 生成）
│   └── verdicts.jsonl            判定追加日志（Actions 生成）
├── docs/DESIGN.md                本文
├── index.html                    GitHub Pages 看板
├── scripts/
│   ├── taskctl.py                领取 / 交接 / 归还 / 登记
│   ├── verify_task.py            通用 checker（按任务配置执行命令）
│   ├── sync_board.py             从 GitHub API 重建 board.json
│   └── bootstrap_repo.py         初始化 label / milestone / issue
└── .github/
    ├── ISSUE_TEMPLATE/task.yml   任务 Issue 表单
    ├── PULL_REQUEST_TEMPLATE.md
    ├── labels.yml                label 定义
    └── workflows/
        ├── claim.yml             自动领取（全局串行锁）
        ├── handoff.yml           流转 / 交接 / 超时回收
        ├── verify.yml            权威验证
        ├── close-and-credit.yml  合并后关单 + 记功
        └── sync-board.yml        定时刷新 Pages 看板
```

---

## 7. 与参考站的对比与取舍

| 维度 | movan.tech 研究台 | 本方案（GitHub-only） | 混合方案（建议演进） |
|---|---|---|---|
| 部署成本 | 需服务器、SQLite、nginx、systemd、OAuth | 0，仓库即平台 | 仓库 + 可选静态站 |
| 任务分配 | 租约 token + SQLite，强一致 | Issue Assignee + Actions 串行锁，最终一致 | 保留 GitHub 入口，外部 DB 做强一致租约 |
| 身份 | GitHub 账号（领取/提交）+ 可选知乎署名 | GitHub 账号，天然 | 同左 |
| 提交 | 单文件 PR | 单文件 PR | 同左 |
| 验证 | 自建 Lean sandbox，ACCEPTED 四态 | Actions + 项目 checker，同四态 | 复用参考站的权威验证端点（HMAC） |
| 公开记录 | 自定义网页 + 榜单 | Pages + Git 历史 | Pages 聚合两边 |
| 并发规模 | 128 租约 / 团队凭证 | 受 Actions 并发与 API 限流约束 | 团队凭证思路可移植 |
| 最适合 | 需要强一致租约与复杂统计 | 快速启动、零运维、 fully auditable | 大规模长期项目 |

**建议**：先用 GitHub-only 跑通流程；当任务数 > 200 或需要严格租约语义时，再把 `desk.py` 那套租约服务接回来，GitHub 仍作为身份与提交层。

---

## 8. 首个任务集：黎曼猜想（RH）

> 重要声明：**黎曼猜想仍是未解决问题**。本任务集不宣称已完成证明，只把可独立审查的子命题、数值复核和文献梳理拆成可验证任务；任何 `ACCEPTED` 只代表"该子任务的冻结命题通过检查"，不代表 RH 成立。

任务清单见 `tasks/index.json`，摘要：

| ID | 类型 | 任务 | 验收方式 | 依赖 |
|---|---|---|---|---|
| RH-001 | formal | 在 Lean 4 中冻结 RH 命题：非平凡零点实部为 1/2（先给出可编译的定义与命题，不要求证明） | Lean 编译 + 命题 SHA-256 匹配 | — |
| RH-002 | formal | zeta 函数函数方程的形式化表述与临界线对称性引理 | Lean 编译 | RH-001 |
| RH-003 | formal | 显式公式：零点求和与 Chebyshev ψ 函数误差项的接口命题 | Lean 编译 | RH-001 |
| RH-004 | numeric | 计算前 N 个 zeta 零点的虚部并检验是否落在临界线（可复现脚本 + 固定随机种子） | pytest + 输出哈希 | — |
| RH-005 | survey | 梳理"RH 误差界 → 素数分布 → 哥德巴赫素数对计数"的接口，产出结构化笔记 | Markdown 结构校验 + 引用可访问性 | — |
| RH-006 | formal | 从 RH 推导 ψ(x) = x + O(sqrt(x) log²x) 的形式化接口（允许作为开放引理登记） | Lean 编译 + 开放引理清单 | RH-003 |
| RH-007 | bridge | 与 Goldbach 研究台对接：把 RH-006 的误差界注册为素数对计数任务的输入 | JSON schema 校验 + 交叉引用 | RH-006 |

每个任务在 `tasks/index.json` 中都有 `id / title / type / statement / statement_sha256 / file / checker / acceptance / parallel / depends_on / milestone`，领取后本地会逐字段复核。

---

## 9. 落地发布记录

本仓库已按上述骨架创建并尝试发布到 GitHub。发布方式：使用本机已保存的 GitHub 凭据，通过 REST API 创建仓库、写入文件、建立 label / milestone / Issue，并启用 Pages 与 auto-merge。执行细节见最终交付说明；若网络或权限导致部分步骤失败，仓库内 `scripts/bootstrap_repo.py` 可补齐后续初始化。

---

## 10. 风险与限制

1. **Actions 并发与限流**：全局串行锁保证正确性但牺牲吞吐；大量领取时可改为分片锁 `group: task-claims-<route>`。
2. **Comment 命令的安全边界**：任何能评论的人都能触发 workflow，必须在 job 的 `if` 里校验 `comment.user.login == issue.user.login` 或 `author_association`，并限制 `permissions`。
3. **不可信代码**：若 checker 执行提交者代码，必须按参考站思路做隔离；本模板默认只执行仓库自带 checker，不执行提交文件内容。
4. **Pages 数据新鲜度**：看板由 Actions 定时生成，存在分钟级延迟；需要实时性时应接外部服务。
5. **GitHub 不是数据库**：Issue 状态可被手工改动；审计依赖 Git 历史与受保护分支，重要仓库应开启 branch protection 与 audit log。
6. **数学正确性**：自动化只能验证形式化命题与代码，**不能判断数学洞见是否真实**；人工 review 仍不可替代。
