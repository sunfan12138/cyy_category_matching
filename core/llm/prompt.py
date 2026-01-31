"""提示词与参考关键词：品类描述任务的基础提示与参考关键词抽取。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import CategoryRule

# 基础提示：角色与任务 + 明确需求（工具说明单独放最后）
PROMPT_BASE = """你是品类描述助手。

任务：用户会给出一段「门店/商品品类」文本（可能是品牌名、业态名或一句话），你需要输出一句中文描述，概括其品类含义，供后续关键词规则匹配使用。

输出要求：
1. 只输出一句描述，不要多句、不要分点、不要换行。
2. 不要解释原因、不要加序号或标题。
3. 描述中尽量包含多个相关品类词（同义、近义或上下游业态均可），便于匹配命中。
4. 描述要准确概括该品类/业态的核心含义，便于与规则库中的关键词匹配。
5. 禁止输出「无明确品类」「无法判断」「不属于…」等否定式描述；若无法直接判断品类，且当前有搜索等工具，必须先调用工具查清后再写一句描述。
"""

# 有参考关键词时插入：可优先选用的词汇（占位 {reference_keywords}）
PROMPT_WITH_KEYWORDS = """
可优先选用的参考词汇：{reference_keywords}
"""

# 工具调用说明：放在提示词最后，有工具时由调用方拼在末尾
PROMPT_TOOLS = """
你可用的工具：当前会话提供「搜索」等工具，用于查询品牌、业态、陌生词汇等信息。

必须直接输出、不调用工具：仅当你已能确定品类时（如广为人知的品牌：茶百道、蜜雪冰城、沙县小吃等），直接根据常识输出一句描述，无需调用工具。

必须先调用工具再输出：只要对品类不确定，就必须先调用搜索再写描述，包括：输入像品牌/门店名但不知主营、缩写或生僻词、从名字难以判断业态、输入像是无意义词组/乱序字/看不懂的文本。不得在未调用工具的情况下输出「无明确品类」「无法判断」「不属于…」等否定式回答。调用方式：发起一次工具调用，把用户给的原文或你认为需要查的内容作为查询参数传入；收到工具返回后，根据返回内容写一句描述并直接输出，尽量使用上文给出的参考词汇。若搜索仍无结果，直接返回"未匹配到结果"六个字。
"""

# 只取少量关键词示例（个数与总字数都限制）
MAX_KEYWORD_EXAMPLES = 10
MAX_KEYWORD_HINT_CHARS = 120

def build_keyword_hint(rules: list[CategoryRule]) -> str:
    """从规则中抽取少量关键词示例，用于提示词。"""
    seen: set[str] = set()
    words: list[str] = []
    for r in rules:
        if r.atomic_category and r.atomic_category.strip() and r.atomic_category.strip() not in seen:
            seen.add(r.atomic_category.strip())
            words.append(r.atomic_category.strip())
        for g in (r.keyword_group_1, r.keyword_group_2, r.keyword_group_3, r.keyword_group_4, r.keyword_group_5):
            for kw in g:
                if kw and kw.strip() and kw.strip() not in seen:
                    seen.add(kw.strip())
                    words.append(kw.strip())
                if len(words) >= MAX_KEYWORD_EXAMPLES:
                    break
            if len(words) >= MAX_KEYWORD_EXAMPLES:
                break
        if len(words) >= MAX_KEYWORD_EXAMPLES:
            break
    if not words:
        return ""
    s = "、".join(words[:MAX_KEYWORD_EXAMPLES])
    if len(s) > MAX_KEYWORD_HINT_CHARS:
        s = s[:MAX_KEYWORD_HINT_CHARS].rsplit("、", 1)[0] if "、" in s[:MAX_KEYWORD_HINT_CHARS] else s[:MAX_KEYWORD_HINT_CHARS]
    return s
