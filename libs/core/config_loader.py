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
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


