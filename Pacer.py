import numpy as np
import time
from PySide6.QtCore import QObject


class Pacer(QObject):
    def __init__(self):
        super().__init__()

        theta = np.linspace(0, 2 * np.pi, 40)
        self.cos_theta = np.cos(theta)
        self.sin_theta = np.sin(theta)

    def breathing_pattern(self, breathing_rate, time):
        """Returns radius of pacer disk.

        Radius is modulated according to sinusoidal breathing pattern
        and scaled between 0 and 1.
        """
        return 0.5 + 0.5 * np.sin(2 * np.pi * breathing_rate / 60 * time)

    def update(self, breathing_rate):
        """Update radius of pacer disc.

        Make current disk radius a function of real time (i.e., don't
        precompute radii with fixed time interval) in order to compensate for
        jitter or delay in QTimer calls.
        """
        radius = self.breathing_pattern(breathing_rate, time.time())
        x = radius * self.cos_theta
        y = radius * self.sin_theta
        return (x, y)
