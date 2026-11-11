"""A small helper that works on every Python from 3.9 on."""


def greet(name):
    """Return a plain greeting for a name."""
    if name:
        return "Hello, " + name
    return "Hello"


def total(numbers):
    """Add up a list of numbers."""
    result = 0
    for number in numbers:
        result += number
    return result
