"""LLM 抽象基类 — 定义统一的模型接口"""

from abc import ABC, abstractmethod
from typing import Dict, Generator, List, Optional


class AbstractLLM(ABC):
    """大语言模型抽象基类

    所有 LLM 实现（OpenAI 兼容、Anthropic 等）必须继承此类，
    实现 chat 和 stream_chat 方法，确保上层代码无需关心具体模型。
    """

    def __init__(self, model_name: str, config: Dict):
        """初始化 LLM

        Args:
            model_name: 配置中的模型名称（如 deepseek-v3）
            config: 模型配置字典，包含 api_key, base_url, model_id 等
        """
        self.model_name = model_name
        self.config = config
        self.model_id = config.get("model_id", "")
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "")

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """发送消息并获取回复（非流式）

        Args:
            messages: 消息列表，格式 [{"role": "system", "content": "..."},
                      {"role": "user", "content": "..."}]
            **kwargs: 额外参数（temperature, max_tokens 等）

        Returns:
            模型的文本回复
        """
        ...

    @abstractmethod
    def stream_chat(self, messages: List[Dict[str, str]], **kwargs) -> Generator[str, None, None]:
        """发送消息并获取流式回复

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Yields:
            文本片段
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.model_name}, model={self.model_id})"
