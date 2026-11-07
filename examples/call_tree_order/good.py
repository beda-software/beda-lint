# The entry point comes first, then its helpers in the order it uses them,
# and each helper's own helpers below it: the file reads top-down.


def build_invoice(order: "Order") -> str:
    lines = _collect_lines(order)
    return _format_invoice(lines)


def _collect_lines(order: "Order") -> list[str]:
    return [_build_line(item) for item in order.items]


def _build_line(item: "Item") -> str:
    return f"{item.name}: {item.price}"


def _format_invoice(lines: list[str]) -> str:
    return "\n".join(lines)


# Functions that call each other in a cycle are not ordered among themselves.
def is_even(number: int) -> bool:
    return number == 0 or is_odd(number - 1)


def is_odd(number: int) -> bool:
    return number != 0 and is_even(number - 1)
