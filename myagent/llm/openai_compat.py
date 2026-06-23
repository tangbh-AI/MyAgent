"""OpenAI 兼容接口 — 支持 DeepSeek、GLM、Qwen 等国产大模型"""

from typing import Dict, Generator, List, Optional

from openai import OpenAI

from myagent.llm.base import AbstractLLM


class OpenAICompatLLM(AbstractLLM):
    """OpenAI 兼容接口实现

    通过 OpenAI SDK 调用所有兼容 OpenAI API 格式的模型，
    包括 DeepSeek、智谱 GLM、通义千问 Qwen 等。
    """

    def __init__(self, model_name: str, config: Dict):
        """初始化 OpenAI 兼容客户端

        Args:
            model_name: 配置中的模型名称
            config: 模型配置字典
        """
        super().__init__(model_name, config)

        # 创建 OpenAI 客户端
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = OpenAI(**client_kwargs)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """非流式对话

        对于仿真脚本生成任务，默认使用较低 temperature 以保证生成质量。
        """
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        return response.choices[0].message.content or ""

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Generator[str, None, None]:
        """流式对话 — 逐步返回生成内容"""
        stream = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
