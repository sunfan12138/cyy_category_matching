"""
CLI 入口：委托给 interface.cli.main，保证 python main.py 与 category-matching 控制台脚本可用。
"""

from interface.cli import main

if __name__ == "__main__":
    main()
