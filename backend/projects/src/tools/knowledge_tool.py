"""
对话实验室知识库检索工具
"""
import re
from langchain.tools import tool
from coze_coding_dev_sdk import KnowledgeClient, Config
from coze_coding_utils.runtime_ctx.context import new_context
from coze_coding_utils.log.write_log import request_context

TABLE_NAME = "coze_doc_knowledge"

# 内部术语映射：把内部标题转换为前台可用的概念
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

# 需要直接移除的标题
_REMOVE_TITLES = ["后台想判断", "不要问", "改问", "家长标签", "不直接采信", "转成分支问题"]


def _clean_table_row(line: str) -> str:
    """把Markdown表格行转换为纯文本描述"""
    line = line.strip()
    if not line.startswith("|") or not line.endswith("|"):
        return line

    cells = [c.strip() for c in line[1:-1].split("|")]
    cells = [c for c in cells if c and c != "---" and not set(c).issubset({"-", ":", " "})]

    if not cells:
        return ""

    # 检测是否是标题行（包含内部术语）
    first_cell = cells[0]
    for title in _REMOVE_TITLES:
        if title in first_cell:
            # 这是内部标题行，直接移除
            return ""

    # 检测是否是"常见说法 → 需要了解 → 具体问题"格式
    if len(cells) >= 3 and any(t in first_cell for t in ["懒", "没内驱力", "不自觉", "玻璃心", "沉迷手机", "没羞耻心"]):
        return f"家长常说孩子{cells[0]}，其实可能需要了解：{cells[2]}"

    # 检测是否是"判断方向 → 避免这样问 → 建议这样问"格式
    if len(cells) >= 3:
        return f"关于{cells[0]}：不要问「{cells[1]}」，建议问「{cells[2]}」"

    # 普通表格行，用逗号连接
    return "；".join(cells)


def _clean_chunk(text: str) -> str:
    """清洗知识库原始内容，去掉内部术语、Markdown表格、章节标题、判断短句"""
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # 跳过空行和纯表格分隔线
        if not stripped:
            continue
        if set(stripped).issubset({"|", "-", ":", " "}):
            continue

        # 去掉行首的Markdown标题标记 (# ## ###)
        stripped = re.sub(r'^#{1,6}\s*', '', stripped)

        # 过滤章节标题：中文数字+顿号/点号+标题，如"十三、禁止过度指责家长"
        if re.match(r'^[一二三四五六七八九十百千零〇]+[、.．]\s*', stripped):
            continue
        # 过滤数字章节标题：如"1. " "1、" "(1)" "①"
        if re.match(r'^(\d+[.．、]|\(\d+\)|[①②③④⑤⑥⑦⑧⑨⑩])\s*', stripped):
            continue
        # 过滤罗马数字章节标题
        if re.match(r'^[IVXLCivxlc]+[.．、]\s*', stripped):
            continue

        # 过滤内部检查语句：包含"是否"+"问/检查/核实/确认/判断"的判断性语句
        if re.search(r'是否[^，。\n]*?(问|检查|核实|确认|判断)', stripped):
            continue
        # 过滤以"是否"开头的整行
        if stripped.startswith('是否'):
            continue

        # 过滤判断性短句（知识库总结性内部判断）
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
        # 过滤黑名单文件中的项目符号项（以私有区bullet或其他符号开头的废弃表达）
        if re.match(r'^[\uf0b7\u2022\u258b\u25cf\u25cb\u25a0\u25aa\u25ab\u2023\u2043\u2219]', stripped):
            continue
        # 过滤黑名单典型模式：看到X就说Y / 孩子这样是您逼出来的
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

        # 如果行包含大量管道符，可能是损坏的表格，尝试清理
        if stripped.count("|") >= 2:
            cleaned = _clean_table_row(stripped)
            if cleaned:
                cleaned_lines.append(cleaned)
            continue

        cleaned_lines.append(stripped)

    # 二次清理：移除残留的管道符和多余空行
    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


@tool
def search_knowledge_base(query: str) -> str:
    """
    搜索对话实验室知识库，获取相关判断素材、案例、话术或反证边界。

    使用场景：
    - 需要查找某个原因分支的详细判断标准和追问方向时
    - 需要把深层判断问题转换成家长好答的日常问题时
    - 需要前台表达模板或诊断卡模板时
    - 需要查看典型案例如何拆解时
    - 输出前想检查是否触犯了黑名单或反证边界时

    Args:
        query: 搜索查询，用自然语言描述你想查的内容。
               示例："能力断层的判断标准和追问问题"
               示例："家长说孩子很乖时该怎么问"
               示例："诊断卡模板"
               示例："不要输出安全废话"
               示例："小尹型案例"

    Returns:
        检索到的知识库文本片段（已清洗为纯文本，不含表格和内部术语）。
    """
    ctx = request_context.get() or new_context(method="search_knowledge_base")
    config = Config()
    client = KnowledgeClient(config=config, ctx=ctx)

    response = client.search(
        query=query,
        top_k=5,
        min_score=0.3,
    )

    if response.code != 0:
        return f"知识库搜索失败: {response.msg}"

    if not response.chunks:
        return "未在知识库中找到相关内容。"

    results = []
    for i, chunk in enumerate(response.chunks, 1):
        cleaned = _clean_chunk(chunk.content)
        if cleaned.strip():
            results.append(cleaned)

    return "\n\n".join(results)
