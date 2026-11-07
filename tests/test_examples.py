import tomllib
from functools import partial
from pathlib import Path

import pytest

from beda_lint.call_tree_order import check_call_tree_order
from beda_lint.cli import CheckTree, check_file
from beda_lint.function_verb_names import (
    DEFAULT_IGNORE_PATTERNS,
    PREDICATE_PREFIXES,
    NamingConfig,
    check_function_names,
    fetch_default_verbs,
)

ROOT = Path(__file__).parents[1]
EXAMPLES = ROOT / "examples"
DEFAULT_NAMING_CONFIG = NamingConfig(
    verbs=fetch_default_verbs(),
    predicate_prefixes=PREDICATE_PREFIXES,
    ignore_decorators=frozenset(),
    ignore_patterns=DEFAULT_IGNORE_PATTERNS,
)
CHECKS: dict[str, CheckTree] = {
    "call_tree_order": check_call_tree_order,
    "function_verb_names": partial(check_function_names, config=DEFAULT_NAMING_CONFIG),
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


def test_examples__every_check_has_an_examples_folder() -> None:
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    check_names = {script.replace("-", "_") for script in scripts}
    folders = {path.name for path in EXAMPLES.iterdir() if path.is_dir()}
    assert folders == check_names == set(CHECKS)


def run_example(check_name: str, file_name: str) -> list[tuple[str, str]]:
    findings = check_file(EXAMPLES / check_name / file_name, CHECKS[check_name])
    return [(finding.code, finding.symbol) for finding in findings]
