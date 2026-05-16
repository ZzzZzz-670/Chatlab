"""
日常对话 Agent 工具集
包含记忆查询、画像查询、记忆写入、画像更新等工具
"""
import json
import logging
from typing import Optional

from langchain.tools import tool
from coze_coding_utils.log.write_log import request_context
from coze_coding_utils.runtime_ctx.context import new_context

from storage.database.memory_service import get_memory_service
from storage.database.profile_service import get_profile_service

logger = logging.getLogger(__name__)


def _get_ctx():
    """获取请求上下文"""
    return request_context.get() or new_context(method="daily_agent_tool")


# ========== 查询类工具 ==========

@tool
def query_child_profile(child_id: str) -> str:
    """查询孩子画像主信息和画像条目。

    读取孩子的基本画像信息（昵称、年级等）以及所有画像条目（学习启动、情绪反应、沟通方式等维度的判断和置信度）。
    每轮对话开始时应该调用此工具获取孩子的画像背景。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        profile_svc = get_profile_service()

        # 获取主画像
        profile = profile_svc.get_child_profile(child_id)

        # 获取画像条目（排除已废弃和归档的）
        entries = profile_svc.get_profile_entries(child_id)

        result = {
            "profile": profile,
            "entries": entries,
            "entry_count": len(entries) if entries else 0,
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询孩子画像失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_diagnosis_handoff(child_id: str) -> str:
    """查询诊断 Agent 的交接摘要。

    读取诊断型 Agent 已形成的初始孩子理解，包括：
    - initial_understanding: 初始理解
    - key_child_patterns: 孩子关键模式
    - parent_concerns: 家长关注点
    - family_interaction_hypotheses: 家庭互动假设
    - pending_observations: 待观察点

    不要每轮都显性展示，只在需要参考时内部使用。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        handoff = memory_svc.get_diagnosis_handoff(child_id)
        if handoff:
            return json.dumps(handoff, ensure_ascii=False, default=str)
        return json.dumps({"message": "暂无诊断交接信息，可能是新用户或诊断尚未完成"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"查询诊断交接失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_growth_records(child_id: str, limit: int = 10) -> str:
    """查询孩子最近的成长记录。

    读取孩子的成长信号记录（正面/中性/预警），用于了解孩子近期变化趋势。

    Args:
        child_id: 孩子唯一标识
        limit: 返回记录数量，默认10条
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        records = memory_svc.get_growth_records(child_id, limit=limit)
        return json.dumps({"records": records, "count": len(records)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询成长记录失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_pending_observations(child_id: str) -> str:
    """查询孩子的待观察点。

    读取诊断 Agent 或日常 Agent 生成的待观察问题列表，帮助判断当前对话是否可以回答某个待观察点。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        observations = memory_svc.get_pending_observations(child_id, status="active")
        return json.dumps({"observations": observations, "count": len(observations)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询待观察点失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_long_term_goals(child_id: str) -> str:
    """查询家长对孩子长期关注的目标。

    读取家长设定的长期关注目标列表，帮助判断当前对话是否涉及这些目标。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        goals = memory_svc.get_long_term_goals(child_id, status="active")
        return json.dumps({"goals": goals, "count": len(goals)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询长期关注目标失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_parent_profile(family_id: str) -> str:
    """查询家长画像条目。

    读取家长的画像信息（如教育焦虑倾向、沟通模式等），帮助理解家长的背景和特点。

    Args:
        family_id: 家庭唯一标识
    """
    _get_ctx()
    try:
        profile_svc = get_profile_service()
        entries = profile_svc.get_parent_profile_entries(family_id)
        return json.dumps({"entries": entries, "count": len(entries)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询家长画像失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_family_interaction_patterns(child_id: str) -> str:
    """查询家庭互动模式。

    读取已识别的家庭互动循环模式（如催促-拖延循环、追问-沉默循环等）。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        profile_svc = get_profile_service()
        patterns = profile_svc.get_family_interaction_patterns(child_id)
        return json.dumps({"patterns": patterns, "count": len(patterns)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询家庭互动模式失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_questionnaire(child_id: str) -> str:
    """查询孩子问卷记录。

    读取孩子填写的问卷结果和摘要，包括孩子的自我视角和与家长描述的冲突点。
    如果没有问卷记录则返回空。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        questionnaire = memory_svc.get_questionnaire(child_id)
        if questionnaire:
            return json.dumps(questionnaire, ensure_ascii=False, default=str)
        return json.dumps({"message": "暂无问卷记录"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"查询问卷记录失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_correction_logs(child_id: str) -> str:
    """查询纠偏历史记录。

    读取对画像判断的纠正记录，了解哪些判断已经被修改，避免重复犯错。

    Args:
        child_id: 孩子唯一标识
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        logs = memory_svc.get_correction_logs(child_id, limit=10)
        return json.dumps({"logs": logs, "count": len(logs)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"查询纠偏记录失败: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ========== 写入类工具 ==========

@tool
def save_growth_record(family_id: str, child_id: str, scene_type: str,
                       signal_type: str, content: str, direction: Optional[str] = None,
                       importance: str = "medium") -> str:
    """保存一条成长记录候选。

    当从家长对话中识别到成长信号时调用。成长信号分为三类：
    - positive: 正面变化（如主动学习、情绪改善）
    - neutral: 中性变化（如习惯调整）
    - warning: 预警信号（如退步、新问题）

    注意：这是候选记录，后端服务会决定是否正式写入。单次事件不会直接变成稳定画像。

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        scene_type: 场景类型（如 homework_start, emotion, social, phone_use 等）
        signal_type: 信号类型（positive/neutral/warning）
        content: 成长记录内容，用一句话描述观察到的变化
        direction: 变化方向（如 improving, stable, declining），可选
        importance: 重要度（low/medium/high），默认 medium
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        result = memory_svc.add_growth_record(
            family_id=family_id,
            child_id=child_id,
            scene_type=scene_type,
            signal_type=signal_type,
            content=content,
            direction=direction,
            importance=importance,
        )

        # 记录画像更新日志
        profile_svc = get_profile_service()
        profile_svc.add_profile_update_log(
            family_id=family_id,
            child_id=child_id,
            operation="add_growth_record",
            target_table="growth_records",
            summary=content,
        )

        return json.dumps({"success": True, "record_id": result.get("id"), "status": result.get("status", "created")}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存成长记录失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ========== 知识库检索工具 ==========

# 知识库表名 → 对应知识领域
_KB_TABLE_MAP = {
    "04a": "kb_04a_child_parent",        # 孩子与家长理解引擎
    "04b": "kb_04b_parent_narrative",     # 家长叙述拆解
    "04c": "kb_04c_child_behavior",       # 孩子行为候选解释
    "04d": "kb_04d_family_cycle",         # 家庭互动循环识别
    "signal": "kb_signal_memory",         # 成长信号/记忆沉淀/长期关注
    "function": "kb_function_rule",       # 纠偏/沟通预演
    "style": "kb_style_example",          # 禁止事项/文风/示例
    "backend": "kb_backend_contract",     # 输出格式/上下文/后端
}


def _search_kb(query: str, table_names: list, top_k: int = 3) -> str:
    """内部公共函数：执行知识库检索。"""
    ctx = _get_ctx()
    try:
        from coze_coding_dev_sdk import KnowledgeClient, Config

        config = Config()
        client = KnowledgeClient(config=config, ctx=ctx)
        response = client.search(
            query=query,
            table_names=table_names,
            top_k=top_k,
        )

        if response.code != 0:
            logger.error(f"知识库检索失败: {response.msg}")
            return json.dumps({"results": [], "error": response.msg}, ensure_ascii=False)

        if not response.chunks:
            return json.dumps({"results": [], "message": "未找到相关知识"}, ensure_ascii=False)

        formatted = []
        for i, chunk in enumerate(response.chunks):
            if chunk.content:
                formatted.append(f"【知识片段{i+1}】(相关度:{chunk.score:.2f})\n{chunk.content}")

        return json.dumps({
            "results": formatted,
            "count": len(formatted),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        return json.dumps({"results": [], "error": str(e)}, ensure_ascii=False)


# ---- 核心理解库 (A/B/C/D) ----

@tool
def search_child_parent_understanding_library(query: str) -> str:
    """04A｜孩子与家长理解引擎规则。
    用途：双视角理解、孩子处境、家长关注、亲子理解差异。
    适用：所有涉及孩子状态、家长感受、亲子判断的场景。
    此工具为核心理解库，每个有效亲子场景必须至少检索两个核心库之一。

    Args:
        query: 搜索查询，如"孩子处境与家长关注差异""双视角理解框架"
    """
    return _search_kb(query, [_KB_TABLE_MAP["04a"]])


@tool
def search_parent_narrative_library(query: str) -> str:
    """04B｜家长叙述拆解规则。
    用途：拆分事实、情绪、评价、推测、目标；防止直接采信家长标签。
    适用：家长说孩子懒、不自觉、沉迷、玻璃心、没责任感、敷衍等。
    此工具为核心理解库，每个有效亲子场景必须至少检索两个核心库之一。

    Args:
        query: 搜索查询，如"家长评价不能直接采信""如何拆解家长叙述"
    """
    return _search_kb(query, [_KB_TABLE_MAP["04b"]])


@tool
def search_child_behavior_library(query: str) -> str:
    """04C｜孩子行为候选解释库。
    用途：生成孩子行为背后的候选解释和保护功能。
    适用：拖延、沉默、手机、说无所谓、表面答应、不问问题、情绪爆发等。
    此工具为核心理解库，每个有效亲子场景必须至少检索两个核心库之一。

    Args:
        query: 搜索查询，如"孩子拖延作业的候选解释""沉默行为的保护功能"
    """
    return _search_kb(query, [_KB_TABLE_MAP["04c"]])


@tool
def search_family_cycle_library(query: str) -> str:
    """04D｜家庭互动循环识别规则。
    用途：识别追问—沉默、加任务—磨蹭、认错—失信、期待—压力等互动循环。
    适用：亲子冲突反复出现、家长复盘沟通、孩子对家长防御时。
    注意：D库只在高度相似案例中调用，不要对普通行为泛搜。

    Args:
        query: 搜索查询，如"追问沉默循环""加任务磨蹭循环"
    """
    return _search_kb(query, [_KB_TABLE_MAP["04d"]])


# ---- 功能辅助库 ----

@tool
def search_signal_memory_library(query: str) -> str:
    """05/06/07｜成长信号抽取、记忆沉淀、家长长期关注库规则。
    用途：判断是否保存成长记录、画像条目、待观察点、长期关注目标。
    适用场景：成长信号输出、记忆更新输出、长期关注输出。
    按输出类型最小追加：成长信号/记忆更新/长期关注时追加。

    Args:
        query: 搜索查询，如"成长信号判断标准""记忆写入前5问""长期关注去重"
    """
    return _search_kb(query, [_KB_TABLE_MAP["signal"]])


@tool
def search_function_rule_library(query: str) -> str:
    """08/09｜纠偏触发规则、沟通预演规则。
    用途：处理家长否定判断、新旧画像冲突、沟通预演流程和边界。
    适用场景：纠偏输出、沟通预演输出。
    按输出类型最小追加：纠偏/沟通预演时追加。

    Args:
        query: 搜索查询，如"纠偏触发条件""沟通预演不是话术生成器"
    """
    return _search_kb(query, [_KB_TABLE_MAP["function"]])


@tool
def search_style_example_library(query: str) -> str:
    """10/11｜禁止事项与文风规范、示例对话库。
    用途：避免说教、心理诊断、话术化、模板化、指责家长。
    适用场景：文风风险时追加。
    按输出类型最小追加：当感觉表达可能违规时追加。

    Args:
        query: 搜索查询，如"禁止表达清单""推荐替代表达""示例对话"
    """
    return _search_kb(query, [_KB_TABLE_MAP["style"]])


@tool
def search_backend_contract_library(query: str) -> str:
    """02/03/12｜输出格式、输入上下文规范、后端对接说明。
    用途：开发调试和字段校验。
    注意：正常家长对话中默认禁止调用！仅在开发调试时使用。

    Args:
        query: 搜索查询，如"输出JSON结构""上下文注入优先级"
    """
    return _search_kb(query, [_KB_TABLE_MAP["backend"]])


# ---- 核心聚合工具 ----

# scene_type → 需要检索的核心库列表
_SCENE_CORE_MAP = {
    "parent_label": ["04b", "04c"],                    # 家长带评价
    "behavior_understanding": ["04a", "04c"],           # 具体孩子行为
    "communication_review": ["04b", "04d"],             # 亲子沟通复盘
    "communication_rehearsal": ["04a", "04d"],          # 沟通预演
    "growth_change": ["04a", "04c"],                    # 成长变化
    "long_term_goal": ["04a", "04b"],                   # 长期目标
    "correction": ["04b", "04d"],                       # 家长否定判断
    "complex_case": ["04a", "04b", "04c"],              # 信息复杂
}

_SCENE_LABELS = {
    "parent_label": "家长带评价（懒/不自觉/沉迷等）",
    "behavior_understanding": "具体孩子行为理解",
    "communication_review": "亲子沟通复盘",
    "communication_rehearsal": "沟通预演",
    "growth_change": "孩子成长变化",
    "long_term_goal": "家长长期目标",
    "correction": "家长否定系统判断",
    "complex_case": "信息复杂多维度",
}


@tool
def search_core_understanding_pack(query: str, scene_type: str) -> str:
    """核心理解包检索工具。每个有效亲子场景必须调用此工具完成核心双检索。

    根据场景类型，自动选择最合适的2-3个核心理解库进行检索。
    核心理解库包括：04A孩子与家长理解、04B家长叙述拆解、04C孩子行为候选解释、04D家庭互动循环。

    scene_type 可选值及对应检索库：
    - parent_label: 家长带评价（懒/不自觉/沉迷/玻璃心） → 检索 04B+04C
    - behavior_understanding: 具体孩子行为（拖延/手机/沉默/爆发） → 检索 04A+04C
    - communication_review: 亲子沟通复盘 → 检索 04B+04D
    - communication_rehearsal: 沟通预演 → 检索 04A+04D
    - growth_change: 孩子成长变化 → 检索 04A+04C
    - long_term_goal: 家长长期目标 → 检索 04A+04B
    - correction: 家长否定系统判断 → 检索 04B+04D
    - complex_case: 信息复杂多维度 → 检索 04A+04B+04C

    Args:
        query: 搜索查询，描述当前场景中你需要理解的核心问题
        scene_type: 场景类型，必须是上述8种之一
    """
    core_keys = _SCENE_CORE_MAP.get(scene_type)
    if not core_keys:
        available = ", ".join(f"'{k}' ({v})" for k, v in _SCENE_LABELS.items())
        return json.dumps({
            "results": [],
            "error": f"无效的 scene_type: '{scene_type}'。可选值: {available}"
        }, ensure_ascii=False)

    table_names = [_KB_TABLE_MAP[k] for k in core_keys]
    return _search_kb(query, table_names, top_k=3)


@tool
def save_profile_entry(family_id: str, child_id: str, category: str,
                       content: str, source: str = "daily_agent",
                       confidence: float = 0.5) -> str:
    """保存一条孩子画像条目候选。

    当从对话中识别到对孩子的新理解时调用。画像维度包括：
    - learning_start: 学习启动特点
    - learning_process: 学习过程特点
    - emotion_response: 情绪反应模式
    - communication_style: 沟通方式
    - social_preference: 社交偏好
    - phone_boundary: 手机使用边界
    - interest_motivation: 兴趣动力
    - self_management: 自我管理能力
    - other: 其他

    核心规则：
    1. 单次事件不直接变成稳定画像，新条目默认为 hypothesis 状态
    2. 同维度相似内容会自动合并，增强置信度
    3. 新事实支持旧判断 → 增强权重
    4. 家长评价不能直接写入孩子画像

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        category: 画像维度
        content: 画像内容，客观描述孩子的特点
        source: 来源（daily_agent/questionnaire/diagnosis_agent），默认 daily_agent
        confidence: 置信度（0-1），默认 0.5
    """
    _get_ctx()
    try:
        profile_svc = get_profile_service()
        result = profile_svc.add_profile_entry(
            family_id=family_id,
            child_id=child_id,
            category=category,
            content=content,
            source=source,
            confidence=confidence,
        )

        # 记录画像更新日志
        profile_svc.add_profile_update_log(
            family_id=family_id,
            child_id=child_id,
            operation="add_profile_entry",
            target_table="profile_entries",
            target_id=result.get("id"),
            summary=content,
        )

        status = result.get("status", "created")
        return json.dumps({
            "success": True,
            "entry_id": result.get("id"),
            "status": status,
            "message": "已合并到已有条目" if status == "merged" else "已新增画像条目候选",
            "new_confidence": result.get("new_confidence"),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存画像条目失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def save_pending_observation(family_id: str, child_id: str, content: str,
                              related_scene: Optional[str] = None,
                              priority: str = "medium") -> str:
    """保存一条待观察点候选。

    当从对话中识别到需要进一步观察的问题时调用。
    待观察点不会直接变成画像判断，而是等待后续对话提供更多证据。

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        content: 待观察内容，描述需要观察什么
        related_scene: 关联场景，可选
        priority: 优先级（low/medium/high），默认 medium
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        result = memory_svc.add_pending_observation(
            family_id=family_id,
            child_id=child_id,
            content=content,
            related_scene=related_scene,
            priority=priority,
        )
        status = result.get("status", "created")
        return json.dumps({
            "success": True,
            "observation_id": result.get("id"),
            "status": status,
            "message": "已有相同待观察点" if status == "duplicate" else "已新增待观察点",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存待观察点失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def save_correction(family_id: str, child_id: str, old_judgment: str,
                    new_judgment: str, correction_type: str, reason: str) -> str:
    """保存一条纠偏记录。

    当发现原有判断需要修正时调用。纠偏类型包括：
    - deprecate_old: 旧判断完全错误，废弃
    - replace_old: 旧判断需要替换为新判断
    - narrow_scope: 旧判断范围太宽，收窄适用范围
    - split_judgment: 旧判断过于笼统，拆分为更精确的多个判断
    - add_exception: 旧判断基本成立，但存在例外情况

    同时会自动降权对应的画像条目。

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        old_judgment: 原判断内容
        new_judgment: 修正后的判断
        correction_type: 纠偏类型（deprecate_old/replace_old/narrow_scope/split_judgment/add_exception）
        reason: 纠偏原因
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        result = memory_svc.add_correction_log(
            family_id=family_id,
            child_id=child_id,
            old_judgment=old_judgment,
            new_judgment=new_judgment,
            correction_type=correction_type,
            reason=reason,
        )

        # 记录画像更新日志
        profile_svc = get_profile_service()
        profile_svc.add_profile_update_log(
            family_id=family_id,
            child_id=child_id,
            operation="correction",
            target_table="correction_logs",
            target_id=result.get("id"),
            summary=f"纠偏: {old_judgment[:30]}... → {new_judgment[:30]}...",
        )

        return json.dumps({"success": True, "correction_id": result.get("id")}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存纠偏记录失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def save_parent_profile_entry(family_id: str, category: str, content: str,
                               confidence: float = 0.5) -> str:
    """保存一条家长画像条目。

    当从对话中识别到家长的特点（如教育焦虑倾向、沟通模式、关注点等）时调用。
    家长画像帮助孩子理解引擎更好地分析亲子互动。

    Args:
        family_id: 家庭唯一标识
        category: 画像维度（如 anxiety_tendency, communication_mode, expectation, concern_focus 等）
        content: 画像内容
        confidence: 置信度（0-1），默认 0.5
    """
    _get_ctx()
    try:
        profile_svc = get_profile_service()
        result = profile_svc.add_parent_profile_entry(
            family_id=family_id,
            category=category,
            content=content,
            confidence=confidence,
        )
        status = result.get("status", "created")
        return json.dumps({
            "success": True,
            "entry_id": result.get("id"),
            "status": status,
            "message": "已有相同条目" if status == "duplicate" else "已新增家长画像条目",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存家长画像条目失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def save_family_interaction_pattern(family_id: str, child_id: str, content: str,
                                     pattern_name: Optional[str] = None,
                                     scene: Optional[str] = None) -> str:
    """保存一条家庭互动模式候选。

    当从对话中识别到亲子互动的循环模式时调用，如：
    - 催促-拖延循环：家长越催促，孩子越拖延
    - 追问-沉默循环：家长追问，孩子沉默
    - 担心-补偿循环：家长担心漏洞，给孩子加量，孩子更不想做

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        content: 互动模式描述
        pattern_name: 模式名称（如 催促-拖延循环），可选
        scene: 关联场景，可选
    """
    _get_ctx()
    try:
        profile_svc = get_profile_service()
        result = profile_svc.add_family_interaction_pattern(
            family_id=family_id,
            child_id=child_id,
            content=content,
            pattern_name=pattern_name,
            scene=scene,
        )
        status = result.get("status", "created")
        return json.dumps({
            "success": True,
            "pattern_id": result.get("id"),
            "status": status,
            "message": "已合并到已有模式" if status == "merged" else "已新增互动模式候选",
            "new_confidence": result.get("new_confidence"),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存家庭互动模式失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def save_long_term_goal(family_id: str, child_id: str, goal_name: str,
                         goal_category: Optional[str] = None,
                         weight: float = 0.5) -> str:
    """保存一条家长长期关注目标。

    当从对话中识别到家长对孩子有持续关注的目标时调用，如：
    - 希望孩子自觉学习
    - 希望孩子管理好手机
    - 希望孩子情绪稳定

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        goal_name: 目标名称
        goal_category: 目标分类（如 learning, emotion, social, phone），可选
        weight: 权重（0-1），默认 0.5
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        result = memory_svc.add_long_term_goal(
            family_id=family_id,
            child_id=child_id,
            goal_name=goal_name,
            goal_category=goal_category,
            weight=weight,
        )
        status = result.get("status", "created")
        return json.dumps({
            "success": True,
            "goal_id": result.get("id"),
            "status": status,
            "message": "已有相同目标" if status == "duplicate" else "已新增长期关注目标",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存长期关注目标失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def save_rehearsal_record(family_id: str, child_id: str, topic: str,
                           parent_goal: Optional[str] = None,
                           child_perspective_summary: Optional[str] = None,
                           parent_child_mismatch: Optional[str] = None,
                           suggested_direction: Optional[str] = None,
                           possible_misunderstanding: Optional[str] = None) -> str:
    """保存一条沟通预演记录。

    当家长进入沟通预演模式时调用，记录预演的完整结果。

    Args:
        family_id: 家庭唯一标识
        child_id: 孩子唯一标识
        topic: 预演主题
        parent_goal: 家长想达成的目标
        child_perspective_summary: 孩子可能的视角
        parent_child_mismatch: 亲子视角差异
        suggested_direction: 建议的表达方向
        possible_misunderstanding: 可能的误解
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        result = memory_svc.add_rehearsal_record(
            family_id=family_id,
            child_id=child_id,
            topic=topic,
            parent_goal=parent_goal,
            child_perspective_summary=child_perspective_summary,
            parent_child_mismatch=parent_child_mismatch,
            suggested_direction=suggested_direction,
            possible_misunderstanding=possible_misunderstanding,
        )
        return json.dumps({"success": True, "record_id": result.get("id")}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存沟通预演记录失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def resolve_pending_observation(observation_id: int) -> str:
    """标记一条待观察点为已解决。

    当当前对话提供了足够证据，可以回答某个待观察点时调用。

    Args:
        observation_id: 待观察点的ID
    """
    _get_ctx()
    try:
        memory_svc = get_memory_service()
        result = memory_svc.resolve_pending_observation(observation_id)
        return json.dumps({"success": True, "observation_id": observation_id, "status": "resolved"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"解决待观察点失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def submit_response_meta(message_type: str, ui_badge: str = "",
                         memory_note_show: bool = False, memory_note_text: str = "",
                         memory_note_detail: str = "",
                         action_labels: Optional[str] = None) -> str:
    """提交当前回复的元信息。每次回复都必须调用此工具。

    这个工具不写入数据库，仅用于将结构化元信息传递给后端，
    以便后端组装完整的 JSON 响应返回给前端。
    你必须在给出自然语言回复的同时调用此工具。

    Args:
        message_type: 回复类型，必须为以下之一：
            - normal_reply: 普通日常回复
            - growth_signal: 发现成长信号时的回复
            - communication_rehearsal: 沟通预演模式
            - correction_reply: 纠偏回复
            - memory_update_reply: 记忆更新确认回复
        ui_badge: UI角标文字，如"已参考孩子小档案""已更新对孩子的理解"，默认空
        memory_note_show: 是否展示记忆提示，默认 false
        memory_note_text: 记忆提示标题，如"已记录一个近期变化"
        memory_note_detail: 记忆提示详情，如"这次记下的是：孩子最近有主动提到学校的情况。"
        action_labels: 交互按钮标签，JSON数组字符串，如 '[{"label":"有点像","action":"confirm"},{"label":"不太像","action":"reject"}]'
            常用 action: confirm(确认), reject(否认), add_info(补充), try(尝试), adjust(调整), observe(观察), talk(聊聊)
    """
    _get_ctx()
    try:
        # 解析 action_labels
        actions = []
        if action_labels:
            try:
                actions = json.loads(action_labels)
            except json.JSONDecodeError:
                logger.warning(f"action_labels JSON解析失败: {action_labels}")

        meta = {
            "message_type": message_type,
            "ui_badge": ui_badge,
            "memory_note_suggestion": {
                "show": memory_note_show,
                "text": memory_note_text,
                "detail": memory_note_detail,
            },
            "actions": actions,
        }
        return json.dumps({"success": True, "meta": meta}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"提交回复元信息失败: {e}")
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
