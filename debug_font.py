# debug_font.py
# Run this once to measure the actual pixel size of one character
# at your chosen font and scale. Update CELL_W / CELL_H in config.py
# with the values printed here.
#
# Usage:  python debug_font.py

import cv2
from config import FONT, FONT_SCALE, FONT_THICKNESS

# getTextSize returns ((width, height), baseline)
(w, h), baseline = cv2.getTextSize("A", FONT, FONT_SCALE, FONT_THICKNESS)

print(f"Character size at FONT_SCALE={FONT_SCALE}:")
print(f"  Width    : {w}  px  → set CELL_W = {w} in config.py")
print(f"  Height   : {h}  px")
print(f"  Baseline : {baseline} px")
print(f"  CELL_H   : {h + baseline + 1}  → set CELL_H = {h + baseline + 1} in config.py")
print()
print("If characters overlap vertically, increase CELL_H by 1 or 2.")
print("If there are gaps between rows, decrease CELL_H by 1.")
