"""
Anti-Repeat-Errors Skill - Configuration

Configuration management for the injection system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class InjectorConfig(BaseModel):
    """
    注入器配置

    支持多种禁用方式（按优先级）:
    1. 环境变量 ANTI_REPEAT_ERRORS_ENABLED=false
    2. 配置文件中 enabled=false
    3. 临时跳过 ANTI_REPEAT_ERRORS_SKIP_ONCE=true
    """

    # 核心开关
    enabled: bool = Field(default=True, description="Enable/disable the injection hook")

    # 规则配置
    rules_dir: Path = Field(
        default=Path("~/.openclaw/skills/anti-repeat-errors/rules"),
        description="Directory containing rule files",
    )

    # 日志配置
    log_level: Literal["debug", "info", "warn", "error"] = Field(
        default="info",
        description="Logging level for injection operations",
    )

    # 超时配置
    inject_timeout_ms: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Max time (ms) for rule injection",
    )

    # 缓存配置
    cache_enabled: bool = Field(
        default=True,
        description="Enable rule caching",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        description="Cache TTL in seconds",
    )

    # 热重载
    hot_reload: bool = Field(
        default=True,
        description="Enable hot reload of rules",
    )

    model_config = {"env_prefix": "ANTI_REPEAT_ERRORS_", "extra": "ignore"}

    @field_validator("rules_dir", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        """Expand ~ in path"""
        return Path(v).expanduser()

    def is_effectively_enabled(self) -> bool:
        """
        检查注入是否实际启用

        综合考虑:
        1. 环境变量 ANTI_REPEAT_ERRORS_ENABLED
        2. 配置中 enabled 字段
        3. 环境变量 ANTI_REPEAT_ERRORS_SKIP_ONCE（单次跳过）
        """
        # 检查单次跳过
        if os.environ.get("ANTI_REPEAT_ERRORS_SKIP_ONCE", "").lower() in ("true", "1", "yes"):
            # 清除单次跳过标记
            os.environ.pop("ANTI_REPEAT_ERRORS_SKIP_ONCE", None)
            return False

        # 检查环境变量覆盖
        env_enabled = os.environ.get("ANTI_REPEAT_ERRORS_ENABLED")
        if env_enabled is not None:
            return env_enabled.lower() in ("true", "1", "yes")

        # 使用配置中的值
        return self.enabled

    def get_skip_reason(self) -> Optional[str]:
        """获取跳过注入的原因（如果被禁用）"""
        if os.environ.get("ANTI_REPEAT_ERRORS_SKIP_ONCE"):
            return "Skipped once (ANTI_REPEAT_ERRORS_SKIP_ONCE=true)"

        env_enabled = os.environ.get("ANTI_REPEAT_ERRORS_ENABLED")
        if env_enabled is not None and env_enabled.lower() in ("false", "0", "no"):
            return "Disabled by environment variable (ANTI_REPEAT_ERRORS_ENABLED=false)"

        if not self.enabled:
            return "Disabled by config (enabled=false)"

        return None


class HookContext(BaseModel):
    """
    Hook 上下文信息

    从 OpenClaw hook 传递到注入器
    """

    session_key: Optional[str] = None
    phase: Optional[int] = None
    task_type: Optional[str] = None
    recent_tools: list[str] = Field(default_factory=list)
    recent_files: list[str] = Field(default_factory=list)
    message_content: Optional[str] = None

    # 扩展字段
    project_dir: Optional[str] = None
    workspace_dir: Optional[str] = None


def load_config_from_dict(config_dict: dict) -> InjectorConfig:
    """
    从字典加载配置

    处理类型转换和默认值
    """
    # 处理 rules_dir 的路径展开
    if "rulesDir" in config_dict:
        config_dict["rules_dir"] = config_dict.pop("rulesDir")
    if "logLevel" in config_dict:
        config_dict["log_level"] = config_dict.pop("logLevel")
    if "injectTimeout" in config_dict:
        config_dict["inject_timeout_ms"] = config_dict.pop("injectTimeout")

    return InjectorConfig(**config_dict)


def load_config_from_env() -> InjectorConfig:
    """
    从环境变量加载配置

    用于独立运行时
    """
    return InjectorConfig()


def get_default_config() -> InjectorConfig:
    """获取默认配置"""
    return InjectorConfig(
        rules_dir=Path("~/.openclaw/skills/anti-repeat-errors/rules").expanduser()
    )