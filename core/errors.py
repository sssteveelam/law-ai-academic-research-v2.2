class ResearchPlatformError(Exception):
    """Base error for expected application failures."""


class ExternalAPIError(ResearchPlatformError):
    """An external scholarly API could not provide a response."""


class ValidationError(ResearchPlatformError):
    """External data did not satisfy the normalized contract."""
