import numpy as np
from typing import Literal


class Aperture:
    def __init__(self, diameter, LCOS_size, px_size):
        self.h, self.w = LCOS_size
        self.R = int(np.floor(diameter / (2 * px_size)))
        self.R2 = self.R * self.R
        self.x = np.arange(self.w, dtype=np.float32)
        self.y = np.arange(self.h, dtype=np.float32)[:, None]
        self.h_aperture = np.zeros((self.h, self.w), dtype=np.uint8)
        self.v_aperture = np.zeros((self.h, self.w), dtype=np.uint8)
        self.total_aperture = np.zeros((self.h, self.w), dtype=np.uint8)

    def _fill_disk(self, out, cx, cy):
        out.fill(0)
        cx, cy = int(cx), int(cy)
        ys = slice(max(0, cy - self.R), min(self.h, cy + self.R + 1))
        xs = slice(max(0, cx - self.R), min(self.w, cx + self.R + 1))
        yy = self.y[ys]
        xx = self.x[xs]
        out[ys, xs] = ((xx - cx) ** 2 + (yy - cy) ** 2) <= self.R2

    def calculate_apertures(self, H_center, V_center):
        self._fill_disk(self.h_aperture, *H_center)
        self._fill_disk(self.v_aperture, *V_center)
        np.logical_or(self.h_aperture, self.v_aperture, out=self.total_aperture)
        return self.h_aperture, self.v_aperture, self.total_aperture


class HologramMask:
    def __init__(self, mask_size: tuple[int, int]):
        self.mask_size = mask_size
        h, w = mask_size
        self.zernike = np.zeros((h, w), dtype=np.float64)
        self.pattern = np.zeros((h, w), dtype=np.float64)
        self.att_weight = 0.0
        self.att_enabled = False
        self.zernikes_enabled = True
        self.pattern_enabled = True


class ModMuxMask:
    def __init__(
        self,
        aperture_diameter: float,
        LCOS_size: tuple[int, int],
        px_size: float,
        mask_size: tuple[int, int],
        Hcenter: tuple[int, int] | None = None,
        Vcenter: tuple[int, int] | None = None,
        offset_center: int = 0,
        ModelabCompatibility: bool = False,
        pol: Literal['H', 'V', 'HV'] = 'HV',
    ):
        self.aperture_diameter = aperture_diameter
        self.LCOS_size = LCOS_size
        self.px_size = px_size
        self.mask_size = mask_size
        self.offset_center = offset_center
        self.ModelabCompatibility = ModelabCompatibility
        self.pol = pol

        self.H = HologramMask(mask_size)
        self.V = HologramMask(mask_size)
        self.aperture = Aperture(aperture_diameter, LCOS_size, px_size)

        default_h, default_v = self._default_centers()
        user_h = Hcenter if Hcenter is not None else default_h
        user_v = Vcenter if Vcenter is not None else default_v
        self._apply_center_corrections(user_h, user_v)
        self.ap_H, self.ap_V, self.ap = self.aperture.calculate_apertures(
            self.Hcenter, self.Vcenter
        )

    def set_centers(self, Hcenter: tuple[int, int], Vcenter: tuple[int, int]):
        self._apply_center_corrections(Hcenter, Vcenter)
        self.ap_H, self.ap_V, self.ap = self.aperture.calculate_apertures(
            self.Hcenter, self.Vcenter
        )
        return self

    def _default_centers(self):
        HmaskCenter = [self.LCOS_size[1] // 4, self.LCOS_size[0] // 2]
        VmaskCenter = [3 * self.LCOS_size[1] // 4, self.LCOS_size[0] // 2]
        return HmaskCenter, VmaskCenter

    def _apply_center_corrections(self, cH, cV):
        """Apply center corrections if ModelabCompatibility is enabled."""
        cH = list(map(int, cH))
        cV = list(map(int, cV))

        if self.ModelabCompatibility:
            cH[1] = self.LCOS_size[0] - (cH[1] + 1)
            cV[1] = self.LCOS_size[0] - (cV[1] + 1)
            cV[0] -= 1

        self.Hcenter = [cH[0] - self.offset_center, cH[1] - self.offset_center]
        self.Vcenter = [cV[0] - self.offset_center, cV[1] - self.offset_center]
