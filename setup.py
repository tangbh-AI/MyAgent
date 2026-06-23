"""MyAgent — Abaqus 自然语言智能助手"""

from setuptools import setup, find_packages

setup(
    name="myagent",
    version="0.1.0",
    description="Abaqus 自然语言智能助手 — 用中文描述仿真需求，自动执行有限元分析",
    author="MyAgent",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "openai>=1.0.0",
        "anthropic>=0.30.0",
        "click>=8.1.0",
        "pyyaml>=6.0",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
        "matplotlib>=3.7.0",
        "colorama>=0.4.6",
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
    ],
    entry_points={
        "console_scripts": [
            "myagent=myagent.main:cli",
            "myagent-web=myagent.web:cli",
        ],
    },
)
