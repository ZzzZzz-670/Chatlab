# 「已查询 x 位清北同学资料」状态条 — 技术实现文档

## 功能概述

用户发送消息后、AI 首个响应到达前，在输入区上方展示一条查询状态条，每 200ms 递增计数，给用户"正在处理中"的感知。首个响应到达后切换为结果文案，2 秒后淡出隐藏。纯前端模拟，不对应真实后端查询。

---

## 三阶段生命周期

```
用户发送消息
      │
      ▼
┌─────────────────────────────────────────────┐
│  阶段一：等待中                               │
│  状态条：🔍 正在查询清北学生资料，已查询 1 位   │
│  每 200ms count++，数字递增（5 次/秒）         │
│  聊天区：三点跳动 typing indicator             │
└──────────────┬──────────────────────────────┘
               │ API 响应到达
               ▼
┌─────────────────────────────────────────────┐
│  阶段二：结果就绪                             │
│  状态条：🔍 本轮查询 N 位清北同学资料          │
│  N = 停止时刻的计数                           │
│  2 秒后添加 fadeout class，0.5s 动画隐藏       │
│  聊天区：typing indicator 移除，AI 气泡渲染     │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  阶段三：正常对话                             │
│  状态条：display:none（DOM 不存在）            │
│  聊天区：AI 回复持续流式输出                   │
└─────────────────────────────────────────────┘
```

---

## 核心状态机

### State 变量

| 变量 | 类型 | 作用 |
|------|------|------|
| `queryPhase` | `"idle" \| "waiting" \| "result"` | 当前阶段 |
| `queryCount` | `number` | 显示用的计数值 |
| `queryFadingOut` | `boolean` | 是否正在执行淡出动画 |

### Ref 变量

| 变量 | 类型 | 作用 |
|------|------|------|
| `queryTimerRef` | `interval ID \| null` | 计数器定时器句柄 |
| `queryFadeoutTimerRef` | `timeout ID \| null` | 淡出启动定时器句柄 |
| `queryHideTimerRef` | `timeout ID \| null` | 隐藏定时器句柄 |
| `queryCountRef` | `number` | 当前计数（最新值，不触发重渲染） |

### 设计与 React 闭包陷阱

**为什么需要 `queryCountRef`？**

React 的 `setInterval` 闭包中引用 state 会捕获创建时刻的旧值。用 `useRef` 保证定时器回调读到最新计数：

```tsx
queryTimerRef.current = setInterval(() => {
  queryCountRef.current += 1;        // ref 始终是最新值
  setQueryCount(queryCountRef.current); // 同步到 state 触发重渲染
}, 200);
```

`stopQueryCounter` 返回 `queryCountRef.current + 1`（显示值 = 内部值 + 1），在 API 响应到达时读取。

---

## 关键函数

### 1. `startQueryCounter()` — 启动阶段一

```tsx
const startQueryCounter = useCallback(() => {
  cleanupQueryTimers();           // 清理旧定时器
  queryCountRef.current = 0;      // 重置内部计数
  setQueryCount(0);               // 重置显示计数
  setQueryPhase("waiting");       // 进入等待阶段
  setQueryFadingOut(false);       // 清除淡出标记（防止上次残留）
  queryTimerRef.current = setInterval(() => {
    queryCountRef.current += 1;
    setQueryCount(queryCountRef.current);
  }, 200);                         // 每 200ms 递增
}, [cleanupQueryTimers]);
```

### 2. `stopQueryCounter()` — 停止计数

```tsx
const stopQueryCounter = useCallback((): number => {
  if (queryTimerRef.current) {
    clearInterval(queryTimerRef.current);
    queryTimerRef.current = null;
  }
  return queryCountRef.current + 1; // 显示值 = count + 1
}, []);
```

**数值示例**：API 在 800ms 后返回 → `count = 4` → 显示 `5 位`

### 3. `transitionQueryResult(finalCount)` — 阶段二

```tsx
const transitionQueryResult = useCallback((finalCount: number) => {
  setQueryCount(finalCount);          // 定格最终数字
  setQueryPhase("result");            // 结果阶段
  setQueryFadingOut(false);           // 清除淡出标记
  // 2s 后开始淡出
  queryFadeoutTimerRef.current = setTimeout(() => {
    setQueryFadingOut(true);          // 触发 CSS 0.5s opacity 过渡
  }, 2000);
  // 2.5s 后彻底移除
  queryHideTimerRef.current = setTimeout(() => {
    setQueryPhase("idle");            // 回到 idle，DOM 不再渲染
  }, 2500);
}, []);
```

### 4. `cleanupQueryTimers()` — 清理所有定时器

```tsx
const cleanupQueryTimers = useCallback(() => {
  if (queryTimerRef.current) { clearInterval(queryTimerRef.current); queryTimerRef.current = null; }
  if (queryFadeoutTimerRef.current) { clearTimeout(queryFadeoutTimerRef.current); queryFadeoutTimerRef.current = null; }
  if (queryHideTimerRef.current) { clearTimeout(queryHideTimerRef.current); queryHideTimerRef.current = null; }
  setQueryFadingOut(false);
}, []);
```

---

## 集成到 `sendAgentMessage`

```tsx
const sendAgentMessage = useCallback((overrideText?: string) => {
  const text = (overrideText ?? input).trim();
  if (!text || isSending) return;

  // 1. 添加用户消息
  setMessages((prev) => [...prev, userMessage]);
  setInput("");
  setIsSending(true);

  // 2. 阶段一：启动查询计数器 + typing indicator
  startQueryCounter();

  void (async () => {
    try {
      const result = await sendMessage({ ... });

      // 3. 阶段二：停止计数器，切换结果
      const finalCount = stopQueryCounter();
      transitionQueryResult(finalCount);

      // 4. 正常处理 AI 回复
      setAgentState(result.next_state);
      setMessages((prev) => [...prev, messageFromAgentResponse(result)]);
      // ... 观察记录等后续逻辑 ...
    } catch (error) {
      // 5. 异常处理：立即清理
      stopQueryCounter();
      cleanupQueryTimers();
      setQueryPhase("idle");
      // ... 错误提示 ...
    } finally {
      setIsSending(false);
    }
  })();
}, [/* deps */]);
```

---

## UI 渲染

### 状态条（ChatPage 内，输入区上方）

```tsx
{queryPhase !== "idle" && (
  <div className={queryFadingOut ? "qhb-status-bar fadeout" : "qhb-status-bar"}>
    <span className="qhb-status-icon">🔍</span>
    <span className="qhb-status-text">
      {queryPhase === "waiting"
        ? `正在查询清北学生资料，已查询 ${queryCount + 1} 位`
        : `本轮查询 ${queryCount} 位清北同学资料`}
    </span>
  </div>
)}
```

### Typing Indicator（聊天区底部，阶段一期间）

```tsx
{queryPhase === "waiting" && (
  <div className="dl2-streaming-row">
    <div className="dl2-streaming-bubble">
      <div className="dl2-streaming-dots" aria-label="AI 正在处理">
        <i /><i /><i />
      </div>
    </div>
  </div>
)}
```

---

## CSS 实现

### 状态条

```css
.qhb-status-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  background: #F0F4FF;
  border-top: 1px solid #DDE8FF;
  color: #2563EB;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  opacity: 1;
  transition: opacity 0.5s ease;   /* 淡出过渡 */
}

.qhb-status-bar.fadeout {
  opacity: 0;
  pointer-events: none;
}
```

### 跳动圆点

```css
.dl2-streaming-dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #8A94A6;
  opacity: 0.35;
  animation: dl2-query-bounce 1.15s infinite ease-in-out;
}

.dl2-streaming-dots i:nth-child(2) { animation-delay: 0.15s; }
.dl2-streaming-dots i:nth-child(3) { animation-delay: 0.3s; opacity: 0.85; }

@keyframes dl2-query-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
  30% { transform: translateY(-6px); opacity: 0.85; }
}
```

---

## DOM 层级

```
.dl2-phone
  ├─ .dl2-topbar                         (z-index: 20)
  ├─ .dl2-chat-scroll                     (聊天区)
  │   ├─ 消息列表...
  │   └─ .dl2-streaming-row              (typing indicator，仅阶段一)
  ├─ .qhb-status-bar                      (状态条，阶段一二，flex-shrink:0)
  └─ .dl2-composer                        (输入区，z-index: 40)
```

状态条位于聊天区和输入区之间，不参与滚动，`flex-shrink: 0` 固定在视口底部输入区上方。

---

## 完整时序图

```
时间  事件                          状态条                              聊天区
────  ────────────────────────────  ─────────────────────────────────  ──────────────
0ms   用户发送消息                  显示，文案"已查询 1 位"               三点跳动
      startQueryCounter()          queryPhase = "waiting"
      定时器启动(count=0)

200ms count++ (count=1)            文案"已查询 2 位"                    三点跳动
400ms count++ (count=2)            文案"已查询 3 位"                    三点跳动
600ms count++ (count=3)            文案"已查询 4 位"                    三点跳动
...   (持续递增)

~Nms  API 响应到达                 文案"本轮查询 (count+1) 位"           typing 移除
      stopQueryCounter()           queryPhase = "result"                AI 气泡渲染
      transitionQueryResult()

+N+2000ms                          开始淡出(opacity → 0, 0.5s)          AI 气泡继续
      queryFadingOut = true

+N+2500ms                          移除(queryPhase = "idle")            AI 气泡继续
      queryPhase = "idle"
```

### 典型数值示例

| API 耗时 | 最终计数 | 显示文案 |
|----------|---------|---------|
| 400ms | 2 位 | 本轮查询 2 位清北同学资料 |
| 800ms | 4 位 | 本轮查询 4 位清北同学资料 |
| 1500ms | 8 位 | 本轮查询 8 位清北同学资料 |
| 3000ms | 15 位 | 本轮查询 15 位清北同学资料 |

---

## 异常处理

```tsx
} catch (error) {
  stopQueryCounter();       // 停止 interval
  cleanupQueryTimers();     // 清除所有 timeout
  setQueryPhase("idle");    // 立即隐藏状态条
  // ... 显示错误消息 ...
}
```

异常时状态条被立即清理，不留任何残留。下次发送消息时 `startQueryCounter()` 会从干净状态重新开始。

---

## 组件卸载清理

```tsx
useEffect(() => () => cleanupQueryTimers(), [cleanupQueryTimers]);
```

组件卸载时清理所有定时器，防止内存泄漏。

---

## 验收标准

- ✅ 发送消息后立即显示状态条 + typing indicator
- ✅ 计数从「已查询 1 位」开始，每 200ms +1
- ✅ API 响应到达后显示最终数字 + 「本轮查询 N 位」
- ✅ 状态条在结果就绪后 2s 开始淡出，0.5s 后完全消失
- ✅ 请求失败时立即清理，不留残留
- ✅ 连续发送消息时，前一次计数器被正确中断和重置
- ✅ 组件卸载时所有定时器被清理
