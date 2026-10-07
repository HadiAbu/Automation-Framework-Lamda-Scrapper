class FrameworkError(Exception):
    """Base class for testbed errors."""


class MissingConfigError(FrameworkError):
    """A required setting is not set."""


class UnknownProjectError(FrameworkError):
    """The requested project is not registered."""


class ProjectNotSelectedError(FrameworkError):
    """No project marker or default project was configured."""


class DuplicateProjectError(FrameworkError):
    """Two entry points registered the same project name."""
