"""提示词与参考关键词：品类描述任务的基础提示与参考关键词抽取。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import CategoryRule

# 基础提示：角色与任务 + 明确需求（工具说明单独放最后）
PROMPT_BASE = """# 角色

你是品类描述助手。

## 任务

用户会给出一段「门店/商品品类」文本（可能是品牌名、业态名或一句话），你需要输出一段**可参与关键词匹配**的品类描述，供后续规则库匹配使用。

## 输出格式（重要）

- 直接输出可被规则命中的**品类词**，多个词用顿号、逗号连接成一句即可；**不要**写「XX是一家…」「XX是…品牌」等介绍句式。
- **描述尽量多写，宁可多写不要少写**：词越多越有利于与规则库关键词命中。**至少输出 15～20 个相关词**，能写更多更好。尽量覆盖：品类本名、同义词、近义词、上下游业态、相关品类、常见叫法、细分类型。
- **示例（多词）**：茶百道 → 奶茶、果茶、新式茶饮、现制饮品、奶盖茶、茶饮、饮品、手摇茶、鲜果茶、芝士茶、珍珠奶茶、茶饮店、现制茶饮；蜜雪冰城 → 奶茶、冰淇淋、茶饮、现制饮品、冰品、冷饮、冰淇淋、甜筒、冰沙、奶昔、现制冰品。目的就是让规则库里的关键词能命中你输出的这些词。
- 只输出一句，不要多句、不要分点、不要换行；不要解释原因、不要加序号或标题。
- **禁止**输出「无明确品类」「无法判断」「不属于…」等否定式描述；若无法直接判断品类且当前有搜索等工具，必须先调用工具查清后再按上述格式输出。
"""

# 有参考关键词时插入：可优先选用的词汇（占位 {reference_keywords}）
PROMPT_WITH_KEYWORDS = """
## 参考词汇

可优先选用：{reference_keywords}
"""

# 工具调用说明：放在提示词最后，有工具时由调用方拼在末尾
PROMPT_TOOLS = """
## 工具使用

当前会话提供「搜索」等工具，用于查询品牌、业态、陌生词汇等信息。

### 必须直接输出、不调用工具

以下情况直接输出品类词，**无需调用工具**：

1. **广为人知的品牌或业态**：如茶百道、蜜雪冰城、沙县小吃、肯德基。
2. **从名字可直接推断出品类**：如「XX奶茶」「XX面馆」「XX咖啡」「麻辣烫」「黄焖鸡」等。

根据常识或名字推断，只输出可匹配的品类词，不要调用搜索，不要写「XX是一家…」等长句。

### 必须先调用工具再输出

以下情况**必须先调用搜索**再写描述：

- 名字中无明确品类指向
- 缩写、生僻词
- 无意义/乱序文本

**不得**在未调用工具的情况下输出「无明确品类」「无法判断」等否定式回答。

**调用方式**：发起一次工具调用，把用户原文或需查的内容作为查询参数传入；收到返回后，从返回内容中提炼品类词，**尽可能多写**，**至少 15～20 个相关词**（同义、近义、上下游、相关业态、常见叫法均可），按「多个词用顿号/逗号连接」的格式输出，尽量使用上文给出的参考词汇，宁可多写不要少写，以提高规则匹配成功率。若搜索仍无结果，直接返回「未匹配到结果」。
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