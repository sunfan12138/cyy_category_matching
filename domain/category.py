"""品类匹配相关数据模型（Pydantic V2）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _strip_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _strip_list_str(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


class CategoryRule(BaseModel):
    """单条品类匹配规则。"""

    level1_category: str = Field(default="", description="一级原子品类")
    category_code: str | int = Field(default="", description="品类编码")
    atomic_category: str = Field(default="", description="原子品类")
    sequence_no: int = Field(default=0, description="序号")
    keyword_group_1: list[str] = Field(default_factory=list, description="关键词组1：需同时包含")
    keyword_group_2: list[str] = Field(default_factory=list, description="关键词组2：需同时包含")
    keyword_group_3: list[str] = Field(default_factory=list, description="关键词组3：需同时包含")
    keyword_group_4: list[str] = Field(default_factory=list, description="关键词组4：需同时包含")
    keyword_group_5: list[str] = Field(default_factory=list, description="关键词组5：任意包含其一")
    must_not_contain: list[str] = Field(default_factory=list, description="一定不包含（且）")

    @field_validator("level1_category", "atomic_category", mode="before")
    @classmethod
    def strip_str_fields(cls, v: Any) -> str:
        return _strip_str(v)

    @field_validator("keyword_group_1", "keyword_group_2", "keyword_group_3", "keyword_group_4", "keyword_group_5", "must_not_contain", mode="before")
    @classmethod
    def normalize_list_str(cls, v: Any) -> list[str]:
        return _strip_list_str(v) if v is not None else []

    model_config = {"frozen": False}


class RuleSheetMeta(BaseModel):
    """表头元数据：第1行判断逻辑、第2行字段解释。"""

    logic_descriptions: list[str] = Field(default_factory=list, description="第1行判断逻辑")
    field_descriptions: list[str] = Field(default_factory=list, description="第2行字段解释")

    @field_validator("logic_descriptions", "field_descriptions", mode="before")
    @classmethod
    def ensure_list_str(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v]
        return []

    model_config = {"frozen": False}


class VerifiedBrand(BaseModel):
    """已校验过的品牌及其对应原子品类（与「校验过的品牌对应原子品类.xlsx」列一致）。"""

    brand_code: str | int = Field(default="", description="品牌编码")
    brand_name: str = Field(default="", description="品牌名称")
    brand_keywords: str = Field(default="", description="品牌关键词（，表示同时包含）")
    atomic_category: str = Field(default="", description="原子品类")
    embedding: list[float] | None = Field(default=None, description="BGE 文本向量，加载后批量编码填充")

    @field_validator("brand_name", "brand_keywords", "atomic_category", mode="before")
    @classmethod
    def strip_str_fields(cls, v: Any) -> str:
        return _strip_str(v)

    model_config = {"frozen": False}
