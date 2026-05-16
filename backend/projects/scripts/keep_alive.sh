#!/bin/bash
# 监控并自动重启对话实验室服务

LOG_FILE="/tmp/keep_alive.log"
APP_LOG="/tmp/app.log"
PID_FILE="/tmp/dialogue_lab.pid"
WORKSPACE="/workspace/projects"
PORT=5000

check_service() {
    curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${PORT}/" 2>/dev/null
}

start_service() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting service..." >> "$LOG_FILE"
    cd "$WORKSPACE" || exit 1
    nohup uv run python src/main.py -m http -p "$PORT" > "$APP_LOG" 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"
    sleep 5
}

# 主循环
while true; do
    STATUS=$(check_service)
    if [ "$STATUS" != "200" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Service down (status=$STATUS), restarting..." >> "$LOG_FILE"
        # 清理旧进程
        pkill -f "src/main.py" 2>/dev/null
        sleep 2
        start_service
        # 验证启动成功
        STATUS=$(check_service)
        if [ "$STATUS" = "200" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Service restarted successfully" >> "$LOG_FILE"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Service restart failed (status=$STATUS)" >> "$LOG_FILE"
        fi
    fi

    # 自 ping 保持容器活跃：每60秒访问一次外部URL，防止平台冷启动休眠
    EXTERNAL_DOMAIN="${COZE_PROJECT_DOMAIN:-9477ea2b-e898-4c7a-b160-9079b1c93f25.dev.coze.site}"
    PING_URL="https://${EXTERNAL_DOMAIN}/health"
    PING_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$PING_URL" 2>/dev/null)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Self-ping $PING_URL → $PING_STATUS" >> "$LOG_FILE"

    # 每60秒检查一次
    sleep 60
done
