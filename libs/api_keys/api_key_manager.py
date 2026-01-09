import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from libs.core.project_paths import get_project_root

logger = logging.getLogger(__name__)


@dataclass
class APIKeyManager:
    """
    API Key 管理器（原子能力）

    能力：
    - 多 key 清单维护
    - 随机/顺序获取策略
    - 自动故障标记与自动重置
    - 支持从环境变量、.env 文件及运行时动态添加
    """

    key_env_vars: List[str] = field(default_factory=lambda: ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
    keys: List[str] = field(default_factory=list)
    failed_keys: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        loaded = []
        # 1. 优先从环境变量读取
        loaded.extend(self._load_from_env(self.key_env_vars))
        # 2. 补充从 .env 文件读取 (根目录)
        loaded.extend(self._load_from_dotenv(self.key_env_vars))
        # 3. 合并初始化传入的 keys
        if self.keys:
            loaded.extend([k.strip() for k in self.keys if k and k.strip()])

        # 去重并保持顺序
        self.keys = list(dict.fromkeys([k for k in loaded if k]))
        logger.info(f"APIKeyManager initialized with {len(self.keys)} keys.")

    def _load_from_env(self, env_vars: List[str]) -> List[str]:
        out: List[str] = []
        for name in env_vars:
            v = os.getenv(name)
            if v and v.strip():
                out.append(v.strip())
        return out

    def _load_from_dotenv(self, env_vars: List[str]) -> List[str]:
        """
        从项目根目录 `.env` 读取（不依赖第三方 python-dotenv）
        """
        root = get_project_root()
        env_path = root / ".env"
        if not env_path.exists():
            return []

        try:
            content = env_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Failed to read .env file: {e}")
            return []

        values: List[str] = []
        want = set(env_vars)
        
        # 使用正则匹配 KEY=VALUE，处理引号和注释
        # 匹配行首 key=value，允许 value 带引号，忽略行尾注释
        pattern = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:["\'](.*?)["\']|([^#\r\n]*))')
        
        for line in content.splitlines():
            match = pattern.match(line)
            if match:
                key = match.group(1)
                if key in want:
                    # group(2) 是带引号的内容，group(3) 是无引号的内容
                    val = match.group(2) if match.group(2) is not None else match.group(3)
                    if val and val.strip():
                        values.append(val.strip())
        return values

    def get_key(self, random_select: bool = True) -> Optional[str]:
        """
        获取一个可用的 Key
        
        策略：
        1. 排除 failed_keys
        2. 如果所有 Key 都标记为失败，则重置 failed_keys（进入下一轮尝试）
        """
        available = [k for k in self.keys if k not in self.failed_keys]
        
        if not available:
            if not self.keys:
                logger.error("No API keys configured.")
                return None
                
            logger.warning("All API keys marked as failed. Resetting failure status for new cycle.")
            self.failed_keys.clear()
            available = list(self.keys)

        if not available:
            return None

        return random.choice(available) if random_select else available[0]

    def mark_failed(self, key: str) -> None:
        """标记 Key 为不可用"""
        if key in self.keys and key not in self.failed_keys:
            logger.warning(f"Marking API Key as failed: ...{key[-4:] if len(key)>4 else key}")
            self.failed_keys.add(key)

    def add_key(self, key: str) -> None:
        k = (key or "").strip()
        if not k:
            return
        if k not in self.keys:
            self.keys.append(k)
            logger.info(f"Added new API Key: ...{k[-4:]}")

    def available_count(self) -> int:
        return len(self.keys) - len(self.failed_keys)

    def reset_failures(self) -> None:
        """手动重置所有失败标记"""
        self.failed_keys.clear()
        logger.info("Manually reset all failed API keys.")


# 全局单例实例
_global_api_key_manager: Optional[APIKeyManager] = None


def get_default_api_key_manager() -> APIKeyManager:
    """获取全局唯一的 APIKeyManager 实例"""
    global _global_api_key_manager
    if _global_api_key_manager is None:
        _global_api_key_manager = APIKeyManager()
    return _global_api_key_manager


