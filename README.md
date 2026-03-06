# Anti-Repeat-Errors OpenClaw Skill

通过结构化规则文件，在 AI Agent 运行时注入约束，防止重复犯相同错误。

## 目录结构

```
anti-repeat-errors/
├── rules/                    # 规则文件目录
│   ├── schema.json           # JSON Schema 验证
│   ├── README.md             # 规则编写指南
│   ├── phases/               # 按阶段组织
│   │   ├── phase-1.yaml
│   │   ├── phase-2.yaml
│   │   └── phase-3.yaml
│   ├── task-types/           # 按任务类型组织
│   │   ├── coding.yaml
│   │   ├── research.yaml
│   │   └── planning.yaml
│   └── global/               # 全局规则
│       └── core.yaml
├── src/
│   ├── models.py             # Pydantic 数据模型
│   └── rule_loader.py        # 规则加载器
├── scripts/
│   └── validate_rules.py     # 规则验证脚本
├── tests/
│   └── test_rule_loader.py   # 单元测试
└── SKILL.md                  # 技能描述
```

## 使用方法

### 加载规则

```python
from src.rule_loader import RuleLoader

loader = RuleLoader(rules_dir="rules")
rules = loader.load_all()

# 按阶段筛选
phase_1_rules = loader.load_by_phase(1)

# 按任务类型筛选
coding_rules = loader.load_by_kind("task-type", "coding")

# 获取匹配当前上下文的规则
context = {"phase": 1, "task_type": "coding"}
matching = loader.get_matching_rules(context)
```

### 验证规则文件

```bash
python scripts/validate_rules.py --rules-dir rules --verbose
```