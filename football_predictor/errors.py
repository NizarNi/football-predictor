from typing import Optional


class APIError(Exception):
    """Unified error class for all external API clients."""

    def __init__(self, source: str, code: str, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.source = source
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "code": self.code,
            "message": self.message,
            **({"details": self.details} if self.details else {}),
        }
