"""
品类匹配解析：规则加载、门店匹配、相似度回退。

原 parser 单文件拆分为：
- models: 数据模型（CategoryRule, RuleSheetMeta, VerifiedBrand）
- loaders: Excel 加载（load_rules, load_verified_brands）
- matching: 规则匹配与相似度（match_rule, match_store, text_similarity, match_by_similarity）
"""

from .embedding import ensure_model_loaded, fill_brand_embeddings
from .loaders import load_rules, load_verified_brands
from .matching import match_by_similarity, match_rule, match_store, text_similarity
from .models import CategoryRule, RuleSheetMeta, VerifiedBrand

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
