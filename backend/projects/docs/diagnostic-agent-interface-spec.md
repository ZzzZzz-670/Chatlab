# 诊断型 Agent 接口需求说明

---

## 一、职责边界

### 负责

1. 通过 2—6 轮对话，从家长零散描述中提取可验证事实、识别行为功能、发现家长盲点；
2. 动态维护 2—4 个候选方向，随新信息调整权重；
3. 当证据充分时，生成孩子理解卡（child_understanding_card）；
4. 同时输出 profileUpdateCandidates、pendingObservations、handoffSummary，供后端写入和日常 Agent 使用；
5. 在画像候选中防止把家长标签直接写成孩子特征。

### 不负责

1. 日常陪聊、后续跟进、记忆更新——属于日常 Agent；
2. 直接写入数据库——所有写操作由后端统一执行；
3. 问卷发放和回收——后端独立处理，Agent 只接收摘要；
4. 心理诊断、医学评估——只能建议家长寻求专业帮助；
5. 跨 session 记忆——Agent 无状态，所有上下文由后端注入。

### 继续追问条件

- 候选方向仍 ≥ 2 个且无明确主方向；
- 核心证据轴（能力/自主权/亲子关系/学校/社交）仍缺 ≥ 2 条；
- 家长刚提供的信息与现有候选方向矛盾，需要新分支；
- 家长使用了强标签但尚未拆解为可验证事实。

### 生成理解卡条件

- 1 个高价值代理事实 + 1 个家长语言信号指向同一分支；
- 2 个中高价值事实指向同一分支；
- 家长一次性提供大量生活事实；
- 当前判断已能解释孩子 ≥ 2 个表面行为；
- 家长明确要求总结；
- 达到最大追问轮次（8 轮）。

### 交给日常 Agent 的信息

| 信息 | 用途 |
|------|------|
| handoffSummary | 日常 Agent 加载为初始上下文，理解孩子核心模式 |
| profileUpdateCandidates | 写入 profile_entries 表，日常 Agent 每次对话前加载活跃画像 |
| pendingObservations | 写入 long_term_goals 表，日常 Agent 在后续对话中继续观察 |
| family_state.diagnosis_completed = true | 路由层判断该家庭走日常 Agent |

---

## 二、输入字段

```jsonc
{
  // === 必填 ===
  "family_id": "string",           // 家庭唯一标识，用于路由和画像查询
  "session_id": "string",          // 当前会话标识，用于 checkpointer 隔离
  "user_message": "string",        // 家长本轮输入

  // === 必填，由后端从 checkpointer/DB 查询后注入 ===
  "conversation_history": [         // 当前 session 的对话历史
    {
      "role": "user | assistant",
      "content": "string",
      "metadata": {}                // 可选：本轮 tool_calls 摘要
    }
  ],

  // === 可选，由后端按状态注入 ===
  "diagnosis_turn_count": 0,        // 当前 session 已进行的诊断轮次数，默认 0
  "existing_child_profile_summary": "string | null",  // 已有画像摘要，无画像时 null
  "questionnaire_status": "none | pending | completed",  // 问卷状态
  "child_questionnaire_summary": "string | null",     // 问卷摘要，未完成时 null
  "parent_basic_info": {            // 可选，注册时收集
    "relationship": "string",       // 妈妈/爸爸/其他
    "education_level": "string"     // 可选
  },
  "child_basic_info": {             // 可选，注册时收集
    "age": "number | null",
    "grade": "string | null",
    "gender": "string | null"
  },
  "previous_pending_questions": [   // 上次诊断遗留的待追问问题
    "string"
  ]
}
```

### 字段注入逻辑

后端在调用 Agent 前执行：

```
1. 查 family_state 表 → diagnosis_turn_count, questionnaire_status
2. 查 profile_entries 表 → existing_child_profile_summary（活跃条目拼接）
3. 查 child_questionnaires 表 → child_questionnaire_summary
4. 查 long_term_goals 表 → previous_pending_questions
5. 拼接 context_prefix 注入 system prompt
```

---

## 三、每轮返回的 message_type

### 3.1 diagnostic_question — 继续追问

**触发条件**：证据不足，需要获取更多信息。

**字段结构**：
```json
{
  "message_type": "diagnostic_question",
  "content": "string",                     // 家长可见的追问文本
  "internal_state": {
    "active_candidates": [                  // 当前活跃的候选方向
      {
        "label": "string",                 // 如"能力断层型"
        "weight": 0.0,                     // 0-1，当前置信度
        "evidence_for": ["string"],        // 支持证据
        "evidence_against": ["string"]     // 反证
      }
    ],
    "diagnosis_turn_count": 3,             // 更新后的轮次
    "info_sufficiency_score": 0.45         // 当前信息充分度
  }
}
```

**前端展示**：显示 content 文本，等待家长回复。

---

### 3.2 child_understanding_card — 生成理解卡

**触发条件**：证据充分或达到最大轮次。

**字段结构**：见第四节完整定义。

**前端展示**：渲染为理解卡组件，含标题、子标题、各字段分区、建议回复可展开。

---

### 3.3 normal_reply — 普通回复

**触发条件**：家长输入为寒暄、简单事实补充、情绪承接，不需要追问或诊断卡。

**字段结构**：
```json
{
  "message_type": "normal_reply",
  "content": "string",
  "internal_state": {
    "diagnosis_turn_count": 3,
    "info_sufficiency_score": 0.45
  }
}
```

**前端展示**：普通聊天气泡。

---

### 3.4 memory_note — 画像提醒

**触发条件**：对话中出现了重要画像信号但本轮不输出诊断卡，需要后端临时记录。

**字段结构**：
```json
{
  "message_type": "memory_note",
  "content": "string",                     // 家长可见的回复文本（正常回复）
  "memory_candidates": [                   // 临时画像候选，后端写入 profile_entries（status=unconfirmed）
    {
      "dimension": "string",
      "summary": "string",
      "evidence": ["string"],
      "confidence": "low | medium | high"
    }
  ]
}
```

**前端展示**：显示 content 文本（与 normal_reply 相同），memory_candidates 不对家长展示。

---

### 3.5 precision_warning — 判断精度警告

**触发条件**：当前判断过于尖锐但证据不充分，需要提醒后端/日常 Agent 注意。

**字段结构**：
```json
{
  "message_type": "precision_warning",
  "content": "string",                     // 家长可见的回复文本（含模糊化处理）
  "warning": {
    "original_judgment": "string",         // 内部原始判断
    "softened_judgment": "string",         // 已模糊化后的家长可见判断
    "reason": "string",                    // 为什么需要模糊化
    "required_evidence": ["string"]        // 还需要什么证据才能确认
  }
}
```

**前端展示**：显示 content 文本，warning 不对家长展示。

---

### 3.6 fallback — 兜底回复

**触发条件**：家长输入完全超出诊断范围（如技术问题、闲聊、投诉）；或 Agent 内部错误。

**字段结构**：
```json
{
  "message_type": "fallback",
  "content": "string",                     // 友好的兜底回复
  "fallback_reason": "out_of_scope | internal_error | timeout"
}
```

**前端展示**：普通聊天气泡，可能含引导语。

---

## 四、孩子理解卡 JSON 字段

```json
{
  "card_id": "string",                     // 唯一标识，格式 card_{family_id}_{timestamp}
  "title": "string",                       // 一句话概括，如"他不是不想做，是一写就发现自己接不上"
  "subtitle": "string",                    // 补充说明，如"作业启动困难 + 被评价防御的组合"
  "child_current_state": "string",         // 必填。孩子当前处境描述（从孩子视角）
  "easily_misunderstood_part": "string",   // 必填。家长容易看反的地方
  "child_core_need": "string",             // 必填。孩子最核心的需要（不是愿望，是需要）
  "family_interaction_pattern": "string",  // 必填。亲子互动中反复出现的闭环
  "next_observation_point": "string",      // 必填。后续最值得观察的一个点
  "confidence_level": "high | medium | low", // 必填。整体判断置信度
  "evidence_summary": [                    // 必填。支撑判断的关键事实
    {
      "fact": "string",                    // 家长描述中的可验证事实
      "interpretation": "string",          // 这个事实指向什么
      "source_turn": 3                     // 来自第几轮对话
    }
  ],
  "possible_meanings": [                   // 必填。候选方向及权重
    {
      "label": "string",                   // 方向标签
      "percentage": 80,                    // 权重百分比
      "description": "string"              // 详细描述
    }
  ],
  "risk_warning": "string",                // 必填。误读风险
  "suggested_replies": {                   // 必填。三种表达方向
    "conservative": {
      "reply": "string",                   // 稳妥版
      "reason": "string"                   // 推荐理由
    },
    "progressive": {
      "reply": "string",                   // 推进版
      "reason": "string"
    },
    "boundary": {
      "reply": "string",                   // 边界版
      "reason": "string"
    }
  },
  "profile_update_candidates": [           // 必填。见第五节
    {}
  ],
  "pending_observations": [                // 必填。后续待观察点
    "string"
  ],
  "handoff_summary": {                     // 必填。交接给日常 Agent 的摘要
    "initial_understanding": "string",
    "key_child_patterns": ["string"],
    "parent_concerns": ["string"],
    "family_interaction_hypotheses": ["string"],
    "suggested_daily_mode": "memory_aware_daily_chat"
  },
  "feedback_actions": [                    // 可选。理解卡展示后的交互按钮
    {
      "action_id": "agree",               // 家长认同
      "label": "这说到了点子上"
    },
    {
      "action_id": "partial",              // 部分认同
      "label": "有一部分对"
    },
    {
      "action_id": "disagree",             // 不认同
      "label": "不太对"
    }
  ]
}
```

### 字段与前端展示对应

| 字段 | 展示方式 |
|------|---------|
| title | 卡片主标题，大字 |
| subtitle | 副标题，灰色小字 |
| child_current_state | 独立区块，"孩子现在的处境" |
| easily_misunderstood_part | 高亮区块，"你可能看反的地方" |
| child_core_need | 独立区块，"他最需要的" |
| family_interaction_pattern | 独立区块，"你们之间可能形成的循环" |
| possible_meanings | 横向条形图，百分比可视化 |
| risk_warning | 警告色区块 |
| suggested_replies | 三栏卡片，各含回复文本+推荐理由 |
| next_observation_point | 底部提示条 |
| feedback_actions | 卡片底部三个按钮 |

---

## 五、初始孩子画像候选字段

Agent 不直接写数据库，只返回 candidates，由后端统一写入 `profile_entries` 表。

```json
{
  "profile_update_candidates": [
    {
      "dimension": "emotion_response | communication_style | social | academic | family_dynamic | other",
      "summary": "string",                  // 必填。画像描述（不能出现家长标签原词）
      "evidence": ["string"],               // 必填。来自家长描述的原始依据
      "confidence": "low | medium | high",  // 必填。当前置信度
      "source": "diagnosis_agent",           // 必填。固定值
      "operation": "add | merge | correct",  // 必填。操作类型
      "suggested_status": "initial_hypothesis | unconfirmed | active"
    }
  ]
}
```

### operation 语义

| operation | 含义 | 后端处理 |
|-----------|------|---------|
| `add` | 新增画像条目 | INSERT 到 profile_entries |
| `merge` | 与已有条目合并 | 找到同 dimension+相似 summary 的条目，evidence_count+1 |
| `correct` | 纠正已有条目 | 找到同 dimension 条目，降权旧条目，新增纠正条目 |

### 硬约束

- summary 中不能出现家长标签原词（懒/不自觉/沉迷/叛逆/玻璃心/没羞耻心/没救/自私）；
- 必须转为可验证的孩子反应模式描述；
- evidence 必须来自家长描述中的具体事实，不能编造。

---

## 六、诊断完成条件

### 信息充分度评分

Agent 内部维护 `info_sufficiency_score`（0-1），每轮更新。评分依据：

```
info_sufficiency = 
  0.3 × (已确认证据轴数 / 总关键轴数)     // 覆盖度
+ 0.3 × (主方向权重 - 次方向权重)           // 方向收敛度
+ 0.2 × (家长语言信号数 ≥ 1 ? 1 : 0)      // 家长盲点识别
+ 0.2 × (反证已检查 ? 1 : 0)              // 反证完整性
```

- 总关键轴：能力/自主权/亲子关系/学校/社交，共 5 个
- 已确认 = 至少有一条直接或间接证据
- 方向收敛 = possibleMeanings[0].percentage - possibleMeanings[1].percentage

### 出卡阈值

| 条件 | 阈值 |
|------|------|
| info_sufficiency ≥ 0.65 | 可出标准理解卡 |
| info_sufficiency 0.40—0.65 | 可出暂定理解卡（confidence_level = medium） |
| info_sufficiency < 0.40 | 继续追问，不出卡 |
| diagnosis_turn_count ≥ 8 | 强制出低置信度理解卡（confidence_level = low） |
| 家长明确要求总结 | 无论 score 多少，立即出卡 |

### 最大追问轮次

- 默认上限：8 轮（diagnosis_turn_count ≥ 8 强制出卡）
- 如果轮次到达但 info_sufficiency < 0.40：
  - 出卡，confidence_level = low
  - evidence_summary 中标注"信息不足方向"
  - pendingObservations 包含所有未排除的候选方向
  - risk_warning 标注"当前判断置信度较低，后续需持续观察"

### 轮次计数规则

- 每次家长输入（user_message）+ Agent 回复 = 1 轮
- 寒暄/事实补充/情绪承接也计入轮次
- 工具调用不计入轮次

---

## 七、完整返回 JSON 示例

### 7.1 继续追问

```json
{
  "message_type": "diagnostic_question",
  "content": "咱先不急着说懒哈。他写作业的时候，是一开始就东摸西摸不想动，还是写到某个地方卡住以后才开始磨？这两个情况背后的原因完全不一样。",
  "internal_state": {
    "active_candidates": [
      {
        "label": "能力断层型",
        "weight": 0.45,
        "evidence_for": ["数学写到应用题会停下来"],
        "evidence_against": ["家长说所有作业都拖"]
      },
      {
        "label": "休息权/自主权争夺",
        "weight": 0.30,
        "evidence_for": ["写完就拿手机说是唯一放松"],
        "evidence_against": []
      },
      {
        "label": "被评价防御",
        "weight": 0.15,
        "evidence_for": [],
        "evidence_against": []
      }
    ],
    "diagnosis_turn_count": 3,
    "info_sufficiency_score": 0.38
  }
}
```

### 7.2 生成孩子理解卡

```json
{
  "message_type": "child_understanding_card",
  "content": "**您的孩子理解卡已生成**\n\n**他不是不想做，是一写就发现自己接不上**\n作业启动困难 + 被评价防御的组合\n\n**孩子现在的处境**：他不是懒。他在作业启动阶段阻力很大，很可能是某类任务的基础已经断了，一进入任务就卡住；同时他怕被你发现"我不会"，所以用拖延保护自己不那么快暴露。\n\n**你可能看反的地方**：你看到的是磨蹭，他在躲的是被证明不行的那个瞬间。你越催他快，他越觉得你在盯着他的短板。\n\n**他最需要的**：不是被催更快，而是被允许说出哪块不会，且说出来之后不会被评价。\n\n**你们之间可能形成的循环**：你催 → 他拖 → 你更急 → 他更防御 → 你贴标签 → 他关闭表达\n\n**可能的判断方向**：\n- 60% 能力断层 + 启动困难\n- 25% 休息权/自主权争夺\n- 15% 被评价防御\n\n**风险提示**：最大的风险是误读"拖延"为"懒"。如果将拖延误读为懒并采取加压催促，极有可能触发孩子进一步关闭表达，从拖延退避为表面配合/内在撤退。\n\n**建议回复**：\n【稳妥版】"咱先不急着赶速度哈，你哪一块觉得最难？说出来我帮你想想办法，肯定不说你。" → 推荐理由：先给安全感，降低被评价防御\n【推进版】"我发现你每次写到数学后面几道大题就会停住，是不是那块有点接不上？接不上很正常的，咱一起看看。" → 推荐理由：直接指出具体卡点，降低被定义感\n【边界版】"你要是今天实在写不动，就先放一放。明天我帮你跟老师说一声，不扣你分。" → 推荐理由：给兜底空间，打破"写不完=被批评"的闭环",
  "card": {
    "card_id": "card_test-family_1719000000",
    "title": "他不是不想做，是一写就发现自己接不上",
    "subtitle": "作业启动困难 + 被评价防御的组合",
    "child_current_state": "他在作业启动阶段阻力很大，很可能是某类任务的基础已经断了，一进入任务就卡住；同时他怕被发现'我不会'，所以用拖延保护自己不那么快暴露。",
    "easily_misunderstood_part": "你看到的是磨蹭，他在躲的是被证明不行的那个瞬间。你越催他快，他越觉得你在盯着他的短板。",
    "child_core_need": "不是被催更快，而是被允许说出哪块不会，且说出来之后不会被评价。",
    "family_interaction_pattern": "你催 → 他拖 → 你更急 → 他更防御 → 你贴标签 → 他关闭表达",
    "next_observation_point": "继续观察他拖延主要出现在任务开始前，还是写到某一类题后。如果写到某类题后卡住，更确认能力断层。",
    "confidence_level": "medium",
    "evidence_summary": [
      {
        "fact": "家长说孩子作业磨蹭",
        "interpretation": "磨蹭可能是启动困难的外在表现",
        "source_turn": 1
      },
      {
        "fact": "数学写到应用题会停下来发呆",
        "interpretation": "特定题型卡住 → 能力断层的强信号",
        "source_turn": 2
      },
      {
        "fact": "写完就拿手机说是唯一放松",
        "interpretation": "手机可能承担恢复/逃避功能，但出现时机在任务完成后",
        "source_turn": 3
      }
    ],
    "possible_meanings": [
      {
        "label": "能力断层 + 启动困难",
        "percentage": 60,
        "description": "某类任务基础断了，一进入就卡住，拖延是绕开暴露"
      },
      {
        "label": "休息权/自主权争夺",
        "percentage": 25,
        "description": "做完也不结束，手机是争取自己时间的方式"
      },
      {
        "label": "被评价防御",
        "percentage": 15,
        "description": "怕被说不行，拖延保护自己不暴露"
      }
    ],
    "risk_warning": "最大的风险是误读拖延为懒。如果将拖延误读为懒并采取加压催促，极有可能触发孩子进一步关闭表达，从拖延退避为表面配合/内在撤退。",
    "suggested_replies": {
      "conservative": {
        "reply": "咱先不急着赶速度哈，你哪一块觉得最难？说出来我帮你想想办法，肯定不说你。",
        "reason": "先给安全感，降低被评价防御"
      },
      "progressive": {
        "reply": "我发现你每次写到数学后面几道大题就会停住，是不是那块有点接不上？接不上很正常的，咱一起看看。",
        "reason": "直接指出具体卡点，降低被定义感"
      },
      "boundary": {
        "reply": "你要是今天实在写不动，就先放一放。明天我帮你跟老师说一声，不扣你分。",
        "reason": "给兜底空间，打破写不完=被批评的闭环"
      }
    },
    "profile_update_candidates": [
      {
        "dimension": "academic",
        "summary": "孩子在作业启动阶段阻力较大，数学应用题尤其容易卡住，具体原因仍需观察（能力断层 vs 启动困难）",
        "evidence": ["家长说作业磨蹭", "数学应用题会停住发呆"],
        "confidence": "medium",
        "source": "diagnosis_agent",
        "operation": "add",
        "suggested_status": "unconfirmed"
      },
      {
        "dimension": "emotion_response",
        "summary": "孩子可能在被评价时容易防御，表现为拖延和回避暴露不会的内容",
        "evidence": ["家长越催越磨蹭", "说懒就不高兴"],
        "confidence": "low",
        "source": "diagnosis_agent",
        "operation": "add",
        "suggested_status": "initial_hypothesis"
      },
      {
        "dimension": "family_dynamic",
        "summary": "亲子互动中可能存在催促-拖延-贴标签的循环，孩子表达逐渐关闭",
        "evidence": ["家长用懒/不自觉标签", "孩子拿手机说是唯一放松"],
        "confidence": "medium",
        "source": "diagnosis_agent",
        "operation": "add",
        "suggested_status": "unconfirmed"
      }
    ],
    "pending_observations": [
      "继续观察孩子拖延主要出现在任务开始前，还是写到某一类题后",
      "观察孩子是否只在面对家长追问时沉默，在学校或同伴面前是否也同样关闭表达",
      "观察手机使用出现时机：任务前/任务中/任务后，不同时机的功能可能不同"
    ],
    "handoff_summary": {
      "initial_understanding": "孩子作业启动困难，可能与能力断层和被评价防御有关，需要继续观察具体卡点和手机使用时机",
      "key_child_patterns": [
        "作业启动阶段阻力大",
        "数学应用题容易卡住",
        "被催促时防御升级"
      ],
      "parent_concerns": [
        "反复担心孩子懒/不自觉",
        "对孩子磨蹭感到焦虑"
      ],
      "family_interaction_hypotheses": [
        "催促-拖延-贴标签循环：家长催促 → 孩子拖延升级 → 家长贴标签 → 孩子关闭表达"
      ],
      "suggested_daily_mode": "memory_aware_daily_chat"
    },
    "feedback_actions": [
      {
        "action_id": "agree",
        "label": "这说到了点子上"
      },
      {
        "action_id": "partial",
        "label": "有一部分对"
      },
      {
        "action_id": "disagree",
        "label": "不太对"
      }
    ]
  }
}
```
