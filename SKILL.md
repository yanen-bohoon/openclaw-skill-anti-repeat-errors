# Anti-Repeat-Errors

通过结构化规则文件，在 AI Agent 运行时注入约束，防止重复犯相同错误。

## 功能

- **规则文件**: 使用 YAML 格式定义规则，支持阶段/任务类型/全局三种维度
- **规则加载器**: Python 实现，支持缓存、热重载、错误容忍
- **条件匹配**: 根据 phase、task_type、文件路径、工具、关键词匹配规则
- **优先级排序**: 规则按优先级排序，高优先级规则优先应用

## 目录结构

```
anti-repeat-errors/
├── rules/                    # 规则文件
│   ├── schema.json           # JSON Schema
│   ├── README.md             # 规则编写指南
│   ├── phases/               # 阶段规则
│   ├── task-types/           # 任务类型规则
│   └── global/               # 全局规则
├── src/
│   ├── models.py             # Pydantic 数据模型
│   └── rule_loader.py        # 规则加载器
├── scripts/
│   └── validate_rules.py     # 验证脚本
└── tests/
    └── test_rule_loader.py   # 单元测试
```

## 使用方法

### 加载规则

```python
from src.rule_loader import RuleLoader

# 创建加载器
loader = RuleLoader(rules_dir="rules")

# 加载所有规则
loaded = loader.load_all()

# 按阶段筛选
phase1_rules = loader.load_by_phase(1)

# 获取匹配上下文的规则
context = {"phase": 1, "task_type": "coding"}
matching = loader.get_matching_rules(context)
for rule in matching:
    print(f"[{rule.priority}] {rule.name}: {rule.content}")
```

### 验证规则文件

```bash
python scripts/validate_rules.py --rules-dir rules --verbose
```

### 运行测试

```bash
pytest tests/test_rule_loader.py -v
```

## 规则格式

```yaml
version: "1.0"
kind: phase | task-type | global
name: rule-set-name
description: Optional description
enabled: true
rules:
  - id: unique-rule-id
    name: "Rule Name"
    condition:
      phase: 1                    # 可选：阶段
      task_type: coding           # 可选：任务类型
      files_matching:             # 可选：文件匹配 (glob)
        - "**/config.json"
      tools: [exec, write]        # 可选：工具名称
      keywords: [git, commit]     # 可选：关键词
    content: |
      规则内容，将被注入到上下文
    priority: 100                 # 0-100，高优先
    enabled: true
    tags: [tag1, tag2]
```

## Hook 集成 (待实现)

此 skill 将在后续 plan 中与 OpenClaw hook 系统集成：

- `on_session_start`: 加载规则到上下文
- `on_tool_call`: 检查规则约束
- `on_message`: 关键词触发规则提醒