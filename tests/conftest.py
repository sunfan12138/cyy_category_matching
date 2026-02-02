"""pytest 共享 fixture 与配置。"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证项目根在 sys.path 中，便于导入 core / app / llm
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
