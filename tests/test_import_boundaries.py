import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_package_dependency_boundaries() -> None:
    roots = {
        "agent": Path("packages/core/src/package/agent"),
        "api": Path("packages/api/src/package/api"),
        "runner": Path("packages/runner/src/package/runner"),
    }
    violations: list[str] = []

    rules = {
        "agent": ("package.api", "package.runner"),
        "api": ("package.runner",),
        "runner": ("package.api",),
    }

    for package_name, forbidden in rules.items():
        for path in roots[package_name].rglob("*.py"):
            for imported in _imports(path):
                if imported.startswith(forbidden):
                    violations.append(f"{path}: {imported}")

    assert violations == []
