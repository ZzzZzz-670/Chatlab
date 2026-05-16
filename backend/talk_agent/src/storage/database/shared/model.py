from coze_coding_dev_sdk.database import Base

from typing import Optional
import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Double, Index, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Table, Text, text
from sqlalchemy.dialects.postgresql import OID
from sqlalchemy.orm import Mapped, mapped_column

class ChildProfiles(Base):
    __tablename__ = 'child_profiles'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='child_profiles_pkey'),
        Index('child_profiles_child_id_idx', 'child_id', unique=True),
        Index('child_profiles_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='孩子唯一标识')
    family_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='家庭唯一标识')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    nickname: Mapped[Optional[str]] = mapped_column(String(64), comment='昵称')
    grade: Mapped[Optional[str]] = mapped_column(String(32), comment='年级')
    gender: Mapped[Optional[str]] = mapped_column(String(16), comment='性别')
    school_stage: Mapped[Optional[str]] = mapped_column(String(32), comment='学段')
    profile_summary: Mapped[Optional[str]] = mapped_column(Text, comment='画像摘要')
    profile_completeness: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0'), comment='画像完整度')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class ConversationEvents(Base):
    __tablename__ = 'conversation_events'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='conversation_events_pkey'),
        Index('conversation_events_conversation_id_idx', 'conversation_id'),
        Index('conversation_events_created_at_idx', 'created_at'),
        Index('conversation_events_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    child_id: Mapped[Optional[str]] = mapped_column(String(64))
    role: Mapped[Optional[str]] = mapped_column(String(16), comment='角色: user/assistant')
    content: Mapped[Optional[str]] = mapped_column(Text, comment='消息内容')
    message_type: Mapped[Optional[str]] = mapped_column(String(64), comment='消息类型')
    raw_agent_output: Mapped[Optional[dict]] = mapped_column(JSON, comment='Agent原始输出')


class CorrectionLogs(Base):
    __tablename__ = 'correction_logs'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='correction_logs_pkey'),
        Index('correction_logs_child_id_idx', 'child_id'),
        Index('correction_logs_created_at_idx', 'created_at'),
        Index('correction_logs_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    old_judgment: Mapped[Optional[str]] = mapped_column(Text, comment='旧判断')
    new_judgment: Mapped[Optional[str]] = mapped_column(Text, comment='新判断')
    correction_type: Mapped[Optional[str]] = mapped_column(String(32), comment='纠偏类型: deprecate_old/replace_old/narrow_scope/split_judgment/add_exception')
    reason: Mapped[Optional[str]] = mapped_column(Text, comment='纠偏原因')
    confidence: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.5'))


class DiagnosisHandoffs(Base):
    __tablename__ = 'diagnosis_handoffs'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='diagnosis_handoffs_pkey'),
        Index('diagnosis_handoffs_child_id_idx', 'child_id'),
        Index('diagnosis_handoffs_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    initial_understanding: Mapped[Optional[str]] = mapped_column(Text, comment='初始理解')
    key_child_patterns: Mapped[Optional[dict]] = mapped_column(JSON, comment='孩子关键模式')
    parent_concerns: Mapped[Optional[dict]] = mapped_column(JSON, comment='家长关注点')
    family_interaction_hypotheses: Mapped[Optional[dict]] = mapped_column(JSON, comment='家庭互动假设')
    pending_observations: Mapped[Optional[dict]] = mapped_column(JSON, comment='待观察点')


class FamilyInteractionPatterns(Base):
    __tablename__ = 'family_interaction_patterns'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='family_interaction_patterns_pkey'),
        Index('family_interaction_patterns_child_id_idx', 'child_id'),
        Index('family_interaction_patterns_family_id_idx', 'family_id'),
        Index('family_interaction_patterns_pattern_name_idx', 'pattern_name')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='模式内容描述')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    pattern_name: Mapped[Optional[str]] = mapped_column(String(64), comment='模式名称')
    scene: Mapped[Optional[str]] = mapped_column(String(64), comment='场景')
    confidence: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.5'))
    evidence_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('1'))
    status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'candidate'::character varying"), comment='状态: candidate/active/confirmed/deprecated')
    last_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class GrowthRecords(Base):
    __tablename__ = 'growth_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='growth_records_pkey'),
        Index('growth_records_child_id_idx', 'child_id'),
        Index('growth_records_created_at_idx', 'created_at'),
        Index('growth_records_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='成长记录内容')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    scene_type: Mapped[Optional[str]] = mapped_column(String(64), comment='场景类型')
    signal_type: Mapped[Optional[str]] = mapped_column(String(64), comment='信号类型: positive/neutral/warning')
    direction: Mapped[Optional[str]] = mapped_column(String(32), comment='变化方向')
    importance: Mapped[Optional[str]] = mapped_column(String(16), comment='重要度: low/medium/high')
    source: Mapped[Optional[str]] = mapped_column(String(32), comment='来源')
    confidence: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.5'))


class HealthCheck(Base):
    __tablename__ = 'health_check'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='health_check_pkey'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('now()'))


class LongTermGoals(Base):
    __tablename__ = 'long_term_goals'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='long_term_goals_pkey'),
        Index('long_term_goals_child_id_idx', 'child_id'),
        Index('long_term_goals_family_id_idx', 'family_id'),
        Index('long_term_goals_status_idx', 'status')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    goal_name: Mapped[str] = mapped_column(String(128), nullable=False, comment='目标名称')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    goal_category: Mapped[Optional[str]] = mapped_column(String(64), comment='目标分类')
    weight: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.5'), comment='权重')
    related_scenes: Mapped[Optional[dict]] = mapped_column(JSON, comment='关联场景列表')
    status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'active'::character varying"), comment='状态')
    last_triggered_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class ParentProfileEntries(Base):
    __tablename__ = 'parent_profile_entries'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='parent_profile_entries_pkey'),
        Index('parent_profile_entries_category_idx', 'category'),
        Index('parent_profile_entries_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='内容')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    category: Mapped[Optional[str]] = mapped_column(String(64), comment='画像维度')
    confidence: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.5'))
    status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'active'::character varying"))
    source: Mapped[Optional[str]] = mapped_column(String(32), comment='来源')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class PendingObservations(Base):
    __tablename__ = 'pending_observations'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='pending_observations_pkey'),
        Index('pending_observations_child_id_idx', 'child_id'),
        Index('pending_observations_family_id_idx', 'family_id'),
        Index('pending_observations_status_idx', 'status')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='待观察内容')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    related_scene: Mapped[Optional[str]] = mapped_column(String(64), comment='关联场景')
    priority: Mapped[Optional[str]] = mapped_column(String(16), server_default=text("'medium'::character varying"), comment='优先级: low/medium/high')
    status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'active'::character varying"), comment='状态: active/resolved/archived')
    source: Mapped[Optional[str]] = mapped_column(String(32), comment='来源')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


t_pg_stat_statements = Table(
    'pg_stat_statements', Base.metadata,
    Column('userid', OID),
    Column('dbid', OID),
    Column('toplevel', Boolean),
    Column('queryid', BigInteger),
    Column('query', Text),
    Column('plans', BigInteger),
    Column('total_plan_time', Double(53)),
    Column('min_plan_time', Double(53)),
    Column('max_plan_time', Double(53)),
    Column('mean_plan_time', Double(53)),
    Column('stddev_plan_time', Double(53)),
    Column('calls', BigInteger),
    Column('total_exec_time', Double(53)),
    Column('min_exec_time', Double(53)),
    Column('max_exec_time', Double(53)),
    Column('mean_exec_time', Double(53)),
    Column('stddev_exec_time', Double(53)),
    Column('rows', BigInteger),
    Column('shared_blks_hit', BigInteger),
    Column('shared_blks_read', BigInteger),
    Column('shared_blks_dirtied', BigInteger),
    Column('shared_blks_written', BigInteger),
    Column('local_blks_hit', BigInteger),
    Column('local_blks_read', BigInteger),
    Column('local_blks_dirtied', BigInteger),
    Column('local_blks_written', BigInteger),
    Column('temp_blks_read', BigInteger),
    Column('temp_blks_written', BigInteger),
    Column('shared_blk_read_time', Double(53)),
    Column('shared_blk_write_time', Double(53)),
    Column('local_blk_read_time', Double(53)),
    Column('local_blk_write_time', Double(53)),
    Column('temp_blk_read_time', Double(53)),
    Column('temp_blk_write_time', Double(53)),
    Column('wal_records', BigInteger),
    Column('wal_fpi', BigInteger),
    Column('wal_bytes', Numeric),
    Column('jit_functions', BigInteger),
    Column('jit_generation_time', Double(53)),
    Column('jit_inlining_count', BigInteger),
    Column('jit_inlining_time', Double(53)),
    Column('jit_optimization_count', BigInteger),
    Column('jit_optimization_time', Double(53)),
    Column('jit_emission_count', BigInteger),
    Column('jit_emission_time', Double(53)),
    Column('jit_deform_count', BigInteger),
    Column('jit_deform_time', Double(53)),
    Column('stats_since', DateTime(True)),
    Column('minmax_stats_since', DateTime(True))
)


t_pg_stat_statements_info = Table(
    'pg_stat_statements_info', Base.metadata,
    Column('dealloc', BigInteger),
    Column('stats_reset', DateTime(True))
)


class ProfileEntries(Base):
    __tablename__ = 'profile_entries'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='profile_entries_pkey'),
        Index('profile_entries_category_idx', 'category'),
        Index('profile_entries_child_id_idx', 'child_id'),
        Index('profile_entries_family_id_idx', 'family_id'),
        Index('profile_entries_status_idx', 'status')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='画像内容')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    category: Mapped[Optional[str]] = mapped_column(String(64), comment='画像维度')
    confidence: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('0.5'), comment='置信度')
    status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'hypothesis'::character varying"), comment='状态: hypothesis/active/confirmed/conflicted/deprecated/archived')
    source: Mapped[Optional[str]] = mapped_column(String(32), comment='来源: diagnosis_agent/daily_agent/questionnaire')
    evidence_count: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('1'), comment='证据数量')
    last_confirmed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class ProfileUpdateLog(Base):
    __tablename__ = 'profile_update_log'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='profile_update_log_pkey'),
        Index('profile_update_log_child_id_idx', 'child_id'),
        Index('profile_update_log_created_at_idx', 'created_at'),
        Index('profile_update_log_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    operation: Mapped[Optional[str]] = mapped_column(String(32), comment='操作类型')
    target_table: Mapped[Optional[str]] = mapped_column(String(64), comment='目标表')
    target_id: Mapped[Optional[int]] = mapped_column(Integer, comment='目标记录ID')
    summary: Mapped[Optional[str]] = mapped_column(Text, comment='更新摘要')
    source_message_id: Mapped[Optional[str]] = mapped_column(String(64), comment='来源消息ID')


class QuestionnaireRecords(Base):
    __tablename__ = 'questionnaire_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='questionnaire_records_pkey'),
        Index('questionnaire_records_child_id_idx', 'child_id'),
        Index('questionnaire_records_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    raw_answers: Mapped[Optional[dict]] = mapped_column(JSON, comment='原始答案')
    summary: Mapped[Optional[str]] = mapped_column(Text, comment='问卷摘要')
    child_self_view: Mapped[Optional[dict]] = mapped_column(JSON, comment='孩子自我视角')
    conflicts_with_parent_view: Mapped[Optional[dict]] = mapped_column(JSON, comment='与家长描述的冲突')
    status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'not_started'::character varying"), comment='状态')


class RehearsalRecords(Base):
    __tablename__ = 'rehearsal_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='rehearsal_records_pkey'),
        Index('rehearsal_records_child_id_idx', 'child_id'),
        Index('rehearsal_records_created_at_idx', 'created_at'),
        Index('rehearsal_records_family_id_idx', 'family_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    topic: Mapped[Optional[str]] = mapped_column(String(256), comment='预演主题')
    parent_goal: Mapped[Optional[str]] = mapped_column(Text, comment='家长目标')
    child_perspective_summary: Mapped[Optional[str]] = mapped_column(Text, comment='孩子视角摘要')
    parent_child_mismatch: Mapped[Optional[str]] = mapped_column(Text, comment='亲子差异')
    suggested_direction: Mapped[Optional[str]] = mapped_column(Text, comment='表达方向')
    possible_misunderstanding: Mapped[Optional[str]] = mapped_column(Text, comment='可能误会')
    related_child_profile_entries: Mapped[Optional[dict]] = mapped_column(JSON)
    related_family_patterns: Mapped[Optional[dict]] = mapped_column(JSON)
