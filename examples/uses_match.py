"""Uses a match statement, which needs Python 3.10 or newer."""


def describe(value):
    """Describe a value with pattern matching."""
    match value:
        case 1:
            return "one"
        case 2:
            return "two"
        case _:
            return "something else"
