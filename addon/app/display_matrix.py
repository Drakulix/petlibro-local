"""Generate DISPLAY_MATRIX_SERVICE payloads for the OneRFID feeder LED display.

Display encoding (from proxy log analysis):
- 5 rows, each row is an integer bitmask
- bit 0 = rightmost column of the display
- content scrolls left: bit N in frame F moves to bit N+1 in frame F+1
- new content enters from the right (bit 0) each frame
- DISPLAY_WIDTH = 26 (max observed bitmask fits in 26 bits)
"""

DISPLAY_WIDTH = 26

# 3-pixel-wide, 5-row-tall font.
# Row values: bit 0 = leftmost pixel of character, bit 2 = rightmost.
# Characters are appended to the pixel strip left-col-first so they scroll in
# correctly (leftmost col enters the display first, from the right edge).
FONT: dict[str, list[int]] = {
    ' ': [0, 0, 0, 0, 0],
    'A': [2, 5, 7, 5, 5],   #  # / # # / ### / # # / # #
    'B': [3, 5, 3, 5, 3],   # ##  / # # / ##  / # # / ##
    'C': [6, 1, 1, 1, 6],   #  ## / #   / #   / #   /  ##
    'D': [3, 5, 5, 5, 3],   # ##  / # # / # # / # # / ##
    'E': [7, 1, 3, 1, 7],   # ### / #   / ##  / #   / ###
    'F': [7, 1, 3, 1, 1],   # ### / #   / ##  / #   / #
    'G': [6, 1, 5, 5, 6],   #  ## / #   / # # / # # /  ##
    'H': [5, 5, 7, 5, 5],   # # # / # # / ### / # # / # #
    'I': [7, 2, 2, 2, 7],   # ### /  #  /  #  /  #  / ###
    'J': [4, 4, 4, 5, 2],   #   # /   # /   # / # # /  #
    'K': [5, 3, 1, 3, 5],   # # # / ##  / #   / ##  / # #
    'L': [1, 1, 1, 1, 7],   # #   / #   / #   / #   / ###
    'M': [5, 7, 5, 5, 5],   # # # / ### / # # / # # / # #
    'N': [5, 7, 7, 5, 5],   # # # / ### / ### / # # / # #
    'O': [2, 5, 5, 5, 2],   #  #  / # # / # # / # # /  #
    'P': [3, 5, 3, 1, 1],   # ##  / # # / ##  / #   / #
    'Q': [2, 5, 5, 3, 6],   #  #  / # # / # # / ##  /  ##
    'R': [3, 5, 3, 5, 5],   # ##  / # # / ##  / # # / # #
    'S': [6, 1, 2, 4, 3],   #  ## / #   /  #  /   # / ##
    'T': [7, 2, 2, 2, 2],   # ### /  #  /  #  /  #  /  #
    'U': [5, 5, 5, 5, 2],   # # # / # # / # # / # # /  #
    'V': [5, 5, 5, 2, 2],   # # # / # # / # # /  #  /  #
    'W': [5, 5, 7, 5, 5],   # # # / # # / ### / # # / # #
    'X': [5, 5, 2, 5, 5],   # # # / # # /  #  / # # / # #
    'Y': [5, 5, 2, 2, 2],   # # # / # # /  #  /  #  /  #
    'Z': [7, 4, 2, 1, 7],   # ### /   # /  #  / #   / ###
    '0': [2, 5, 5, 5, 2],   #  #  / # # / # # / # # /  #
    '1': [2, 3, 2, 2, 7],   #  #  / ##  /  #  /  #  / ###
    '2': [3, 4, 6, 1, 7],   # ##  /   # /  ## / #   / ###
    '3': [3, 4, 6, 4, 3],   # ##  /   # / ##  /   # / ##
    '4': [5, 5, 7, 4, 4],   # # # / # # / ### /   # /   #
    '5': [7, 1, 3, 4, 3],   # ### / #   / ##  /   # / ##
    '6': [2, 1, 3, 5, 2],   #  #  / #   / ##  / # # /  #
    '7': [7, 4, 2, 2, 2],   # ### /   # /  #  /  #  /  #
    '8': [2, 5, 2, 5, 2],   #  #  / # # /  #  / # # /  #
    '9': [2, 5, 6, 4, 2],   #  #  / # # /  ## /   # /  #
}

# Built-in icon bitmaps — captured via proxy, format [0, r1..r5, 0].
ICON_FRAMES: dict[int, list[int]] = {
    5: [0, 55296,  130048, 130048, 130048, 63488,  28672,  8192],   # Heart
    6: [0, 16384,  245760, 246016, 32256,  32256,  16896,  50688],  # Dog
    7: [0, 69632,  126976, 86016,  58368,  17408,  62464,  130048], # Cat
    8: [0, 540672, 1032192,196608, 522240, 260096, 174080, 174080], # Elk
}

_CHAR_WIDTH = 3   # visible pixel columns per character
_LOOP_GAP   = 4   # extra blank columns added after last char before the loop restarts
                   # (1px inter-char gap is already present, so total loop gap = 5px,
                   # matching the visual spacing of a space character between words)


def _build_strips(text: str) -> list[list[int]]:
    """Build per-row pixel lists from text.

    Each strip entry is 0 or 1.  Characters are appended left-column-first so
    column 0 (leftmost) enters the display window first (from the right edge).
    A _LOOP_GAP of extra blank columns follows the last character so the circular
    scroll has a visible pause between repetitions of the text.
    """
    strips: list[list[int]] = [[] for _ in range(5)]
    for ch in text:
        glyph = FONT.get(ch, FONT[' '])
        for r in range(5):
            row_val = glyph[r]
            for col in range(_CHAR_WIDTH):
                strips[r].append((row_val >> col) & 1)
            strips[r].append(0)  # inter-character gap
    for r in range(5):
        strips[r].extend([0] * _LOOP_GAP)  # loop gap before restart
    return strips


def text_to_frames(text: str) -> list[list[int]]:
    """Return frames for the given text string.

    Each frame is [0, r1, r2, r3, r4, r5, 0] matching DISPLAY_MATRIX_SERVICE.

    Short text (fits within DISPLAY_WIDTH): one centered static frame.
    Longer text: one full loop cycle using circular (modular) strip indexing so
    the animation loops seamlessly with no blank gap between repetitions.
    Pair scrolling frames with loopDisplay=true on the feeder.
    """
    if not text:
        return []
    text = text.upper()
    char_pixel_width = len(text) * (_CHAR_WIDTH + 1)  # text pixels only (no loop gap)
    strips = _build_strips(text)
    n = len(strips[0])  # total strip length including loop gap

    if char_pixel_width <= DISPLAY_WIDTH:
        # ── Static centered frame ─────────────────────────────────────────────
        # Build the frame as if text is fully entered and right-justified
        # (frame index = n-1), then shift left to center in the display.
        margin = (DISPLAY_WIDTH - char_pixel_width) // 2
        row_vals: list[int] = []
        for r in range(5):
            val = 0
            for col in range(char_pixel_width):
                pos = (n - _LOOP_GAP - 1) - col  # skip loop gap; start at last char column
                if 0 <= pos < n:
                    val |= strips[r][pos] << col
            row_vals.append(val << margin)
        return [[0] + row_vals + [0]]

    # ── Circular scrolling frames ─────────────────────────────────────────────
    # Circular indexing makes the loop seamless: as the last pixel of the text
    # exits the left edge, the first pixel immediately re-enters the right edge.
    frames: list[list[int]] = []
    for i in range(n):
        row_vals = []
        for r in range(5):
            val = 0
            for col in range(DISPLAY_WIDTH):
                pos = (i - col) % n  # wrap around the strip
                val |= strips[r][pos] << col
            row_vals.append(val)
        frames.append([0] + row_vals + [0])
    return frames
