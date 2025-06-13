
from datetime import datetime
from typing import List, Dict, Optional, Any
import pandas as pd
from dataclasses import dataclass, field
from langchain_chroma import Chroma
from langchain_core.documents import Document
from pathlib import Path
import os
import json

if "__file__" in globals():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    current_dir = os.path.join(current_dir, "..", "..", "..")
else:
    # 在 Jupyter Notebook 环境中
    current_dir = os.getcwd()
    current_dir = os.path.join(current_dir, "..")

current_dir = os.path.normpath(current_dir)

if __package__:
    # 作为包导入时使用相对导入
    from .base_module import BaseModule, BaseProcessor, BaseEntry, ModuleConfig, ProcessResult
else:
    # 直接运行时使用绝对导入
    from Module.Components.chat_module.base_module import BaseModule, BaseProcessor, BaseEntry, ModuleConfig, ProcessResult



class NoteEntry(BaseEntry):
    """笔记条目，不同子领域共享一套属性
    属性说明：
    - id: 唯一标识符，由NoteManager生成
    - content: 笔记内容
    - category: 所属类别 - 明确类别时，对应子领域的名称
    - tags: 标签列表 - 不明确类别时，用于快速标记和筛选笔记的关键特征，要结合已有tags分析，以及定期聚类分析，单条不超过5个
    - is_private: 是否私有 - private的在外人RAG的时候不会被搜索到
    - is_outdated: 是否过时 - 过时的内容在RAG的时候不会被搜索到
    - source_type: 来源类型(text/audio/image)
    - review_schedule: 复习计划
    - version_history: 历史版本
    - created_at: 创建时间
    - updated_at: 最后更新时间
    - related_persons: 相关人员 - 后续版本规划，人员这个可行性待定
    - attachments: 附件列表 - 后续版本规划
    - relations: 关联关系 - 后续版本规划
    """
    def __init__(self, content: str, metadata: dict = None):
        super().__init__()
        self.content: str = content
        if metadata:
            for key, value in metadata.items():
                setattr(self, key, value)
        else:
            # 分类属性
            self.category: str = ""
            self.tags: List[str] = []
            self.source_type: str = "text"
            # 关联属性
            self.related_persons: List[str] = []
            self.attachments: List[Dict] = []
            # 版本和关系
            self.version_history: List[Dict] = []
            self.relations: Dict[str, List[str]] = {}
            self.review_schedule: Optional[Dict] = None

    def to_document(self) -> Document:
        """转换为Document格式（用于向量存储）"""
        return Document(
            page_content=self.content,
            metadata={
                "category": self.category,
                "tags": ','.join(self.tags),
                "is_private": bool(self.is_private),
                "is_outdated": bool(self.is_outdated),
                "source_type": self.source_type,
                "related_persons": ','.join(self.related_persons),  # 转换为字符串
            }
        )

    def update_content(self, new_content: str):
        """更新内容，保存历史版本，可能也用不上"""
        self.version_history.append({
            "content": self.content,
            "updated_at": self.updated_at
        })
        self.content = new_content
        self.update()

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        base_dict = vars(self)
        return base_dict

@dataclass
class StorageConfig:
    """存储配置"""
    name: str
    root_dir: Path
    data_dir: Optional[Path] = None
    config_path: Optional[Path] = None
    df_path: Optional[Path] = None
    vector_path: Optional[Path] = None

    def __post_init__(self):
        """初始化后设置路径"""
        # 设置子领域的数据目录
        self.data_dir = self.root_dir / "Data" / self.name
        # 配置文件路径
        self.config_path = self.data_dir / "config.json"
        # DataFrame存储路径
        self.df_path = self.data_dir / "notes.csv"
        # 向量存储路径
        self.vector_path = self.data_dir / "vectorstore"

    def ensure_directories(self):
        """确保所需目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vector_path.mkdir(parents=True, exist_ok=True)


@dataclass
class NoteConfig:
    """统一的笔记配置"""
    name: str
    description: str = ""
    long_term_field: str = ""
    is_active: bool = True
    default_private: bool = False
    is_temp_container: bool = False
    field_descriptions: Dict[str, str] = field(default_factory=lambda: {
        "category": "笔记分类，表示内容所属的主题领域",
        "tags": "标签列表（不超过5个），用于快速标记和筛选笔记的关键特征",
        "is_private": "是否私密，标记是否包含敏感或个人信息",
        "is_outdated": "是否过时，标记内容是否需要更新或已不再适用",
        "related_persons": "相关人员列表，记录与内容相关的人名",
        "source_type": "来源类型，可以是'text'（文本）, 'audio'（语音）, 'image'（图片）"
    })


class NoteManager:
    """笔记管理器
    管理数据流: CSV/Excel -> DataFrame -> NoteEntry -> Document -> Vectorstore
    """
    # 提供给LLM的字段说明
    def __init__(self, name: str, root_dir: Optional[str] = None, config: Optional[NoteConfig] = None):
        # 确定根目录
        self.storage = StorageConfig(
            name=name,
            root_dir=Path(root_dir or self._get_default_root()).resolve()
        )
        self.storage.ensure_directories()

        self.config = config or self._load_or_create_config(name)
        self._save_config()  # 保存配置（如果是新创建的）
        self.df = pd.DataFrame()  # 内存中的数据框
        self.vectorstore = None
        # 初始化或加载配置
        # self._init_config()

    def _get_default_root(self) -> Path:
        """获取默认的根目录"""
        if "__file__" in globals():
            return Path(os.path.dirname(os.path.abspath(__file__))) / ".." / ".." / ".."
        else:
            return Path(os.getcwd()) / ".."

    def _save_config(self):
        """保存配置到文件"""
        config_dict = {
            "name": self.config.name,
            "description": self.config.description,
            "long_term_field": self.config.long_term_field,
            "is_active": self.config.is_active,
            "default_private": self.config.default_private,
            "is_temp_container": self.config.is_temp_container,
            "field_descriptions": self.config.field_descriptions
        }
        with open(self.storage.config_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

    def _load_or_create_config(self, name: str) -> NoteConfig:
        """加载或创建配置"""
        if self.storage.config_path.exists():
            # 从文件加载配置
            with open(self.storage.config_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
                return NoteConfig(**config_dict)
        else:
            # 创建新配置
            return NoteConfig(
                name=name,
                description=f"{name} notes",
                long_term_field="general"
            )

    def load_data(self):
        """加载或创建DataFrame"""
        if self.storage.df_path.exists():
            self.df = pd.read_csv(self.storage.df_path)
        else:
            # 创建新的DataFrame，包含所需的列
            self.df = pd.DataFrame(columns=[
                'id', 'content', 'created_at', 'updated_at',
                'category', 'tags', 'is_private', 'is_outdated',
                'related_persons', 'source_type', 'is_vectorized'
            ])
            self.save_data()

    def save_data(self):
        """保存DataFrame到文件"""
        self.df.to_csv(self.storage.df_path, index=False)

    def init_vectorstore(self, embeddings):
        """初始化向量存储"""
        self.vectorstore = Chroma(
            persist_directory=str(self.storage.vector_path),
            embedding_function=embeddings
        )

    def create_note_entry(self, row: pd.Series) -> NoteEntry:
        """从DataFrame行创建NoteEntry"""
        note = NoteEntry(content=row['content'])
        # 从DataFrame复制属性到NoteEntry
        for field in ['category', 'tags', 'is_private', 'is_outdated',
                     'related_persons', 'source_type']:
            if field in row and pd.notna(row[field]):
                # 处理列表类型的字段
                if field in ['tags', 'related_persons']:
                    value = eval(row[field]) if isinstance(row[field], str) else row[field]
                else:
                    value = row[field]
                setattr(note, field, value)
        return note

    def get_fields_prompt(self, content: str) -> str:
        """生成用于LLM分析的字段说明提示词"""
        field_descriptions = self.config.field_descriptions
        prompt = f"""请分析以下内容，并按照要求提供相关字段信息。

内容：{content}

需要提供的字段信息：
"""
        for field, desc in field_descriptions.items():
            prompt += f"- {field}: {desc}\n"

        prompt += """
请以JSON格式返回结果，例如：
{
    "category": "...",
    "tags": ["...", "..."],
    "is_private": false,
    "is_outdated": false,
    "related_persons": ["...", "..."],
    "source_type": "text"
}"""
        return prompt

    def analyze_content(self, content: str, llm_client) -> Dict:
        """使用LLM分析内容并返回元数据"""
        prompt = self.get_fields_prompt(content)
        # return prompt
        response = llm_client.quick_chat(prompt)

        try:
            # 假设response是JSON字符串
            test_split = response.split("json")
            use_pos = min(len(test_split) - 1, 1)
            finaltext = response.split("json")[use_pos].strip().replace("```", "")
            metadata = json.loads(finaltext, strict=False)
            # metadata = json.loads(response)
            return metadata
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM返回的结果无法解析为JSON: {str(e)}，返回结果：{response}")

    def process_new_note(self, content: str, llm_client) -> Dict:
        """处理新的笔记内容

        Args:
            content: 笔记内容
            llm_client: LLM客户端

        Returns:
            Dict: 处理结果，包含笔记ID和处理状态
        """
        # try:
            # 1. 使用LLM分析内容
        metadata = self.analyze_content(content, llm_client)

        # 2. 创建笔记条目
        note = NoteEntry(content=content, metadata=metadata)

        # 3. 添加到DataFrame
        note_dict = note.to_dict()
        note_dict['is_vectorized'] = False
        self.df.loc[len(self.df)] = note_dict

        # 4. 转换为Document并存入向量库
        if self.vectorstore:
            doc = note.to_document()
            self.vectorstore.add_documents([doc])
            # 更新向量化状态
            self.df.loc[self.df['id'] == note.id, 'is_vectorized'] = True

        # 5. 保存更新
        self.save_data()

        return {
            "success": True,
            "note_id": note.id,
            "message": "笔记处理成功",
            "metadata": metadata
        }

        # except Exception as e:
        #     return {
        #         "success": False,
        #         "message": f"处理失败: {str(e)}",
        #         "error": str(e)
        #     }
