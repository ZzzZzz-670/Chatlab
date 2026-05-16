"""
ProfileService — 孩子画像 + 长期关注 + 问卷 + handoff 的读写服务

职责：
1. 读取 family_state（Agent Router 用）
2. 读取/写入 profile_entries（画像条目）
3. 读取/写入 long_term_goals（长期关注目标）
4. 读取/写入 handoff_summaries（诊断→日常交接摘要）
5. 读取/写入 child_questionnaires（问卷）
6. 合并 profile_update_candidates（新增/合并/降权/纠偏）
7. 写入 profile_update_log（审计追踪）
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------- DB 连接 ----------

_db_url = None

def _get_db_url() -> str:
    global _db_url
    if _db_url:
        return _db_url
    _db_url = os.getenv("PGDATABASE_URL")
    if not _db_url:
        try:
            from coze_workload_identity import Client
            _db_url = Client().get_db_url()
        except Exception:
            pass
    return _db_url


def _get_conn():
    import psycopg
    url = _get_db_url()
    if not url:
        return None
    return psycopg.connect(url, autocommit=True)


# ---------- Family State ----------

def get_family_state(family_id: str) -> Optional[dict]:
    """获取家庭状态（Agent Router 用）"""
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT family_id, child_name, child_age, child_grade, "
            "diagnosis_completed, first_card_id, questionnaire_status, "
            "questionnaire_completed_at, last_agent_type, created_at, updated_at "
            "FROM family_state WHERE family_id = %s",
            (family_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = ["family_id", "child_name", "child_age", "child_grade",
                "diagnosis_completed", "first_card_id", "questionnaire_status",
                "questionnaire_completed_at", "last_agent_type", "created_at", "updated_at"]
        return dict(zip(cols, row))
    except Exception as e:
        logger.error(f"get_family_state error: {e}")
        return None
    finally:
        conn.close()


def upsert_family_state(family_id: str, **kwargs) -> bool:
    """插入或更新家庭状态"""
    conn = _get_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        # 确保行存在
        cur.execute(
            "INSERT INTO family_state (family_id) VALUES (%s) "
            "ON CONFLICT (family_id) DO NOTHING",
            (family_id,)
        )
        # 更新指定字段
        if kwargs:
            set_clauses = []
            values = []
            for k, v in kwargs.items():
                if k == "family_id":
                    continue
                set_clauses.append(f"{k} = %s")
                values.append(v)
            set_clauses.append("updated_at = NOW()")
            values.append(family_id)
            cur.execute(
                f"UPDATE family_state SET {', '.join(set_clauses)} WHERE family_id = %s",
                values
            )
        return True
    except Exception as e:
        logger.error(f"upsert_family_state error: {e}")
        return False
    finally:
        conn.close()


def mark_diagnosis_completed(family_id: str, card_id: str) -> bool:
    """诊断完成后更新状态"""
    return upsert_family_state(
        family_id,
        diagnosis_completed=True,
        first_card_id=card_id,
        last_agent_type="diagnosis_agent"
    )


# ---------- Profile Entries ----------

def get_active_entries(family_id: str, min_weight: float = 0.3, limit: int = 10) -> list:
    """获取有效的画像条目（按权重降序）"""
    conn = _get_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, category, content, source, weight, confidence, "
            "evidence_count, status, created_at "
            "FROM profile_entries "
            "WHERE family_id = %s AND weight >= %s AND superseded_by IS NULL "
            "ORDER BY weight DESC, created_at DESC LIMIT %s",
            (family_id, min_weight, limit)
        )
        cols = ["id", "category", "content", "source", "weight", "confidence",
                "evidence_count", "status", "created_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"get_active_entries error: {e}")
        return []
    finally:
        conn.close()


def find_similar_entry(family_id: str, category: str, content: str) -> Optional[dict]:
    """查找相似的画像条目（关键词重叠查重）"""
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        # 先按 category 筛选，再逐条做关键词重叠
        cur.execute(
            "SELECT id, category, content, weight, evidence_count, status "
            "FROM profile_entries "
            "WHERE family_id = %s AND category = %s AND weight >= 0.3 AND superseded_by IS NULL",
            (family_id, category)
        )
        cols = ["id", "category", "content", "weight", "evidence_count", "status"]
        entries = [dict(zip(cols, row)) for row in cur.fetchall()]

        if not entries:
            return None

        # 关键词重叠查重
        content_words = set(content.replace("，", " ").replace("。", " ").replace("、", " ").split())
        best_match = None
        best_score = 0.0
        for entry in entries:
            entry_words = set(entry["content"].replace("，", " ").replace("。", " ").replace("、", " ").split())
            if not content_words or not entry_words:
                continue
            overlap = len(content_words & entry_words) / max(len(content_words), len(entry_words))
            if overlap > best_score:
                best_score = overlap
                best_match = entry

        if best_score > 0.4:
            return best_match
        return None
    except Exception as e:
        logger.error(f"find_similar_entry error: {e}")
        return None
    finally:
        conn.close()


def insert_entry(family_id: str, candidate: dict) -> Optional[int]:
    """插入新画像条目"""
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO profile_entries (family_id, category, content, source, weight, confidence, evidence_count, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (family_id,
             candidate.get("dimension", "other"),
             candidate.get("summary", ""),
             candidate.get("source", "diagnosis"),
             1.0,
             candidate.get("confidence", "medium"),
             1,
             candidate.get("status", "initial_hypothesis"))
        )
        entry_id = cur.fetchone()[0]
        return entry_id
    except Exception as e:
        logger.error(f"insert_entry error: {e}")
        return None
    finally:
        conn.close()


def update_entry(entry_id: int, **kwargs) -> bool:
    """更新画像条目"""
    conn = _get_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        set_clauses = []
        values = []
        for k, v in kwargs.items():
            set_clauses.append(f"{k} = %s")
            values.append(v)
        set_clauses.append("updated_at = NOW()")
        values.append(entry_id)
        cur.execute(
            f"UPDATE profile_entries SET {', '.join(set_clauses)} WHERE id = %s",
            values
        )
        return True
    except Exception as e:
        logger.error(f"update_entry error: {e}")
        return False
    finally:
        conn.close()


# ---------- Merge Profile Candidates ----------

def merge_profile_candidates(family_id: str, session_id: str, candidates: list) -> list:
    """
    合并画像候选：新增 / 合并 / 降权
    返回每条候选的处理结果（供前端显示"已记录/已合并/已调整"）
    """
    results = []
    existing = get_active_entries(family_id, min_weight=0.0)

    for c in candidates:
        action = c.get("action", "add_entry")

        if action == "add_entry" or (action not in ["add_entry", "deprecate_entry", "add_goal", "update_profile"] and "summary" in c):
            # 新增或合并画像条目
            category = c.get("dimension", "other")
            content = c.get("summary", "")
            confidence = c.get("confidence", "medium")

            # 查重
            similar = find_similar_entry(family_id, category, content)
            if similar:
                # 合并：evidence_count+1，weight 微增
                new_count = (similar.get("evidence_count") or 1) + 1
                new_weight = min(1.0, (similar.get("weight") or 1.0) + 0.05)
                update_entry(similar["id"], evidence_count=new_count, weight=new_weight)
                _log_update(family_id, session_id, "merged", "profile_entries",
                           similar["id"], f"已合并到：{similar['content'][:40]}")
                results.append({
                    "action": "merged",
                    "detail": f"已合并到：{similar['content'][:40]}",
                    "category": category
                })
            else:
                # 新增
                entry_id = insert_entry(family_id, c)
                if entry_id:
                    _log_update(family_id, session_id, "created", "profile_entries",
                               entry_id, f"已记录：{content[:40]}")
                    results.append({
                        "action": "created",
                        "detail": f"已记录：{content[:40]}",
                        "category": category
                    })

        elif action == "deprecate_entry":
            # 降权旧判断
            target_match = c.get("target_content_match", "")
            # 在所有条目中找最相似的
            conn = _get_conn()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id, content, weight FROM profile_entries "
                        "WHERE family_id = %s AND weight >= 0.3 AND superseded_by IS NULL "
                        "ORDER BY weight DESC LIMIT 20",
                        (family_id,)
                    )
                    rows = cur.fetchall()
                    target_words = set(target_match.replace("，", " ").replace("。", " ").split())
                    best = None
                    best_score = 0.0
                    for row in rows:
                        row_words = set(row[1].replace("，", " ").replace("。", " ").split())
                        if not target_words or not row_words:
                            continue
                        overlap = len(target_words & row_words) / max(len(target_words), len(row_words))
                        if overlap > best_score:
                            best_score = overlap
                            best = row
                    if best and best_score > 0.3:
                        old_weight = best[2]
                        new_weight = old_weight * 0.3
                        update_entry(best[0], weight=new_weight)
                        _log_update(family_id, session_id, "deprecated", "profile_entries",
                                   best[0], f"已调整判断：{best[1][:40]}",
                                   before_value=str(old_weight), after_value=str(new_weight))
                        results.append({
                            "action": "deprecated",
                            "detail": f"已调整判断：{best[1][:40]}"
                        })
                except Exception as e:
                    logger.error(f"deprecate_entry error: {e}")
                finally:
                    conn.close()

        elif action == "add_goal":
            # 长期关注目标
            goal_name = c.get("goal_name", "")
            goal_category = c.get("goal_category", "")
            if goal_name:
                existing_goal = _find_goal_by_name(family_id, goal_name)
                if existing_goal:
                    # 已存在，提高权重
                    _bump_goal_weight(existing_goal["id"], delta=0.1)
                    _log_update(family_id, session_id, "goal_weighted", "long_term_goals",
                               existing_goal["id"], f"已提高关注：{goal_name}")
                    results.append({
                        "action": "goal_weighted",
                        "detail": f"已提高关注：{goal_name}"
                    })
                else:
                    # 新增
                    goal_id = _insert_goal(family_id, goal_name, goal_category, c.get("reason", ""))
                    if goal_id:
                        _log_update(family_id, session_id, "goal_added", "long_term_goals",
                                   goal_id, f"已加入长期观察：{goal_name}")
                        results.append({
                            "action": "goal_added",
                            "detail": f"已加入长期观察：{goal_name}"
                        })

        elif action == "update_profile":
            # 更新家庭基本信息（child_name, child_grade 等）
            field = c.get("field", "")
            value = c.get("value", "")
            if field and value:
                # 映射字段名
                field_map = {
                    "child_name": "child_name",
                    "child_age": "child_age",
                    "child_grade": "child_grade",
                    "core_pattern": "core_pattern",
                }
                db_field = field_map.get(field)
                if db_field:
                    upsert_family_state(family_id, **{db_field: value})
                    _log_update(family_id, session_id, "updated", "family_state",
                               None, f"已更新小档案：{field}")
                    results.append({
                        "action": "updated",
                        "detail": f"已更新小档案：{field}"
                    })

    return results


# ---------- Long Term Goals ----------

def get_active_goals(family_id: str, limit: int = 5) -> list:
    conn = _get_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, goal_name, goal_category, weight, trigger_count, "
            "last_triggered, status FROM long_term_goals "
            "WHERE family_id = %s AND status = 'active' "
            "ORDER BY weight DESC LIMIT %s",
            (family_id, limit)
        )
        cols = ["id", "goal_name", "goal_category", "weight", "trigger_count",
                "last_triggered", "status"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"get_active_goals error: {e}")
        return []
    finally:
        conn.close()


def _find_goal_by_name(family_id: str, goal_name: str) -> Optional[dict]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, goal_name, weight, trigger_count, status "
            "FROM long_term_goals WHERE family_id = %s AND goal_name = %s",
            (family_id, goal_name)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = ["id", "goal_name", "weight", "trigger_count", "status"]
        return dict(zip(cols, row))
    except Exception as e:
        logger.error(f"_find_goal_by_name error: {e}")
        return None
    finally:
        conn.close()


def _insert_goal(family_id: str, goal_name: str, goal_category: str, reason: str) -> Optional[int]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO long_term_goals (family_id, goal_name, goal_category, weight, last_triggered) "
            "VALUES (%s, %s, %s, 0.5, NOW()) RETURNING id",
            (family_id, goal_name, goal_category)
        )
        return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"_insert_goal error: {e}")
        return None
    finally:
        conn.close()


def _bump_goal_weight(goal_id: int, delta: float = 0.1) -> bool:
    conn = _get_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE long_term_goals SET weight = LEAST(1.0, weight + %s), "
            "trigger_count = trigger_count + 1, last_triggered = NOW(), updated_at = NOW() "
            "WHERE id = %s",
            (delta, goal_id)
        )
        return True
    except Exception as e:
        logger.error(f"_bump_goal_weight error: {e}")
        return False
    finally:
        conn.close()


# ---------- Handoff Summary ----------

def save_handoff_summary(family_id: str, card_id: str, handoff: dict) -> Optional[int]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO handoff_summaries "
            "(family_id, card_id, initial_understanding, key_child_patterns, "
            "parent_concerns, family_interaction_hypotheses, pending_observations, suggested_daily_mode) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (family_id, card_id,
             handoff.get("initialUnderstanding", ""),
             handoff.get("keyChildPatterns", []),
             handoff.get("parentConcern", []),
             handoff.get("familyInteractionHypotheses", []),
             handoff.get("pendingObservations", []),
             handoff.get("suggestedDailyMode", "memory_aware_daily_chat"))
        )
        return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"save_handoff_summary error: {e}")
        return None
    finally:
        conn.close()


def get_latest_handoff(family_id: str) -> Optional[dict]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, card_id, initial_understanding, key_child_patterns, "
            "parent_concerns, family_interaction_hypotheses, pending_observations, "
            "suggested_daily_mode, created_at "
            "FROM handoff_summaries WHERE family_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (family_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = ["id", "card_id", "initial_understanding", "key_child_patterns",
                "parent_concerns", "family_interaction_hypotheses", "pending_observations",
                "suggested_daily_mode", "created_at"]
        return dict(zip(cols, row))
    except Exception as e:
        logger.error(f"get_latest_handoff error: {e}")
        return None
    finally:
        conn.close()


# ---------- Questionnaire ----------

def get_questionnaire(family_id: str) -> Optional[dict]:
    conn = _get_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, completed_at, child_self_report_summary, "
            "structured_answers, conflicts_with_parent "
            "FROM child_questionnaires WHERE family_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (family_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = ["id", "status", "completed_at", "child_self_report_summary",
                "structured_answers", "conflicts_with_parent"]
        return dict(zip(cols, row))
    except Exception as e:
        logger.error(f"get_questionnaire error: {e}")
        return None
    finally:
        conn.close()


def save_questionnaire(family_id: str, data: dict) -> bool:
    conn = _get_conn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        # Upsert
        cur.execute(
            "INSERT INTO child_questionnaires (family_id, status, completed_at, "
            "child_self_report_summary, structured_answers, conflicts_with_parent) "
            "VALUES (%s, %s, NOW(), %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (family_id,
             data.get("status", "completed"),
             data.get("child_self_report_summary", ""),
             json.dumps(data.get("structured_answers", []), ensure_ascii=False),
             json.dumps(data.get("conflicts_with_parent", []), ensure_ascii=False))
        )
        # Update family state
        upsert_family_state(family_id,
                           questionnaire_status=data.get("status", "completed"),
                           questionnaire_completed_at=datetime.now(timezone.utc))
        return True
    except Exception as e:
        logger.error(f"save_questionnaire error: {e}")
        return False
    finally:
        conn.close()


# ---------- Profile Update Log ----------

def _log_update(family_id: str, session_id: str, action: str,
                target_table: str, target_id: Optional[int],
                detail: str, before_value: str = None, after_value: str = None):
    conn = _get_conn()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO profile_update_log "
            "(family_id, session_id, action, target_table, target_id, detail, before_value, after_value) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (family_id, session_id, action, target_table, target_id, detail, before_value, after_value)
        )
    except Exception as e:
        logger.error(f"_log_update error: {e}")
    finally:
        conn.close()


def get_recent_updates(family_id: str, limit: int = 5) -> list:
    conn = _get_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT action, detail, created_at FROM profile_update_log "
            "WHERE family_id = %s ORDER BY created_at DESC LIMIT %s",
            (family_id, limit)
        )
        cols = ["action", "detail", "created_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"get_recent_updates error: {e}")
        return []
    finally:
        conn.close()


# ---------- Context Builder (for prompt injection) ----------

def build_profile_context(family_id: str) -> str:
    """
    构建注入到 Agent system prompt 末尾的孩子画像上下文
    格式紧凑，节省 token
    """
    parts = []

    # 1. 基本信息
    state = get_family_state(family_id)
    if state:
        info_parts = []
        if state.get("child_name"):
            info_parts.append(f"昵称：{state['child_name']}")
        if state.get("child_grade"):
            info_parts.append(f"年级：{state['child_grade']}")
        if state.get("child_age"):
            info_parts.append(f"年龄：{state['child_age']}")
        if info_parts:
            parts.append("【孩子基本信息】" + "，".join(info_parts))

    # 2. 画像条目
    entries = get_active_entries(family_id, min_weight=0.3, limit=10)
    if entries:
        parts.append("【近期画像记录】")
        category_labels = {
            "learning_start": "学习启动",
            "emotion_response": "情绪反应",
            "communication_style": "沟通方式",
            "phone_boundary": "手机边界",
            "parent_child_interaction": "亲子互动",
            "social": "社交",
            "behavioral": "行为观察",
            "family_dynamic": "家庭动力",
            "other": "其他",
        }
        for i, e in enumerate(entries, 1):
            label = category_labels.get(e["category"], e["category"])
            weight_mark = "⭐" if e["weight"] >= 0.8 else ""
            evidence = f"（佐证{e['evidence_count']}次）" if e.get("evidence_count", 1) > 1 else ""
            parts.append(f"  {i}. [{label}-{e['confidence']}{weight_mark}] {e['content']}{evidence}")

    # 3. 长期关注目标
    goals = get_active_goals(family_id, limit=5)
    if goals:
        parts.append("【长期关注目标】")
        for g in goals:
            days = ""
            if g.get("last_triggered"):
                delta = datetime.now(timezone.utc) - g["last_triggered"].replace(tzinfo=timezone.utc) if g["last_triggered"] else None
                if delta:
                    days = f"（最近{delta.days}天提及）"
            parts.append(f"  · {g['goal_name']}（权重{g['weight']:.1f}）{days}")

    # 4. 问卷摘要
    q = get_questionnaire(family_id)
    if q and q.get("status") == "completed" and q.get("child_self_report_summary"):
        parts.append(f"【孩子自述摘要】{q['child_self_report_summary']}")
        if q.get("conflicts_with_parent"):
            conflicts = q["conflicts_with_parent"] if isinstance(q["conflicts_with_parent"], list) else []
            if conflicts:
                parts.append("【与家长描述的差异】" + "；".join(str(c) for c in conflicts[:3]))

    # 5. handoff（仅日常 Agent 用）
    handoff = get_latest_handoff(family_id)
    if handoff:
        parts.append(f"【诊断交接摘要】{handoff['initial_understanding']}")
        if handoff.get("pending_observations"):
            obs = handoff["pending_observations"] if isinstance(handoff["pending_observations"], list) else []
            if obs:
                parts.append("【待观察点】" + "；".join(str(o) for o in obs[:5]))

    if not parts:
        return ""

    return "\n[当前孩子画像]\n" + "\n".join(parts) + "\n[/当前孩子画像]"
