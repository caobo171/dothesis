"""
DoThesis - AI-Powered Academic Writing Framework

Generate publication-ready theses with 15 specialized AI agents and 200M+ research papers.
"""

# Relative import: this package is reachable both as `opendraft` (engine/ on
# sys.path) and as `engine.opendraft` (engine/ is itself a package). An absolute
# import would only resolve under the first, so keep intra-package imports relative.
from .version import __version__

__author__ = "Federico De Ponte"
__license__ = "MIT"

__all__ = ["__version__"]
