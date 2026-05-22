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

## Debug (Python)

`jet` includes a Python debugger sidebar.

- Cycle to the **Debug** sidebar with `Ctrl+B`.
- `Option+click` a line in the editor to toggle a breakpoint.
- Press **▶ Run** to start. The active file is launched inside an external terminal app (default: LiquidTerminal.app) where you can see prints and type into `input()`.
- The sidebar shows local + global variables when paused.
- Buttons: **⏵ Continue**, **↷ Step over**, **↘ Step into**, **↖ Step out**, **■ Stop**.
- The current execution line is highlighted in the gutter (▶ when line numbers are off, otherwise the line number is recolored).

### Changing the external terminal

Open the Settings sidebar (`Ctrl+B` once from the tree). The **Debug terminal command** field accepts any shell template containing `{cmd}`. Examples:

- macOS Terminal.app: `osascript -e 'tell application "Terminal" to do script "{cmd}"'`
- iTerm2: `osascript -e 'tell application "iTerm" to create window with default profile command "{cmd}"'`
- Linux (GNOME): `gnome-terminal -- bash -c "{cmd}; read"`

## Why

Nano is fine. VSCode is heavy. `jet` is the middle ground when you live in the terminal.
