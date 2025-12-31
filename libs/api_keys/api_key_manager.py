import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from libs.core.project_paths import get_project_root


@dataclass
class APIKeyManager:
    """
    API Key 管理器（原子能力）

    能力：
    - 多 key 清单
    - 随机/顺序获取
    - 失败标记与自动切换
    - 从环境变量与根目录 .env 读取
    """

    key_env_vars: List[str] = field(default_factory=lambda: ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
    keys: List[str] = field(default_factory=list)
    failed_keys: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        loaded = []
        loaded.extend(self._load_from_env(self.key_env_vars))
        loaded.extend(self._load_from_dotenv(self.key_env_vars))
        loaded.extend([k.strip() for k in self.keys if k and k.strip()])
        # 去重（保持顺序）
        self.keys = list(dict.fromkeys([k for k in loaded if k]))

    def _load_from_env(self, env_vars: List[str]) -> List[str]:
        out: List[str] = []
        for name in env_vars:
            v = os.getenv(name)
            if v and v.strip():
                out.append(v.strip())
        return out

    def _load_from_dotenv(self, env_vars: List[str]) -> List[str]:
        """
        从项目根目录 `.env` 读取（不依赖工作目录）

        说明：
        - 只解析 KEY=VALUE 的简单格式
        - 只提取 env_vars 列表中指定的变量
        """
        root = get_project_root()
        env_path = root / ".env"
        if not env_path.exists():
            return []

        content = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        values: List[str] = []
        want = set(env_vars)
        for line in content:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            if k not in want:
                continue
            v = v.strip().strip('"').strip("'")
            if v:
                values.append(v)
        return values

    def get_key(self, random_select: bool = True) -> Optional[str]:
        available = [k for k in self.keys if k not in self.failed_keys]
        if not available:
            self.failed_keys.clear()
            available = list(self.keys)
        if not available:
            return None
        return random.choice(available) if random_select else available[0]

    def mark_failed(self, key: str) -> None:
        if key in self.keys:
            self.failed_keys.add(key)

    def add_key(self, key: str) -> None:
        k = (key or "").strip()
        if not k:
            return
        if k not in self.keys:
            self.keys.append(k)

    def available_count(self) -> int:
        return len([k for k in self.keys if k not in self.failed_keys])


