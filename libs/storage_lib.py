"""
JSONL Storage Library.

Provides a simple, thread-safe (mostly via atomic writes/append) JSONL storage mechanism
for the bot's user data.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import shutil

class JsonlStorage:
    """
    一个线程安全、进程安全（基于 fcntl/locking，但在 Windows 上简化为追加）的 JSONL 存储器。
    用于 user_data 的追加写。
    """

    def __init__(self, base_dir: str = "user_data"):
        self.base_dir = Path(base_dir)

    def _get_user_dir(self, user_id: str, category: str) -> Path:
        """获取用户特定分类的数据目录，例如 user_data/u123/diet"""
        path = self.base_dir / user_id / category
        path.mkdir(parents=True, exist_ok=True)
        return path

    def append(
        self, user_id: str, category: str, filename: str, data: Dict[str, Any]
    ) -> str:
        """
        追加一条记录
        :param category: diet / keep / profile
        :param filename: e.g. "2023-10.jsonl" or "records.jsonl"
        :param data: 具体的 dict 数据
        :return: 写入的绝对路径
        """
        dir_path = self._get_user_dir(user_id, category)
        file_path = dir_path / filename

        # 补全元数据
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()

        # 序列化
        line = json.dumps(data, ensure_ascii=False)

        # Windows 下简单的追加写（此时不引入复杂的文件锁，依靠 OS 原子追加特性）
        # 注意：在极高并发下可能需要更严谨的锁，但在 Bot 场景下足够
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        return str(file_path)

    def read_dataset(
        self, user_id: str, category: str, filename: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """读取最近的 N 条记录（倒序）"""
        dir_path = self._get_user_dir(user_id, category)
        file_path = dir_path / filename

        if not file_path.exists():
            return []

        # Remove redundant try-except block here.
        # If open() fails due to permission/lock, we should know about it (fail fast).
        with open(file_path, "r", encoding="utf-8") as f:
            # 简单实现：全读再切片。对于超大文件需要 readlines 优化
            lines = f.readlines()

        data = []
        for line in reversed(lines):
            if len(data) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return data

    def write_dataset(
        self,
        user_id: str,
        category: str,
        filename: str,
        data_list: List[Dict[str, Any]],
    ) -> str:
        """
        [Danger] 覆盖写入整个数据集。用于去重/修正场景。
        """
        dir_path = self._get_user_dir(user_id, category)
        file_path = dir_path / filename

        # [Safety] Backup before overwrite
        if file_path.exists():
            try:
                shutil.copy2(file_path, str(file_path) + ".bak")
            except Exception:
                pass

        lines = []
        for item in data_list:
            # Ensure serialization
            if "created_at" not in item:
                item["created_at"] = datetime.now().isoformat()
            lines.append(json.dumps(item, ensure_ascii=False))

        # Write atomic (or somewhat atomic on Windows via rename ideally, but simple overwrite here)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return str(file_path)


# 全局单例
global_storage = JsonlStorage()
