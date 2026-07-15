"""SPM-Kit Data Hunter public API.

The historical single-module API remains available for compatibility while the
campaign engine and paged source adapters live in dedicated modules.
"""

from .legacy import *  # noqa: F401,F403
from .version import __version__

__all__ = ["__version__"]
