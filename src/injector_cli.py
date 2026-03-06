#!/usr/bin/env python3
"""
Anti-Repeat-Errors Skill - Injector CLI

CLI entry point for the injector, called from TypeScript hook.

Usage:
    python injector_cli.py --context '{"phase": 1, "task_type": "coding"}' [--config '{}']
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 添加 src 目录到 path
src_dir = Path(__file__).parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir.parent))

from config import InjectorConfig
from injector import RuleInjector, InjectionResult


def setup_logging(level: str = "info") -> None:
    """设置日志"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # 日志输出到 stderr，结果输出到 stdout
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Anti-Repeat-Errors Injector CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # 基本使用
    python injector_cli.py --context '{"phase": 1}'

    # 带配置
    python injector_cli.py --context '{"phase": 1}' --config '{"log_level": "debug"}'

    # 从文件读取上下文
    python injector_cli.py --context-file context.json

    # 检查模式（仅输出匹配的规则 ID）
    python injector_cli.py --context '{"phase": 1}' --check-only
        """,
    )

    parser.add_argument(
        "--context",
        type=str,
        required=False,
        help="JSON context string",
    )

    parser.add_argument(
        "--context-file",
        type=str,
        help="Path to JSON file containing context",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="{}",
        help="JSON config string (default: {})",
    )

    parser.add_argument(
        "--config-file",
        type=str,
        help="Path to JSON file containing config",
    )

    parser.add_argument(
        "--rules-dir",
        type=str,
        help="Override rules directory",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["debug", "info", "warn", "error"],
        default="info",
        help="Log level (default: info)",
    )

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check for matching rules, output rule IDs",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration and exit",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Force reload rules cache",
    )

    return parser.parse_args()


def load_context(args: argparse.Namespace) -> dict[str, Any]:
    """加载上下文"""
    if args.context_file:
        with open(args.context_file, "r", encoding="utf-8") as f:
            return json.load(f)

    if args.context:
        return json.loads(args.context)

    # 默认空上下文
    return {}


def load_config(args: argparse.Namespace) -> dict[str, Any]:
    """加载配置"""
    config = {}

    if args.config_file:
        with open(args.config_file, "r", encoding="utf-8") as f:
            config.update(json.load(f))

    if args.config:
        config.update(json.loads(args.config))

    # 命令行覆盖
    if args.rules_dir:
        config["rules_dir"] = args.rules_dir

    return config


def main() -> int:
    """主入口"""
    args = parse_args()

    # 设置日志
    setup_logging(args.log_level)
    logger = logging.getLogger("anti-repeat-errors.cli")

    try:
        # 加载配置
        config_dict = load_config(args)

        # 处理 rules_dir 路径展开
        if "rules_dir" in config_dict:
            config_dict["rules_dir"] = str(Path(config_dict["rules_dir"]).expanduser())
        elif "rulesDir" in config_dict:
            config_dict["rules_dir"] = str(Path(config_dict["rulesDir"]).expanduser())

        config = InjectorConfig(**config_dict)

        # 验证模式
        if args.validate:
            logger.info(f"Configuration valid: {config.model_dump()}")
            return 0

        # 创建注入器
        injector = RuleInjector(config)

        # 重载模式
        if args.reload:
            count = injector.reload_rules()
            logger.info(f"Reloaded {count} rules")
            return 0

        # 加载上下文
        context = load_context(args)

        # 仅检查模式
        if args.check_only:
            matched = injector.loader.get_matching_rules(context)
            result = {
                "matched": len(matched),
                "rule_ids": [r.id for r in matched],
            }
            print(json.dumps(result))
            return 0

        # 执行注入
        result = injector.build_injection_content(context)

        # 输出 JSON 结果到 stdout
        print(json.dumps(result.to_dict()))

        # 返回状态码
        return 0 if result.injected or not result.errors else 1

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return 2
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.log_level == "debug":
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())