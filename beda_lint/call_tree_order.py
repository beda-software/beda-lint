"""Check that each function sits below its last caller, so a module reads as a call tree."""

import ast
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from beda_lint.cli import Finding, run_check

CODE = "ORDER001"
PROPERTY_DECORATORS = frozenset({"property", "cached_property", "setter", "getter", "deleter"})

TopLevelFunc = ast.FunctionDef | ast.AsyncFunctionDef


def main(argv: Sequence[str] | None = None) -> int:
    return run_check(check_call_tree_order, __doc__, argv)


def check_call_tree_order(tree: ast.Module, path: Path) -> list[Finding]:
    module_functions = _get_defs(tree.body)
    module_callers = [(func.name, func) for func in module_functions] + [
        (f"{cls.name}.{method.name}", method)
        for cls in tree.body
        if isinstance(cls, ast.ClassDef)
        for method in _get_defs(cls.body)
    ]
    findings = _check_scope_order(module_functions, module_callers, None, "", path)
    for cls, prefix in _iterate_classes(tree.body, ""):
        methods = _get_defs(cls.body)
        findings.extend(
            _check_scope_order(
                [method for method in methods if not _is_property(method)],
                [(f"{prefix}{method.name}", method) for method in methods],
                frozenset({"self", "cls", cls.name}),
                prefix,
                path,
            )
        )
    return findings


def _get_defs(body: list[ast.stmt]) -> list[TopLevelFunc]:
    return [node for node in body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)]


def _iterate_classes(body: list[ast.stmt], prefix: str) -> Iterator[tuple[ast.ClassDef, str]]:
    """Module-level classes and those nested in them; a class inside a function is not ordered."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            class_prefix = f"{prefix}{node.name}."
            yield node, class_prefix
            yield from _iterate_classes(node.body, class_prefix)


def _is_property(method: TopLevelFunc) -> bool:
    """Read as attributes, so code that uses them never calls them."""
    return any(
        (isinstance(decorator, ast.Name) and decorator.id in PROPERTY_DECORATORS)
        or (isinstance(decorator, ast.Attribute) and decorator.attr in PROPERTY_DECORATORS)
        for decorator in method.decorator_list
    )


def _check_scope_order(
    callees: list[TopLevelFunc],
    callers: list[tuple[str, TopLevelFunc]],
    receivers: frozenset[str] | None,
    symbol_prefix: str,
    path: Path,
) -> list[Finding]:
    """Each helper sits below its last caller; members of one call cycle are not ordered."""
    # Overload stubs and redefinitions share a name: the helper sits at its first definition.
    positions: dict[str, TopLevelFunc] = {}
    for callee in callees:
        positions.setdefault(callee.name, callee)
    uses = [
        (caller_name, caller, _collect_uses(caller, positions.keys(), receivers))
        for caller_name, caller in callers
    ]
    component_of = _map_strongly_connected_components(
        _build_call_graph(uses, positions.keys(), symbol_prefix)
    )

    callers_by_callee: dict[str, list[tuple[str, TopLevelFunc]]] = defaultdict(list)
    for caller_name, caller, used_names in uses:
        same_scope_name = caller.name if caller_name == f"{symbol_prefix}{caller.name}" else None
        for used_name in used_names:
            if same_scope_name in component_of and (
                component_of[used_name] == component_of[same_scope_name]
            ):
                continue
            callers_by_callee[used_name].append((caller_name, caller))

    findings = []
    for callee_name, callers_of_callee in callers_by_callee.items():
        last_caller_name, last_caller = max(callers_of_callee, key=lambda item: item[1].lineno)
        callee = positions[callee_name]
        if callee.lineno < last_caller.lineno:
            symbol = f"{symbol_prefix}{callee_name}"
            findings.append(
                Finding(
                    path,
                    callee.lineno,
                    CODE,
                    symbol,
                    f"`{symbol}` is defined above its caller `{last_caller_name}` "
                    f"(line {last_caller.lineno}); move helpers below their last caller",
                )
            )
    return findings


def _collect_uses(
    caller: TopLevelFunc, known: Iterable[str], receivers: frozenset[str] | None
) -> set[str]:
    """Names of `known` the body calls or passes on: bare names, or `self.x` with `receivers`.

    Decorators and defaults are left out: they run at definition time, so they must stay above.
    """
    known_names = set(known)
    if receivers is None:
        return {
            node.id
            for statement in caller.body
            for node in ast.walk(statement)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in known_names
        }

    return {
        node.attr
        for node in _walk_outside_classes(caller.body)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in receivers
        and node.attr in known_names
    }


def _walk_outside_classes(statements: list[ast.stmt]) -> Iterator[ast.AST]:
    """A nested class's `self` is its own instance, not the enclosing method's."""
    pending: list[ast.AST] = [node for node in statements if not isinstance(node, ast.ClassDef)]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(
            child for child in ast.iter_child_nodes(current) if not isinstance(child, ast.ClassDef)
        )


def _build_call_graph(
    uses: list[tuple[str, TopLevelFunc, set[str]]], names: Iterable[str], symbol_prefix: str
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {name: set() for name in names}
    for caller_name, caller, used_names in uses:
        if caller_name == f"{symbol_prefix}{caller.name}" and caller.name in graph:
            graph[caller.name] |= used_names
    return graph


def _map_strongly_connected_components(graph: dict[str, set[str]]) -> dict[str, int]:
    """Iterative Tarjan: a recursive walk overflows the stack on long call chains."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    component: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    for root, root_targets in graph.items():
        if root in index:
            continue

        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        pending = [(root, iter(sorted(root_targets)))]
        while pending:
            node, targets = pending[-1]
            target = next(targets, None)
            if target is not None:
                if target not in index:
                    index[target] = low[target] = len(index)
                    stack.append(target)
                    on_stack.add(target)
                    pending.append((target, iter(sorted(graph[target]))))
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
                continue

            pending.pop()
            if pending:
                parent = pending[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component[member] = index[node]
                    if member == node:
                        break
    return component


if __name__ == "__main__":
    sys.exit(main())
