"""Business-rule errors, rendered as {"code", "message", **extra} by the handler in main.py."""


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra
