"""
Pydantic V2 Schema：全局配置、类目节点、匹配结果及配置项解析。

- CategoryConfig: 全局配置、阈值与路径。
- CategoryNode: 类目树节点（ID、名称、层级关系）。
- MatchResult: 匹配输出（原始文本、预测类目、相似度得分）。
- LlmConfigSchema / McpConfigSchema: JSON 配置解析，供 core.config 使用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ----- 全局配置与路径 -----


class CategoryConfig(BaseModel):
    """全局配置：阈值与路径，用于管理匹配流程。"""

    similarity_threshold: float = Field(default=0.0, description="相似度匹配阈值")
    llm_fallback_threshold: float = Field(default=0.9, description="低于此相似度时触发大模型回退")
    rules_filename: str = Field(default="原子品类关键词.xlsx", description="规则 Excel 文件名")
    verified_filename: str = Field(default="校验过的品牌对应原子品类.xlsx", description="已校验品牌 Excel 文件名")

    model_config = {"frozen": False, "extra": "forbid"}


class RunConfigSchema(BaseModel):
    """运行时路径配置：Excel 目录、输出目录、日志目录。"""

    excel_dir: Path = Field(description="规则与已校验品牌 Excel 所在目录")
    output_dir: Path = Field(description="匹配结果输出目录")
    log_dir: Path = Field(description="日志文件目录")
    rules_filename: str = Field(default="原子品类关键词.xlsx", description="规则 Excel 文件名")
    verified_filename: str = Field(default="校验过的品牌对应原子品类.xlsx", description="已校验品牌 Excel 文件名")

    @property
    def rules_path(self) -> Path:
        return self.excel_dir / self.rules_filename

    @property
    def verified_path(self) -> Path:
        return self.excel_dir / self.verified_filename

    model_config = {"frozen": False}


# ----- 类目树节点 -----


class CategoryNode(BaseModel):
    """类目树节点：ID、名称、层级关系。"""

    id: str = Field(default="", description="类目 ID / 编码")
    name: str = Field(default="", description="类目名称")
    level: int = Field(default=1, ge=0, description="层级，1 为一级")
    parent_id: str = Field(default="", description="父节点 ID，空表示根")

    @field_validator("name", "id", "parent_id", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    model_config = {"frozen": False}


# ----- 匹配结果 -----


class MatchResult(BaseModel):
    """匹配输出：原始文本、预测类目、相似度得分及匹配方式。"""

    raw_text: str = Field(default="", description="原始输入文本")
    level1_category: str = Field(default="", description="一级原子品类")
    category_code: str = Field(default="", description="品类编码")
    atomic_category: str = Field(default="", description="原子品类")
    method: str = Field(default="", description="匹配方式：规则/相似度/搜索后匹配/未匹配等")
    similarity_detail: str = Field(default="", description="相似度匹配结果列内容")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="相似度得分，仅相似度匹配时有意义")
    llm_desc: str = Field(default="", description="大模型描述，可选")

    @field_validator("raw_text", "level1_category", "category_code", "atomic_category", "method", "similarity_detail", "llm_desc", mode="before")
    @classmethod
    def strip_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def to_result_row(self) -> tuple[str, str, str, str, str, str, str]:
        """转为 7 列 ResultRow 元组，与 app.io.ResultRow 一致。"""
        return (
            self.raw_text,
            self.level1_category,
            self.category_code,
            self.atomic_category,
            self.method,
            self.similarity_detail,
            self.llm_desc,
        )

    @classmethod
    def from_result_row(cls, row: tuple[str, str, str, str, str, str, str]) -> MatchResult:
        """从 7 列 ResultRow 元组构造。"""
        return cls(
            raw_text=row[0] or "",
            level1_category=row[1] or "",
            category_code=row[2] or "",
            atomic_category=row[3] or "",
            method=row[4] or "",
            similarity_detail=row[5] or "",
            llm_desc=row[6] or "",
        )

    model_config = {"frozen": False}


# ----- LLM 配置 JSON 解析 -----


class LlmConfigSchema(BaseModel):
    """app_config.yaml 中 llm 节结构；用于 model_validate 解析。"""

    api_key: str = Field(default="", description="明文 API Key")
    api_key_encrypted: str = Field(default="", description="加密后的 API Key")
    base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", description="API base URL")
    model: str = Field(default="qwen-plus", description="模型名")

    @field_validator("api_key", "api_key_encrypted", "base_url", "model", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("base_url", mode="after")
    @classmethod
    def rstrip_slash(cls, v: str) -> str:
        return v.rstrip("/") if v else v


# ----- MCP 配置 JSON 解析 -----


class McpServerSchema(BaseModel):
    """单个 MCP 服务器配置项。"""

    name: str = Field(description="服务器名称")
    transport: str = Field(default="stdio", description="stdio | streamable-http | sse")
    url: str = Field(default="", description="URL，用于 http/sse")
    command: str = Field(default="", description="命令行，用于 stdio")
    args: list[str] | None = Field(default=None, description="命令行参数")
    env: dict[str, str] | None = Field(default=None, description="环境变量")
    cwd: str | None = Field(default=None, description="工作目录")

    @field_validator("name", "transport", "url", "command", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("transport", mode="after")
    @classmethod
    def lower_transport(cls, v: str) -> str:
        return v.lower() if v else "stdio"


class McpConfigSchema(BaseModel):
    """app_config.yaml 中 mcp 节结构。"""

    servers: list[McpServerSchema] = Field(default_factory=list, description="MCP 服务器列表")


# ----- 运行时配置/结果（替代 tuple/dict） -----


class LlmConfigResult(BaseModel):
    """大模型配置加载结果：(api_key, base_url, model)。"""

    api_key: str | None = Field(default=None, description="API Key，未配置时为 None")
    base_url: str = Field(default="", description="API base URL")
    model: str = Field(default="", description="模型名")

    @classmethod
    def from_tuple(cls, t: tuple[str | None, str, str]) -> LlmConfigResult:
        return cls(api_key=t[0], base_url=t[1] or "", model=t[2] or "")

    def to_tuple(self) -> tuple[str | None, str, str]:
        return (self.api_key, self.base_url, self.model)


class ConfigDisplay(BaseModel):
    """用于界面/日志的配置展示：base_url、model、key 脱敏。"""

    base_url: str = Field(default="", description="API base URL")
    model: str = Field(default="", description="模型名")
    api_key_masked: str = Field(default="", description="脱敏后的 Key")
    configured: str = Field(default="否", description="是否已配置（是/否）")


class LlmCallParams(BaseModel):
    """LLM+MCP 调用参数：供 llm/client 使用，替代 7-tuple。"""

    api_key: str = Field(description="API Key")
    base_url: str = Field(description="API base URL")
    model: str = Field(description="模型名")
    mcp_config: list[Any] = Field(default_factory=list, description="MCP 服务器配置列表")
    prompt_base: str = Field(default="", description="系统提示词基础")
    prompt_tools: str = Field(default="", description="工具说明提示词")
    reference_keywords: str = Field(default="", description="参考关键词")

    model_config = {"arbitrary_types_allowed": True}


class SimilarityMatchResult(BaseModel):
    """相似度匹配结果：(rules, brand, score)。"""

    rules: list[Any] = Field(default_factory=list, description="匹配到的规则列表，运行时为 list[CategoryRule]")
    brand: Any = Field(default=None, description="命中的品牌，运行时为 VerifiedBrand | None")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="相似度得分")

    model_config = {"arbitrary_types_allowed": True}


class MatchStoreResult(BaseModel):
    """单条匹配结果：(matched_rules, from_similarity, ref_brand, score, llm_desc)。"""

    matched_rules: list[Any] = Field(default_factory=list, description="匹配到的规则，运行时为 list[CategoryRule]")
    from_similarity: bool = Field(default=False, description="是否由相似度匹配")
    ref_brand: Any = Field(default=None, description="命中的品牌，运行时为 VerifiedBrand | None")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="相似度得分")
    llm_desc: str | None = Field(default=None, description="大模型描述，可选")

    model_config = {"arbitrary_types_allowed": True}


# ----- 统一 YAML 配置 app_config.yaml -----


class MatchingSection(BaseModel):
    """匹配相关：相似度阈值、LLM 回退、并发数、未匹配标记、分块写入。"""

    similarity_threshold: float = Field(default=0.0, description="相似度匹配阈值")
    llm_fallback_threshold: float = Field(default=0.9, description="低于此相似度时触发大模型")
    batch_max_workers: int = Field(default=8, ge=1, description="批量匹配并发数")
    batch_save_chunk_size: int = Field(
        default=0,
        ge=0,
        description="每处理多少条就追加写入结果文件一次，0 表示不分块一次性写入；>0 可降低内存并保留部分结果",
    )
    llm_unmatched_marker: str = Field(default="未匹配到结果", description="未匹配时展示标记")
    llm_unmatched_aliases: list[str] = Field(
        default_factory=lambda: ["未匹配到结果", "未匹配到"],
        description="视为未匹配的文案列表",
    )


class AppSection(BaseModel):
    """应用层：规则/品牌文件名、输入文件名忽略。"""

    rules_filename: str = Field(default="原子品类关键词.xlsx", description="规则 Excel 文件名")
    verified_filename: str = Field(default="校验过的品牌对应原子品类.xlsx", description="已校验品牌 Excel 文件名")
    input_stem_ignore: str = Field(default="新建文本文档", description="视为未提供文件名的 stem")


class LoggingSection(BaseModel):
    """日志：按大小切割时的单文件上限与保留备份数。"""

    log_rotate_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        description="单日志文件超过该字节数时切割（默认 10MB）",
    )
    log_rotate_backup_count: int = Field(
        default=5,
        ge=0,
        description="切割后保留的历史文件个数，0 表示不限制",
    )


class EmbeddingSection(BaseModel):
    """向量模型：BGE 模型 ID、权重、批大小。"""

    bge_model_id: str = Field(default="BAAI/bge-small-zh-v1.5", description="BGE 模型 ID")
    bge_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="BGE 与 Jaro-Winkler 权重")
    fill_embedding_chunk: int = Field(default=16000, ge=1, description="单次编码最大条数")
    encode_batch_size: int = Field(default=512, ge=1, description="编码批大小")


class LlmClientSection(BaseModel):
    """LLM 客户端：max_tokens、日志摘要长度。"""

    max_tokens: int = Field(default=768, ge=1, description="单次调用最大 token")
    log_input_summary_len: int = Field(default=80, ge=1, description="日志输入摘要长度")
    log_result_summary_len: int = Field(default=120, ge=1, description="日志结果摘要长度")


class PromptSection(BaseModel):
    """提示词相关：参考关键词个数与字数。"""

    max_keyword_examples: int = Field(default=10, ge=1, description="参考关键词最多条数")
    max_keyword_hint_chars: int = Field(default=120, ge=1, description="参考关键词最多字数")


class AppConfigSchema(BaseModel):
    """统一配置文件 app_config.yaml 的完整结构；缺省节使用默认值。"""

    llm: LlmConfigSchema = Field(default_factory=LlmConfigSchema, description="大模型配置")
    mcp: McpConfigSchema = Field(default_factory=McpConfigSchema, description="MCP 服务器列表")
    matching: MatchingSection = Field(default_factory=MatchingSection, description="匹配参数")
    app: AppSection = Field(default_factory=AppSection, description="应用层参数")
    logging: LoggingSection = Field(default_factory=LoggingSection, description="日志切割参数")
    embedding: EmbeddingSection = Field(default_factory=EmbeddingSection, description="向量模型参数")
    llm_client: LlmClientSection = Field(default_factory=LlmClientSection, description="LLM 客户端参数")
    prompt: PromptSection = Field(default_factory=PromptSection, description="提示词参数")
