"""tread - read PDF files in the terminal.

Pages are drawn as images on terminals that support inline graphics
(Ghostty, kitty, WezTerm, iTerm2). Other terminals get reflowed text.
"""

import argparse
import base64
import fcntl
import math
import os
import select
import struct
import sys
import termios
import textwrap
import tty
from collections import Counter

import pymupdf

HELP = "n/p page  j/k scroll  w fit width  d dark  : go to  q quit"
BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"
TEXT_WIDTH = 80

KEYS = {
    "\x1b[A": "up", "k": "up",
    "\x1b[B": "down", "j": "down",
    "\x1b[C": "next", "n": "next", " ": "next", "\x1b[6~": "next",
    "\x1b[D": "prev", "p": "prev", "b": "prev", "\x1b[5~": "prev",
    "g": "first", "G": "last", "w": "fit", "d": "dark", ":": "goto",
    "q": "quit", "\x1b": "quit",
}


def write(text):
    sys.stdout.write(text)


def terminal_size():
    """Return (columns, rows, pixel_width, pixel_height) of the terminal."""
    packed = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
    rows, cols, width, height = struct.unpack("HHHH", packed)
    return cols, rows, width, height


def graphics_protocol():
    """Guess which inline image protocol the terminal speaks, if any."""
    term = os.environ.get("TERM", "")
    program = os.environ.get("TERM_PROGRAM", "")
    if "kitty" in term or "ghostty" in term or program in ("ghostty", "WezTerm"):
        return "kitty"
    if "KITTY_WINDOW_ID" in os.environ:
        return "kitty"
    if program == "iTerm.app":
        return "iterm"
    return None


# --- Text layout ---------------------------------------------------------


def page_lines(page, width, styled=True):
    """Lay out a page as reflowed paragraphs; larger text becomes bold headings."""
    blocks = page.get_text("dict", sort=True)["blocks"]
    sizes = [
        round(span["size"])
        for block in blocks
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["text"].strip()
    ]
    if not sizes:
        return ["(no text on this page)"]
    body_size = Counter(sizes).most_common(1)[0][0]

    lines = []
    for block in blocks:
        if block["type"] == 1:
            lines += [f"{DIM}[image]{RESET}" if styled else "[image]", ""]
            continue

        paragraph, largest = "", 0
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            largest = max([largest] + [s["size"] for s in line["spans"] if s["text"].strip()])
            if not text:
                continue
            # Join words hyphenated across a line break.
            if paragraph.endswith("-") and text[:1].islower():
                paragraph = paragraph[:-1] + text
            else:
                paragraph = f"{paragraph} {text}".strip()
        if not paragraph:
            continue

        heading = styled and largest > body_size * 1.15
        for row in textwrap.wrap(paragraph, width):
            lines.append(f"{BOLD}{row}{RESET}" if heading else row)
        lines.append("")
    return lines


# --- Drawing ---------------------------------------------------------------


def draw_image(page, protocol, cols, rows, px_width, px_height, scroll, fit_width, dark):
    """Draw the page as an image. Returns (scroll, max_scroll, scroll_step)."""
    cell_w, cell_h = px_width / cols, px_height / rows
    box_w, box_h = px_width - 2, (rows - 1) * cell_h - 2
    rect = page.rect

    if fit_width:
        zoom = box_w / rect.width
        visible = box_h / zoom
        max_scroll = max(rect.height - visible, 0)
        scroll = min(max(scroll, 0), max_scroll)
        clip = pymupdf.Rect(rect.x0, rect.y0 + scroll, rect.x1, rect.y0 + scroll + visible) & rect
        step = visible / 4
    else:
        zoom = min(box_w / rect.width, box_h / rect.height)
        clip, scroll, max_scroll, step = rect, 0, 0, 0

    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    if dark:
        pixmap.invert_irect()
    data = base64.standard_b64encode(pixmap.tobytes("png")).decode()

    width_cells = math.ceil(pixmap.width / cell_w)
    height_cells = math.ceil(pixmap.height / cell_h)
    write(f"\x1b[1;{max((cols - width_cells) // 2, 0) + 1}H")

    if protocol == "kitty":
        chunks = [data[i : i + 4096] for i in range(0, len(data), 4096)]
        for i, chunk in enumerate(chunks):
            header = "a=T,f=100,q=2,C=1," if i == 0 else ""
            write(f"\x1b_G{header}m={int(i < len(chunks) - 1)};{chunk}\x1b\\")
    else:
        write(
            f"\x1b]1337;File=inline=1;width={width_cells};height={height_cells};"
            f"preserveAspectRatio=1:{data}\a"
        )
    return scroll, max_scroll, step


def draw_text(page, cols, rows, scroll):
    """Draw the page as reflowed text. Returns (scroll, max_scroll, scroll_step)."""
    width = min(cols - 4, TEXT_WIDTH)
    left = (cols - width) // 2 + 1
    lines = page_lines(page, width)
    body = rows - 1
    max_scroll = max(len(lines) - body + 1, 0)
    scroll = min(max(scroll, 0), max_scroll)

    for row, line in enumerate(lines[scroll : scroll + body - 1], start=2):
        write(f"\x1b[{row};{left}H{line}")
    return scroll, max_scroll, 1


def draw_status(cols, rows, title, page_no, page_count, fit_width):
    left = f" {title}  page {page_no + 1}/{page_count}{'  [fit width]' if fit_width else ''} "
    right = f" {HELP} "
    gap = cols - len(left) - len(right)
    bar = left + " " * gap + right if gap > 0 else left.ljust(cols)
    write(f"\x1b[{rows};1H\x1b[7m{bar[:cols]}{RESET}")


# --- Main loop -------------------------------------------------------------


def read_key(fd, timeout):
    if not select.select([fd], [], [], timeout)[0]:
        return None
    return KEYS.get(os.read(fd, 32).decode(errors="ignore"))


def prompt(fd, old_settings, rows, label):
    """Read a line of input on the status row using normal terminal settings."""
    write(f"\x1b[{rows};1H\x1b[2K{label}\x1b[?25h")
    sys.stdout.flush()
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    try:
        return sys.stdin.readline().strip()
    finally:
        tty.setcbreak(fd)
        write("\x1b[?25l")


def view(doc, title):
    protocol = graphics_protocol()
    page_no, scroll, fit_width, dark = 0, 0, False, False
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    write("\x1b[?1049h\x1b[?25l")  # Alternate screen, hidden cursor.
    tty.setcbreak(fd)
    try:
        size, dirty = None, True
        while True:
            if dirty or terminal_size() != size:
                size = terminal_size()
                cols, rows, px_width, px_height = size
                write("\x1b[2J")
                if protocol == "kitty":
                    write("\x1b_Ga=d,q=2\x1b\\")
                page = doc[page_no]
                if protocol and px_width and px_height:
                    scroll, max_scroll, step = draw_image(
                        page, protocol, cols, rows, px_width, px_height, scroll, fit_width, dark
                    )
                else:
                    scroll, max_scroll, step = draw_text(page, cols, rows, scroll)
                draw_status(cols, rows, title, page_no, len(doc), fit_width)
                sys.stdout.flush()
                dirty = False

            action = read_key(fd, 0.25)
            if action is None:
                continue
            dirty = True
            last = len(doc) - 1

            if action == "quit":
                return
            elif action == "down":
                if scroll < max_scroll:
                    scroll += step
                elif page_no < last:
                    page_no, scroll = page_no + 1, 0
            elif action == "up":
                if scroll > 0:
                    scroll -= step
                elif page_no > 0:
                    page_no, scroll = page_no - 1, math.inf
            elif action == "next" and page_no < last:
                page_no, scroll = page_no + 1, 0
            elif action == "prev" and page_no > 0:
                page_no, scroll = page_no - 1, 0
            elif action == "first":
                page_no, scroll = 0, 0
            elif action == "last":
                page_no, scroll = last, 0
            elif action == "fit":
                fit_width, scroll = not fit_width, 0
            elif action == "dark":
                dark = not dark
            elif action == "goto":
                answer = prompt(fd, old_settings, rows, "Go to page: ")
                if answer.isdigit() and 1 <= int(answer) <= len(doc):
                    page_no, scroll = int(answer) - 1, 0
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if protocol == "kitty":
            write("\x1b_Ga=d,q=2\x1b\\")
        write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(prog="tread", description="Read a PDF in the terminal.")
    parser.add_argument("file", help="path to a PDF file")
    parser.add_argument("--plain", action="store_true", help="print the text instead of opening the viewer")
    args = parser.parse_args()

    try:
        doc = pymupdf.open(args.file)
    except Exception as error:
        sys.exit(f"tread: cannot open {args.file}: {error}")
    if len(doc) == 0:
        sys.exit("tread: the PDF has no pages")

    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if args.plain or not interactive:
        for number, page in enumerate(doc, 1):
            print(f"--- page {number} ---\n")
            print("\n".join(page_lines(page, TEXT_WIDTH, styled=sys.stdout.isatty())))
        return

    try:
        view(doc, os.path.basename(args.file))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
