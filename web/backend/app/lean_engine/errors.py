from ..core.errors import LeanWebError


class LeanPlatformError(LeanWebError, ValueError):
    pass
