# terminal-reader

Read PDF files inside your terminal.

On terminals with inline image support (Ghostty, kitty, WezTerm, iTerm2) pages are
rendered exactly as they look in a PDF reader. Other terminals show cleanly
reflowed text with bold headings.

## Install

```bash
pip install git+https://github.com/ketiyohannes/terminal-reader.git
```

## Usage

```bash
tread document.pdf
```

| Key                       | Action                       |
| ------------------------- | ---------------------------- |
| `n` / `space` / `→`       | Next page                    |
| `p` / `b` / `←`           | Previous page                |
| `j` / `k` / `↓` / `↑`     | Scroll (continues to next page) |
| `w`                       | Toggle fit page / fit width  |
| `d`                       | Toggle dark mode             |
| `g` / `G`                 | First / last page            |
| `:`                       | Go to page                   |
| `q` / `Esc`               | Quit                         |

Print the text instead of opening the viewer (also used automatically when piping):

```bash
tread document.pdf --plain | less
```

Note: images do not work inside tmux; the text view is used there.
