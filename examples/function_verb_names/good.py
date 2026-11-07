from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from aiohttp import web

VALID_TOKENS = frozenset({"alpha", "beta"})


# A function does something, so its name starts with what it does.
def fetch_patient(patient_id: str) -> "Patient": ...


def _build_payload(patient: "Patient") -> dict: ...


def calculate_invoice_total(items: list) -> int: ...


def convert_chat_to_dict(chat: "Chat") -> dict: ...


def sync() -> None: ...


# A bool function answers a question about its argument, so it reads as a statement.
def is_closed(task: "Task") -> bool: ...


def has_slots(schedule: "Schedule") -> bool: ...


def should_retry(error: Exception) -> bool: ...


def matches_requirement(task: "Task") -> bool: ...


# Without an annotation, the returned comparison still marks it as a bool function.
def is_valid_token(token: str):
    return token in VALID_TOKENS


# Properties, dunders, fixtures and `*_op` operations are named by their role.
class Invoice:
    @property
    def total(self) -> int: ...

    def __len__(self) -> int: ...


@pytest.fixture
def patient() -> "Patient": ...


def patient_terminate_op(operation: dict, request: dict) -> web.Response: ...


# An aiohttp lifecycle hook registered in the same module is named for the resource it manages.
async def database(app: web.Application) -> AsyncIterator[None]:
    yield


app = web.Application()
app.cleanup_ctx.append(database)


# A deliberate exception is suppressed on its `def` line.
def dt(value: str) -> datetime:  # noqa: NAME001
    return datetime.fromisoformat(value)
