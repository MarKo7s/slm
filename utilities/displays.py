from pylab import *
from PySide6.QtWidgets import QApplication

def display_discovery():         
    app = QApplication.instance()
    screens = {}
    for i, s in enumerate(app.screens()):
        g = s.geometry()
        screens[i] = {
            "name": s.name(),
            "width": g.width(),
            "height": g.height(),
            "x": g.x(),
            "y": g.y()
        }

    return screens

def find_display(screens, w = 1920, h = 1152):
    
    for i, info in screens.items():
        if info["width"] == w and info["height"] == h:
            return i

    raise ValueError(f"No screen with {w}x{h}. Found: {screens}")





