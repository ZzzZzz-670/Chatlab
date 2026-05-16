# 03_日常Agent输入上下文规范.md

## 一、文档目的

本文定义「对话实验室」日常对话 Agent 每轮调用时，后端 / 工作流需要注入哪些上下文、按什么优先级注入、如何控制长度、如何避免信息污染，以及如何让日常 Agent 稳定调用孩子画像、家长关注和家庭互动记忆。

本文主要给后端、工作流编排、MemoryLoader 和 Agent Router 使用。

核心原则：

> 日常 Agent 的输出质量，取决于每轮输入上下文是否准确。它不是靠一次超长 Prompt 记住所有事，而是靠后端每轮把“当前最相关、最可信、最新的家庭信息”拼给它。

---

## 二、输入上下文的总体定位

日常 Agent 每轮需要三类输入：

```text
1. 当前用户输入
2. 最近对话上下文
3. 结构化长期记忆
```

其中结构化长期记忆包括：

- 孩子基础画像；
- 首次理解卡摘要；
- 孩子稳定画像；
- 近期成长变化；
- 待观察点；
- 家长长期关注目标；
- 孩子问卷摘要；
- 家长画像 / 家长沟通偏好；
- 家庭互动模式；
- 纠偏记录；
- 沟通预演记录。

日常 Agent 不应依赖完整聊天历史来理解家庭。  
完整历史太长、噪声太多、容易污染判断。

正确方式是：

```text
聊天历史 → 后端结构化沉淀 → 每轮按需检索 → 注入 Agent
```

---

## 三、每轮输入总结构

推荐后端每轮传给日常 Agent 的上下文格式：

```json
{
  "runtime_context": {
    "conversation_id": "conv_xxx",
    "family_id": "family_xxx",
    "child_id": "child_xxx",
    "user_role": "parent",
    "current_time": "2026-05-15T20:30:00+08:00",
    "entry_mode": "daily_chat"
  },
  "current_user_message": {
    "text": "家长本轮输入",
    "attachments": [],
    "source": "chat_input"
  },
  "recent_conversation": [],
  "child_context": {},
  "parent_context": {},
  "family_interaction_context": {},
  "memory_context": {},
  "routing_context": {},
  "output_contract": {}
}
```

---

## 四、输入模块总览

| 模块 | 是否必传 | 作用 |
|---|---|---|
| `runtime_context` | 必传 | 标识会话、家庭、孩子、入口 |
| `current_user_message` | 必传 | 家长本轮输入 |
| `recent_conversation` | 必传 | 最近几轮对话，避免断上下文 |
| `child_context` | 强烈建议 | 孩子画像与孩子问卷 |
| `parent_context` | 强烈建议 | 家长目标、沟通偏好、近期压力 |
| `family_interaction_context` | 建议 | 亲子互动循环和历史模式 |
| `memory_context` | 强烈建议 | 近期变化、待观察点、纠偏记录 |
| `routing_context` | 建议 | 当前应由哪个 Agent / 模式处理 |
| `output_contract` | 必传 | 本轮输出格式要求 |

---

# 五、runtime_context

## 1. 字段结构

```json
{
  "runtime_context": {
    "conversation_id": "conv_123",
    "family_id": "family_001",
    "child_id": "child_001",
    "user_role": "parent",
    "current_time": "2026-05-15T20:30:00+08:00",
    "entry_mode": "daily_chat",
    "platform": "web_mobile"
  }
}
```

## 2. 字段说明

| 字段 | 说明 |
|---|---|
| `conversation_id` | 当前会话 ID，只代表本次对话 |
| `family_id` | 家庭 ID，是长期记忆主键 |
| `child_id` | 孩子 ID，一个家庭可有多个孩子 |
| `user_role` | parent / child / teacher / operator |
| `current_time` | 当前时间，用于识别周末、考试前后、周期复盘 |
| `entry_mode` | daily_chat / rehearsal / record / profile / questionnaire |
| `platform` | web_mobile / mini_program / internal_demo |

## 3. 关键规则

长期记忆必须以 `family_id + child_id` 为核心，不要依赖 `conversation_id`。

原因：

```text
conversation_id 是一次会话。
family_id + child_id 才是一个孩子长期小档案。
```

如果换了新会话，只要 `family_id + child_id` 一样，日常 Agent 仍应读取同一套孩子画像。

---

# 六、current_user_message

## 1. 字段结构

```json
{
  "current_user_message": {
    "text": "他今天又拖作业，我真的很烦，说了半天才动。",
    "attachments": [],
    "source": "chat_input",
    "created_at": "2026-05-15T20:30:00+08:00"
  }
}
```

## 2. 处理要求

后端应原样传入家长本轮输入，不要提前替 Agent 改写。

可以额外做轻量预处理：

- 去掉多余空格；
- 保留表情和语气词；
- 保留家长原话；
- 保留换行；
- 保留图片/语音转写来源。

不要提前把家长输入改成总结句，否则会丢失语气、情绪和关键词。

---

# 七、recent_conversation

## 1. 作用

`recent_conversation` 用于让 Agent 理解本轮对话的直接上下文。

它不是长期记忆库。

只保留最近必要轮次，避免上下文过长导致判断被旧信息污染。

## 2. 推荐结构

```json
{
  "recent_conversation": [
    {
      "role": "parent",
      "content": "他最近总说没事，但看着很累。",
      "timestamp": "2026-05-15T20:20:00+08:00"
    },
    {
      "role": "assistant",
      "content": "综合孩子之前的信息，他说没事不一定代表真的没压力……",
      "timestamp": "2026-05-15T20:21:00+08:00",
      "message_type": "normal_reply"
    }
  ]
}
```

## 3. 截断规则

推荐：

```text
普通日常对话：最近 6–10 轮
沟通预演：最近 4–6 轮 + 当前预演主题
纠偏场景：最近 8–12 轮 + 相关旧判断
阶段复盘：最近 20 轮摘要 + 结构化记忆
```

不要把完整历史无脑塞入 Agent。

## 4. 优先级

最近对话的作用是理解“这轮在接什么话”，不是覆盖结构化记忆。

优先级：

```text
当前用户输入 > 最近对话 > 结构化高置信记忆 > 低置信旧记忆
```

---

# 八、child_context

`child_context` 是日常 Agent 理解孩子的核心输入。

## 1. 推荐结构

```json
{
  "child_context": {
    "child_basic_info": {},
    "initial_understanding_card": {},
    "stable_profile_entries": [],
    "questionnaire_summary": {},
    "recent_growth_records": [],
    "pending_observations": [],
    "correction_history": []
  }
}
```

---

## 2. child_basic_info

```json
{
  "child_basic_info": {
    "nickname": "小尹",
    "grade": "高二",
    "school_stage": "高中",
    "gender": "未知",
    "region": "北京",
    "important_events": ["近期分班", "期中考试后"]
  }
}
```

使用规则：

- 用于判断年龄阶段、学业压力和生活节奏；
- 不要在前台机械复述；
- 只有和当前问题有关时才自然引用。

---

## 3. initial_understanding_card

首次诊断型 Agent 生成的孩子理解卡摘要。

```json
{
  "initial_understanding_card": {
    "summary": "孩子在被连续追问时容易关闭表达，作业拖延可能与任务边界和休息权有关。",
    "core_hypotheses": [
      {
        "content": "孩子对休息边界较敏感",
        "confidence": 0.68,
        "status": "hypothesis"
      },
      {
        "content": "孩子在被连续追问时容易沉默",
        "confidence": 0.75,
        "status": "likely"
      }
    ],
    "blind_spot_summary": "家长可能以为孩子是在不配合，但孩子可能先感受到被追问。",
    "pending_points": [
      "确认手机出现时间：学习前、学习中、完成任务后还是无任务时",
      "确认拖延主要发生在开始前还是写到一半后"
    ],
    "created_at": "2026-05-10T21:00:00+08:00"
  }
}
```

## 4. 使用规则

首次理解卡只能作为“第一版假设”，不是最终结论。

Agent 必须允许它被：

- 验证；
- 补充；
- 修正；
- 降权；
- 拆分；
- 替换。

不要把首次诊断卡当成绝对真相。

---

## 5. stable_profile_entries

孩子稳定画像条目。

```json
{
  "stable_profile_entries": [
    {
      "id": "entry_001",
      "category": "communication",
      "content": "孩子在被连续追问时容易沉默，可能是在降低冲突",
      "confidence": 0.78,
      "source": "diagnosis_and_chat",
      "status": "active",
      "last_confirmed_at": "2026-05-14T20:00:00+08:00",
      "evidence_count": 3
    }
  ]
}
```

## 6. 推荐注入数量

按相关度和置信度注入，不要全量注入。

推荐：

```text
高相关画像：最多 6 条
中相关画像：最多 4 条
低相关画像：不注入
```

排序：

```text
当前场景相关度 > 最近确认时间 > 置信度 > 证据数量
```

## 7. 状态规则

| status | 含义 | 是否注入 |
|---|---|---|
| `active` | 当前有效 | 是 |
| `hypothesis` | 候选判断 | 视相关性注入 |
| `pending` | 待观察 | 注入到待观察模块 |
| `deprecated` | 已降权 | 一般不注入，纠偏场景可注入 |
| `conflicted` | 存在冲突 | 需要注入给纠偏判断 |

---

## 8. questionnaire_summary

孩子问卷摘要。

```json
{
  "questionnaire_summary": {
    "completed": true,
    "completed_at": "2026-05-13T18:00:00+08:00",
    "summary": "孩子自评在被催促时容易烦，更希望先知道任务做到哪里算结束。",
    "child_self_view": [
      "被连续催促时容易烦",
      "希望任务边界更清楚",
      "更愿意在不被评价时说真实想法"
    ],
    "conflicts_with_parent_view": [
      {
        "parent_view": "孩子不自觉",
        "child_view": "任务边界不清时更难开始",
        "status": "needs_observation"
      }
    ]
  }
}
```

## 9. 使用规则

孩子问卷是孩子视角的重要补充，但也不是绝对真相。

处理方式：

- 与家长观察一致：提高相关画像权重；
- 与家长观察不一致：写入待观察点；
- 与旧画像冲突：触发纠偏候选；
- 未完成问卷：涉及孩子主观体验时降低确定性。

---

# 九、parent_context

`parent_context` 用于让 Agent 理解家长，而不是评价家长。

## 1. 推荐结构

```json
{
  "parent_context": {
    "long_term_goals": [],
    "parent_profile_entries": [],
    "advice_preferences": {},
    "recent_parent_state": {}
  }
}
```

---

## 2. long_term_goals

```json
{
  "long_term_goals": [
    {
      "goal_name": "责任感与抗压能力",
      "goal_category": "resilience",
      "weight": 0.82,
      "related_scenes": ["作业启动", "手机规则", "考试复盘"],
      "last_triggered_at": "2026-05-14T21:00:00+08:00",
      "status": "active"
    }
  ]
}
```

## 3. 注入规则

推荐每轮注入：

```text
权重最高的长期目标：最多 3 条
与当前场景强相关目标：最多 2 条
```

不要每轮都把所有长期目标塞入。

如果当前场景和长期目标相关，可自然带回。

例如：

```text
这件事也能放进您之前提到的“责任感”里一起观察。
```

---

## 4. parent_profile_entries

家长侧理解条目。

```json
{
  "parent_profile_entries": [
    {
      "category": "communication_style",
      "content": "家长在作业场景中容易连续确认原因，希望尽快判断孩子为什么不写",
      "confidence": 0.65,
      "status": "active",
      "last_seen_at": "2026-05-15T20:00:00+08:00"
    },
    {
      "category": "advice_preference",
      "content": "家长偏好简洁、具体、可执行的回复，不喜欢被教育感",
      "confidence": 0.9,
      "status": "active"
    }
  ]
}
```

## 5. 使用规则

家长画像只服务于更合适的回复，不用于给家长贴标签。

前台不要说：

```text
您的沟通模式是……
您属于……
您控制欲比较强……
```

可以说：

```text
咱们这边是想尽快确认原因，但孩子那边可能先感受到的是被连续追问。
```

---

## 6. advice_preferences

```json
{
  "advice_preferences": {
    "prefer_short_reply": true,
    "avoid_report_style": true,
    "avoid_direct_script": true,
    "allow_direct_blindspot": false,
    "tone": "natural_warm_clear"
  }
}
```

用途：

- 控制回复长度；
- 控制是否结构化；
- 控制是否展开建议；
- 控制是否主动追问；
- 避免触发用户反感的表达。

---

## 7. recent_parent_state

```json
{
  "recent_parent_state": {
    "emotion_level": "high",
    "recent_emotions": ["焦虑", "无力"],
    "likely_needs": ["先被接住", "需要具体判断"],
    "last_updated_at": "2026-05-15T20:00:00+08:00"
  }
}
```

使用规则：

- 家长情绪高时，少给复杂建议；
- 家长明显疲惫时，不主动布置任务；
- 家长连续多轮讨论同一问题时，可更直接给判断；
- 家长刚否定系统时，先纠偏，不辩解。

---

# 十、family_interaction_context

用于让 Agent 识别家庭互动循环。

## 1. 推荐结构

```json
{
  "family_interaction_context": {
    "active_patterns": [],
    "candidate_patterns": [],
    "recent_interaction_events": []
  }
}
```

---

## 2. active_patterns

```json
{
  "active_patterns": [
    {
      "pattern_name": "追问—沉默循环",
      "content": "家长越想确认原因，越容易连续追问；孩子在这种场景下更容易沉默或表面答应",
      "confidence": 0.76,
      "evidence_count": 3,
      "last_seen_at": "2026-05-14T20:00:00+08:00"
    }
  ]
}
```

## 3. candidate_patterns

```json
{
  "candidate_patterns": [
    {
      "pattern_name": "加任务—磨蹭循环",
      "content": "孩子可能形成了做完一件后还会被继续安排的预期",
      "confidence": 0.55,
      "status": "needs_observation"
    }
  ]
}
```

## 4. 使用规则

如果当前事件与已有互动模式相关，Agent 可以自然引用，但不要说“系统识别到模式”。

推荐：

```text
这和前面聊过的情况有点相关：咱们这边越想确认原因，孩子那边越容易先沉默。
```

避免：

```text
系统识别到你们存在追问—沉默循环。
```

---

# 十一、memory_context

`memory_context` 汇总近期变化、待观察点和纠偏记录。

## 1. 推荐结构

```json
{
  "memory_context": {
    "recent_growth_records": [],
    "pending_observations": [],
    "correction_history": [],
    "rehearsal_records": []
  }
}
```

---

## 2. recent_growth_records

```json
{
  "recent_growth_records": [
    {
      "scene_type": "school",
      "content": "孩子主动提到学校里的事",
      "signal_type": "主动表达",
      "created_at": "2026-05-14T19:30:00+08:00",
      "importance": "medium"
    }
  ]
}
```

推荐注入：

```text
最近 7–14 天内，最多 5 条
与当前场景相关优先
```

用途：

- 识别孩子是否出现新趋势；
- 生成周期小观察；
- 判断当前事件是否延续某个变化。

---

## 3. pending_observations

```json
{
  "pending_observations": [
    {
      "content": "确认孩子拿手机更偏学习前逃避，还是完成任务后的恢复",
      "related_scene": "手机与休息",
      "priority": "high",
      "created_at": "2026-05-13T20:00:00+08:00",
      "status": "active"
    }
  ]
}
```

推荐注入：

```text
当前场景相关：最多 5 条
高优先级：最多 3 条
长期未验证但重要：最多 2 条
```

用途：

- 支撑轻主动追问；
- 支撑纠偏；
- 防止日常 Agent 忘记未完成判断。

---

## 4. correction_history

```json
{
  "correction_history": [
    {
      "old_judgment": "孩子拿手机主要是逃避学习",
      "new_judgment": "孩子拿手机也可能是完成任务后的恢复",
      "correction_type": "narrow_scope",
      "created_at": "2026-05-14T21:00:00+08:00"
    }
  ]
}
```

推荐注入：

```text
与当前场景相关的纠偏记录：最多 3 条
近期纠偏记录：最多 3 条
```

用途：

- 防止 Agent 反复犯同一个错误；
- 支撑“我改一下前面的理解”；
- 防止旧诊断卡覆盖新事实。

---

## 5. rehearsal_records

```json
{
  "rehearsal_records": [
    {
      "topic": "周末是否加英语课",
      "child_perspective_summary": "孩子可能先感到休息时间被压缩",
      "suggested_direction": "先一起确认英语哪一块最吃力",
      "created_at": "2026-05-14T21:30:00+08:00"
    }
  ]
}
```

推荐注入：

```text
当前沟通主题相关：最多 3 条
近期保存预演：最多 3 条
```

用途：

- 避免重复生成完全不同的沟通方向；
- 支撑后续复盘“上次这样说之后孩子反应如何”。

---

# 十二、routing_context

`routing_context` 用于 Agent Router 判断当前应进入哪个模式。

## 1. 推荐结构

```json
{
  "routing_context": {
    "current_agent": "daily_agent",
    "available_modes": [
      "daily_chat",
      "communication_rehearsal",
      "correction",
      "growth_record",
      "stage_review_suggestion"
    ],
    "profile_completeness": 0.68,
    "questionnaire_completed": true,
    "should_consider_diagnosis_agent": false,
    "routing_reason": "已有孩子画像，当前为日常对话"
  }
}
```

## 2. 什么时候继续用日常 Agent

- 已有孩子画像；
- 当前只是普通记录；
- 当前是轻分析；
- 当前是沟通预演；
- 当前是小纠偏；
- 当前是长期目标记录；
- 当前是成长信号识别。

## 3. 什么时候考虑切换诊断型 Agent / 阶段复盘

- 家长首次进入且没有画像；
- 家长主动要求“整体分析一下”；
- 当前信息已经明显推翻第一版诊断卡；
- 多个近期事件无法被现有画像解释；
- 孩子问卷和家长描述差异很大；
- 同类冲突高频重复，日常轻回应不够；
- 家长需要阶段性孩子理解卡。

日常 Agent 自己不直接输出诊断卡，只能返回：

```json
{
  "should_trigger_review": true,
  "review_reason": "近期多条记录显示旧画像需要阶段性重整"
}
```

---

# 十三、output_contract

每轮调用日常 Agent 时，后端应明确输出协议。

```json
{
  "output_contract": {
    "must_return_json": true,
    "include_reply": true,
    "include_understanding_engine": true,
    "include_memory_candidates": true,
    "frontend_should_show_internal_fields": false,
    "max_next_question_count": 1
  }
}
```

作用：

- 保证 Agent 返回自然回复 + 结构化数据；
- 防止 Agent 只输出自然语言；
- 防止 Agent 把内部字段展示给家长；
- 保证每轮最多一个问题。

---

# 十四、上下文优先级规则

当信息冲突时，按以下优先级处理：

```text
当前用户明确事实
>
孩子问卷中的孩子自述
>
近期多次成长记录
>
家长近期补充事实
>
高置信稳定画像
>
首次诊断卡假设
>
低置信旧判断
```

## 1. 当前事实优先

如果当前家长提供了具体新事实，应优先考虑当前事实。

例如：

```text
旧判断：孩子拿手机主要是学习前逃避。
新事实：最近三次都是完成任务后才拿手机。
处理：旧判断缩小适用范围，新增“完成任务后恢复需求”候选。
```

## 2. 孩子问卷不能绝对压过家长事实

孩子问卷是重要补充，但也可能不完整。

如果孩子问卷和家长观察冲突：

```text
不直接判定谁对。
写入待观察点。
必要时触发纠偏候选。
```

## 3. 首次诊断卡不能压过后续多次记录

首次诊断卡是第一版假设。

如果后续多次记录显示不同方向，必须允许修正。

---

# 十五、长度控制规则

## 1. 总输入长度建议

后端每轮拼给 Agent 的上下文不宜过长。

推荐：

```text
普通日常对话：3000–5000 中文字以内
复杂纠偏 / 阶段复盘：6000–9000 中文字以内
不要全量塞入历史聊天记录
```

## 2. 压缩优先级

如果上下文过长，按以下顺序裁剪：

```text
1. 删除低相关旧对话
2. 删除低置信旧画像
3. 删除低优先级待观察点
4. 压缩首次诊断卡
5. 保留当前场景相关画像
6. 保留最近纠偏记录
7. 保留当前长期目标
```

## 3. 必须保留

无论如何都应保留：

- 当前用户输入；
- 最近 3–6 轮对话；
- 当前场景最相关的孩子画像；
- 当前场景最相关的待观察点；
- 相关纠偏记录；
- 家长长期关注目标；
- 输出格式要求。

---

# 十六、MemoryLoader 推荐流程

每轮调用日常 Agent 前，后端 MemoryLoader 建议按以下步骤读取记忆：

```text
1. 根据 family_id + child_id 读取孩子主画像
2. 根据当前用户输入识别场景关键词
3. 检索相关 profile_entries
4. 检索 recent_growth_records
5. 检索 pending_observations
6. 检索 long_term_goals
7. 检索 parent_profile
8. 检索 family_interaction_patterns
9. 检索 correction_history
10. 检索 questionnaire_summary
11. 拼接 recent_conversation
12. 生成输入上下文
```

## 场景关键词示例

| 当前输入关键词 | 检索重点 |
|---|---|
| 作业、拖、磨蹭 | academic / task_barrier / family_dynamic |
| 手机、游戏、短视频 | rest_boundary / self_management / phone |
| 沉默、不说话 | communication / family_interaction |
| 成绩、考试、排名 | academic / emotional / parent_goal |
| 朋友、学校、老师 | social / emotional |
| 累、没精神、睡觉 | rest / emotional |
| 责任感、自觉、抗压 | long_term_goals / self_management |
| 怎么说、要不要谈 | rehearsal_records / communication |

---

# 十七、示例：完整输入上下文

```json
{
  "runtime_context": {
    "conversation_id": "conv_20260515_001",
    "family_id": "family_001",
    "child_id": "child_001",
    "user_role": "parent",
    "current_time": "2026-05-15T20:30:00+08:00",
    "entry_mode": "daily_chat"
  },
  "current_user_message": {
    "text": "我刚才一直问他为什么不写，他就不说话。",
    "attachments": [],
    "source": "chat_input"
  },
  "recent_conversation": [
    {
      "role": "parent",
      "content": "他今天作业又拖了很久。",
      "timestamp": "2026-05-15T20:25:00+08:00"
    }
  ],
  "child_context": {
    "child_basic_info": {
      "grade": "高二",
      "school_stage": "高中"
    },
    "initial_understanding_card": {
      "summary": "孩子在被连续追问时容易关闭表达，作业拖延可能与任务边界和休息权有关。",
      "core_hypotheses": [
        {
          "content": "孩子在被连续追问时容易沉默",
          "confidence": 0.75,
          "status": "likely"
        }
      ],
      "pending_points": [
        "确认拖延主要发生在开始前还是写到一半后"
      ]
    },
    "stable_profile_entries": [
      {
        "category": "communication",
        "content": "孩子在被连续追问时容易沉默，可能是在降低冲突",
        "confidence": 0.78,
        "status": "active"
      }
    ],
    "questionnaire_summary": {
      "completed": true,
      "summary": "孩子自评被催促时容易烦，更希望先知道任务做到哪里算结束。"
    }
  },
  "parent_context": {
    "long_term_goals": [
      {
        "goal_name": "责任感与自我管理",
        "weight": 0.82,
        "related_scenes": ["作业启动", "周末安排"]
      }
    ],
    "parent_profile_entries": [
      {
        "category": "communication_style",
        "content": "家长在作业场景中容易连续确认原因，希望尽快判断孩子为什么不写",
        "confidence": 0.65
      }
    ],
    "advice_preferences": {
      "prefer_short_reply": true,
      "avoid_report_style": true
    }
  },
  "family_interaction_context": {
    "active_patterns": [
      {
        "pattern_name": "追问—沉默循环",
        "content": "家长越想确认原因，越容易连续追问；孩子在这种场景下更容易沉默或表面答应",
        "confidence": 0.76
      }
    ]
  },
  "memory_context": {
    "pending_observations": [
      {
        "content": "确认孩子作业拖延主要发生在开始前，还是写到一半后",
        "related_scene": "作业启动",
        "priority": "high"
      }
    ],
    "correction_history": []
  },
  "routing_context": {
    "current_agent": "daily_agent",
    "profile_completeness": 0.7,
    "questionnaire_completed": true,
    "should_consider_diagnosis_agent": false
  },
  "output_contract": {
    "must_return_json": true,
    "include_reply": true,
    "include_understanding_engine": true,
    "include_memory_candidates": true,
    "frontend_should_show_internal_fields": false,
    "max_next_question_count": 1
  }
}
```

---

# 十八、输入上下文质量检查

每轮调用前，后端应检查：

```text
1. 是否有 family_id + child_id？
2. 是否包含当前用户原始输入？
3. 是否包含最近对话？
4. 是否读取了当前场景相关孩子画像？
5. 是否读取了相关待观察点？
6. 是否读取了家长长期关注？
7. 是否读取了相关纠偏记录？
8. 是否避免注入大量无关旧信息？
9. 是否明确输出格式？
10. 是否避免把低置信旧判断当成稳定事实？
```

---

# 十九、最低验收标准

输入上下文规范完成后，应满足：

1. 换一个新会话，只要 family_id + child_id 不变，日常 Agent 仍能记得孩子；
2. 日常 Agent 能调用首次诊断卡，但不会被它锁死；
3. 孩子问卷结果能影响后续回复；
4. 家长长期目标能在相关场景中被自然带回；
5. 待观察点能驱动轻追问；
6. 纠偏记录能防止 Agent 重复旧错误；
7. 家长沟通偏好能影响回复风格；
8. 家庭互动模式能帮助 Agent 解释亲子差异；
9. 输入上下文不会因为全量历史过长而污染判断；
10. 后端能稳定拼接出 Agent 所需上下文。

---

## 二十、最终一句话

日常 Agent 不是靠“记住所有聊天记录”变准，而是靠后端每轮注入最相关、最可信、最新的结构化家庭信息变准。

> 输入上下文越干净，日常 Agent 越像真的懂这个家庭；输入上下文越混乱，Agent 越容易变成普通聊天机器人。
