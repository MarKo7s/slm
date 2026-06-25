"""Center coordinate helpers (user / Modelab ↔ display coords)."""


def display_center_to_user(
    display_xy: list[int],
    lcos_size: tuple[int, int],
    offset: int,
    modelab: bool,
    is_v: bool,
) -> tuple[int, int]:
    """Convert internal display center back to user coordinates for the GUI."""
    x = int(display_xy[0]) + offset
    y = int(display_xy[1]) + offset
    if modelab:
        y = lcos_size[0] - (y + 1)
        if is_v:
            x += 1
    return x, y
