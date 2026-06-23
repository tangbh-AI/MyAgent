"""Anthropic 原生接口 — 支持 Claude 系列模型"""

from typing import Dict, Generator, List, Optional

from anthropic import Anthropic

from myagent.llm.base import AbstractLLM


class AnthropicLLM(AbstractLLM):
    """Anthropic Claude 接口实现

    使用 Anthropic 原生 SDK，支持 Claude 系列模型。
    Messages API 格式与 OpenAI 略有不同：
    - system 参数独立传入
    - messages 中不允许 system role
    """

    def __init__(self, model_name: str, config: Dict):
        """初始化 Anthropic 客户端

        Args:
            model_name: 配置中的模型名称
            config: 模型配置字典（支持 base_url 用于第三方 Anthropic 兼容 API）
        """
        super().__init__(model_name, config)

        # 支持自定义 base_url（如 DeepSeek 的 Anthropic 兼容端点）
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = Anthropic(**client_kwargs)

    def _split_system_messages(
        self, messages: List[Dict[str, str]]
    ) -> tuple:
        """将 OpenAI 格式的消息分离为 system prompt 和对话消息

        Anthropic API 要求 system 独立传入，messages 中不能有 system role。

        Args:
            messages: OpenAI 格式的消息列表

        Returns:
            (system_text, user_messages) 元组
        """
        system_parts = []
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                user_messages.append(msg)

        system_text = "\n\n".join(system_parts) if system_parts else ""
        return system_text, user_messages

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """非流式对话"""
        system_text, user_messages = self._split_system_messages(messages)

        create_kwargs = {
            "model": self.model_id,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        if system_text:
            create_kwargs["system"] = system_text

        response = self.client.messages.create(**create_kwargs)

        # Anthropic 返回的 content 可能是列表
        if isinstance(response.content, list):
            return "".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )
        return str(response.content)

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Generator[str, None, None]:
        """流式对话"""
        system_text, user_messages = self._split_system_messages(messages)

        create_kwargs = {
            "model": self.model_id,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        if system_text:
            create_kwargs["system"] = system_text

        with self.client.messages.stream(**create_kwargs) as stream:
            for text in stream.text_stream:
                yield text
