"""MODMUX dual-polarization LCOS SLM driver and Qt control widgets."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("slm")
except PackageNotFoundError:
    __version__ = "0.1.0"

from .pyLCOS import LCOS
from .maksSpecs import Aperture, HologramMask, ModMuxMask

__all__ = [
    "__version__",
    "LCOS",
    "Aperture",
    "HologramMask",
    "ModMuxMask",
]
