# 贡献 GaiaAgent 指南

> 🌐 [English](CONTRIBUTING.md)
> **感谢你关注 GaiaAgent 并考虑贡献！**

无论你是修 bug、提功能、写协议桥接，还是改进文档——你的贡献都会让 AI Agent 生态更紧密、更强大。

---

## 目录

- [行为准则](#行为准则)
- [我可以如何贡献？](#我可以如何贡献)
- [开发环境准备](#开发环境准备)
- [开发流程](#开发流程)
- [代码规范](#代码规范)
- [测试](#测试)
- [提交 Pull Request](#提交-pull-request)
- [协议变更（AURC-RFC）](#协议变更aurc-rfc)
- [架构决策](#架构决策)
- [社区](#社区)

---

## 行为准则

我们致力于为每一个人提供友好、包容的环境，无论经验水平、性别认同、性取向、残障状况、外貌、体型、种族、民族、年龄、宗教或国籍。

**保持尊重。保持建设性。保持友善。**

---

## 我可以如何贡献？

### 🐛 报告 Bug

发现 bug？请[提交 bug 报告](https://github.com/gaiaagent/gaiaagent/issues/new?template=bug_report.md)，并包含：

- **Python 版本**（`python --version`）
- **操作系统**（Linux/macOS/Windows + 版本）
- **最小复现**（代码片段或仓库链接）
- **期望行为与实际行为**
- **完整错误 traceback**（如适用）

### 💡 建议功能

有想法？请[提交功能请求](https://github.com/gaiaagent/gaiaagent/issues/new?template=feature_request.md)，并包含：

- **用例** —— 解决什么问题？
- **提议的 API** —— 从开发者视角看会是什么样子？
- **考虑过的替代方案** —— 你还想过哪些？

### 🔌 编写协议桥接

最有价值的贡献方式之一，是为新协议编写桥接。详见[桥接开发者指南](docs/zh/architecture/bridge-guide.md)，内含逐步说明。

现有桥接：MCP、A2A、ACP。我们欢迎针对以下协议的桥接：gRPC、GraphQL、NATS、Kafka、AMQP，或任何你在用的协议。

### 📝 改进文档

文档是一等公民。错别字、含糊的说明、缺失的示例——都可以改。文档 PR 通常在 24 小时内合并。

### 🧪 编写测试

每个模块都应有测试。如果你发现未覆盖的代码路径，补充测试就是一份很好的贡献。

---

## 开发环境准备

```bash
# 1. 在 GitHub 上 Fork 仓库，然后克隆你的 fork
git clone https://github.com/YOUR-USERNAME/gaiaagent
cd gaiaagent

# 2. 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. 安装全部开发依赖
pip install -e ".[all]"

# 4. 验证一切正常
pytest
mypy src/
ruff check src/ tests/
```

---

## 开发流程

```
1. 挑选一个 issue（或新建一个）
2. 在 issue 下评论，告知他人你正在处理
3. 从 main 创建功能分支
4. 编写代码 + 测试
5. 运行完整测试套件
6. 提交 Pull Request
```

### 分支命名

```
feature/short-description     # 新功能
fix/issue-number-description  # bug 修复
bridge/protocol-name          # 新协议桥接
docs/what-youre-documenting   # 文档
refactor/what-youre-refactoring  # 重构
```

### 提交信息

我们遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat(bridges): add gRPC bridge implementation
fix(lifecycle): prevent invalid PAUSED→COMPLETED transition
docs(workflows): add nested pattern examples
test(security): add delegation chain edge cases
refactor(bus): extract routing logic into strategy pattern
```

---

## 代码规范

| 规范 | 工具 | 配置 |
|:---|:---|:---|
| **格式化** | `ruff format` | 行宽：100 |
| **Lint** | `ruff check` | 规则：E, F, I, N, W, UP |
| **类型检查** | `mypy` | 启用严格模式 |
| **Docstring** | Google 风格 | 鼓励双语（EN/ZH） |
| **异步** | `async/await` | 所有 I/O 必须异步 |
| **模型** | Pydantic v2 | 用于所有数据结构 |

### 常用命令

```bash
# 格式化代码
ruff format src/ tests/

# 检查问题
ruff check src/ tests/

# 类型检查
mypy src/

# 一次性运行全部检查
make all
```

---

## 测试

### 运行测试

```bash
# 全部测试
pytest

# 指定模块
pytest tests/test_lifecycle.py

# 详细输出
pytest -v --tb=short

# 带覆盖率
pytest --cov=src/gaiaagent --cov-report=term-missing

# 只跑快速测试（跳过集成测试）
pytest -m "not integration"
```

### 编写测试

- **每个新函数都需要测试** —— 无例外
- **同时测试正常路径与错误路径**
- **异步测试用 `pytest-asyncio`**（在 `pyproject.toml` 中配置）
- **使用描述性测试名**：`test_delegation_chain_rejects_scope_escalation` 而非 `test_delegation`

```python
import pytest

@pytest.mark.asyncio
async def test_bridge_translates_mcp_to_aurc():
    bridge = MCPBridge()
    mcp_msg = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "search"}}

    aurc_msg = await bridge.translate_to_aurc(mcp_msg)

    assert aurc_msg.type == MessageDirection.REQUEST
    assert aurc_msg.body.skill == "search"
```

---

## 提交 Pull Request

### 提交前

- [ ] 全部测试通过（`pytest`）
- [ ] 无 lint 错误（`ruff check src/ tests/`）
- [ ] 无类型错误（`mypy src/`）
- [ ] 新代码有测试
- [ ] 新公开 API 有 docstring
- [ ] 已更新 `CHANGELOG.md`（如适用）

### PR 描述模板

```markdown
## What does this PR do?

Brief description of the change.

## Motivation

Why is this change needed? Link to issue if applicable.

## Changes

- Change 1
- Change 2

## Testing

- How did you test this?
- What tests did you add?

## Checklist

- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes (or documented in CHANGELOG)
```

### 评审流程

1. **自动检查**运行（CI、lint、类型检查）
2. **至少 1 位维护者**评审并批准
3. **回应反馈** —— 向同一分支推送新提交
4. **压缩并合并** —— 维护者会在合并时压缩你的提交

---

<a id="protocol-changes"></a>

## 协议变更（AURC-RFC）

对 AURC 协议规范的修改需要走正式的 **RFC（Request for Comments）流程**：

### 何时提交 RFC

- 新增消息类型
- 修改消息格式 schema
- 新增生命周期状态或状态转换
- 修改安全模型
- 新增桥接接口要求

### RFC 流程

```
1. Create: docs/rfcs/AURC-RFC-NNN-short-title.md
2. Include: motivation, specification, backward compatibility, migration plan
3. Open PR: labeled "rfc" for community review
4. Discussion: 2-week public comment period
5. Revision: address feedback
6. Approval: requires 2+ maintainer approvals
7. Implementation: reference implementation in GaiaAgent
8. Standardization: after 2+ independent implementations, becomes part of spec
```

### RFC 模板

```markdown
# AURC-RFC-NNN: Title

## Status: Draft | Discussion | Accepted | Rejected

## Motivation
What problem does this solve?

## Specification
Detailed technical specification.

## Backward Compatibility
How does this affect existing implementations?

## Migration Plan
How do existing users upgrade?

## Security Considerations
Any security implications?

## Unresolved Questions
Open questions for discussion.
```

---

## 架构决策

在做重大架构变更时，请考虑这些核心原则：

| 原则 | 含义 |
|:---|:---|
| **Bridge First（桥接优先）** | 不要发明新的通信原语；统一现有协议 |
| **Runtime is King（运行时为王）** | Agent = 模型 + 宿主；宿主是一等公民 |
| **Progressive Complexity（渐进复杂度）** | 简单内核，企业特性作为可选模块 |
| **Protocol-Agnostic Identity（协议无关身份）** | 一个 Agent，一个跨所有协议的身份 |
| **Security by Default（默认安全）** | 权限可在协议层强制执行，而非仅声明式 |

---

## 社区

- **GitHub Issues** —— bug 报告、功能请求
- **GitHub Discussions** —— 问题、想法、社区交流
- **Discord** —— 与其他贡献者实时交流
- **RFC 流程** —— 正式的协议演进

### 成为维护者

对代码库与协议有深入理解、且持续活跃的贡献者，可能被邀请成为维护者。维护者可以：

- 合并 PR
- 分拣 issue
- 参与架构决策
- 评审 RFC

---

## 许可证

向 GaiaAgent 贡献，即表示你同意你的贡献按以下协议授权：

- **代码**：[Apache-2.0](LICENSE)
- **文档**：[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **协议规范**：[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

---

<p align="center">
  <strong>准备好贡献了吗？</strong>
  <a href="https://github.com/gaiaagent/gaiaagent/issues">浏览开放 issue →</a>
</p>
