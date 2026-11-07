import ast
from pathlib import Path

import pytest

from beda_lint.call_tree_order import check_call_tree_order
from beda_lint.cli import CheckTree, Finding
from beda_lint.function_verb_names import check_function_names, fetch_config

EXAMPLES = Path(__file__).parents[1] / "examples"
DEFAULT_NAMING_CONFIG = fetch_config(EXAMPLES / "no-pyproject.toml")


def check_function_names_with_defaults(tree: ast.Module, path: Path) -> list[Finding]:
    return check_function_names(tree, path, DEFAULT_NAMING_CONFIG)


CHECKS: dict[str, CheckTree] = {
    "call_tree_order": check_call_tree_order,
    "function_verb_names": check_function_names_with_defaults,
}
EXPECTED_BAD_FINDINGS = {
    "call_tree_order": [("ORDER001", "_format_invoice"), ("ORDER001", "_render")],
    "function_verb_names": [
        ("NAME001", "patient_data"),
        ("NAME001", "invoice_total"),
        ("NAME001", "records"),
        ("NAME001", "chat_to_dict"),
        ("NAME002", "check_paid"),
        ("NAME002", "record_satisfier"),
        ("NAME002", "validate_token"),
    ],
}


@pytest.mark.parametrize("check_name", CHECKS)
def test_examples__good_file_has_no_findings(check_name: str) -> None:
    assert run_example(check_name, "good.py") == []


@pytest.mark.parametrize("check_name", CHECKS)
def test_examples__bad_file_has_exactly_the_documented_findings(check_name: str) -> None:
    assert run_example(check_name, "bad.py") == EXPECTED_BAD_FINDINGS[check_name]


def test_examples__every_check_has_a_good_and_a_bad_file() -> None:
    folders = {path.name for path in EXAMPLES.iterdir() if path.is_dir()}
    assert folders == set(CHECKS)
    assert all((EXAMPLES / name / "good.py").exists() for name in folders)
    assert all((EXAMPLES / name / "bad.py").exists() for name in folders)


def run_example(check_name: str, file_name: str) -> list[tuple[str, str]]:
    path = EXAMPLES / check_name / file_name
    findings = CHECKS[check_name](ast.parse(path.read_text()), path)
    return [(finding.code, finding.symbol) for finding in findings]
