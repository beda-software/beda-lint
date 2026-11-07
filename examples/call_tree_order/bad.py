# ORDER001: the helper sits above its caller, so the reader meets details before the
# function that explains why they exist. Move `_format_invoice` below `build_invoice`.
def _format_invoice(lines):
    return "\n".join(lines)


def build_invoice(order):
    return _format_invoice(order.lines)


# ORDER001: a helper shared by several callers goes below the last of them,
# here below `send_invoice`, not between the two callers.
def print_invoice(order):
    print(_render(order))


def _render(order):
    return str(order)


def send_invoice(order, mailer):
    mailer.send(_render(order))
