"""Uses a type statement, which needs Python 3.12 or newer."""


type UserId = int


def show(user_id: UserId):
    """Show a user id."""
    return "user " + str(user_id)
