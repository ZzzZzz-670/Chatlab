"""
对话实验室知识库分库检索工具
按 A/B/C/D/E 五库独立检索，基于 pgvector 直接查询 PostgreSQL。
"""
import os
import re
import json
import psycopg2
from langchain.tools import tool
from coze_coding_dev_sdk import EmbeddingClient, Config
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

# tool_trace 日志：直接写文件，避免 logging 缓冲问题
_TRACE_LOG_PATH = "/tmp/knowledge_tool_trace.log"

def _write_trace(entry: dict):
    """写入 tool_trace 日志（直接 append 到文件）"""
    try:
        with open(_TRACE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass

# 各库对应表名
_LIB_TABLE_MAP = {
    "A": "knowledge.coze_doc_knowledge_a",
    "B": "knowledge.coze_doc_knowledge_b",
    "C": "knowledge.coze_doc_knowledge_c",
    "D": "knowledge.coze_doc_knowledge_d",
    "E": "knowledge.coze_doc_knowledge_e",
}

# 各库最低 score 阈值
_LIB_MIN_SCORE = {
    "A": 0.45,
    "B": 0.42,
    "C": 0.42,
    "D": 0.45,
    "E": 0.32,
}

# 内部术语映射
_INTERNAL_TITLE_MAP = {
    "后台想判断": "判断方向",
    "不要问": "避免这样问",
    "改问": "建议这样问",
    "家长标签": "常见说法",
    "不直接采信": "需要进一步了解",
    "转成分支问题": "转化为具体问题",
    "前台必须": "表达要点",
    "前台表达": "表达建议",
    "追问问题": "可以问",
    "判断标准": "参考标准",
    "反证边界": "需要注意",
    "黑名单": "避免的说法",
    "安全废话": "避免空洞安慰",
    "能力断层": "学习基础",
    "无结束感": "缺乏完成感",
    "自主权不足": "自主空间",
    "被评价防御": "对评价的敏感",
    "亲子污染": "沟通方式",
    "表面配合": "表面顺从",
    "压力出口": "情绪释放",
    "休息权争夺": "休息需求",
    "控制感缺失": "自主感受",
}

_REMOVE_TITLES = ["后台想判断", "不要问", "改问", "家长标签", "不直接采信", "转成分支问题"]


def _get_db_conn():
    """获取 PostgreSQL 连接"""
    url = os.environ.get("PGDATABASE_URL")
    return psycopg2.connect(url)


def _get_embedding(text: str) -> list:
    """生成 1024 维 embedding 向量"""
    config = Config()
    ctx = request_context.get() or new_context(method="knowledge_embed")
    client = EmbeddingClient(config=config, ctx=ctx, verbose=False)
    resp = client.embed(texts=[text], dimensions=1024)
    return resp.data.embedding


def _search_lib(lib: str, query: str, top_k: int = 3) -> str:
    """
    在指定库中检索，返回清洗后的结果文本。

    Args:
        lib: 库名 "A"/"B"/"C"/"D"/"E"
        query: 搜索查询
        top_k: 返回最多几条

    Returns:
        清洗后的检索结果文本
    """
    table = _LIB_TABLE_MAP.get(lib)
    if not table:
        return f"未知库名: {lib}"

    min_score = _LIB_MIN_SCORE.get(lib, 0.35)

    try:
        query_emb = _get_embedding(query)
    except Exception as e:
        return f"向量生成失败: {e}"

    emb_str = "[" + ",".join(str(v) for v in query_emb) + "]"

    conn = None
    try:
        conn = _get_db_conn()
        cur = conn.cursor()

        # 禁用索引扫描，使用全表扫描（小数据量时更可靠）
        cur.execute("SET enable_indexscan = off")
        cur.execute("SET enable_seqscan = on")

        cur.execute(f"""
            SELECT content, 1 - (embedding <=> %s::vector) as score
            FROM {table}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (emb_str, emb_str, top_k))

        rows = cur.fetchall()

        if not rows:
            return f"未在{lib}库中找到相关内容。"

        # === tool_trace 日志 ===
        trace_entry = {
            "lib": lib,
            "query": query,
            "top_k": top_k,
            "min_score": min_score,
            "raw_results": [],
            "adopted": [],
            "ignored": [],
        }
        for content, score in rows:
            trace_entry["raw_results"].append({
                "score": round(score, 4),
                "content_preview": content[:80],
            })

        results = []
        for content, score in rows:
            if score < min_score:
                trace_entry["ignored"].append({"score": round(score, 4), "reason": "below_threshold"})
                continue
            cleaned = _clean_chunk(content)
            if cleaned.strip():
                results.append(cleaned)
                trace_entry["adopted"].append({"score": round(score, 4), "content_preview": cleaned[:80]})
            else:
                trace_entry["ignored"].append({"score": round(score, 4), "reason": "empty_after_clean"})

        _write_trace(trace_entry)

        if not results:
            return f"未在{lib}库中找到足够相关的内容（最高score低于阈值{min_score}）。"

        return "\n\n".join(results)

    except Exception as e:
        _write_trace({"lib": lib, "query": query, "error": str(e)})
        return f"检索失败: {e}"
    finally:
        if conn:
            conn.close()


def _clean_table_row(line: str) -> str:
    """把Markdown表格行转换为纯文本描述"""
    line = line.strip()
    if not line.startswith("|") or not line.endswith("|"):
        return line

    cells = [c.strip() for c in line[1:-1].split("|")]
    cells = [c for c in cells if c and c != "---" and not set(c).issubset({"-", ":", " "})]

    if not cells:
        return ""

    first_cell = cells[0]
    for title in _REMOVE_TITLES:
        if title in first_cell:
            return ""

    if len(cells) >= 3 and any(t in first_cell for t in ["懒", "没内驱力", "不自觉", "玻璃心", "沉迷手机", "没羞耻心"]):
        return f"家长常说孩子{cells[0]}，其实可能需要了解：{cells[2]}"

    if len(cells) >= 3:
        return f"关于{cells[0]}：不要问「{cells[1]}」，建议问「{cells[2]}」"

    return "；".join(cells)


def _clean_chunk(text: str) -> str:
    """清洗知识库原始内容，去掉内部术语、Markdown表格、章节标题、判断短句"""
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue
        if set(stripped).issubset({"|", "-", ":", " "}):
            continue

        # 去掉行首的Markdown标题标记
        stripped = re.sub(r'^#{1,6}\s*', '', stripped)

        # 过滤章节标题
        if re.match(r'^[一二三四五六七八九十百千零〇]+[、.．]\s*', stripped):
            continue
        if re.match(r'^(\d+[.．、]|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩])\s*', stripped):
            continue
        if re.match(r'^[IVXLCivxlc]+[.．、]\s*', stripped):
            continue

        # 过滤内部检查语句
        if re.search(r'是否[^，。\n]*?(问|检查|核实|确认|判断)', stripped):
            continue
        if stripped.startswith('是否'):
            continue

        # 过滤判断性短句
        if re.match(r'^家长[^，。]{0,20}(高控制|控制|没有结束感|努力被加码|被加码|自主权不足|被评价防御|表面配合|亲子污染)', stripped):
            continue

        # 过滤内部规则/黑名单短句
        if re.match(r'^家长说[^，。]{0,20}就判断', stripped):
            continue
        if '全部解释成' in stripped or '或反过来' in stripped:
            continue
        if '顺着家长说' in stripped:
            continue
        if '就默认解释成' in stripped:
            continue
        if re.match(r'^[\uf0b7\u2022\u258b\u25cf\u25cb\u25a0\u25aa\u25ab\u2023\u2043\u2219]', stripped):
            continue
        if re.match(r'^看到[^，。]{0,12}就说', stripped):
            continue
        if re.match(r'^孩子这样是[^，。]{0,12}(逼出来|造成的|导致的)', stripped):
            continue
        if re.match(r'^(看到母亲|看到父亲|看到孩子|看到拖延|看到顶嘴|看到没朋友|看到玩手机|看到乖)', stripped):
            continue
        if re.match(r'^(只看到|只看|只注意|只盯着)', stripped):
            continue
        if '不能作为主要输出' in stripped or '废弃表达' in stripped:
            continue
        if '禁止安全废话' in stripped or '禁止过度' in stripped:
            continue
        if '避免' in stripped and ('问' in stripped or '说' in stripped):
            continue

        # 处理Markdown表格行
        if stripped.startswith("|") and stripped.endswith("|"):
            cleaned = _clean_table_row(stripped)
            if cleaned:
                cleaned_lines.append(cleaned)
            continue

        # 处理普通行中的内部术语
        for old, new in _INTERNAL_TITLE_MAP.items():
            stripped = stripped.replace(old, new)

        if stripped.count("|") >= 2:
            cleaned = _clean_table_row(stripped)
            if cleaned:
                cleaned_lines.append(cleaned)
            continue

        cleaned_lines.append(stripped)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


# ============================================================
# 5 个分库检索工具
# ============================================================

@tool
def search_branch_library(query: str) -> str:
    """
    A库｜原因分支库
    用途：判断孩子行为背后的可能原因、候选方向、反证边界、下一步追问方向。
    适用：作业拖延、手机、沉默、厌学、没内驱力、表面配合、社交归属感弱、家长叙事错位等原因判断。
    不适用：生成前台文案、输出诊断卡语言、查黑名单。

    Args:
        query: 搜索查询，建议格式：场景+家长说法+孩子行为+需要区分的候选原因
               示例："原因分支 判断标准：场景=作业拖延，家长说法=孩子懒不自觉，孩子行为=写作业磨蹭，区分能力断层/任务暴露/休息权/被评价防御"

    Returns:
        检索到的A库内容（已清洗为纯文本）。
    """
    return _search_lib("A", query, top_k=3)


@tool
def search_question_library(query: str) -> str:
    """
    B库｜事实转换库
    用途：把家长标签转成可验证事实问题，把后台判断转成家长容易回答的自然追问。
    适用：准备追问、家长说孩子懒/不自觉/玻璃心/沉迷手机/没内驱力时。
    不适用：直接判断最终原因。

    Args:
        query: 搜索查询，建议格式：家长标签+后台想确认的方向+如何转成家长好回答的问题
               示例："事实转换 追问方式：家长标签=懒，后台想确认=能力断层或启动困难，如何问成家长好回答的问题"

    Returns:
        检索到的B库内容（已清洗为纯文本）。
    """
    return _search_lib("B", query, top_k=3)


@tool
def search_blacklist_library(query: str) -> str:
    """
    E库｜黑名单与反证边界库
    用途：检查是否出现安全废话、绝对化判断、心理诊断、顺着家长标签、指责家长、模板化输出等问题。
    适用：诊断卡前、建议回复前、判断较尖锐时、涉及心理/人格/家长责任时。
    不适用：每轮普通回复都强制调用。

    Args:
        query: 搜索查询，建议格式：输出类型+风险点
               示例："黑名单 自检：输出类型=profileUpdateCandidates，风险=把家长说孩子懒直接写成孩子画像"

    Returns:
        检索到的E库内容（已清洗为纯文本）。
    """
    return _search_lib("E", query, top_k=3)


@tool
def search_expression_library(query: str) -> str:
    """
    C库｜前台表达与诊断卡库
    用途：校准自然语言表达、诊断卡字段写法、普通轮次表达方式、清华师兄师姐式语气。
    适用：诊断卡、建议回复、需要把后台判断转成家长可读表达时。
    不适用：原因判断本身。

    Args:
        query: 搜索查询，建议格式：输出类型+场景+语气要求
               示例："前台表达 模板：输出类型=诊断卡，场景=孩子作业拖延与家长高投入焦虑，语气=自然直接不冒犯"

    Returns:
        检索到的C库内容（已清洗为纯文本）。
    """
    return _search_lib("C", query, top_k=3)


@tool
def search_case_library(query: str) -> str:
    """
    D库｜典型案例库
    用途：参考典型案例结构，如小尹型、任务暴露型、表面乖巧型、社交归属感弱型。
    适用：当前案例和某个典型案例高度相似，或需要阶段性复盘时。
    不适用：普通轮次默认调用；不能用案例覆盖当前孩子事实。

    Args:
        query: 搜索查询，建议格式：当前案例简短摘要+寻找是否类似某类典型案例
               示例："典型案例 对照：当前案例=高投入妈妈+孩子表面答应但不行动，寻找是否类似小尹型"

    Returns:
        检索到的D库内容（已清洗为纯文本）。
    """
    return _search_lib("D", query, top_k=3)
