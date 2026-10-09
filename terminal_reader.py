"""tread - a minimal PDF reader for the terminal."""

import argparse
import curses
import os
import sys
import textwrap

import pymupdf

HELP = "j/k scroll  n/p page  g/G first/last  : go to page  q quit"


def load_pages(path):
    """Extract the plain text of every page in the PDF."""
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


def wrap(text, width):
    """Wrap page text to the terminal width, keeping blank lines."""
    lines = []
    for line in text.splitlines():
        lines.extend(textwrap.wrap(line, width) or [""])
    return lines


def prompt(screen, label):
    """Read a line of input on the bottom row."""
    height, width = screen.getmaxyx()
    screen.move(height - 1, 0)
    screen.clrtoeol()
    screen.addstr(height - 1, 0, label[: width - 1])
    curses.echo()
    curses.curs_set(1)
    try:
        return screen.getstr(height - 1, len(label), 10).decode()
    finally:
        curses.noecho()
        curses.curs_set(0)


def run(screen, pages, title):
    curses.curs_set(0)
    page, top = 0, 0

    while True:
        height, width = screen.getmaxyx()
        body_height = max(height - 1, 1)
        lines = wrap(pages[page], max(width - 1, 1))
        max_top = max(len(lines) - body_height, 0)
        top = min(top, max_top)

        screen.erase()
        for row, line in enumerate(lines[top : top + body_height]):
            screen.addnstr(row, 0, line, width - 1)
        status = f" page {page + 1}/{len(pages)}  {title}  |  {HELP} "
        screen.addnstr(height - 1, 0, status.ljust(width - 1), width - 1, curses.A_REVERSE)
        screen.refresh()

        key = screen.getch()
        if key in (ord("q"), 27):
            return
        elif key in (ord("j"), curses.KEY_DOWN):
            top = min(top + 1, max_top)
        elif key in (ord("k"), curses.KEY_UP):
            top = max(top - 1, 0)
        elif key in (ord("n"), ord(" "), curses.KEY_RIGHT, curses.KEY_NPAGE):
            if page < len(pages) - 1:
                page, top = page + 1, 0
        elif key in (ord("p"), ord("b"), curses.KEY_LEFT, curses.KEY_PPAGE):
            if page > 0:
                page, top = page - 1, 0
        elif key == ord("g"):
            page, top = 0, 0
        elif key == ord("G"):
            page, top = len(pages) - 1, 0
        elif key == ord(":"):
            answer = prompt(screen, "Go to page: ")
            if answer.isdigit() and 1 <= int(answer) <= len(pages):
                page, top = int(answer) - 1, 0


def main():
    parser = argparse.ArgumentParser(prog="tread", description="Read a PDF in the terminal.")
    parser.add_argument("file", help="path to a PDF file")
    parser.add_argument("--plain", action="store_true", help="print text to stdout instead of opening the viewer")
    args = parser.parse_args()

    try:
        pages = load_pages(args.file)
    except Exception as error:
        sys.exit(f"tread: cannot open {args.file}: {error}")

    if not pages:
        sys.exit("tread: the PDF has no pages")

    if args.plain or not sys.stdout.isatty():
        for number, text in enumerate(pages, 1):
            print(f"--- page {number} ---\n{text}")
        return

    curses.wrapper(run, pages, os.path.basename(args.file))


if __name__ == "__main__":
    main()
