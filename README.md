# jet

Fast TUI text editor for the terminal — mouse, file tree, syntax highlighting, auto-indent, auto-close brackets. Python-first.

## Install

```bash
pipx install .
jet path/to/file.py
jet .   # open project at current directory
```

## Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+S` | Save |
| `Ctrl+W` | Close buffer |
| `Ctrl+Q` | Quit |
| `Ctrl+B` | Toggle sidebar |
| `Ctrl+P` | Fuzzy file finder |
| `Ctrl+F` | Find |
| `Ctrl+H` | Replace |
| `Ctrl+G` | Goto line |
| `Ctrl+Tab` | Next buffer |
| `Cmd+C` / `Cmd+V` / `Cmd+X` | Handled by your terminal (iTerm2/Terminal.app, LiquidTerminal) against the system clipboard |

## Design

Minimalist, transparent UI. Thin white separators, no filled panels, lots of empty space — built to sit on top of a translucent terminal like LiquidTerminal. Only code tokens carry color. No footer hint bar; status line is a single muted strip.

## Why

Nano is fine. VSCode is heavy. `jet` is the middle ground when you live in the terminal.
