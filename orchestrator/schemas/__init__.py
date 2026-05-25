"""Module output schemas — one Pydantic model per of the 5 research modules."""
from .m1 import M1Output
from .m2 import M2Output, CitedGap, PaperReference
from .m3 import M3Output
from .m4 import M4Output
from .m5 import M5Output, ExportArtifact

__all__ = [
    "M1Output", "M2Output", "M3Output", "M4Output", "M5Output",
    "CitedGap", "PaperReference", "ExportArtifact",
]
