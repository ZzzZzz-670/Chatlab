"""
Profile Service - 孩子画像更新服务
负责画像条目的读写、合并、置信度调整、降权、纠偏
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from postgrest.exceptions import APIError
from storage.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


# 画像维度枚举
PROFILE_DIMENSIONS = [
    "learning_start",       # 学习启动
    "learning_process",     # 学习过程
    "emotion_response",     # 情绪反应
    "communication_style",  # 沟通方式
    "social_preference",    # 社交偏好
    "phone_boundary",       # 手机边界
    "interest_motivation",  # 兴趣动力
    "self_management",      # 自我管理
    "other",                # 其他
]

# 状态流转规则
STATUS_TRANSITIONS = {
    "hypothesis": ["active", "deprecated"],   # 初始假设 → 确认或废弃
    "active": ["confirmed", "conflicted", "deprecated"],  # 当前有效 → 确认/冲突/废弃
    "confirmed": ["conflicted", "deprecated"],  # 已确认 → 冲突/废弃
    "conflicted": ["active", "deprecated"],    # 冲突 → 恢复或废弃
    "deprecated": ["archived"],                # 废弃 → 归档
    "archived": [],                            # 终态
}


class ProfileService:
    """画像服务：负责孩子画像条目的读写和更新"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    # ========== 孩子画像主表 ==========

    def get_child_profile(self, child_id: str) -> Optional[dict]:
        """获取孩子画像主信息"""
        try:
            response = self.client.table("child_profiles") \
                .select("id,child_id,family_id,nickname,grade,gender,school_stage,profile_summary,profile_completeness,created_at,updated_at") \
                .eq("child_id", child_id) \
                .maybe_single() \
                .execute()
            return response.data if response else None
        except APIError as e:
            logger.error(f"获取孩子画像失败: {e.message}")
            raise Exception(f"获取孩子画像失败: {e.message}")

    def get_or_create_child_profile(self, child_id: str, family_id: str,
                                     nickname: Optional[str] = None) -> dict:
        """获取或创建孩子画像"""
        existing = self.get_child_profile(child_id)
        if existing:
            return existing

        try:
            response = self.client.table("child_profiles").insert({
                "child_id": child_id,
                "family_id": family_id,
                "nickname": nickname,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"创建孩子画像失败: {e.message}")
            raise Exception(f"创建孩子画像失败: {e.message}")

    # ========== 画像条目 ==========

    def get_profile_entries(self, child_id: str, status: Optional[str] = None,
                             category: Optional[str] = None) -> list[dict]:
        """获取孩子的画像条目"""
        try:
            query = self.client.table("profile_entries") \
                .select("id,category,content,confidence,status,source,evidence_count,last_confirmed_at,created_at,updated_at") \
                .eq("child_id", child_id)

            if status:
                query = query.eq("status", status)
            if category:
                query = query.eq("category", category)

            response = query.order("updated_at", desc=True).limit(50).execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取画像条目失败: {e.message}")
            raise Exception(f"获取画像条目失败: {e.message}")

    def add_profile_entry(self, family_id: str, child_id: str, category: str,
                           content: str, source: str = "daily_agent",
                           confidence: float = 0.5) -> dict:
        """新增画像条目（带去重和合并逻辑）

        核心规则：
        1. 单次事件不直接变成稳定画像
        2. 同类记忆要合并，不要重复新增
        3. 新事实支持旧判断 → 增强权重
        4. 新事实挑战旧判断 → 生成纠偏候选
        """
        try:
            # 1. 查找同维度的现有条目
            existing_entries = self.client.table("profile_entries") \
                .select("id,content,confidence,status,evidence_count,source") \
                .eq("child_id", child_id) \
                .eq("category", category) \
                .neq("status", "archived") \
                .neq("status", "deprecated") \
                .execute()

            if existing_entries and existing_entries.data:
                # 2. 检查是否有语义相似的条目（简化版：通过文本匹配）
                for entry in existing_entries.data:
                    # 简单相似度判断：内容核心关键词重合
                    if self._is_similar_content(entry["content"], content):
                        # 3. 合并：增强已有条目的置信度
                        new_confidence = min(entry.get("confidence", 0.5) + 0.1, 1.0)
                        new_evidence_count = entry.get("evidence_count", 1) + 1

                        update_data = {
                            "confidence": new_confidence,
                            "evidence_count": new_evidence_count,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }

                        # 证据数 >= 3 时从 hypothesis 升级到 active
                        if new_evidence_count >= 3 and entry["status"] == "hypothesis":
                            update_data["status"] = "active"
                            update_data["last_confirmed_at"] = datetime.now(timezone.utc).isoformat()

                        self.client.table("profile_entries") \
                            .update(update_data) \
                            .eq("id", entry["id"]) \
                            .execute()

                        return {"id": entry["id"], "status": "merged", "new_confidence": new_confidence}

            # 4. 无相似条目，新增
            response = self.client.table("profile_entries").insert({
                "family_id": family_id,
                "child_id": child_id,
                "category": category,
                "content": content,
                "confidence": confidence,
                "source": source,
                "evidence_count": 1,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增画像条目失败: {e.message}")
            raise Exception(f"新增画像条目失败: {e.message}")

    def update_profile_entry(self, entry_id: int, updates: dict) -> dict:
        """更新画像条目"""
        try:
            if "updated_at" not in updates:
                updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            response = self.client.table("profile_entries") \
                .update(updates) \
                .eq("id", entry_id) \
                .execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"更新画像条目失败: {e.message}")
            raise Exception(f"更新画像条目失败: {e.message}")

    def deprecate_profile_entry(self, entry_id: int, reason: Optional[str] = None) -> dict:
        """降权/废弃画像条目"""
        try:
            updates = {
                "status": "deprecated",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            response = self.client.table("profile_entries") \
                .update(updates) \
                .eq("id", entry_id) \
                .execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"降权画像条目失败: {e.message}")
            raise Exception(f"降权画像条目失败: {e.message}")

    # ========== 家长画像条目 ==========

    def get_parent_profile_entries(self, family_id: str, category: Optional[str] = None) -> list[dict]:
        """获取家长画像条目"""
        try:
            query = self.client.table("parent_profile_entries") \
                .select("id,category,content,confidence,status,source,created_at,updated_at") \
                .eq("family_id", family_id)

            if category:
                query = query.eq("category", category)

            response = query.order("updated_at", desc=True).limit(20).execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取家长画像条目失败: {e.message}")
            raise Exception(f"获取家长画像条目失败: {e.message}")

    def add_parent_profile_entry(self, family_id: str, category: str, content: str,
                                  source: str = "daily_agent", confidence: float = 0.5) -> dict:
        """新增家长画像条目"""
        try:
            # 去重
            existing = self.client.table("parent_profile_entries") \
                .select("id") \
                .eq("family_id", family_id) \
                .eq("category", category) \
                .eq("content", content) \
                .neq("status", "deprecated") \
                .maybe_single() \
                .execute()
            if existing:
                return {"id": existing.data["id"], "status": "duplicate"}

            response = self.client.table("parent_profile_entries").insert({
                "family_id": family_id,
                "category": category,
                "content": content,
                "confidence": confidence,
                "source": source,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增家长画像条目失败: {e.message}")
            raise Exception(f"新增家长画像条目失败: {e.message}")

    # ========== 家庭互动模式 ==========

    def get_family_interaction_patterns(self, child_id: str, status: Optional[str] = None) -> list[dict]:
        """获取家庭互动模式"""
        try:
            query = self.client.table("family_interaction_patterns") \
                .select("id,pattern_name,content,scene,confidence,evidence_count,status,last_seen_at,created_at") \
                .eq("child_id", child_id)

            if status:
                query = query.eq("status", status)

            response = query.order("updated_at", desc=True).limit(10).execute()
            return response.data if response else []
        except APIError as e:
            logger.error(f"获取家庭互动模式失败: {e.message}")
            raise Exception(f"获取家庭互动模式失败: {e.message}")

    def add_family_interaction_pattern(self, family_id: str, child_id: str, content: str,
                                        pattern_name: Optional[str] = None,
                                        scene: Optional[str] = None,
                                        confidence: float = 0.5) -> dict:
        """新增家庭互动模式（带去重和增强逻辑）"""
        try:
            # 查找相似模式
            existing_patterns = self.client.table("family_interaction_patterns") \
                .select("id,content,confidence,evidence_count,status") \
                .eq("child_id", child_id) \
                .neq("status", "deprecated") \
                .execute()

            if existing_patterns and existing_patterns.data:
                for pattern in existing_patterns.data:
                    if self._is_similar_content(pattern["content"], content):
                        # 增强已有模式
                        new_confidence = min(pattern.get("confidence", 0.5) + 0.1, 1.0)
                        new_evidence_count = pattern.get("evidence_count", 1) + 1

                        update_data = {
                            "confidence": new_confidence,
                            "evidence_count": new_evidence_count,
                            "last_seen_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        if new_evidence_count >= 3 and pattern["status"] == "candidate":
                            update_data["status"] = "active"

                        self.client.table("family_interaction_patterns") \
                            .update(update_data) \
                            .eq("id", pattern["id"]) \
                            .execute()

                        return {"id": pattern["id"], "status": "merged", "new_confidence": new_confidence}

            # 新增
            response = self.client.table("family_interaction_patterns").insert({
                "family_id": family_id,
                "child_id": child_id,
                "pattern_name": pattern_name,
                "content": content,
                "scene": scene,
                "confidence": confidence,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"新增家庭互动模式失败: {e.message}")
            raise Exception(f"新增家庭互动模式失败: {e.message}")

    # ========== 画像更新日志 ==========

    def add_profile_update_log(self, family_id: str, child_id: str, operation: str,
                                target_table: str, target_id: Optional[int] = None,
                                summary: Optional[str] = None,
                                source_message_id: Optional[str] = None) -> dict:
        """记录画像更新操作"""
        try:
            response = self.client.table("profile_update_log").insert({
                "family_id": family_id,
                "child_id": child_id,
                "operation": operation,
                "target_table": target_table,
                "target_id": target_id,
                "summary": summary,
                "source_message_id": source_message_id,
            }).execute()
            return response.data[0] if response and response.data else {}
        except APIError as e:
            logger.error(f"记录画像更新日志失败: {e.message}")
            raise Exception(f"记录画像更新日志失败: {e.message}")

    # ========== 辅助方法 ==========

    @staticmethod
    def _is_similar_content(existing: str, new: str, threshold: float = 0.5) -> bool:
        """简单的内容相似度判断（基于关键词重叠）

        注意：这是简化版本，生产环境应使用嵌入向量做语义相似度
        """
        if not existing or not new:
            return False

        # 完全匹配
        if existing.strip() == new.strip():
            return True

        # 提取关键词（简单分词）
        existing_words = set(existing.replace("，", " ").replace("。", " ").replace("的", " ").split())
        new_words = set(new.replace("，", " ").replace("。", " ").replace("的", " ").split())

        # 去除停用词和短词
        stop_words = {"了", "是", "在", "有", "和", "都", "也", "就", "要", "会", "着", "没", "这", "那", "他", "她", "我", "你"}
        existing_words = {w for w in existing_words if len(w) >= 2 and w not in stop_words}
        new_words = {w for w in new_words if len(w) >= 2 and w not in stop_words}

        if not existing_words or not new_words:
            return False

        # Jaccard 相似度
        intersection = existing_words & new_words
        union = existing_words | new_words
        similarity = len(intersection) / len(union) if union else 0

        return similarity >= threshold


# 全局单例
_profile_service = None

def get_profile_service() -> ProfileService:
    global _profile_service
    if _profile_service is None:
        _profile_service = ProfileService()
    return _profile_service
