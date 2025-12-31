from pathlib import Path


def get_project_root() -> Path:
    """
    获取项目根目录（不依赖工作目录）。

    规则：
    - 以当前文件所在位置向上回溯
    - 找到同时包含 `config.json` 与 `Module/` 的目录作为根目录
    - 找不到则退化为 libs 的上一级
    """
    here = Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / "config.json").exists() and (parent / "Module").exists():
            return parent
    # 退化：.../libs/core/project_paths.py -> .../libs -> .../<root>
    return here.parents[2]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


