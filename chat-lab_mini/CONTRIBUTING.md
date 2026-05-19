# 协作说明

这份文档给参与前端开发的同学看。目标是让多人一起改代码时不混乱。

## 基本原则

- 不要直接把代码压缩包发来发去。
- 所有人都从同一个 Git 仓库获取代码。
- 不要直接改 `main` 分支。
- 每个功能或修复单独开一个分支。
- 改完后提交合并请求，由负责人确认后再合入 `main`。
- `.env.local`、token、密钥不能提交到仓库。

## 推荐分支命名

```text
feature/功能名
fix/问题名
chore/维护事项
```

例子：

```text
feature/diagnosis-tabs
fix/mobile-input-bar
chore/update-readme
```

## 开发流程

1. 拉取最新代码

```bash
git pull
```

2. 新建自己的分支

```bash
git checkout -b feature/你的功能名
```

3. 本地启动并修改

```bash
corepack pnpm dev
```

4. 修改完成后先构建检查

```bash
corepack pnpm build
```

5. 提交代码

```bash
git add .
git commit -m "feat: 描述你做了什么"
git push
```

6. 在 Gitee / GitHub 上发起 Pull Request / Merge Request。

## 提交信息建议

常用格式：

```text
feat: 新功能
fix: 修复问题
style: 样式调整
refactor: 代码重构
docs: 文档修改
chore: 工程配置或杂项
```

例子：

```text
fix: improve diagnosis reply parsing
style: polish mobile chat layout
docs: add deployment notes
```

## 提交前检查

提交前至少确认：

- 页面能正常打开。
- 聊天流式回复正常。
- 诊断卡能正常弹出。
- 没有把 `.env.local` 或 token 提交上来。
- `corepack pnpm build` 能通过。

## 负责人合并前检查

合并到 `main` 前建议看：

- 改动是否和需求一致。
- 是否影响主聊天链路。
- 是否影响 SSE 流式输出。
- 是否影响诊断卡结构化渲染。
- 是否新增了公开密钥或敏感信息。

`main` 分支应该始终保持可部署状态。
