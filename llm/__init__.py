"""LLM 独立封装：根据品类文本生成品类描述，支持 MCP 工具（搜索等）。"""

from .client import (
    get_category_description_with_search,
    get_category_description_with_search_async,
)

__all__ = [
    "get_category_description_with_search",
    "get_category_description_with_search_async",
]