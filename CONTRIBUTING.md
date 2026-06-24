# Contributing to GaiaAgent / 贡献指南

Thank you for your interest in contributing to the AURC Protocol!
感谢你关注 AURC 协议并考虑贡献！

## Code of Conduct / 行为准则

We are committed to providing a welcoming and inclusive environment.
我们致力于提供友好和包容的环境。

## How to Contribute / 如何贡献

### Reporting Bugs / 报告 Bug

1. Check existing issues first / 先检查已有 Issue
2. Use the bug report template / 使用 Bug 报告模板
3. Include: Python version, OS, reproduction steps / 包括：Python 版本、操作系统、复现步骤

### Suggesting Features / 建议功能

1. Open a discussion in GitHub Discussions / 在 GitHub Discussions 开讨论
2. Describe the use case and motivation / 描述使用场景和动机
3. Protocol changes require an AURC-RFC / 协议变更需要提交 AURC-RFC

### Submitting Code / 提交代码

1. Fork the repository / Fork 仓库
2. Create a feature branch / 创建功能分支
3. Write tests for your changes / 为你的修改编写测试
4. Ensure all tests pass: `uv run pytest` / 确保所有测试通过
5. Run linter: `uv run ruff check src/ tests/` / 运行代码检查
6. Submit a pull request / 提交 Pull Request

## Development Setup / 开发环境

```bash
git clone https://github.com/gaiaagent/gaiaagent
cd gaiaagent
pip install -e ".[dev]"
```

### Running Tests / 运行测试

```bash
# All tests / 全部测试
pytest

# Specific module / 特定模块
pytest tests/test_lifecycle.py

# With coverage / 带覆盖率
pytest --cov=src/gaiaagent --cov-report=term-missing
```

### Code Style / 代码风格

- **Formatter**: ruff (line-length=100) / ruff 格式化
- **Type checking**: mypy (strict mode) / mypy 严格模式
- **Docstrings**: Google style with bilingual comments / Google 风格，双语注释

```bash
# Format / 格式化
ruff format src/ tests/

# Lint / 检查
ruff check src/ tests/

# Type check / 类型检查
mypy src/
```

## Protocol Changes / 协议变更

Changes to the AURC protocol specification require an **AURC-RFC** (Request for Comments):

1. Create `docs/rfcs/AURC-RFC-NNN-title.md`
2. Include: motivation, specification, backward compatibility, migration plan
3. Open a PR for community review
4. Requires approval from at least 2 maintainers

对 AURC 协议规范的变更需要提交 **AURC-RFC**：

1. 创建 `docs/rfcs/AURC-RFC-NNN-title.md`
2. 包括：动机、规范、向后兼容性、迁移计划
3. 开启 PR 供社区审查
4. 需要至少 2 位维护者批准

## License / 许可证

By contributing, you agree that your contributions will be licensed under:
- **Code**: AGPL-3.0
- **Documentation**: CC BY-SA 4.0

贡献即表示你同意你的贡献以以下许可证发布：
- **代码**: AGPL-3.0
- **文档**: CC BY-SA 4.0
