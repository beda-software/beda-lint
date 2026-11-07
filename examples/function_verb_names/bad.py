# BVN001: named after what it returns, not what it does. Use `fetch_patient`.
def patient_data(patient_id: str) -> "Patient": ...


# BVN001: a noun phrase. Use `calculate_invoice_total`.
def invoice_total(items: list) -> int: ...


# BVN001: only a bool function may start with a third-person form, so `records` reads as a noun.
# Use `fetch_records`.
def records(patient: "Patient") -> list: ...


# BVN001: a conversion still needs its verb. Use `convert_chat_to_dict`.
def chat_to_dict(chat: "Chat") -> dict: ...


# BVN002: returns bool but reads as an action that may raise. Use `is_paid`.
def check_paid(invoice: "Invoice") -> bool: ...


# BVN002: an imperative promises an action it does not take. Use `has_satisfier`.
def record_satisfier(task: "Task") -> bool: ...


VALID_TOKENS = frozenset({"alpha", "beta"})


# BVN002: no annotation, but it returns a comparison. Use `is_valid_token`.
def validate_token(token: str):
    return token in VALID_TOKENS
