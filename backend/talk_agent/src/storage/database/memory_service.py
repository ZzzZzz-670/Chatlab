"""
Memory Service - 记忆读写服务
负责成长记录、待观察点、长期关注目标的读写和合并逻辑
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from postgrest.exceptions import APIError
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class MemoryService:
    """记忆服务：负责成长记录、待观察点、长期关注目标的读写"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    # ========== 成长记录 ==========

    def get_growth_records(self, child_id: str, limit: int = 20) -> list[dict]:
        """获取孩子的成长记录，按时间倒序"""
        try:
            response = self.client.table("growth_records") \
                .select("id,scene_type,signal_type,content,direction,importance,source,confidence,created_at") \
                .eq("child_id", child_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取成长记录失败: {e.message}")
            raise Exception(f"获取成长记录失败: {e.message}")

    def add_growth_record(self, family_id: str, child_id: str, scene_type: str,
                          signal_type: str, content: str, direction: Optional[str] = None,
                          importance: Optional[str] = "medium", source: Optional[str] = "daily_agent",
                          confidence: Optional[float] = 0.5) -> dict:
        """新增成长记录"""
        try:
            response = self.client.table("growth_records").insert({
                "family_id": family_id,
                "child_id": child_id,
                "scene_type": scene_type,
                "signal_type": signal_type,
                "content": content,
                "direction": direction,
                "importance": importance,
                "source": source,
                "confidence": confidence,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增成长记录失败: {e.message}")
            raise Exception(f"新增成长记录失败: {e.message}")

    # ========== 待观察点 ==========

    def get_pending_observations(self, child_id: str, status: str = "active") -> list[dict]:
        """获取孩子的待观察点"""
        try:
            query = self.client.table("pending_observations") \
                .select("id,content,related_scene,priority,status,source,created_at") \
                .eq("child_id", child_id)

            if status:
                query = query.eq("status", status)

            response = query.order("created_at", desc=True).limit(10).execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取待观察点失败: {e.message}")
            raise Exception(f"获取待观察点失败: {e.message}")

    def add_pending_observation(self, family_id: str, child_id: str, content: str,
                                 related_scene: Optional[str] = None,
                                 priority: Optional[str] = "medium",
                                 source: Optional[str] = "daily_agent") -> dict:
        """新增待观察点"""
        try:
            # 先检查是否已有相似待观察点（去重）
            existing = self.client.table("pending_observations") \
                .select("id") \
                .eq("child_id", child_id) \
                .eq("status", "active") \
                .eq("content", content) \
                .maybe_single() \
                .execute()
            if existing:
                return {"id": existing.data["id"], "status": "duplicate"}

            response = self.client.table("pending_observations").insert({
                "family_id": family_id,
                "child_id": child_id,
                "content": content,
                "related_scene": related_scene,
                "priority": priority,
                "source": source,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增待观察点失败: {e.message}")
            raise Exception(f"新增待观察点失败: {e.message}")

    def resolve_pending_observation(self, observation_id: int) -> dict:
        """标记待观察点为已解决"""
        try:
            response = self.client.table("pending_observations") \
                .update({"status": "resolved", "updated_at": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", observation_id) \
                .execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"解决待观察点失败: {e.message}")
            raise Exception(f"解决待观察点失败: {e.message}")

    # ========== 长期关注目标 ==========

    def get_long_term_goals(self, child_id: str, status: str = "active") -> list[dict]:
        """获取家长长期关注目标"""
        try:
            query = self.client.table("long_term_goals") \
                .select("id,goal_name,goal_category,weight,related_scenes,status,last_triggered_at,created_at") \
                .eq("child_id", child_id)

            if status:
                query = query.eq("status", status)

            response = query.order("weight", desc=True).limit(10).execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取长期关注目标失败: {e.message}")
            raise Exception(f"获取长期关注目标失败: {e.message}")

    def add_long_term_goal(self, family_id: str, child_id: str, goal_name: str,
                            goal_category: Optional[str] = None,
                            weight: Optional[float] = 0.5) -> dict:
        """新增长期关注目标"""
        try:
            # 去重检查
            existing = self.client.table("long_term_goals") \
                .select("id") \
                .eq("child_id", child_id) \
                .eq("goal_name", goal_name) \
                .eq("status", "active") \
                .maybe_single() \
                .execute()
            if existing:
                return {"id": existing.data["id"], "status": "duplicate"}

            response = self.client.table("long_term_goals").insert({
                "family_id": family_id,
                "child_id": child_id,
                "goal_name": goal_name,
                "goal_category": goal_category,
                "weight": weight,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增长期关注目标失败: {e.message}")
            raise Exception(f"新增长期关注目标失败: {e.message}")

    # ========== 纠偏记录 ==========

    def get_correction_logs(self, child_id: str, limit: int = 10) -> list[dict]:
        """获取纠偏记录"""
        try:
            response = self.client.table("correction_logs") \
                .select("id,old_judgment,new_judgment,correction_type,reason,confidence,created_at") \
                .eq("child_id", child_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取纠偏记录失败: {e.message}")
            raise Exception(f"获取纠偏记录失败: {e.message}")

    def add_correction_log(self, family_id: str, child_id: str, old_judgment: str,
                            new_judgment: str, correction_type: str, reason: str,
                            confidence: Optional[float] = 0.5) -> dict:
        """新增纠偏记录"""
        try:
            response = self.client.table("correction_logs").insert({
                "family_id": family_id,
                "child_id": child_id,
                "old_judgment": old_judgment,
                "new_judgment": new_judgment,
                "correction_type": correction_type,
                "reason": reason,
                "confidence": confidence,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增纠偏记录失败: {e.message}")
            raise Exception(f"新增纠偏记录失败: {e.message}")

    # ========== 诊断交接 ==========

    def get_diagnosis_handoff(self, child_id: str) -> Optional[dict]:
        """获取诊断 Agent 的交接摘要"""
        try:
            response = self.client.table("diagnosis_handoffs") \
                .select("id,initial_understanding,key_child_patterns,parent_concerns,family_interaction_hypotheses,pending_observations,created_at") \
                .eq("child_id", child_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            if response and response.data:
                return response.data[0]
            return None
        except APIError as e:
            logger.error(f"获取诊断交接失败: {e.message}")
            raise Exception(f"获取诊断交接失败: {e.message}")

    # ========== 问卷记录 ==========

    def get_questionnaire(self, child_id: str) -> Optional[dict]:
        """获取孩子问卷记录"""
        try:
            response = self.client.table("questionnaire_records") \
                .select("id,raw_answers,summary,child_self_view,conflicts_with_parent_view,status,created_at") \
                .eq("child_id", child_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            if response and response.data:
                return response.data[0]
            return None
        except APIError as e:
            logger.error(f"获取问卷记录失败: {e.message}")
            raise Exception(f"获取问卷记录失败: {e.message}")

    # ========== 沟通预演记录 ==========

    def add_rehearsal_record(self, family_id: str, child_id: str, topic: str,
                              parent_goal: Optional[str] = None,
                              child_perspective_summary: Optional[str] = None,
                              parent_child_mismatch: Optional[str] = None,
                              suggested_direction: Optional[str] = None,
                              possible_misunderstanding: Optional[str] = None) -> dict:
        """新增沟通预演记录"""
        try:
            response = self.client.table("rehearsal_records").insert({
                "family_id": family_id,
                "child_id": child_id,
                "topic": topic,
                "parent_goal": parent_goal,
                "child_perspective_summary": child_perspective_summary,
                "parent_child_mismatch": parent_child_mismatch,
                "suggested_direction": suggested_direction,
                "possible_misunderstanding": possible_misunderstanding,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增沟通预演记录失败: {e.message}")
            raise Exception(f"新增沟通预演记录失败: {e.message}")

    # ========== 对话事件 ==========

    def add_conversation_event(self, conversation_id: str, family_id: str,
                                role: str, content: str, child_id: Optional[str] = None,
                                message_type: Optional[str] = None,
                                raw_agent_output: Optional[dict] = None) -> dict:
        """记录对话事件"""
        try:
            response = self.client.table("conversation_events").insert({
                "conversation_id": conversation_id,
                "family_id": family_id,
                "child_id": child_id,
                "role": role,
                "content": content,
                "message_type": message_type,
                "raw_agent_output": raw_agent_output,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"记录对话事件失败: {e.message}")
            raise Exception(f"记录对话事件失败: {e.message}")


# 全局单例
_memory_service = None

def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
