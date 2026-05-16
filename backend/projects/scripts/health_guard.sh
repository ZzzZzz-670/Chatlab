#!/bin/bash
# 对话实验室 - 进程守护脚本
# 同时监控 port 5000(静态HTTP) 和 port 9000(API服务)，不响应则自动重启

LOG_FILE="/tmp/health_guard.log"
WORKSPACE="/workspace/projects"
SOURCE_DIR="/source"
CHECK_INTERVAL=30
MAX_RETRY=3

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

check_http() {
    local port=$1
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:${port}/" 2>/dev/null)
    echo "$code"
}

check_api_alive() {
    # API服务对 / 返回401是正常的（需要认证），所以检查进程+端口
    local proc_count
    proc_count=$(pgrep -f "uvicorn.*port 9000" | wc -l)
    local port_listening
    port_listening=$(ss -tlnp 2>/dev/null | grep -c ":9000" || netstat -tlnp 2>/dev/null | grep -c ":9000" || echo "0")
    if [ "$proc_count" -gt 0 ] && [ "$port_listening" -gt 0 ]; then
        echo "200"
    else
        echo "down"
    fi
}

kill_service() {
    local pattern=$1
    local name=$2
    log "Killing $name processes matching: $pattern"
    pkill -f "$pattern" 2>/dev/null
    sleep 2
    local remaining
    remaining=$(pgrep -f "$pattern" | wc -l)
    if [ "$remaining" -gt 0 ]; then
        log "Force killing remaining $name processes..."
        pkill -9 -f "$pattern" 2>/dev/null
        sleep 1
    fi
}

start_api() {
    log "Starting API service (port 9000)..."
    cd "$SOURCE_DIR" || exit 1
    export WORKSPACE_PATH=${WORKSPACE_PATH:-/workspace/projects}
    export LOG_LEVEL=${LOG_LEVEL:-INFO}
    export PORT=9000
    export RELEASE_PKG_DIR=${RELEASE_PKG_DIR:-/space/pack_release_pkg}
    export SCHEDULED_PKG_DIR=${SCHEDULED_PKG_DIR:-/space/pack_projects}
    export COPY_PACKAGE_DIR=${COPY_PACKAGE_DIR:-/space/pack_copy_projects}
    export PKG_TEMP_PATH=${PKG_TEMP_PATH:-/workspace/pkg_temp}

    nohup python3 -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 9000 \
        --log-level info \
        >> /tmp/api_service.log 2>&1 &
    sleep 5
}

start_http() {
    log "Starting HTTP service (port 5000)..."
    cd "$WORKSPACE" || exit 1
    nohup bash scripts/http_run.sh -p 5000 >> /tmp/http_service.log 2>&1 &
    sleep 5
}

restart_api() {
    local retry=0
    while [ "$retry" -lt "$MAX_RETRY" ]; do
        kill_service "uvicorn.*port 9000" "API"
        start_api
        local status
        status=$(check_api_alive)
        if [ "$status" = "200" ]; then
            log "API service (port 9000) restarted successfully"
            return 0
        fi
        retry=$((retry + 1))
        log "API service restart attempt $retry failed, retrying..."
        sleep 5
    done
    log "ERROR: API service restart failed after $MAX_RETRY attempts"
    return 1
}

restart_http() {
    local retry=0
    while [ "$retry" -lt "$MAX_RETRY" ]; do
        kill_service "src/main.py.*http.*5000" "HTTP"
        start_http
        local status
        status=$(check_http 5000)
        if [ "$status" = "200" ]; then
            log "HTTP service (port 5000) restarted successfully"
            return 0
        fi
        retry=$((retry + 1))
        log "HTTP service restart attempt $retry failed (status=$status), retrying..."
        sleep 5
    done
    log "ERROR: HTTP service restart failed after $MAX_RETRY attempts"
    return 1
}

# 主循环
log "=== Health Guard Started ==="
log "Monitoring ports: 5000 (HTTP), 9000 (API)"
log "Check interval: ${CHECK_INTERVAL}s"

while true; do
    # 检查 port 9000 (API服务) - 检查进程+端口，curl 401 是正常的
    API_STATUS=$(check_api_alive)
    if [ "$API_STATUS" != "200" ]; then
        log "ALERT: API service (port 9000) not alive (process/port missing)"
        restart_api
    fi

    # 检查 port 5000 (静态HTTP服务)
    HTTP_STATUS=$(check_http 5000)
    if [ "$HTTP_STATUS" != "200" ]; then
        log "ALERT: HTTP service (port 5000) not responding (status=$HTTP_STATUS)"
        restart_http
    fi

    sleep "$CHECK_INTERVAL"
done
