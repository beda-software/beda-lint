"""Check that function names start with a verb, and that bool functions read as predicates."""

import ast
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import partial
from importlib.resources import files
from pathlib import Path

from beda_lint.cli import Finding, run_check

NOT_A_VERB = "NAME001"
NOT_A_PREDICATE = "NAME002"
CONFIG_TABLE = "function-verb-names"
CONFIG_KEYS = frozenset(
    {"extra-verbs", "extra-predicate-prefixes", "ignore-decorators", "ignore-patterns"}
)
PREDICATE_PREFIXES = frozenset({"is", "are", "has", "have", "can", "should"})
EXEMPT_NAMES = frozenset({"main"})
DEFAULT_IGNORE_PATTERNS = ("*_op",)
EXEMPT_DECORATORS = frozenset(
    {
        "property",
        "cached_property",
        "functools.cached_property",
        "overload",
        "typing.overload",
        "fixture",
        "pytest.fixture",
    }
)
ACCESSOR_DECORATOR_ATTRIBUTES = frozenset({"setter", "getter", "deleter"})
AIOHTTP_APP_SIGNALS = frozenset(
    {"cleanup_ctx", "on_startup", "on_shutdown", "on_cleanup", "on_response_prepare"}
)
BOOL_GUARD_TYPES = frozenset({"TypeGuard", "TypeIs"})
BOOL_FUNCTIONS = frozenset(
    {"bool", "isinstance", "issubclass", "hasattr", "callable", "any", "all", "startswith",
     "endswith", "isdigit", "isalpha", "exists", "is_file", "is_dir"}
)  # fmt: skip
WORD_BOUNDARY = re.compile(r"_|(?=[A-Z])")

FunctionDef = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class NamingConfig:
    verbs: frozenset[str]
    predicate_prefixes: frozenset[str]
    ignore_decorators: frozenset[str]
    ignore_patterns: tuple[str, ...]


def main(argv: Sequence[str] | None = None) -> int:
    config = fetch_config(Path("pyproject.toml"))
    return run_check(partial(check_function_names, config=config), __doc__, argv)


def fetch_config(pyproject: Path) -> NamingConfig:
    """Built-in verbs and prefixes, extended by `[tool.beda-lint.function-verb-names]`."""
    table = _fetch_config_table(pyproject)
    return NamingConfig(
        verbs=fetch_default_verbs() | _get_words(table, "extra-verbs"),
        predicate_prefixes=PREDICATE_PREFIXES | _get_words(table, "extra-predicate-prefixes"),
        ignore_decorators=frozenset(_get_strings(table, "ignore-decorators")),
        ignore_patterns=DEFAULT_IGNORE_PATTERNS + tuple(_get_strings(table, "ignore-patterns")),
    )


def _fetch_config_table(pyproject: Path) -> dict[str, object]:
    if not pyproject.exists():
        return {}

    table = tomllib.loads(pyproject.read_text()).get("tool", {}).get("beda-lint", {})
    table = table.get(CONFIG_TABLE, {})
    unknown = set(table) - CONFIG_KEYS
    if unknown:
        sys.exit(f"{pyproject}: unknown [tool.beda-lint.{CONFIG_TABLE}] keys: {sorted(unknown)}")

    return table


def fetch_default_verbs() -> frozenset[str]:
    text = files("beda_lint").joinpath("verbs.txt").read_text()
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


def _get_words(table: dict[str, object], key: str) -> frozenset[str]:
    return frozenset(word.lower() for word in _get_strings(table, key))


def _get_strings(table: dict[str, object], key: str) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        sys.exit(f"[tool.beda-lint.{CONFIG_TABLE}] {key} must be a list of strings")

    return value


def check_function_names(tree: ast.Module, path: Path, config: NamingConfig) -> list[Finding]:
    lifecycle_hooks = _collect_aiohttp_lifecycle_hooks(tree)
    findings = []
    for qualname, func in _iterate_functions(tree.body, ""):
        stem = get_stem(func.name)
        if not stem or func.name in lifecycle_hooks or _is_exempt(func, config):
            continue

        if _has_bool_return(func):
            if not is_predicate(stem, config):
                findings.append(
                    Finding(
                        path,
                        func.lineno,
                        NOT_A_PREDICATE,
                        qualname,
                        f"`{func.name}` returns bool, so name it as a statement about its "
                        f"argument: `is_`, `has_`, `should_`, `can_`, or a third-person verb "
                        f"such as `matches_`",
                    )
                )
        elif stem not in config.verbs and not is_predicate(stem, config):
            findings.append(
                Finding(
                    path,
                    func.lineno,
                    NOT_A_VERB,
                    qualname,
                    f"`{func.name}` does not start with a verb; name it for what it does "
                    f"(`fetch_`, `build_`, ...) or add `{stem}` to extra-verbs",
                )
            )
    return findings


def _collect_aiohttp_lifecycle_hooks(tree: ast.Module) -> set[str]:
    """Functions this module registers on an app signal: `app.cleanup_ctx.append(db)`."""
    hooks: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr in AIOHTTP_APP_SIGNALS
        ):
            for argument in node.args:
                items = argument.elts if isinstance(argument, ast.List | ast.Tuple) else [argument]
                hooks.update(item.id for item in items if isinstance(item, ast.Name))
    return hooks


def _iterate_functions(nodes: Sequence[ast.AST], prefix: str) -> Iterator[tuple[str, FunctionDef]]:
    """Every function with its dotted path, including methods and nested functions."""
    for node in nodes:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            qualname = f"{prefix}{node.name}"
            yield qualname, node
            yield from _iterate_functions(node.body, f"{qualname}.")
        elif isinstance(node, ast.ClassDef):
            yield from _iterate_functions(node.body, f"{prefix}{node.name}.")
        else:
            yield from _iterate_functions(list(ast.iter_child_nodes(node)), prefix)


def get_stem(name: str) -> str:
    """First word of a snake_case or camelCase name, lowercased, ignoring leading underscores."""
    return WORD_BOUNDARY.split(name.lstrip("_"))[0].lower()


def _is_exempt(func: FunctionDef, config: NamingConfig) -> bool:
    if (func.name.startswith("__") and func.name.endswith("__")) or func.name in EXEMPT_NAMES:
        return True

    if any(fnmatchcase(func.name, pattern) for pattern in config.ignore_patterns):
        return True

    decorators = [_get_decorator_name(decorator) for decorator in func.decorator_list]
    return any(
        name in EXEMPT_DECORATORS
        or name in config.ignore_decorators
        or name.rsplit(".", 1)[-1] in ACCESSOR_DECORATOR_ATTRIBUTES
        for name in decorators
    )


def _get_decorator_name(decorator: ast.expr) -> str:
    """Dotted name without call arguments: `@sdk.operation(...)` gives `sdk.operation`."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(target)


def _has_bool_return(func: FunctionDef) -> bool:
    """The annotation decides; without one, every `return` must give a bool expression."""
    if func.returns is None:
        values = [statement.value for statement in _iterate_own_returns(func.body)]
        return bool(values) and all(
            value is not None and _is_bool_expression(value) for value in values
        )

    returns = func.returns
    if isinstance(returns, ast.Constant) and isinstance(returns.value, str):
        returns = ast.parse(returns.value, mode="eval").body
    if isinstance(returns, ast.Subscript):
        return _get_type_name(returns.value) in BOOL_GUARD_TYPES

    return returns is not None and _get_type_name(returns) == "bool"


def _iterate_own_returns(nodes: Sequence[ast.AST]) -> Iterator[ast.Return]:
    """Return statements of this function, not of functions or classes nested in it."""
    for node in nodes:
        if isinstance(node, ast.Return):
            yield node
        elif not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            yield from _iterate_own_returns(list(ast.iter_child_nodes(node)))


def _is_bool_expression(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, bool)

    if isinstance(node, ast.Compare):
        return True

    if isinstance(node, ast.UnaryOp):
        return isinstance(node.op, ast.Not)

    if isinstance(node, ast.BoolOp):
        return all(_is_bool_expression(value) for value in node.values)

    if isinstance(node, ast.Call):
        return _get_type_name(node.func) in BOOL_FUNCTIONS

    return False


def _get_type_name(node: ast.expr) -> str:
    return node.attr if isinstance(node, ast.Attribute) else ast.unparse(node)


def is_predicate(stem: str, config: NamingConfig) -> bool:
    """`is`/`has`/...-style prefixes, or the third-person form of a known verb (`matches`)."""
    return stem in config.predicate_prefixes or bool(_get_base_forms(stem) & config.verbs)


def _get_base_forms(stem: str) -> set[str]:
    forms = set()
    if stem.endswith("ies"):
        forms.add(f"{stem[:-3]}y")
    if stem.endswith("es"):
        forms.add(stem[:-2])
    if stem.endswith("s"):
        forms.add(stem[:-1])
    return forms


if __name__ == "__main__":
    sys.exit(main())
