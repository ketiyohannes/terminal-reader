# terminal-reader

Read PDF files inside your terminal.

## Install

```bash
pip install .
```

Or install it as an isolated tool straight from this folder:

```bash
uv tool install .
```

## Usage

```bash
tread document.pdf
```

| Key                  | Action          |
| -------------------- | --------------- |
| `j` / `k` / arrows   | Scroll          |
| `n` / `space` / `→`  | Next page       |
| `p` / `b` / `←`      | Previous page   |
| `g` / `G`            | First/last page |
| `:`                  | Go to page      |
| `q` / `Esc`          | Quit            |

Print the text instead of opening the viewer (also used automatically when piping):

```bash
tread document.pdf --plain | less
```
