"""
大模型调用：根据品类文本生成简短描述，用于二次关键词规则匹配。
带 MCP 工具（如搜索），模型可调用后再生成描述。
配置见 core/config（程序内统一从 core.config 获取）、core/llm/llm_config.py（llm_config.json 或环境变量）。
"""


def __getattr__(name: str):
    if name in ("get_category_description_with_search", "get_category_description_with_search_async"):
        from . import client
        return getattr(client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_category_description_with_search", "get_category_description_with_search_async"]
