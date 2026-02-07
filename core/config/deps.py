"""
依赖注入：基于 typing.Annotated 与 Depends 标记，由 inject() 解析并返回配置等依赖。

用法：
    from core.config import inject, AppConfig

    app_cfg = inject(AppConfig)
"""

from __future__ import annotations

from typing import Annotated, Callable, get_args, get_origin


class Depends:
    """依赖标记：在 Annotated[T, Depends(getter)] 中保存解析函数 getter，由 inject() 调用。"""

    __slots__ = ("getter",)

    def __init__(self, getter: Callable[[], object]) -> None:
        self.getter = getter


def inject(typed: type) -> object:
    """
    解析 Annotated[T, Depends(getter)]，调用 getter() 并返回 T。
    若 typed 不是 Annotated 或没有 Depends 元数据，则抛出 TypeError。
    """
    origin = get_origin(typed)
    if origin is not Annotated:
        raise TypeError(f"期望 Annotated 类型，得到: {typed}")
    args = get_args(typed)
    if not args:
        raise TypeError(f"Annotated 缺少参数: {typed}")
    for meta in args[1:]:
        if isinstance(meta, Depends):
            return meta.getter()
    raise TypeError(f"未找到 Depends 元数据: {typed}")
