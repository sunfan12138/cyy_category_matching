"""
匹配核心：数据模型、规则加载、规则/相似度匹配、向量嵌入、大模型回退。
"""

from domain.category import CategoryRule, RuleSheetMeta, VerifiedBrand
from .loaders import load_rules, load_verified_brands
from application.services.matching_service import match_by_similarity, match_rule, match_store, text_similarity
from infrastructure.embedding.embedding import ensure_model_loaded, fill_brand_embeddings

__all__ = [
    "CategoryRule",
    "RuleSheetMeta",
    "VerifiedBrand",
    "ensure_model_loaded",
    "fill_brand_embeddings",
    "load_rules",
    "load_verified_brands",
    "match_rule",
    "match_store",
    "text_similarity",
    "match_by_similarity",
]
