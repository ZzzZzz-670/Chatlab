# 「孩子画像已生成」通知动效 — 技术实现文档

## 功能概述

首次出现「孩子理解卡」（`child_understanding_card`）后，对话框顶部浮现淡蓝色毛玻璃通知："孩子画像已生成，今后可用于辅助家庭判断"，3 秒后自动消失。整个生命周期只触发一次。

---

## 触发逻辑

```
消息列表 messages 变化
    │
    ├─ portraitShownRef.current 已为 true? → 跳过
    │
    ├─ 扫描 messages 中是否有 type === "child_understanding_card"
    │
    └─ 有? → portraitShownRef = true → setPortraitNotify(true) → 3s 后 setPortraitNotify(false)
```

### 关键代码

```tsx
// 1. 声明 ref（跨渲染持久，确保只触发一次）
const portraitShownRef = useRef(false);

// 2. 声明通知状态
const [portraitNotify, setPortraitNotify] = useState(false);

// 3. 监听 messages，首次命中时触发
useEffect(() => {
  if (portraitShownRef.current) return;
  const hasUnderstandingCard = messages.some((m) => m.type === "child_understanding_card");
  if (hasUnderstandingCard) {
    portraitShownRef.current = true;
    setPortraitNotify(true);
    setTimeout(() => setPortraitNotify(false), 3000);
  }
}, [messages]);
```

**为什么用 `useRef` 而非 state？**
- `portraitShownRef` 需要跨 `useEffect` 多次执行保持标记
- 如果用 state 会导致"已触发过 → 标记 true → effect 重跑"的无限可能
- ref 写操作不触发重渲染，性能最优

---

## 动效时间线

```
t=0ms    opacity: 0, translateY(-8px)      ← 初始状态（隐藏 + 微上偏）
t=240ms  opacity: 1, translateY(0)         ← 淡入完成
t=2250ms opacity: 1, translateY(0)         ← 保持显示（75% 时间点）
t=3000ms opacity: 0, translateY(-4px)      ← 淡出 + 上飘消失
```

总时长 3s：淡入 ~8%，保持 ~67%，淡出 ~25%

---

## CSS 实现

### 定位

```css
.portrait-notify {
  position: fixed;                                             /* 浮于内容之上 */
  left: 50%;
  top: calc(56px + env(safe-area-inset-top, 0px) + 12px);    /* 导航栏下方 12pt */
  transform: translateX(-50%);                                 /* 水平居中 */
  z-index: 60;                                                 /* 高于导航栏（20） */
  pointer-events: none;                                        /* 不阻挡触摸 */
}
```

### 样式

```css
.portrait-notify {
  padding: 8px 16px;
  border-radius: 16px;
  background: rgba(238, 244, 255, 0.92);    /* #EEF4FF 半透明 */
  backdrop-filter: blur(8px);                /* 毛玻璃 */
  -webkit-backdrop-filter: blur(8px);
  color: #2563EB;                            /* 品牌蓝 */
  font-size: 13px;
  font-weight: 400;
  line-height: 1.4;
  white-space: nowrap;
  animation: portraitIn 3s ease both;
}
```

### 关键帧

```css
@keyframes portraitIn {
  0%   { opacity: 0; transform: translateX(-50%) translateY(-8px); }
  8%   { opacity: 1; transform: translateX(-50%) translateY(0);    }
  75%  { opacity: 1; transform: translateX(-50%) translateY(0);    }
  100% { opacity: 0; transform: translateX(-50%) translateY(-4px); }
}
```

---

## DOM 结构

```html
<div class="dl2-phone">
  <!-- portraitNotify === true 时渲染 -->
  <div class="portrait-notify">
    孩子画像已生成，今后可用于辅助家庭判断
  </div>
  <header class="dl2-topbar">...</header>
  <main class="dl2-chat-scroll">...</main>
  ...
</div>
```

通知在 `dl2-phone` 内部、`TopBar` 之前渲染，由 `portraitNotify` state 控制条件渲染。

---

## 数据流

```
messages (state)
  │
  └─ useEffect ──→ 首次 child_understanding_card?
                      │
                      ├─ 否 → 无动作
                      └─ 是 → portraitShownRef = true
                               setPortraitNotify(true)
                               setTimeout(3000) → setPortraitNotify(false)
                                        │
                                        └─ portraitNotify 变化
                                             │
                                             └─ ChatPage 重渲染
                                                  └─ 条件渲染 <div class="portrait-notify">
```

---

## 验收标准

- ✅ 第一次出现孩子理解卡时，通知浮现
- ✅ 通知持续 3 秒后完全消失
- ✅ 不阻挡任何触摸事件（`pointer-events: none`）
- ✅ 同一会话中后续重复出现理解卡不再弹出
- ✅ 页面刷新后重置（ref 不持久）
