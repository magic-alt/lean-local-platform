class LeanWebError(Exception):
    """Expected application error suitable for HTTP 400 responses."""


class NotFoundError(LeanWebError):
    """Requested local resource does not exist."""
