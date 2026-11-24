## 任务

- 任务编号：RH-___
- 冻结命题（逐字复制 tasks/index.json 的 statement）：

```
在此粘贴命题原文
```

## 改动

- [ ] 只新增 `tasks/index.json` 中指定的一个文件
- [ ] 基于默认分支，未改动其他文件
- [ ] 命题原文逐字出现在提交文件中

## 结果摘要

简述方法、依赖、仍未解决的开放引理。**不要写"已证明黎曼猜想"这类结论。**

## 验证

提交后由同一 GitHub 账号运行：

```bash
python scripts/taskctl.py submit <本 PR 编号>
```

它会自动评论 `/verify RH-___` 触发权威检查。判定见本 PR 评论与 Actions 运行。
