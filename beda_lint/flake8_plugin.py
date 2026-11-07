"""flake8 plugins running the same checks, for editors and pipelines built on flake8."""

import ast
from abc import ABC, abstractmethod
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from beda_lint.call_tree_order import check_call_tree_order
from beda_lint.cli import Finding
from beda_lint.function_verb_names import NamingConfig, check_function_names, fetch_config

Error = tuple[int, int, str, type]


class _Plugin(ABC):
    def __init__(self, tree: ast.Module, filename: str) -> None:
        self.tree = tree
        self.path = Path(filename)

    def run(self) -> Iterator[Error]:
        for finding in self.check():
            yield finding.line, 0, f"{finding.code} {finding.message}", type(self)

    @abstractmethod
    def check(self) -> list[Finding]: ...


class CallTreeOrder(_Plugin):
    def check(self) -> list[Finding]:
        return check_call_tree_order(self.tree, self.path)


class FunctionVerbNames(_Plugin):
    def check(self) -> list[Finding]:
        return check_function_names(self.tree, self.path, _fetch_naming_config())


@cache
def _fetch_naming_config() -> NamingConfig:
    return fetch_config()
