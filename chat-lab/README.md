# 对话实验室前端

面向家长的对话式 AI 前端应用，使用 Next.js App Router 搭建。前端通过本项目自己的 API 代理请求后端，真实 Coze 后端地址和 token 只放在服务端环境变量中，不暴露给浏览器。

## 技术栈

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4
- pnpm

## 本地启动

1. 安装依赖

```bash
corepack pnpm install
```

2. 创建本地环境变量

```bash
cp .env.local.example .env.local
```

然后在 `.env.local` 里填写真实后端配置：

```bash
COZE_API_BASE_URL=https://你的后端服务地址
COZE_API_TOKEN=你的后端 API Token
```

注意：`.env.local` 不能上传到代码仓库。

3. 启动开发环境

```bash
corepack pnpm dev
```

默认访问：

```text
http://localhost:5000
```

如果 5000 端口被占用，可以指定端口：

```bash
DEPLOY_RUN_PORT=5001 corepack pnpm dev
```

## 生产构建

```bash
corepack pnpm build
```

## 关键接口

浏览器只请求本项目自己的接口：

- `POST /api/chat`
- `POST /api/asr`
- `POST /api/tts`

这三个接口会在 Next.js 服务端读取：

- `COZE_API_BASE_URL`
- `COZE_API_TOKEN`

然后再转发到真实后端。这样公开部署时，浏览器看不到后端 token。

## 重要页面

- `/`：主聊天页
- `/community`：社区
- `/qa`：直答
- `/character`：人物
- `/english`：英语角
- `/schedule`：课表
- `/exam`：试卷分析

## 部署提醒

本项目不是纯静态站点，因为需要 `/api/chat`、`/api/asr`、`/api/tts` 服务端代理。部署平台必须支持 Next.js API Route 或服务端函数。

部署平台需要配置环境变量：

```bash
COZE_API_BASE_URL=https://你的后端服务地址
COZE_API_TOKEN=你的后端 API Token
```

不要把真实 token 写进 README、截图、聊天记录或公开仓库。
