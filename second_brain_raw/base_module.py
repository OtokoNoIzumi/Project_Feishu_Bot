from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import uuid

@dataclass
class ModuleConfig:
    """模块配置类"""
    name: str
    description: str
    long_term_field: str
    is_active: bool = True
    default_private: bool = False
    max_retry: int = 3

@dataclass
class ProcessResult:
    """处理结果的标准返回格式"""
    success: bool
    data: Any
    message: str
    error: Optional[Exception] = None

class BaseEntry:
    """所有模块条目的基类"""
    def __init__(self):
        self.id: str = str(uuid.uuid4())
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()
        self.is_outdated: bool = False
        self.is_private: bool = False

    def update(self):
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict:
        """转换为字典格式（用于数据存储）"""
        result = {}
        for attr in vars(self):
            if attr != "metadata":
                result[attr] = getattr(self, attr)
        return result

class BaseProcessor(ABC):
    """所有处理器的基类"""
    def __init__(self, config: ModuleConfig):
        self.config = config
        self.llm_client = None  # 将在实际使用时注入
        self.vector_store = None  # 将在实际使用时注入

    @abstractmethod
    async def process(self, data: Any) -> ProcessResult:
        """处理输入数据的抽象方法"""
        pass

    @abstractmethod
    async def validate(self, data: Any) -> bool:
        """验证输入数据的抽象方法"""
        pass

class BaseModule(ABC):
    """模块基类"""
    def __init__(self, config: ModuleConfig):
        self.config = config
        self.processor = self._init_processor()

    def get_description(self, index:int=0):
        """获取模块的描述"""
        if self.config.is_active:
            return f"{index}. {self.config.description}"
        else:
            return ""

    @abstractmethod
    def _init_processor(self) -> BaseProcessor:
        """初始化处理器"""
        pass

    async def handle(self, data: Any) -> ProcessResult:
        """处理输入的统一接口"""
        try:
            if not await self.processor.validate(data):
                return ProcessResult(
                    success=False,
                    data=None,
                    message="Input validation failed"
                )

            result = await self.processor.process(data)
            return result

        except Exception as e:
            return ProcessResult(
                success=False,
                data=None,
                message=f"Error processing data: {str(e)}",
                error=e
            )
