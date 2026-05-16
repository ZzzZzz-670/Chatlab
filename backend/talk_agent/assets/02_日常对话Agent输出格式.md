# 02_日常对话Agent输出格式.md

## 一、文档目的

本文定义「对话实验室」日常对话 Agent 的输出格式。

日常 Agent 每轮不能只返回一段自然语言。它需要同时返回：

1. 给家长看的自然回复；
2. 给前端渲染用的展示字段；
3. 给后端处理的结构化候选更新；
4. 给记忆系统使用的孩子、家长、家庭互动更新候选；
5. 给调试和质量评估使用的理解引擎摘要。

核心原则：

> 家长看到的是自然回复；前端根据结构化字段渲染卡片和小字；后端根据候选更新判断是否真实写入记忆库。所有“已记录 / 已更新 / 已调整”提示都必须来自真实后端写入，不能由前端伪造。

---

## 二、输出设计总原则

## 1. 前台轻，后台准

日常 Agent 的前台输出要自然、轻、短，不要像报告。

但后台输出必须结构化，能支持：

- 成长信号识别；
- 孩子画像更新；
- 家长长期关注更新；
- 家长沟通偏好更新；
- 家庭互动模式更新；
- 待观察点生成；
- 纠偏；
- 沟通预演保存；
- 阶段复盘触发；
- 后端调试和质量评估。

---

## 2. 功能层不变，理解层作为内部字段

日常 Agent 的产品功能仍然是：

- 轻回应；
- 成长信号；
- 记忆沉淀；
- 孩子小档案更新；
- 家长长期关注；
- 沟通预演；
- 纠偏；
- 周期性小观察。

但每轮输出中要包含 `understanding_engine`，用于记录本轮内部理解结果。

`understanding_engine` 不展示给家长，只用于后端和调试。

---

## 3. Agent 返回的是“候选”，不是最终写入结果

Agent 不直接写数据库。

Agent 返回：

```text
候选更新
```

后端 ProfileService / MemoryService 负责：

- 判断新增、合并、增强、降权、纠偏；
- 写入对应数据表；
- 生成最终写入结果；
- 返回最终 `memory_note`；
- 控制前端是否展示“已记录 / 已更新 / 已调整”。

---

## 4. memory_note 必须来自真实写入

前端小字如：

- 已记录一个近期变化；
- 已更新孩子小档案；
- 已加入后续观察；
- 已加入长期观察；
- 已调整前面的一个判断；
- 已存到预演记录；

必须对应后端真实写入或真实更新。

Agent 可以给出 `memory_note_suggestion`，但前端最终展示应以后端返回的 `memory_note_final` 为准。

---

## 三、输出总体结构

推荐每轮输出结构：

```json
{
  "reply": {
    "message_type": "normal_reply",
    "ui_badge": "已调用孩子画像",
    "content": "给家长看的自然回复"
  },
  "understanding_engine": {
    "input_decomposition": {
      "facts": [],
      "child_behaviors": [],
      "parent_emotions": [],
      "parent_interpretations": [],
      "parent_goals": [],
      "missing_key_info": []
    },
    "child_understanding": {
      "possible_child_experience": "",
      "candidate_explanations": [],
      "selected_explanation": "",
      "basis_from_child_profile": [],
      "confidence": 0.0
    },
    "parent_understanding": {
      "possible_parent_concern": "",
      "parent_pattern_candidate": "",
      "parent_goal_detected": "",
      "basis_from_parent_profile": [],
      "confidence": 0.0
    },
    "family_interaction_understanding": {
      "parent_child_mismatch": "",
      "interaction_pattern_candidate": "",
      "related_previous_pattern": "",
      "confidence": 0.0
    },
    "memory_decision": {
      "should_write": false,
      "write_types": [],
      "reason": ""
    }
  },
  "memory_note_suggestion": {
    "show": false,
    "text": "",
    "detail": ""
  },
  "profile_update_candidates": [],
  "growth_record_candidates": [],
  "pending_observation_candidates": [],
  "long_term_goal_updates": [],
  "parent_profile_candidates": [],
  "family_interaction_candidates": [],
  "correction_candidates": [],
  "rehearsal_save_candidate": null,
  "actions": [],
  "next_question": null,
  "should_trigger_review": false,
  "review_reason": ""
}
```

---

## 四、reply 字段

`reply` 是前端直接展示给家长的内容。

```json
{
  "message_type": "normal_reply",
  "ui_badge": "已调用孩子画像",
  "content": "这个变化挺值得记一下。您之前提到过，孩子平时不是特别愿意主动聊学校，所以这次愿意说，至少说明当时他对您是有一点打开的。"
}
```

---

## 五、message_type 类型

| message_type | 使用场景 | 前端展示 |
|---|---|---|
| `normal_reply` | 普通日常回应 | 普通 AI 气泡 |
| `growth_signal` | 识别到成长变化 | 成长信号样式或普通气泡 + 小字 |
| `communication_rehearsal` | 家长准备和孩子沟通 | 沟通预演卡 |
| `correction_reply` | 调整旧判断 | 纠偏样式 |
| `long_term_goal_update` | 识别长期关注目标 | 普通气泡 + 小字 |
| `questionnaire_summary` | 孩子问卷完成后 | 孩子视角摘要 |
| `stage_review_suggestion` | 建议阶段复盘 | 轻提示，不自动进入大报告 |
| `further_explanation` | 用户点击进一步解释 | 展开解释气泡 |
| `memory_update_reply` | 本轮主要是小档案更新 | 普通气泡 + 更新提示 |
| `parent_pattern_note` | 轻触及家长沟通习惯 | 普通气泡，不显示“家长画像”字样 |

---

## 六、ui_badge 字段

`ui_badge` 是前端可展示的小标识，用来让家长感受到系统正在调用孩子小档案和历史记录。

可选值：

```text
已调用孩子画像
已参考孩子小档案
已结合近期记录
已参考孩子问卷
已结合长期关注
已参考沟通记录
已更新孩子小档案
```

规则：

- 可以显示在 AI 气泡顶部或底部；
- 不要每条都强行展示；
- 涉及孩子状态判断时优先展示；
- 正文里不要机械说“根据孩子画像，我判断”；
- 如果只是普通安抚或简单问候，可以不展示。

---

## 七、understanding_engine 字段

`understanding_engine` 是日常 Agent 的内部理解摘要。

它不展示给家长，不参与普通前端渲染，只给后端、日志、调试和质量评估使用。

它的作用是保证日常 Agent 不只是轻聊天，而是在后台完成：

- 家长输入拆解；
- 孩子视角推理；
- 家长侧理解；
- 亲子差异判断；
- 记忆写入决策。

---

# 八、input_decomposition 字段

用于拆解家长输入。

```json
{
  "input_decomposition": {
    "facts": [
      "孩子今天写完一页作业后拿手机"
    ],
    "child_behaviors": [
      "完成一段任务后拿手机"
    ],
    "parent_emotions": [
      "担心孩子沉迷手机"
    ],
    "parent_interpretations": [
      "家长倾向理解为孩子控制不住手机"
    ],
    "parent_goals": [
      "希望孩子更自觉管理手机"
    ],
    "missing_key_info": [
      "孩子拿手机前是否已经明确完成任务",
      "手机使用时长是否可控"
    ]
  }
}
```

## 1. facts

客观事实。

可写：

```text
孩子写完一页后拿手机。
孩子被问为什么不写时沉默。
孩子说“知道了”，但后续没有执行。
```

不可写：

```text
孩子就是懒。
孩子没有责任感。
孩子沉迷手机。
```

---

## 2. child_behaviors

孩子具体行为。

示例：

```json
"child_behaviors": [
  "作业开始前拖延",
  "被连续追问后沉默",
  "表面答应但后续未执行"
]
```

---

## 3. parent_emotions

家长情绪。

示例：

```json
"parent_emotions": [
  "焦虑",
  "无力",
  "失望",
  "担心"
]
```

规则：

- 家长情绪用于调整回复语气；
- 不写入孩子画像；
- 可作为 `parent_profile_candidates` 的近期状态候选。

---

## 4. parent_interpretations

家长对孩子行为的解释。

示例：

```json
"parent_interpretations": [
  "家长将拖延理解为不自觉",
  "家长将沉默理解为不配合",
  "家长将手机使用理解为沉迷"
]
```

规则：

- 这是家长解释，不是事实；
- 不能直接写入孩子画像；
- 后续要生成候选解释或待观察点。

---

## 5. parent_goals

家长期待或长期目标。

示例：

```json
"parent_goals": [
  "希望孩子提升责任感",
  "希望孩子更能抗压",
  "希望孩子减少手机依赖"
]
```

可进入：

```text
long_term_goal_updates
```

---

## 6. missing_key_info

缺失但影响判断的信息。

示例：

```json
"missing_key_info": [
  "拖延发生在开始前还是写到一半后",
  "手机出现在任务开始前还是完成一段之后",
  "孩子沉默前家长具体说了什么"
]
```

如果缺失信息影响判断，`next_question` 可选择其中最关键的一项。

---

# 九、child_understanding 字段

用于记录孩子视角推理。

```json
{
  "child_understanding": {
    "possible_child_experience": "孩子可能不是单纯不想做，而是在开始前那一下很难推进",
    "candidate_explanations": [
      "启动困难",
      "担心做完后被继续加任务",
      "当前任务暴露短板"
    ],
    "selected_explanation": "启动困难更符合当前信息",
    "basis_from_child_profile": [
      "孩子过去在作业开始前更容易受阻",
      "孩子对任务边界较敏感"
    ],
    "confidence": 0.72
  }
}
```

## 1. possible_child_experience

从孩子视角理解当前事件。

要求：

- 不假装孩子本人；
- 不用绝对语气；
- 不做心理疾病判断；
- 不把孩子行为简单归因为懒、叛逆、不自觉。

推荐写法：

```text
孩子可能先感受到的是又被追问，而不是家长在帮他解决问题。
```

---

## 2. candidate_explanations

内部候选解释。

示例：

```json
"candidate_explanations": [
  "启动困难",
  "任务边界不清",
  "怕暴露短板",
  "用沉默降低冲突"
]
```

规则：

- 可以保留多个候选；
- 前台通常只呈现一个最有用方向；
- 不要把全部候选都讲给家长。

---

## 3. selected_explanation

当前最适合前台表达的解释。

示例：

```json
"selected_explanation": "孩子沉默更可能是在降低冲突，而不是完全没想法"
```

---

## 4. basis_from_child_profile

调用了哪些已有孩子画像或近期记录。

示例：

```json
"basis_from_child_profile": [
  "孩子在被连续追问时容易沉默",
  "近期多次出现表面答应但后续执行弱"
]
```

规则：

- 只写依据摘要；
- 不展示给家长；
- 用于调试 Agent 是否真的调用了画像。

---

## 5. confidence

本轮孩子视角判断置信度。

建议范围：

| 分值 | 含义 | 处理方式 |
|---|---|---|
| 0.0 - 0.4 | 信息不足 | 优先追问或写待观察 |
| 0.4 - 0.65 | 有方向但不稳 | 轻判断 + 待观察 |
| 0.65 - 0.8 | 较稳 | 可轻回应并写候选画像 |
| 0.8 - 1.0 | 多次验证 | 可增强稳定画像 |

---

# 十、parent_understanding 字段

用于记录对家长侧的理解。

```json
{
  "parent_understanding": {
    "possible_parent_concern": "家长担心孩子长期缺少自我管理能力",
    "parent_pattern_candidate": "家长在作业场景中倾向通过连续确认原因来推进问题",
    "parent_goal_detected": "责任感与自我管理",
    "basis_from_parent_profile": [
      "家长多次提到孩子不自觉",
      "家长反复关注作业和手机"
    ],
    "confidence": 0.68
  }
}
```

## 1. possible_parent_concern

家长真正担心的东西。

示例：

```text
家长表面在说手机，深层更担心孩子缺少自我管理。
```

---

## 2. parent_pattern_candidate

家长沟通或理解习惯候选。

可写：

```text
家长在作业场景中容易连续确认原因。
家长倾向将孩子的拖延理解为态度问题。
家长高度关注成绩稳定和漏洞补齐。
```

不可写：

```text
家长控制欲强。
家长焦虑型。
家长沟通方式有问题。
```

---

## 3. parent_goal_detected

识别到的长期目标。

示例：

```text
责任感与抗压能力
心理健康与人格健全
成绩稳定与学习主动性
```

---

## 4. basis_from_parent_profile

调用了哪些家长侧历史信息。

示例：

```json
"basis_from_parent_profile": [
  "家长此前提到希望孩子更有责任感",
  "家长近期多次关注高二成绩压力"
]
```

---

## 5. confidence

家长侧理解置信度。

规则：

- 单次表达只作为候选；
- 多次重复后增强权重；
- 不写负面标签；
- 优先服务于更贴合的回应和长期关注更新。

---

# 十一、family_interaction_understanding 字段

用于记录亲子差异和互动循环判断。

```json
{
  "family_interaction_understanding": {
    "parent_child_mismatch": "家长想确认原因，孩子可能先感受到被连续追问",
    "interaction_pattern_candidate": "追问—沉默循环",
    "related_previous_pattern": "此前记录过孩子在被连续追问时容易沉默",
    "confidence": 0.74
  }
}
```

## 1. parent_child_mismatch

家长意图和孩子接收之间的差异。

常见表达：

```text
家长想确认原因，孩子可能先感受到被追问。
家长想补短板，孩子可能先感到休息被压缩。
家长想提高效率，孩子可能担心效率越高任务越多。
家长想让孩子负责，孩子可能感到自己一直被不信任。
```

---

## 2. interaction_pattern_candidate

家庭互动循环候选。

可选值：

```text
追问—沉默循环
加任务—磨蹭循环
认错—失信循环
期待—压力循环
手机冲突循环
信任下降循环
边界争夺循环
暂不确定
```

---

## 3. related_previous_pattern

和历史家庭互动记录的关系。

示例：

```text
与此前“追问—沉默循环”一致。
与此前“休息边界敏感”有关。
与此前记录不同，可能需要纠偏。
```

---

## 4. confidence

互动循环判断置信度。

规则：

- 单次事件不直接写成稳定家庭模式；
- 多次出现才增强；
- 家长确认后可提高权重；
- 家长否定后应降权或改写为待观察。

---

# 十二、memory_decision 字段

用于说明本轮是否建议写入记忆，以及写入类型。

```json
{
  "memory_decision": {
    "should_write": true,
    "write_types": [
      "growth_record",
      "pending_observation"
    ],
    "reason": "孩子本轮出现相对旧画像有意义的主动表达，但具体稳定性仍需后续观察"
  }
}
```

## write_types 可选值

```text
growth_record
profile_entry
pending_observation
long_term_goal
parent_profile
family_interaction_pattern
correction
rehearsal_record
none
```

---

# 十三、memory_note_suggestion 字段

`memory_note_suggestion` 是 Agent 对前端小字的建议。

最终是否展示，必须以后端真实写入结果为准。

```json
{
  "show": true,
  "text": "已记录一个近期变化",
  "detail": "孩子今天主动提到学校，建议写入 growth_records。"
}
```

## 可用 text

| text | 对应后端动作 |
|---|---|
| 已记录一个近期变化 | 写入 `growth_records` |
| 已更新孩子小档案 | 写入或合并 `profile_entries` |
| 已加入后续观察 | 写入 `pending_observations` |
| 已加入长期观察 | 写入或更新 `long_term_goals` |
| 已调整前面的一个判断 | 写入 `correction_logs` 或 `profile_update_log` |
| 已存到预演记录 | 写入 `rehearsal_records` |
| 已补充孩子视角 | 写入 `questionnaire_records` 和相关画像 |
| 已更新沟通理解 | 写入 `family_interaction_patterns` 或 `parent_profile` |

规则：

- Agent 只能建议；
- 后端写入成功后再返回最终 memory_note；
- 没有真实写入时，前端不展示小字。

---

# 十四、profile_update_candidates

用于更新孩子画像。

```json
[
  {
    "action": "add_entry",
    "category": "academic",
    "content": "孩子在作业开始前阻力较大，进入状态后不一定差",
    "source": "chat",
    "confidence": 0.75,
    "evidence": "家长本轮提到孩子坐下前一直拖，写起来后能完成一段"
  }
]
```

## action 类型

| action | 含义 |
|---|---|
| `add_entry` | 新增画像条目 |
| `merge_entry` | 合并到已有画像 |
| `strengthen_entry` | 增强已有画像权重 |
| `deprecate_entry` | 降低旧画像权重 |
| `update_profile` | 更新孩子核心画像字段 |
| `split_entry` | 将过于笼统的旧判断拆分为多个场景判断 |

---

## category 类型

| category | 含义 |
|---|---|
| `academic` | 学习状态、作业、科目压力 |
| `emotional` | 情绪反应、压力表现 |
| `communication` | 沟通偏好、表达方式 |
| `family_dynamic` | 家庭互动模式 |
| `rest_boundary` | 休息边界、娱乐恢复 |
| `interest` | 兴趣爱好、能量来源 |
| `social` | 学校、同伴、社交关系 |
| `self_management` | 自我管理、责任感、主动性 |
| `confidence_self_image` | 自尊、优秀感、自我形象 |
| `task_barrier` | 任务启动、任务拆解、暴露短板 |

规则：

- 单次信息不要直接写成稳定画像；
- 不确定时写入成长记录或待观察点；
- `confidence < 0.6` 的候选默认不写入稳定画像；
- 最终是否写入由后端 ProfileService 决定。

---

# 十五、growth_record_candidates

用于记录近期成长变化。

```json
[
  {
    "scene_type": "school",
    "content": "孩子今天主动提到学校里的事",
    "signal_type": "主动表达",
    "source": "chat",
    "importance": "medium",
    "difference_from_previous_profile": "此前孩子较少主动聊学校"
  }
]
```

## 适合写入的内容

- 孩子主动表达；
- 孩子情绪反应变化；
- 孩子学习启动方式变化；
- 孩子愿意沟通；
- 孩子抵触减少；
- 手机使用方式变化；
- 出现新的兴趣或恢复方式；
- 家庭互动出现有效经验；
- 家长长期目标相关的微小变化。

## 不适合写入的内容

- 家长单纯情绪宣泄；
- 没有具体事件的判断；
- 一次性强情绪评价；
- “孩子就是懒 / 不自觉 / 叛逆”这类缺少事实的判断。

---

# 十六、pending_observation_candidates

用于写入待观察点。

```json
[
  {
    "content": "需要继续确认孩子拿手机更偏向逃避学习，还是完成任务后的恢复方式",
    "related_scene": "手机与休息",
    "source": "chat",
    "priority": "medium",
    "distinguishes_between": [
      "学习前逃避压力",
      "完成任务后的恢复需求"
    ]
  }
]
```

适合写入待观察点的情况：

- 信息还不够，但方向重要；
- 家长描述中出现两种可能；
- 新信息可能改变旧判断；
- 孩子问卷和家长观察不完全一致；
- 长期目标需要后续场景验证；
- 旧诊断卡中的判断需要继续验证。

前端小字：

```text
已加入后续观察
```

---

# 十七、long_term_goal_updates

用于更新家长长期关注目标。

```json
[
  {
    "action": "add_or_weight",
    "goal_name": "责任感与抗压能力",
    "goal_category": "resilience",
    "source": "parent_focus",
    "weight_delta": 0.15,
    "reason": "家长明确提到希望孩子更有责任感和抗压能力",
    "related_scenes": [
      "作业启动",
      "手机规则",
      "考试复盘",
      "周末安排"
    ]
  }
]
```

## goal_category 类型

| goal_category | 示例 |
|---|---|
| `academic` | 成绩稳定、学习主动性 |
| `resilience` | 抗压能力、责任感 |
| `mental_health` | 心理健康、情绪稳定 |
| `relationship` | 亲子信任、沟通改善 |
| `well_rounded_growth` | 人格健全、综合素质 |
| `self_management` | 自律、自我安排 |
| `interest_development` | 兴趣发展、长期动力 |
| `social` | 社交能力、同伴关系 |

规则：

- 同名目标不重复新增，只提高权重；
- 家长多次提及，权重上升；
- 后续相关场景中可自然带回；
- 写入成功后返回 memory_note：`已加入长期观察：xxx`。

---

# 十八、parent_profile_candidates

用于更新家长侧理解。

```json
[
  {
    "action": "add_or_weight",
    "category": "communication_style",
    "content": "家长在作业场景中倾向通过连续确认原因来推进问题",
    "source": "chat",
    "confidence": 0.65,
    "evidence": "家长多次提到追问孩子为什么不写"
  }
]
```

## category 类型

| category | 含义 |
|---|---|
| `communication_style` | 家长沟通习惯 |
| `concern_source` | 家长焦虑来源 |
| `long_term_focus` | 家长长期关注 |
| `advice_preference` | 家长建议偏好 |
| `emotional_state` | 家长近期承受状态 |
| `interpretation_style` | 家长常用解释方式 |
| `decision_style` | 家长做教育决策的倾向 |

规则：

- 不写负面标签；
- 不写“控制欲强”“过度焦虑”；
- 只写可观察、可服务后续回复的描述；
- 用于让 Agent 后续更贴合家长，而不是评价家长。

---

# 十九、family_interaction_candidates

用于记录家庭互动模式。

```json
[
  {
    "action": "add_or_weight",
    "pattern_name": "追问—沉默循环",
    "content": "家长越想确认原因，越容易连续追问；孩子在这种场景下更容易沉默或表面答应",
    "source": "chat",
    "confidence": 0.72,
    "evidence": "本轮和此前多次提到被追问后沉默"
  }
]
```

## pattern_name 可选值

```text
追问—沉默循环
加任务—磨蹭循环
认错—失信循环
期待—压力循环
手机冲突循环
信任下降循环
边界争夺循环
暂不确定
```

规则：

- 单次事件不写稳定互动模式；
- 两次以上相似场景可写候选；
- 家长确认后提高权重；
- 家长否定后降权或转待观察；
- 前台不要说“系统识别到家庭互动循环”。

---

# 二十、correction_candidates

用于调整旧判断。

```json
[
  {
    "old_judgment": "孩子拿手机主要是逃避学习",
    "new_judgment": "孩子拿手机可能更偏向完成一段任务后的恢复方式",
    "reason": "最近两次家长都提到孩子是在完成一段任务后拿手机",
    "affected_profile_keywords": [
      "手机",
      "逃避学习",
      "休息边界"
    ],
    "correction_type": "narrow_scope",
    "confidence": 0.7
  }
]
```

## correction_type 可选值

| correction_type | 含义 |
|---|---|
| `deprecate_old` | 降低旧判断权重 |
| `replace_old` | 用新判断替换旧判断 |
| `narrow_scope` | 旧判断缩小适用范围 |
| `split_judgment` | 将旧判断拆成多个场景判断 |
| `add_exception` | 增加例外情况 |

触发情况：

- 家长点“不太像”；
- 家长明确否定；
- 新信息和旧画像方向不同；
- 孩子问卷和家长观察不同；
- 多次新记录显示旧判断不再适用。

前端小字：

```text
已调整前面的一个判断
```

正文推荐表达：

```text
我改一下前面的理解。这个信息会让之前那个判断更谨慎一点。
```

---

# 二十一、rehearsal_save_candidate

用于沟通预演保存。

```json
{
  "topic": "周末是否加英语课",
  "parent_goal": "补英语短板",
  "child_perspective_summary": "孩子可能先感到周末休息时间被压缩",
  "parent_child_mismatch": "家长在谈补弱，孩子可能先感到被安排",
  "suggested_direction": "先从英语最近哪一块吃力聊起，再一起确认要不要补、怎么补",
  "possible_misunderstanding": "像“必须补”这类表达，孩子容易先理解成自己又被安排了",
  "source_message_id": "msg_123"
}
```

规则：

- 沟通预演不给家长照念原话；
- 保存的是预演主题、家长目标、孩子视角、亲子差异、表达方向、可能误会；
- 点击“存到预演记录”后，后端真实写入；
- 写入成功后返回 memory_note：`已存到预演记录`。

---

# 二十二、actions 字段

前端按钮由 `actions` 控制。

```json
[
  {
    "label": "有点像",
    "action": "confirm"
  },
  {
    "label": "不太像",
    "action": "reject"
  },
  {
    "label": "补充一点",
    "action": "add_info"
  },
  {
    "label": "存到小档案",
    "action": "save_to_profile"
  }
]
```

## 通用 actions

| label | action | 用途 |
|---|---|---|
| 有点像 | `confirm` | 提高相关画像权重 |
| 不太像 | `reject` | 降低判断权重，触发纠偏 |
| 补充一点 | `add_info` | 用户补充事实 |
| 存到小档案 | `save_to_profile` | 保存重要内容 |
| 复制 | `copy` | 复制当前回复 |
| 存到预演记录 | `save_rehearsal` | 保存沟通预演 |
| 进一步解释 | `further_explanation` | 展开详细解释 |

## 沟通预演固定按钮

```text
复制｜存到预演记录｜进一步解释
```

---

# 二十三、next_question 字段

如果需要补问，只能问一个问题。

```json
{
  "next_question": "还想问您一个细节：他最近是睡眠明显变少，还是白天回家后话变少？"
}
```

规则：

- 不要每轮都问；
- 不要连续追问；
- 不要像问卷；
- 问题要能区分候选解释；
- 如果问题已写在自然回复里，`next_question` 可同步记录；
- 没有问题时为 `null`。

---

# 二十四、should_trigger_review

用于判断是否建议阶段复盘。

```json
{
  "should_trigger_review": true,
  "review_reason": "同类手机冲突在近期多次出现，且旧判断可能需要重整"
}
```

规则：

- 不直接切换成重诊断；
- 只提示后端 / Router 可考虑进入阶段复盘；
- 前端可展示轻提示；
- 阶段复盘由 Router 决定，不由日常 Agent 自行决定。

适合触发的情况：

- 同类问题多次出现；
- 多个待观察点已经积累；
- 旧诊断卡需要明显更新；
- 孩子问卷与家长描述差异较大；
- 家长主动问“整体怎么看”；
- 近期成长变化足够形成阶段小结。

---

# 二十五、不同场景输出示例

## 1. 普通回复 + 成长记录

```json
{
  "reply": {
    "message_type": "normal_reply",
    "ui_badge": "已调用孩子画像",
    "content": "这个变化挺值得记一下。您之前提到过，孩子平时不是特别愿意主动聊学校，所以这次愿意说，至少说明当时他对您是有一点打开的。后面可以关注一下，他是愿意继续说具体事，还是只浅浅提一句。"
  },
  "understanding_engine": {
    "input_decomposition": {
      "facts": ["孩子今天主动提到学校里的事"],
      "child_behaviors": ["主动表达学校相关内容"],
      "parent_emotions": [],
      "parent_interpretations": [],
      "parent_goals": [],
      "missing_key_info": ["孩子是浅浅提一句，还是愿意展开聊"]
    },
    "child_understanding": {
      "possible_child_experience": "孩子当时对家长有一定打开",
      "candidate_explanations": ["沟通开放度提升", "当时学校事件较想分享"],
      "selected_explanation": "沟通开放度可能出现微小变化",
      "basis_from_child_profile": ["此前孩子较少主动聊学校"],
      "confidence": 0.72
    },
    "memory_decision": {
      "should_write": true,
      "write_types": ["growth_record"],
      "reason": "当前事件相对旧画像有变化，值得记录为近期成长变化"
    }
  },
  "memory_note_suggestion": {
    "show": true,
    "text": "已记录一个近期变化",
    "detail": "孩子主动提到学校，建议写入近期成长变化。"
  },
  "growth_record_candidates": [
    {
      "scene_type": "school",
      "content": "孩子主动提到学校里的事",
      "signal_type": "主动表达",
      "source": "chat",
      "importance": "medium",
      "difference_from_previous_profile": "此前孩子较少主动聊学校"
    }
  ],
  "actions": [
    { "label": "有点像", "action": "confirm" },
    { "label": "不太像", "action": "reject" },
    { "label": "补充一点", "action": "add_info" }
  ]
}
```

---

## 2. 分析孩子状态 + 待观察点

```json
{
  "reply": {
    "message_type": "normal_reply",
    "ui_badge": "已参考孩子小档案",
    "content": "综合孩子之前的信息，我觉得他说“没事”不一定代表真的没压力，也可能是他还没整理清楚，不想在被追问时马上解释。对孩子来说，累可能不只是身体累，也可能是学校里的事、学习任务、同伴关系、睡眠不足几件事叠在一起。还想问您一个细节：他最近是睡眠明显变少，还是白天回家后话变少？"
  },
  "understanding_engine": {
    "input_decomposition": {
      "facts": ["孩子最近看起来很累", "家长询问时孩子说没事"],
      "child_behaviors": ["疲惫", "关闭表达"],
      "parent_emotions": ["担心"],
      "parent_interpretations": ["孩子可能有事不说"],
      "parent_goals": ["想知道孩子最近怎么了"],
      "missing_key_info": ["睡眠是否变化", "白天回家后话是否变少"]
    },
    "child_understanding": {
      "possible_child_experience": "孩子可能还没整理清楚压力来源，不想在被追问时马上解释",
      "candidate_explanations": ["睡眠不足", "学校消耗", "学习任务压力", "同伴关系影响"],
      "selected_explanation": "疲惫可能由多重消耗叠加，不宜直接定性",
      "basis_from_child_profile": ["孩子在压力大时不一定马上表达"],
      "confidence": 0.58
    },
    "memory_decision": {
      "should_write": true,
      "write_types": ["pending_observation"],
      "reason": "信息重要但尚不足以确认疲惫来源"
    }
  },
  "memory_note_suggestion": {
    "show": true,
    "text": "已加入后续观察",
    "detail": "需要继续确认孩子疲惫更偏睡眠不足，还是白天消耗后不想沟通。"
  },
  "pending_observation_candidates": [
    {
      "content": "确认孩子疲惫更偏睡眠不足，还是白天消耗后不想沟通",
      "related_scene": "情绪与休息",
      "source": "chat",
      "priority": "medium",
      "distinguishes_between": ["睡眠不足", "学校消耗", "关闭表达"]
    }
  ],
  "next_question": "他最近是睡眠明显变少，还是白天回家后话变少？"
}
```

---

## 3. 沟通预演

```json
{
  "reply": {
    "message_type": "communication_rehearsal",
    "ui_badge": "已参考孩子小档案",
    "content": "这件事孩子可能先感受到的不是“英语要补”，而是“周末又少了一块能喘口气的时间”。他之前对休息边界比较敏感，所以如果直接进入加课安排，容易先产生抵触。\n\n可以先从英语最近哪一块最吃力聊起，再一起确认要不要补、怎么补。这样孩子会更容易觉得自己参与了安排，而不是被通知。\n\n像“必须补”“不能再拖了”这类表达，容易让孩子先进入防御。"
  },
  "understanding_engine": {
    "input_decomposition": {
      "facts": ["家长准备和孩子谈周末加英语课"],
      "child_behaviors": [],
      "parent_emotions": ["担心英语短板"],
      "parent_interpretations": ["孩子需要补英语"],
      "parent_goals": ["补齐英语短板"],
      "missing_key_info": ["孩子是否认同英语需要补", "孩子对周末安排的接受度"]
    },
    "child_understanding": {
      "possible_child_experience": "孩子可能先感到周末休息时间被压缩",
      "candidate_explanations": ["休息边界敏感", "对被安排抵触", "担心加课意味着压力增加"],
      "selected_explanation": "休息边界敏感最需要在表达中被考虑",
      "basis_from_child_profile": ["孩子此前对休息边界较敏感"],
      "confidence": 0.73
    },
    "parent_understanding": {
      "possible_parent_concern": "家长担心英语漏洞继续扩大",
      "parent_pattern_candidate": "家长倾向通过增加资源解决学科短板",
      "parent_goal_detected": "英语补弱",
      "basis_from_parent_profile": [],
      "confidence": 0.66
    },
    "family_interaction_understanding": {
      "parent_child_mismatch": "家长在谈补弱，孩子可能先感到被安排",
      "interaction_pattern_candidate": "边界争夺循环",
      "related_previous_pattern": "休息边界敏感",
      "confidence": 0.7
    },
    "memory_decision": {
      "should_write": true,
      "write_types": ["rehearsal_record"],
      "reason": "本轮生成沟通预演，用户可选择保存"
    }
  },
  "rehearsal_save_candidate": {
    "topic": "周末是否加英语课",
    "parent_goal": "补英语短板",
    "child_perspective_summary": "孩子可能先感到周末休息时间被压缩",
    "parent_child_mismatch": "家长在谈补弱，孩子可能先感到被安排",
    "suggested_direction": "先从英语最近哪一块吃力聊起，再一起确认要不要补、怎么补",
    "possible_misunderstanding": "像“必须补”这类表达，孩子容易先理解成自己又被安排了"
  },
  "actions": [
    { "label": "复制", "action": "copy" },
    { "label": "存到预演记录", "action": "save_rehearsal" },
    { "label": "进一步解释", "action": "further_explanation" }
  ]
}
```

---

## 4. 长期关注目标更新

```json
{
  "reply": {
    "message_type": "long_term_goal_update",
    "ui_badge": "已调用孩子画像",
    "content": "这个目标很重要，我会把它放进孩子的长期成长规划里。后面我们聊作业、手机、周末安排、考试复盘时，我会帮您一起关注：他是更愿意承担一点自己的安排了，还是一遇到压力就先退回去。"
  },
  "understanding_engine": {
    "input_decomposition": {
      "facts": [],
      "child_behaviors": [],
      "parent_emotions": ["期待孩子长期发展更稳"],
      "parent_interpretations": [],
      "parent_goals": ["责任感", "抗压能力"],
      "missing_key_info": []
    },
    "parent_understanding": {
      "possible_parent_concern": "家长担心孩子只关注成绩，缺少长期自我管理和抗压能力",
      "parent_pattern_candidate": "家长重视综合成长",
      "parent_goal_detected": "责任感与抗压能力",
      "basis_from_parent_profile": [],
      "confidence": 0.82
    },
    "memory_decision": {
      "should_write": true,
      "write_types": ["long_term_goal"],
      "reason": "家长明确表达长期培养目标"
    }
  },
  "memory_note_suggestion": {
    "show": true,
    "text": "已加入长期观察：责任感与抗压能力",
    "detail": "家长长期关注目标建议写入 long_term_goals。"
  },
  "long_term_goal_updates": [
    {
      "action": "add_or_weight",
      "goal_name": "责任感与抗压能力",
      "goal_category": "resilience",
      "source": "parent_focus",
      "weight_delta": 0.15,
      "reason": "家长明确表达希望孩子更有责任感和抗压能力",
      "related_scenes": ["作业启动", "手机规则", "考试复盘", "周末安排"]
    }
  ]
}
```

---

## 5. 纠偏回复

```json
{
  "reply": {
    "message_type": "correction_reply",
    "ui_badge": "已结合近期记录",
    "content": "我改一下前面的理解。这个信息会让之前那个判断更谨慎一点：这次可能不是休息边界的问题，更像是他当时没有进入学习状态。还想问您一个细节，他当时更像是不知道从哪儿开始，还是明知道要做但就是不愿意坐下？"
  },
  "understanding_engine": {
    "input_decomposition": {
      "facts": ["家长反馈本次不是休息边界，而是根本没开始"],
      "child_behaviors": ["学习启动失败"],
      "parent_emotions": [],
      "parent_interpretations": ["孩子根本没开始"],
      "parent_goals": ["修正系统理解"],
      "missing_key_info": ["是不知道从哪儿开始，还是明知道但不愿意坐下"]
    },
    "child_understanding": {
      "possible_child_experience": "孩子本次可能更偏学习启动困难",
      "candidate_explanations": ["不知道从哪儿开始", "明知道但不愿意坐下", "任务抵触"],
      "selected_explanation": "学习启动问题比休息边界更符合本轮信息",
      "basis_from_child_profile": ["旧判断中有休息边界敏感，但本轮被家长修正"],
      "confidence": 0.7
    },
    "memory_decision": {
      "should_write": true,
      "write_types": ["correction", "pending_observation"],
      "reason": "家长明确否定旧判断，需要降权并补充新的待观察方向"
    }
  },
  "memory_note_suggestion": {
    "show": true,
    "text": "已调整前面的一个判断",
    "detail": "建议降低“休息边界问题”在本场景中的权重。"
  },
  "correction_candidates": [
    {
      "old_judgment": "孩子拖延主要和休息边界有关",
      "new_judgment": "本次更偏学习启动困难",
      "reason": "家长明确反馈孩子不是想休息，而是根本没有开始",
      "affected_profile_keywords": ["作业拖延", "休息边界", "学习启动"],
      "correction_type": "narrow_scope",
      "confidence": 0.7
    }
  ],
  "pending_observation_candidates": [
    {
      "content": "确认孩子学习启动困难更偏不知道从哪儿开始，还是明知道但不愿意坐下",
      "related_scene": "作业启动",
      "source": "chat",
      "priority": "medium",
      "distinguishes_between": ["任务拆解困难", "任务抵触"]
    }
  ],
  "next_question": "他当时更像是不知道从哪儿开始，还是明知道要做但就是不愿意坐下？"
}
```

---

# 二十六、前端渲染要求

前端不需要理解 Agent 内部逻辑，只根据字段渲染。

| 字段 | 前端表现 |
|---|---|
| `reply.content` | 展示主回复 |
| `reply.message_type` | 决定卡片 / 气泡样式 |
| `reply.ui_badge` | 显示轻标识 |
| `memory_note_final.show=true` | 显示底部小字 |
| `actions` | 显示按钮 |
| `rehearsal_save_candidate` | 点击保存时写入预演记录 |
| `profile_update_results` | 展示真实写入结果 |
| `should_trigger_review=true` | 可提示阶段复盘 |

前端不要自己生成：

- 已记录一个近期变化；
- 已更新孩子小档案；
- 已加入长期观察；
- 已调整前面的一个判断；
- 已存到预演记录。

这些都必须来自后端。

---

# 二十七、后端处理要求

Agent 返回的是候选，不是最终写入结果。

后端需要：

1. 接收 Agent 输出；
2. 读取候选更新字段；
3. 调用 ProfileService / MemoryService；
4. 判断新增、合并、增强、降权、纠偏；
5. 写入对应表；
6. 写入 `profile_update_log`；
7. 返回最终 `profile_update_results`；
8. 返回最终 `memory_note_final`；
9. 前端只展示最终结果。

---

## 后端推荐处理顺序

```text
1. 处理 correction_candidates
2. 处理 profile_update_candidates
3. 处理 growth_record_candidates
4. 处理 pending_observation_candidates
5. 处理 long_term_goal_updates
6. 处理 parent_profile_candidates
7. 处理 family_interaction_candidates
8. 处理 rehearsal_save_candidate
9. 生成 profile_update_log
10. 返回 memory_note_final
```

---

# 二十八、最低验收标准

本输出格式完成后，应满足：

1. 日常 Agent 可以返回自然回复；
2. 后端可以识别 message_type；
3. 前端可以渲染普通回复、沟通预演、纠偏、成长信号；
4. `understanding_engine` 能记录本轮理解摘要；
5. Agent 不直接把家长评价写入孩子画像；
6. 孩子、家长、家庭互动三类记忆都能生成候选；
7. 有真实记忆更新时，前端出现最终 memory_note；
8. 没有真实写入时，不出现假小字；
9. 长期目标、成长变化、待观察点、纠偏都能进入对应候选字段；
10. 沟通预演能保存，但不生成家长照念原话；
11. 日常 Agent 和记忆库可以稳定对接；
12. 首次诊断卡能通过日常记录被持续验证、修正、补充和降权。

---

## 二十九、最终一句话

`02_日常对话Agent输出格式` 的核心不是让前端变复杂，而是让日常 Agent 的每一次轻回应背后都有可追踪、可更新、可纠偏的结构化结果。

> 家长看到轻回复；系统沉淀真记忆；后端保留可验证的理解过程。
