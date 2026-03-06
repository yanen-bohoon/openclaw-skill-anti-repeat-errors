#!/usr/bin/env python3
"""
Guardrail CLI Entry Point

Called from TypeScript before_tool_call hook.
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running as script directly
try:
    from .guardrail_hook import GuardrailHook, ToolCallContext, GuardrailResult
except ImportError:
    from guardrail_hook import GuardrailHook, ToolCallContext, GuardrailResult


def main():
    parser = argparse.ArgumentParser(description="Guardrail CLI")
    parser.add_argument(
        "--tool-name",
        required=True,
        help="Tool name being called",
    )
    parser.add_argument(
        "--tool-params",
        required=True,
        help="JSON-encoded tool parameters",
    )
    parser.add_argument(
        "--context",
        default="{}",
        help="JSON-encoded context (session_key, phase, etc.)",
    )
    parser.add_argument(
        "--rules-dir",
        default=None,
        help="Custom rules directory",
    )
    
    args = parser.parse_args()
    
    # Parse inputs
    try:
        tool_params = json.loads(args.tool_params)
    except json.JSONDecodeError as e:
        result = GuardrailResult(
            allowed=True,  # 解析失败不阻断
            modified=False,
            tool_name=args.tool_name,
            original_params={},
            result_params={},
            message=f"Failed to parse tool_params: {e}",
        )
        print(json.dumps(result.to_dict()))
        sys.exit(0)
    
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError:
        context = {}
    
    # Build ToolCallContext
    tool_call_context = ToolCallContext(
        tool_name=args.tool_name,
        tool_params=tool_params,
        session_key=context.get("session_key"),
        phase=context.get("phase"),
        task_type=context.get("task_type"),
        message_content=context.get("message_content"),
    )
    
    # Create and run guardrail hook
    rules_dir = Path(args.rules_dir) if args.rules_dir else None
    hook = GuardrailHook(rules_dir=rules_dir)
    
    result = hook.process_tool_call(tool_call_context)
    
    # Output result as JSON
    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()