"""
Minimal Python wrapper for the Meadowlark Blink 1920 HDMI SDK (Blink_C_wrapper.dll).

Display of phase masks can use :meth:`MeadowlarkSDK.write_image` (SDK ``Write_image``)
or separately via ``hdmi.fullscreenqt`` / pyLCOS ``LCOS_Display``.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

DEFAULT_SDK_PATH = Path(r"C:\Program Files\Meadowlark Optics\Blink 1920 HDMI\SDK")
DEFAULT_PIXEL_PITCH_UM = 9.2  # not exposed by HDMI SDK; set from datasheet / calibration


class MeadowlarkSDKError(RuntimeError):
    """Raised when Blink SDK calls fail or the DLL cannot be loaded."""


def _set_dpi_awareness() -> None:
    """Match Meadowlark's example scripts so the SDK window aligns with the SLM monitor."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def _pump_win32_messages(max_ms: float = 50.0) -> None:
    """
    Process pending Win32 messages for the Meadowlark SFML display window.

    Jupyter and other non-GUI hosts do not run a message loop, so the SDK
    window often shows "(Not Responding)" after the first ``Write_image`` even
    when the SLM updated correctly. Pumping messages on the calling thread
    (the same thread that called ``Create_SDK``) keeps the window responsive.
    """
    if sys.platform != "win32":
        return

    import time

    user32 = ctypes.windll.user32
    PM_REMOVE = 0x0001

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam", ctypes.c_size_t),
            ("lParam", ctypes.c_size_t),
            ("time", ctypes.c_uint),
            ("pt", POINT),
        ]

    msg = MSG()
    deadline = time.perf_counter() + max_ms / 1000.0
    while time.perf_counter() < deadline:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.001)


class MeadowlarkSDK:
    """
    Thin wrapper around Blink_C_wrapper.dll for the P1920 HDMI SLM.

    Parameters
    ----------
    sdk_path : path-like, optional
        Folder containing Blink_C_wrapper.dll (default: Meadowlark install SDK path).
    pixel_pitch_um : float, optional
        Pixel pitch in microns. The HDMI SDK does not report this; set manually.
    init_sdk : bool, optional
        If True (default), call Create_SDK() on construction.
        Set False to load the DLL without opening the SDK display window.
    """

    def __init__(
        self,
        sdk_path: os.PathLike = DEFAULT_SDK_PATH,
        pixel_pitch_um: float = DEFAULT_PIXEL_PITCH_UM,
        init_sdk: bool = True,
    ) -> None:
        self.sdk_path = Path(sdk_path)
        self.pixel_pitch_um = float(pixel_pitch_um)
        self._lib: Optional[ctypes.CDLL] = None
        self._initialized = False
        self._rgba_buffer: Optional[np.ndarray] = None

        self._load_library()
        if init_sdk:
            self.open()

    def _load_library(self) -> None:
        dll_path = self.sdk_path / "Blink_C_wrapper.dll"
        if not dll_path.is_file():
            raise MeadowlarkSDKError(f"Blink_C_wrapper.dll not found at {dll_path}")

        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(self.sdk_path))

        self._lib = ctypes.CDLL(str(dll_path))
        lib = self._lib

        lib.Create_SDK.argtypes = []
        lib.Create_SDK.restype = None

        lib.Delete_SDK.argtypes = []
        lib.Delete_SDK.restype = None

        for name in ("Get_Width", "Get_Height", "Get_Depth", "Get_SLMFound", "Get_COMFound"):
            getattr(lib, name).restype = ctypes.c_int

        for name in ("Get_SLMTemp", "Get_SLMVCom"):
            getattr(lib, name).restype = ctypes.c_double

        lib.Load_lut.argtypes = [ctypes.c_char_p]
        lib.Load_lut.restype = ctypes.c_int

        lib.Set_channel.argtypes = [ctypes.c_int]
        lib.Set_channel.restype = ctypes.c_int

        lib.Write_image.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint]
        lib.Write_image.restype = None

        lib.Resync.argtypes = []
        lib.Resync.restype = ctypes.c_int

    def pump_messages(self, max_ms: float = 50.0) -> None:
        """
        Process Win32 messages for the SDK display window.

        Call after ``write_image`` in Jupyter if the HDMI window shows
        "(Not Responding)" while the SLM pattern is correct.
        """
        _pump_win32_messages(max_ms)

    def _init_buffers(self) -> None:
        """Allocate the RGBA frame buffer once (reused by every ``write_image``)."""
        h, w = self.shape
        if self._rgba_buffer is not None and self._rgba_buffer.shape == (h, w, 4):
            return
        self._rgba_buffer = np.zeros((h, w, 4), dtype=np.uint8)
        self._rgba_buffer[:, :, 3] = 255

    def _require_buffers(self) -> np.ndarray:
        if self._rgba_buffer is None:
            raise MeadowlarkSDKError(
                "Image buffer not allocated; call open() first or use init_sdk=True."
            )
        return self._rgba_buffer

    @property
    def image_buffer(self) -> np.ndarray:
        """
        Pre-allocated ``(height, width)`` uint8 gray buffer (red HDMI plane).

        Write phase/level data here, then call :meth:`write_image` with no arguments
        to display without an extra copy from a temporary array.
        """
        return self._require_buffers()[:, :, 0]

    @property
    def rgb_buffer(self) -> np.ndarray:
        """View of the pre-allocated ``(height, width, 3)`` RGB portion of the frame."""
        return self._require_buffers()[:, :, :3]

    def open(self) -> None:
        """Initialize the SDK. Opens the Meadowlark display window on the SLM monitor."""
        if self._initialized:
            return
        _set_dpi_awareness()
        self._lib.Create_SDK()
        self._initialized = True
        self._init_buffers()
        _pump_win32_messages()

    def close(self) -> None:
        """Shut down the SDK and release the display window."""
        if not self._initialized:
            return
        self._lib.Delete_SDK()
        self._initialized = False
        self._rgba_buffer = None

    def __enter__(self) -> "MeadowlarkSDK":
        if not self._initialized:
            self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self._initialized

    def _require_open(self) -> ctypes.CDLL:
        if not self._initialized:
            raise MeadowlarkSDKError("SDK not initialized; call open() first or use init_sdk=True.")
        return self._lib

    # --- geometry (from SDK) ---

    @property
    def width(self) -> int:
        """Panel width in pixels (SDK Get_Width)."""
        return int(self._require_open().Get_Width())

    @property
    def height(self) -> int:
        """Panel height in pixels (SDK Get_Height)."""
        return int(self._require_open().Get_Height())

    @property
    def bit_depth(self) -> int:
        """Bit depth reported by the SDK (Get_Depth)."""
        return int(self._require_open().Get_Depth())

    @property
    def resolution(self) -> Tuple[int, int]:
        """(width, height) in pixels."""
        return self.width, self.height

    @property
    def shape(self) -> Tuple[int, int]:
        """(height, width) — numpy-style shape for image arrays."""
        w, h = self.resolution
        return h, w

    @property
    def pixel_pitch(self) -> Tuple[float, float]:
        """(pitch_x_um, pitch_y_um). HDMI SDK does not provide this; user-supplied."""
        p = self.pixel_pitch_um
        return p, p

    # --- connection status ---

    @property
    def slm_found(self) -> bool:
        """True if the SLM HDMI display was detected."""
        return bool(self._require_open().Get_SLMFound())

    @property
    def com_found(self) -> bool:
        """True if the USB serial (COM) port for SLM settings was detected."""
        return bool(self._require_open().Get_COMFound())

    # --- monitoring (USB) ---

    def get_temperature(self) -> float:
        """SLM temperature in degrees Celsius."""
        return float(self._require_open().Get_SLMTemp())

    def get_coverglass_voltage(self) -> float:
        """Coverglass voltage in volts."""
        return float(self._require_open().Get_SLMVCom())

    # --- configuration ---

    def load_lut(self, lut_path: os.PathLike) -> None:
        """
        Load a Meadowlark LUT file (*.lut, *.blt, *.txt) onto the SLM controller.

        Linear input graylevels (0–255) are mapped to calibrated drive levels in hardware.
        """
        path = Path(lut_path)
        if not path.is_file():
            raise FileNotFoundError(f"LUT file not found: {path}")
        ok = self._require_open().Load_lut(str(path).encode("utf-8"))
        if not ok:
            raise MeadowlarkSDKError(f"Load_lut failed for {path}")

    def set_channel(self, channel: int) -> None:
        """
        HDMI color channel used as 8-bit input: 0=red (default), 1=green, 2=blue.
        """
        if channel not in (0, 1, 2):
            raise ValueError("channel must be 0 (red), 1 (green), or 2 (blue)")
        ok = self._require_open().Set_channel(channel)
        if not ok:
            raise MeadowlarkSDKError(f"Set_channel({channel}) failed")

    def _copy_into_buffer(self, image: np.ndarray) -> None:
        """Copy *image* into the persistent RGBA buffer (no allocation)."""
        h, w = self.shape
        buf = self._require_buffers()
        gray = buf[:, :, 0]
        arr = np.asarray(image)

        if arr.ndim == 2:
            if arr.shape != (h, w):
                raise ValueError(f"Expected shape {self.shape}, got {arr.shape}")
            if arr is gray or np.may_share_memory(arr, buf):
                return
            if arr.dtype == np.uint8:
                np.copyto(gray, arr)
            else:
                np.copyto(gray, np.clip(arr, 0, 255).astype(np.uint8))
            buf[:, :, 1] = 0
            buf[:, :, 2] = 0
            return

        if arr.ndim == 3:
            if arr.shape[2] != 3:
                raise ValueError(
                    f"Expected (height, width, 3) RGB array, got shape {arr.shape}. "
                    "Pass 2D gray or 3D RGB; alpha is stored in the pre-allocated buffer."
                )
            if arr.shape[:2] != (h, w):
                raise ValueError(f"Expected spatial shape {self.shape}, got {arr.shape[:2]}")
            rgb = buf[:, :, :3]
            if arr is rgb or np.may_share_memory(arr, buf):
                return
            if arr.dtype == np.uint8:
                np.copyto(rgb, arr)
            else:
                np.copyto(rgb, np.clip(arr, 0, 255).astype(np.uint8))
            return

        raise ValueError(
            f"Expected (height, width) gray or (height, width, 3) RGB; got shape {arr.shape}"
        )

    def write_image(self, image: Optional[np.ndarray] = None) -> None:
        """
        Display a mask on the SLM via ``Write_image``.

        Uses a pre-allocated RGBA buffer created in :meth:`open`. Passing *image*
        copies into that buffer; calling with no argument sends the current
        :attr:`image_buffer` / :attr:`rgb_buffer` contents (zero extra allocation).

        Parameters
        ----------
        image : numpy.ndarray, optional
            ``(height, width)`` gray 0–255 (red plane; use :meth:`set_channel` ``0``),
            or ``(height, width, 3)`` RGB. If omitted, the existing internal buffer
            is sent unchanged.

        Examples
        --------
        Copy path::

            slm.write_image(gray)

        In-place path (fastest)::

            slm.image_buffer[:] = gray
            slm.write_image()
        """
        if image is not None:
            self._copy_into_buffer(image)

        buf = self._require_buffers()

        self._require_open().Write_image(
            buf.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte)),
            ctypes.c_uint(0),
        )
        try:
            self._require_open().Resync()
        except (AttributeError, OSError):
            pass
        _pump_win32_messages()

    def info(self) -> dict:
        """Summary dict of SLM geometry, connection status, and monitoring reads."""
        return {
            "resolution": self.resolution,
            "shape": self.shape,
            "bit_depth": self.bit_depth,
            "pixel_pitch_um": self.pixel_pitch,
            "slm_found": self.slm_found,
            "com_found": self.com_found,
            "temperature_C": self.get_temperature(),
            "coverglass_V": self.get_coverglass_voltage(),
        }

    def __repr__(self) -> str:
        if not self._initialized:
            return f"MeadowlarkSDK(sdk_path={self.sdk_path!s}, initialized=False)"
        w, h = self.resolution
        return (
            f"MeadowlarkSDK({w}x{h}, {self.bit_depth}-bit, "
            f"slm_found={self.slm_found}, com_found={self.com_found})"
        )


if __name__ == "__main__":
    print("Meadowlark Blink 1920 HDMI — basic SDK query")
    print(f"SDK path: {DEFAULT_SDK_PATH}\n")

    with MeadowlarkSDK() as slm:
        print(repr(slm))
        for key, value in slm.info().items():
            print(f"  {key}: {value}")
