# ChatLab 跨局域网部署指南（cpolar 方案）

> 适用场景：Ubuntu 内网服务器、无公网 IP、临时演示/测试、零客户端访问

---

## 一、核心架构

本项目采用 **"单入口"** 暴露策略：只需要把 Next.js 前端（端口 5000）暴露到公网，所有后端调用由 Next.js **服务端路由** 内部转发。

```
公网用户浏览器
        │
        ▼
[cpolar 公网 URL] ──► Ubuntu :5000 (Next.js 前端)
                              │
                              ├── /api/v1/chat ──► localhost:8000/8001 ──► FastAPI 后端
                              └── /api/asr ──► COZE_API_BASE_URL ──► Coze 远程 API
```

**关键优势**：浏览器从不直接访问后端 8000/8001，因此 `.env.local` 中的 `localhost:8000/8001` 完全无需修改。

---

## 二、Ubuntu 环境准备

```bash
# 1. 更新系统
sudo apt update && sudo apt upgrade -y

# 2. 安装 Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# 3. 安装 Python 3 + pip
sudo apt install -y python3 python3-pip python3-venv

# 4. 安装 pnpm
sudo npm install -g pnpm

# 5. 确认版本
node -v       # v22.x
python3 --version
pnpm -v
```

---

## 三、上传代码

在 WSL（开发机）上打包：

```bash
cd /mnt/c/Users/boshe/code/my_project/Chatlab
tar czf chatlab-deploy.tar.gz backend/ chat-lab/ call_api*.py
```

传到 Ubuntu（替换 `user@192.168.x.x` 为实际用户名和 IP）：

```bash
scp chatlab-deploy.tar.gz user@192.168.x.x:~/
ssh user@192.168.x.x
tar xzf chatlab-deploy.tar.gz
```

---

## 四、配置环境变量

```bash
cd ~/Chatlab

# 前端环境变量
cat > chat-lab/.env.local << 'EOF'
DIAGNOSIS_BACKEND_URL=http://localhost:8000
DAILY_TALK_BACKEND_URL=http://localhost:8001
COZE_API_BASE_URL=https://api.coze.cn
COZE_API_TOKEN=pat_Id8whVrK8pZEUnj6jdHItdGHzJZZXcwbmpucloZhjclvmAyoF3dlkvsJBPqc3rYc
COZE_COLD_START_RETRIES=4
EOF

# diagnosis 后端环境变量
cat > backend/diagnosis/.env << 'EOF'
COZE_STREAM_RUN_URL=https://gnp8dz4r4n.coze.site/stream_run
COZE_TOKEN=pat_Id8whVrK8pZEUnj6jdHItdGHzJZZXcwbmpucloZhjclvmAyoF3dlkvsJBPqc3rYc
COZE_PROJECT_ID=7640760744073658402
BACKEND_PORT=8000
EOF

# daily_talk 后端环境变量
cat > backend/daily_talk/.env << 'EOF'
COZE_STREAM_RUN_URL=https://4vd6j8c98y.coze.site/stream_run
COZE_TOKEN=pat_Id8whVrK8pZEUnj6jdHItdGHzJZZXcwbmpucloZhjclvmAyoF3dlkvsJBPqc3rYc
COZE_PROJECT_ID=7641269679604039732
BACKEND_PORT=8001
EOF
```

> ⚠️ 注意：`COZE_API_TOKEN` 和 `COZE_TOKEN` 已填入当前开发环境的值。如需更换，请手动修改。

---

## 五、安装依赖并构建

```bash
# 前端依赖 + 构建
cd ~/Chatlab/chat-lab
pnpm install
pnpm build

# diagnosis 后端依赖
cd ~/Chatlab/backend/diagnosis
pip3 install -r requirements.txt

# daily_talk 后端依赖
cd ~/Chatlab/backend/daily_talk
pip3 install -r requirements.txt
```

---

## 六、安装 cpolar

```bash
# 安装
curl -L https://www.cpolar.com/static/downloads/install-release-cpolar.sh | sudo bash

# 验证
cpolar version

# 认证（去 https://dashboard.cpolar.com 注册获取 Authtoken）
cpolar authtoken <你的 Authtoken>
```

---

## 七、启动服务

需要 **3 个终端窗口**（或使用后面的 `start.sh` 脚本）。

### 终端 1：diagnosis 后端
```bash
cd ~/Chatlab/backend/diagnosis
python3 main.py
# 应显示: Uvicorn running on http://0.0.0.0:8000
```

### 终端 2：daily_talk 后端
```bash
cd ~/Chatlab/backend/daily_talk
python3 main.py
# 应显示: Uvicorn running on http://0.0.0.0:8001
```

### 终端 3：前端 + cpolar
```bash
# 3a. 启动前端生产服务
cd ~/Chatlab/chat-lab
PORT=5000 node .next/standalone/server.js

# 3b. 另开终端启动 cpolar
cpolar http 5000
# 输出示例: https://a1b2c3d4.cpolar.io -> http://localhost:5000
```

把 `https://a1b2c3d4.cpolar.io` 发给访问者，浏览器直接打开即可。

---

## 八、一键启动脚本

创建 `~/Chatlab/start.sh`：

```bash
#!/bin/bash
set -e
cd ~/Chatlab

echo "[1/3] 启动 diagnosis 后端..."
cd backend/diagnosis
python3 main.py > /tmp/diagnosis.log 2>&1 &
PID1=$!
cd ../..

echo "[2/3] 启动 daily_talk 后端..."
cd backend/daily_talk
python3 main.py > /tmp/daily_talk.log 2>&1 &
PID2=$!
cd ../..

echo "[3/3] 等待后端就绪并启动前端..."
sleep 3
cd chat-lab
PORT=5000 node .next/standalone/server.js > /tmp/frontend.log 2>&1 &
PID3=$!

echo ""
echo "========================================"
echo "  服务已启动"
echo "  前端:     http://localhost:5000"
echo "  diagnosis: http://localhost:8000"
echo "  daily_talk: http://localhost:8001"
echo ""
echo "  现在运行: cpolar http 5000"
echo "========================================"
echo ""
echo "按 Enter 停止所有服务"
read

kill $PID1 $PID2 $PID3 2>/dev/null
echo "已停止"
```

赋予执行权限：

```bash
chmod +x ~/Chatlab/start.sh
```

以后每次演示只需：

```bash
./start.sh
# 另开终端运行
cpolar http 5000
```

---

## 九、免费版限制

| 限制项 | 说明 |
|--------|------|
| 带宽 | 1Mbps，1-2 人同时访问流畅 |
| 域名 | 随机生成，每次重启 cpolar 会变 |
| 连接时长 | 约 4 小时自动断开，需重新启动 |
| 并发 | 有限制，不宜大规模分发 |

如需固定域名和更高带宽，可升级 cpolar 付费版（约 6 元/月起）。

---

## 十、停止服务

```bash
# 在前端终端按 Ctrl+C
# 在后端终端按 Ctrl+C
# 或在运行 start.sh 的终端按 Enter
```

---

## 附录：修改记录

本部署方案未修改任何业务逻辑代码，仅涉及：
- 环境变量配置（`.env` / `.env.local`）
- 启动参数（`--hostname 0.0.0.0` 已在生产构建中通过 `next.config.ts` 的 `output: "standalone"` 自动处理）
- 添加本文档和启动脚本
