"""
Anti-Repeat-Errors Skill - Phase Tracker

Tracks current project phase from STATE.md and other sources.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class PhaseInfo(BaseModel):
    """阶段信息"""

    current: Optional[int] = None
    total: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None  # in_progress, completed, failed, blocked

    def is_valid(self) -> bool:
        """检查是否有有效阶段信息"""
        return self.current is not None


@dataclass
class ProjectContext:
    """项目上下文"""

    project_dir: Optional[Path] = None
    phase_info: Optional[PhaseInfo] = None
    task_type: Optional[str] = None
    recent_files: list[str] = None
    recent_tools: list[str] = None

    def __post_init__(self):
        if self.recent_files is None:
            self.recent_files = []
        if self.recent_tools is None:
            self.recent_tools = []


class PhaseTracker:
    """
    追踪当前项目阶段

    从多种来源读取阶段信息:
    1. PROJECT 文件
    2. STATE.md 文件
    3. .planning/ 目录结构
    """

    # 状态文件的可能位置
    STATE_FILE_PATTERNS = [
        ".planning/STATE.md",
        ".planning/state.md",
        "STATE.md",
        "state.md",
    ]

    # 阶段正则表达式
    PHASE_PATTERNS = [
        # "Phase: 1 of 3 (Phase Name)"
        re.compile(r"Phase:\s*(\d+)\s*of\s*(\d+)\s*\(([^)]+)\)", re.IGNORECASE),
        # "Phase: 1 of 3"
        re.compile(r"Phase:\s*(\d+)\s*of\s*(\d+)", re.IGNORECASE),
        # "Current Phase: 1"
        re.compile(r"Current\s+Phase:\s*(\d+)", re.IGNORECASE),
        # "phase: 1"
        re.compile(r"^phase:\s*(\d+)", re.IGNORECASE | re.MULTILINE),
    ]

    # 状态正则
    STATUS_PATTERN = re.compile(r"Status:\s*(in_progress|completed|failed|blocked)", re.IGNORECASE)

    def __init__(self, project_dir: Optional[Path | str] = None):
        """
        初始化 Phase Tracker

        Args:
            project_dir: 项目目录，如果为 None 则尝试自动检测
        """
        self.project_dir = Path(project_dir) if project_dir else None
        self._logger = logging.getLogger("anti-repeat-errors.phase_tracker")
        self._cache: dict[str, PhaseInfo] = {}

    def set_project_dir(self, project_dir: Path | str) -> None:
        """设置项目目录"""
        self.project_dir = Path(project_dir)
        self._cache.clear()

    def get_current_phase(self, project_dir: Optional[Path | str] = None) -> Optional[PhaseInfo]:
        """
        获取当前阶段信息

        Args:
            project_dir: 可选的项目目录覆盖

        Returns:
            PhaseInfo 对象，如果无法确定则返回 None
        """
        dir_path = Path(project_dir) if project_dir else self.project_dir

        if not dir_path:
            self._logger.debug("No project directory specified")
            return None

        # 检查缓存
        cache_key = str(dir_path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 尝试各种状态文件
        for pattern in self.STATE_FILE_PATTERNS:
            state_file = dir_path / pattern
            if state_file.exists():
                phase_info = self._parse_state_file(state_file)
                if phase_info and phase_info.is_valid():
                    self._cache[cache_key] = phase_info
                    return phase_info

        # 尝试从目录结构推断
        phase_info = self._infer_from_directory_structure(dir_path)
        if phase_info:
            self._cache[cache_key] = phase_info
            return phase_info

        self._logger.debug(f"No phase info found in {dir_path}")
        return None

    def _parse_state_file(self, state_file: Path) -> Optional[PhaseInfo]:
        """解析状态文件"""
        try:
            content = state_file.read_text(encoding="utf-8")
            return self._parse_state_content(content)
        except Exception as e:
            self._logger.warning(f"Failed to read state file {state_file}: {e}")
            return None

    def _parse_state_content(self, content: str) -> Optional[PhaseInfo]:
        """解析状态文件内容"""
        phase_info = PhaseInfo()

        # 解析阶段
        for pattern in self.PHASE_PATTERNS:
            match = pattern.search(content)
            if match:
                groups = match.groups()
                phase_info.current = int(groups[0])

                if len(groups) >= 2 and groups[1]:
                    try:
                        phase_info.total = int(groups[1])
                    except ValueError:
                        pass

                if len(groups) >= 3 and groups[2]:
                    phase_info.name = groups[2].strip()

                break

        # 解析状态
        status_match = self.STATUS_PATTERN.search(content)
        if status_match:
            phase_info.status = status_match.group(1).lower()

        return phase_info if phase_info.is_valid() else None

    def _infer_from_directory_structure(self, project_dir: Path) -> Optional[PhaseInfo]:
        """从目录结构推断阶段"""
        planning_dir = project_dir / ".planning" / "phases"
        if not planning_dir.exists():
            return None

        # 查找所有 phase 目录
        phase_dirs = sorted(
            [d for d in planning_dir.iterdir() if d.is_dir() and d.name.startswith("0")],
            key=lambda x: x.name,
        )

        if not phase_dirs:
            return None

        # 查找最新的活动阶段
        # 假设目录名格式为 "01-phase-name", "02-another-phase"
        latest_phase = None
        for i, phase_dir in enumerate(phase_dirs, 1):
            # 检查是否有完成的标记
            # 通常最后一个没有完成标记的就是当前阶段
            state_file = phase_dir / "STATE.md"
            if state_file.exists():
                try:
                    content = state_file.read_text(encoding="utf-8")
                    if "completed" in content.lower():
                        continue
                except Exception:
                    pass

            latest_phase = PhaseInfo(current=i, total=len(phase_dirs))
            # 尝试从目录名提取阶段名称
            parts = phase_dir.name.split("-", 1)
            if len(parts) > 1:
                latest_phase.name = parts[1].replace("-", " ").title()

        return latest_phase

    def get_project_context(
        self,
        project_dir: Optional[Path | str] = None,
        recent_files: Optional[list[str]] = None,
        recent_tools: Optional[list[str]] = None,
    ) -> ProjectContext:
        """
        获取完整项目上下文

        Args:
            project_dir: 项目目录
            recent_files: 最近操作的文件列表
            recent_tools: 最近使用的工具列表

        Returns:
            ProjectContext 对象
        """
        dir_path = Path(project_dir) if project_dir else self.project_dir
        phase_info = self.get_current_phase(dir_path)

        return ProjectContext(
            project_dir=dir_path,
            phase_info=phase_info,
            recent_files=recent_files or [],
            recent_tools=recent_tools or [],
        )

    def clear_cache(self) -> None:
        """清除缓存"""
        self._cache.clear()


def infer_task_type(
    message: Optional[str] = None,
    recent_tools: Optional[list[str]] = None,
    recent_files: Optional[list[str]] = None,
) -> Optional[str]:
    """
    推断任务类型

    基于消息内容、工具和文件推断任务类型
    """
    tools = recent_tools or []
    files = recent_files or []
    msg = (message or "").lower()

    # 基于 tools 推断
    if "exec" in tools or "shell" in tools:
        if "write" in tools or "edit" in tools:
            return "coding"
        return "shell"

    if "write" in tools or "edit" in tools:
        return "coding"

    if "read" in tools and not tools:
        return "review"

    # 基于消息关键词推断
    coding_keywords = ["implement", "fix", "refactor", "create", "update", "write code", "debug"]
    for kw in coding_keywords:
        if kw in msg:
            return "coding"

    review_keywords = ["review", "analyze", "check", "explain", "read"]
    for kw in review_keywords:
        if kw in msg:
            return "review"

    # 基于文件类型推断
    if files:
        code_extensions = [".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c"]
        for f in files:
            if any(f.endswith(ext) for ext in code_extensions):
                return "coding"

    return None


def create_phase_tracker(project_dir: Optional[str] = None) -> PhaseTracker:
    """创建 PhaseTracker 的便捷函数"""
    return PhaseTracker(project_dir)