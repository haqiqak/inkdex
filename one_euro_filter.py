# one_euro_filter.py
# The One Euro Filter — a velocity-aware adaptive low-pass filter.
#
# WHY NOT JUST USE EMA (exponential moving average)?
#   EMA uses a fixed alpha. Low alpha = smooth but laggy. High alpha = responsive
#   but jittery. You can't win both at once — it's a fixed tradeoff.
#
# THE ONE EURO INSIGHT:
#   The right amount of smoothing depends on how FAST the signal is moving.
#   - Hand held still  → velocity ≈ 0 → apply heavy smoothing (kill the noise)
#   - Hand moving fast → velocity is high → apply light smoothing (follow quickly)
#
#   This gives you both: a cursor that feels perfectly still when you're not
#   moving, and instant response when you make a deliberate movement.
#
# MATH (simplified):
#   alpha = 1 / (1 + Tc / (cutoff_frequency * 2π))
#   where Tc = 1/sample_rate
#   cutoff_frequency = fc_min + beta * |velocity|
#
#   fc_min : minimum cutoff (controls smoothing when still) — lower = smoother
#   beta   : speed coefficient — higher = responds faster to fast movement
#   fc_d   : cutoff for the velocity signal itself (prevents noisy velocity)
#
# TUNING GUIDE:
#   fc_min=0.5, beta=0.007 → very smooth cursor, slight lag on fast moves
#   fc_min=1.0, beta=0.01  → balanced, good starting point
#   fc_min=2.0, beta=0.02  → responsive, more jitter when still
#   beta is the most important knob: raise it if cursor feels sluggish on fast moves

import math


class OneEuroFilter:
    def __init__(self, freq=30.0, fc_min=1.0, beta=0.01, fc_d=1.0):
        """
        freq   : expected sample rate (frames per second)
        fc_min : minimum cutoff frequency (Hz) — controls smoothing at rest
        beta   : speed coefficient — higher = less lag during fast motion
        fc_d   : cutoff for derivative (velocity) signal
        """
        self._freq  = freq
        self._fc_min = fc_min
        self._beta  = beta
        self._fc_d  = fc_d

        # Internal state — one filter for the signal, one for its derivative
        self._x_prev    = None    # last filtered position
        self._dx_prev   = 0.0    # last filtered velocity
        self._initialized = False

    def _alpha(self, cutoff):
        """Compute the EMA alpha from a cutoff frequency."""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te  = 1.0 / self._freq
        return 1.0 / (1.0 + tau / te)

    def filter(self, x):
        """
        Feed a new measurement x, get back the filtered value.
        x can be a float (1D) — use two separate filters for x and y.
        """
        if not self._initialized:
            self._x_prev = x
            self._initialized = True
            return x

        # Step 1: filter the derivative (velocity) with a fixed cutoff.
        dx   = (x - self._x_prev) * self._freq
        a_d  = self._alpha(self._fc_d)
        dx_f = a_d * dx + (1 - a_d) * self._dx_prev

        # Step 2: compute adaptive cutoff from filtered velocity magnitude.
        cutoff = self._fc_min + self._beta * abs(dx_f)

        # Step 3: filter the position signal with the adaptive cutoff.
        a     = self._alpha(cutoff)
        x_f   = a * x + (1 - a) * self._x_prev

        # Update state for next frame.
        self._x_prev  = x_f
        self._dx_prev = dx_f

        return x_f

    def reset(self):
        """Call when signal is lost (hand leaves frame) to clear state."""
        self._x_prev     = None
        self._dx_prev    = 0.0
        self._initialized = False


class OneEuroCursor:
    """Convenience wrapper: one filter for X, one for Y."""
    def __init__(self, freq=30.0, fc_min=1.0, beta=0.01):
        self._fx = OneEuroFilter(freq=freq, fc_min=fc_min, beta=beta)
        self._fy = OneEuroFilter(freq=freq, fc_min=fc_min, beta=beta)

    def filter(self, x, y):
        """Returns (filtered_x, filtered_y) as floats."""
        return self._fx.filter(float(x)), self._fy.filter(float(y))

    def reset(self):
        self._fx.reset()
        self._fy.reset()
