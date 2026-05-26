# ascii_mapper.py
# Responsibility: convert a 2D grayscale pixel array into rows of ASCII characters.

import numpy as np
from config import ASCII_CHARS


# ── Lookup table ────────────────────────────────────────────────────────────
# Built once at import time. Maps every possible brightness value (0–255)
# directly to a character from ASCII_CHARS.
# At runtime we index into this table with the entire pixel array in one
# vectorised NumPy operation — no Python loop over individual pixels.
_CHAR_LOOKUP = np.array(
    [ASCII_CHARS[int(v * (len(ASCII_CHARS) - 1) / 255)] for v in range(256)],
    dtype='U1'   # U1 = Unicode string, one character per element
)


def pixels_to_ascii(gray_resized):
    """
    Converts a (H, W) uint8 array to a list of strings, one per row.

    Steps:
        1. _CHAR_LOOKUP[gray_resized]  — fancy-index the lookup table
                                          with the whole pixel grid at once.
           Result shape: (H, W), each cell is now a character.
        2. ''.join(row)               — concatenate each row into a string.

    Returns:
        list[str]  — length H, each string length W.
    """
    char_grid = _CHAR_LOOKUP[gray_resized]
    return [''.join(row) for row in char_grid]
