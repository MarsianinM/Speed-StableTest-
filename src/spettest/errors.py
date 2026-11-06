"""Користувацькі помилки без traceback у консолі."""


class SpetTestError(Exception):
    """Помилка, яку можна безпечно показати користувачу українською."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
