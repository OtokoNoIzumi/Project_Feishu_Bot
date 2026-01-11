"""
Config Loader.

Loads configuration from JSON files (e.g., config.json) in the project root
or other specified locations.
"""

import json
from pathlib import Path
from typing import Any, Dict

from .project_paths import get_project_root


def load_root_config() -> Dict[str, Any]:
    """
    加载项目根目录 `config.json`（不依赖工作目录）。

    注意：
    - 配置优先级应由调用方实现：环境变量 > config.json
    """
    root = get_project_root()
    config_path = root / "config.json"
    if not config_path.exists():
        return {}

    # Removed redundant try-except. If config.json exists but is bad, it should raise.
    return json.loads(config_path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    # Removed redundant try-except.
    return json.loads(path.read_text(encoding="utf-8"))
