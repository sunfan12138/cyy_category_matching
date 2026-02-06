"""
Logfire trace 本地文件导出：不上传云端，将 Pydantic AI 的 trace/span 写入 log 目录下 JSONL。
参见 https://ai.pydantic.org.cn/logfire/
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

_instrumented = False
_lock = threading.Lock()


def _get_log_dir() -> Path | None:
    """获取日志目录；若尚未加载配置则返回 None。"""
    try:
        from core.config import get_log_dir
        return get_log_dir()
    except Exception:
        return None


def _unescape_unicode(s: str) -> str:
    """将字符串中的 \\uXXXX 转为实际 Unicode 字符，便于日志中中文可读。"""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


class _FileSpanExporter:
    """将 span 以 JSONL 形式写入 log 目录下的 logfire_traces_YYYYMMDD.jsonl。"""

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = Path(log_dir)
        self._lock = threading.Lock()

    def _file_path(self) -> Path:
        return self._log_dir / f"logfire_traces_{datetime.now().strftime('%Y%m%d')}.jsonl"

    def export(self, spans: Sequence[Any]) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult
        if not spans:
            return SpanExportResult.SUCCESS
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            path = self._file_path()
            with self._lock:
                with open(path, "a", encoding="utf-8") as f:
                    for span in spans:
                        rec = self._span_to_record(span)
                        if rec:
                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("Logfire 文件导出跳过: %s", e)
        return SpanExportResult.SUCCESS

    def _span_to_record(self, span: Any) -> dict[str, Any] | None:
        try:
            start = getattr(span, "start_time", None)
            end = getattr(span, "end_time", None)
            duration_ms = None
            if start is not None and end is not None:
                try:
                    ns = int(end) - int(start)
                    duration_ms = round(ns / 1e6, 2)
                except (TypeError, ValueError):
                    pass
            attrs = {}
            for k, v in (getattr(span, "attributes", None) or {}).items():
                try:
                    if isinstance(v, str):
                        v = _unescape_unicode(v)
                    elif not isinstance(v, (int, float, bool)):
                        v = _unescape_unicode(str(v))
                    attrs[str(k)] = v
                except Exception:
                    pass
            return {
                "name": getattr(span, "name", ""),
                "duration_ms": duration_ms,
                "attributes": attrs,
            }
        except Exception:
            return None

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def ensure_logfire_file_export() -> None:
    """
    启用 Pydantic AI 检测，不上传云端，将 trace 写入 log 目录下 logfire_traces_YYYYMMDD.jsonl。
    仅执行一次，重复调用无副作用。
    """
    global _instrumented
    with _lock:
        if _instrumented:
            return
        try:
            import logfire
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.trace import get_tracer_provider

            log_dir = _get_log_dir()
            logfire.configure(send_to_logfire=False)
            logfire.instrument_pydantic_ai()

            if log_dir is not None:
                try:
                    provider = get_tracer_provider()
                    if hasattr(provider, "add_span_processor"):
                        provider.add_span_processor(BatchSpanProcessor(_FileSpanExporter(log_dir)))
                except Exception as e:
                    logger.debug("Logfire 文件导出未启用: %s", e)
            _instrumented = True
            logger.debug("Logfire 已启用（仅本地，trace 写入 log 目录）")
        except Exception as e:
            logger.debug("Logfire 未启用: %s", e)
        finally:
            _instrumented = True
