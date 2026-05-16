# 部署说明

## 部署前确认

1. 代码已经上传到 Git 仓库。
2. `.env.local` 没有上传。
3. 生产平台已经配置环境变量：

```bash
COZE_API_BASE_URL=https://你的后端服务地址
COZE_API_TOKEN=你的后端 API Token
```

4. 本地构建可以通过：

```bash
corepack pnpm build
```

## 为什么不能纯静态部署

当前前端需要三个服务端代理接口：

- `/api/chat`
- `/api/asr`
- `/api/tts`

这些接口的作用是保护后端 token。浏览器请求自己的前端服务，前端服务端再带 token 请求 Coze 后端。

所以部署平台需要支持 Next.js 服务端能力，不能只上传静态 HTML。

## 上线后的检查

上线后按顺序检查：

1. 打开首页。
2. 发送一条文字消息，确认 AI 可以流式回复。
3. 看诊断卡是否能弹出。
4. 测试语音输入。
5. 打开浏览器开发者工具，确认请求里看不到真实 `COZE_API_TOKEN`。

## 后端冷启动

如果后端部署在 Coze devbox 这类会自动休眠的环境，第一次请求可能返回 `instance_not_found`、502、503 或等待较久。本项目的 `/api/chat`、`/api/asr`、`/api/tts` 代理层会自动做短暂重试。

可以用环境变量调整重试次数：

```bash
COZE_COLD_START_RETRIES=4
```

这只能改善用户第一次访问时的体验，不能替代稳定的生产后端。正式公开发布时，建议把后端部署到支持常驻实例、最小实例数或定时保活的平台。

## 域名记录

等部署平台生成访问地址后，再去 DNSPod 添加解析记录。常见方式是：

```text
主机记录：www 或 chat
记录类型：CNAME
记录值：部署平台给你的 CNAME 地址
```

根域名 `yihe.site` 是否能直接 CNAME，要看部署平台和 DNSPod 的支持方式。
