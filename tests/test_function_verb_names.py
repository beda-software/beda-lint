import ast
import textwrap
from pathlib import Path

import pytest

from beda_lint.function_verb_names import (
    PREDICATE_PREFIXES,
    ConfigError,
    NamingConfig,
    check_function_names,
    fetch_config,
    fetch_default_verbs,
    get_stem,
    main,
)

DEFAULT_CONFIG = NamingConfig(
    verbs=fetch_default_verbs(),
    predicate_prefixes=PREDICATE_PREFIXES,
    ignore_decorators=frozenset(),
    ignore_patterns=(),
)


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("fetch_patient", "fetch"),
        ("_build_payload", "build"),
        ("__private_sync", "private"),
        ("setUp", "set"),
        ("assertEqual", "assert"),
        ("sync", "sync"),
        ("Total", "total"),
        ("HTTPThing", "httpthing"),
    ],
)
def test_get_stem__takes_the_first_word_of_snake_and_camel_case(name: str, stem: str) -> None:
    assert get_stem(name) == stem


def test_check_function_names__accepts_a_name_starting_with_a_verb() -> None:
    assert check_source("def fetch_patient(): ...\ndef _build_payload(): ...") == []


def test_check_function_names__flags_a_name_starting_with_a_noun() -> None:
    assert check_source("def patient_data(): ...") == [("BVN001", "patient_data")]


@pytest.mark.parametrize("name", ["records", "updates_for_patient", "Total"])
def test_check_function_names__flags_plural_and_capitalized_nouns(name: str) -> None:
    assert check_source(f"def {name}(): ...") == [("BVN001", name)]


def test_check_function_names__names_a_method_with_its_class() -> None:
    source = """
        class Cart:
            def total(self): ...
    """
    assert check_source(source) == [("BVN001", "Cart.total")]


def test_check_function_names__checks_nested_and_async_functions() -> None:
    source = """
        async def fetch_all():
            def inner(): ...
    """
    assert check_source(source) == [("BVN001", "fetch_all.inner")]


def test_check_function_names__checks_functions_inside_if_blocks() -> None:
    source = """
        if True:
            def helper(): ...
    """
    assert check_source(source) == [("BVN001", "helper")]


@pytest.mark.parametrize(
    "source",
    [
        "def is_closed() -> bool: ...",
        "def has_slots() -> bool: ...",
        "def should_evaluate() -> bool: ...",
        "def matches_requirement() -> bool: ...",
        "def applies() -> bool: ...",
        "def belongs_to_program() -> bool: ...",
        "def does_exist() -> bool: ...",
        "def is_ready() -> 'bool': ...",
        "def is_patient(x) -> TypeGuard[Patient]: ...",
    ],
)
def test_check_function_names__accepts_a_predicate_name_for_a_bool_function(source: str) -> None:
    assert check_source(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "def record_satisfier() -> bool: ...",
        "def ready() -> bool: ...",
        "def check_patient(x) -> typing.TypeGuard[Patient]: ...",
        "def check_ready() -> ' bool': ...",
    ],
)
def test_check_function_names__flags_a_bool_function_without_a_predicate_name(
    source: str,
) -> None:
    assert [code for code, _ in check_source(source)] == ["BVN002"]


def test_check_function_names__accepts_a_predicate_name_without_a_bool_annotation() -> None:
    assert check_source("def is_closed(task): ...") == []


def test_check_function_names__skips_a_string_annotation_that_is_not_valid_python() -> None:
    assert check_source("def fetch_task() -> 'not valid(': ...") == []


@pytest.mark.parametrize(
    "body",
    [
        "return True",
        "return task.status == 'closed'",
        "return not task.done",
        "return isinstance(task, Task) and task.id is not None",
        "return any(t.done for t in tasks)",
        "return self._is_valid(task)",
        "if task:\n        return False\n    return True",
    ],
)
def test_check_function_names__infers_a_bool_return_without_an_annotation(body: str) -> None:
    source = f"def check_task(task):\n    {body}\n"
    assert check_source(source) == [("BVN002", "check_task")]


@pytest.mark.parametrize(
    "body",
    [
        "return task",
        "if task:\n        return True\n    return task.status",
        "pass",
        "def is_ready():\n        return True\n    return task",
    ],
)
def test_check_function_names__does_not_infer_bool_from_mixed_or_missing_returns(
    body: str,
) -> None:
    assert check_source(f"def fetch_task(task):\n    {body}\n") == []


def test_check_function_names__trusts_a_non_bool_annotation_over_bool_returns() -> None:
    assert check_source("def fetch_flag() -> int:\n    return True\n") == []


@pytest.mark.parametrize(
    "source",
    [
        "def __len__(self): ...",
        "def main(): ...",
        "def test_patient_is_created(): ...",
        "@property\ndef total(self): ...",
        "@functools.cached_property\ndef total(self): ...",
        "@total.setter\ndef total(self, value): ...",
        "@pytest.fixture\ndef patient(): ...",
        "@pytest.fixture(scope='session')\ndef db(): ...",
        "@overload\ndef value(x: int) -> int: ...",
    ],
)
def test_check_function_names__exempts_protocol_accessor_fixture_and_test_names(
    source: str,
) -> None:
    assert check_source(source) == []


def test_check_function_names__skips_ignored_decorators_and_patterns() -> None:
    config = NamingConfig(
        verbs=DEFAULT_CONFIG.verbs,
        predicate_prefixes=DEFAULT_CONFIG.predicate_prefixes,
        ignore_decorators=frozenset({"sdk.operation"}),
        ignore_patterns=("m_*", "*_op"),
    )
    source = """
        @sdk.operation(["POST"], ["Patient", "$terminate"])
        def patient_terminate(operation, request): ...

        def m_create_patient(): ...

        def patient_reset_op(): ...

        def patient_data(): ...
    """
    assert check_source(source, config) == [("BVN001", "patient_data")]


def test_check_function_names__exempts_aiohttp_lifecycle_hooks_registered_in_the_module() -> None:
    source = """
        async def db(app):
            yield

        async def twilio(app):
            yield

        async def warmup(app): ...

        async def heartbeat(app): ...

        async def settings(app): ...

        def create_app():
            app.cleanup_ctx.append(db)
            app.cleanup_ctx.extend([twilio])
            app.on_startup.append(warmup)
            app.on_startup += [heartbeat]
    """
    assert check_source(source) == [("BVN001", "settings")]


def test_main__skips_a_finding_with_a_noqa_comment_for_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text(
        "def patient_data(): ...  # noqa: BVN001\n"
        "def invoice_total(): ...  # noqa: E501, BVN001 legacy name\n"
        "def order_total(): ...  # noqa: BCT001\n"
        "def cart_total(): ...  # noqa: E501 see BVN001\n"
    )
    monkeypatch.chdir(tmp_path)
    exit_code = main(["mod.py"])
    assert exit_code == 1
    output = capsys.readouterr().out
    assert [line.split(" ")[0] for line in output.splitlines()] == ["mod.py:3:", "mod.py:4:"]


def test_fetch_config__extends_the_defaults_from_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.beda-lint.function-verb-names]\n"
        'extra-verbs = ["Reconcile2"]\n'
        'extra-predicate-prefixes = ["needs"]\n'
        'ignore-decorators = ["sdk.operation"]\n'
        'ignore-patterns = ["m_*"]\n'
    )
    config = fetch_config(pyproject)
    assert "reconcile2" in config.verbs
    assert "fetch" in config.verbs
    assert {"is", "needs"} <= config.predicate_prefixes
    assert config.ignore_decorators == frozenset({"sdk.operation"})
    assert {"*_op", "m_*"} <= set(config.ignore_patterns)


def test_main__checks_with_built_in_defaults_without_a_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "mod.py").write_text("def fetch_rows(): ...\ndef patient_reset_op(): ...\n")
    monkeypatch.chdir(tmp_path)
    assert main(["mod.py"]) == 0


@pytest.mark.parametrize(
    "pyproject_text",
    [
        '[tool.beda-lint.function-verb-names]\nextra-verb = ["sync"]\n',
        '[tool.beda-lint.function-verb-names]\nextra-verbs = "sync"\n',
        '[tool]\nbeda-lint = "on"\n',
    ],
)
def test_fetch_config__rejects_an_unknown_key_a_non_list_value_or_a_non_table(
    tmp_path: Path, pyproject_text: str
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(pyproject_text)
    with pytest.raises(ConfigError):
        fetch_config(pyproject)


def test_main__reads_the_config_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mod.py").write_text("def rehydrate_rows(): ...\ndef patient_data(): ...\n")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.beda-lint.function-verb-names]\nextra-verbs = ["rehydrate"]\n'
    )
    monkeypatch.chdir(tmp_path)
    exit_code = main(["mod.py"])
    assert exit_code == 1
    assert capsys.readouterr().out == (
        "mod.py:2: BVN001 `patient_data` does not start with a verb; name it for what it does "
        "(`fetch_`, `build_`, ...) or add `patient` to extra-verbs\n"
    )


def test_fetch_default_verbs__is_sorted_lowercase_and_unique() -> None:
    lines = (Path(__file__).parents[1] / "beda_lint" / "verbs.txt").read_text().splitlines()
    assert lines == sorted(set(lines))
    assert all(line == line.lower().strip() and line for line in lines)


def check_source(source: str, config: NamingConfig = DEFAULT_CONFIG) -> list[tuple[str, str]]:
    tree = ast.parse(textwrap.dedent(source))
    return [(f.code, f.symbol) for f in check_function_names(tree, Path("f.py"), config)]
