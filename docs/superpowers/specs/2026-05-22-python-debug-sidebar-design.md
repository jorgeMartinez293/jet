# Python Debug Sidebar — Design

Date: 2026-05-22
Status: Approved (pending user review of written spec)

## Goal

Add a Python debug sidebar to the `jet` TUI editor. The sidebar lets the user run the currently active Python file under a debugger that supports breakpoints, full stepping (continue, step over, step into, step out), stop, and live inspection of local and global variables. Program stdout/stderr/stdin happen in an external terminal window (default: LiquidTerminal.app, configurable). Breakpoints are toggled by Option+click on a line while the debug sidebar is the active sidebar. Currently-executing lines are highlighted in the editor gutter using theme accent colors (or marker characters when line numbers are off).

## Non-Goals

- Remote debugging or attaching to running processes.
- Languages other than Python.
- Watch expressions, conditional breakpoints, exception filters.
- Step navigation through external library code by default (stays in user code; library frames still appear in stack but are not auto-stepped into).
- Persisting breakpoints across editor sessions (in-memory only for MVP).

## Architecture

Two processes, communicating over a UNIX domain socket. The debug runner does NOT inherit the editor's stdio; instead the runner is launched **inside the external terminal app**, so it inherits that terminal's tty for stdin/stdout/stderr. `input()`, `print()`, and tracebacks all work through the user's external terminal naturally.

```
┌────────────────────────┐                    ┌────────────────────────┐
│ jet editor (parent)    │   JSON-lines       │ python -m jet.debug    │
│ DebugPanel + Editor    │◄──────socket──────►│   .runner <target>     │
│                        │                    │   (JetDebugger : bdb)  │
└──────┬─────────────────┘                    └──────────┬─────────────┘
       │                                                 │
       │ launches via osascript                          │ tty = external
       │                                                 │       terminal
       ▼                                                 ▼
┌────────────────────────┐                    ┌────────────────────────┐
│ external terminal app  │  runs command  →   │ user sees prints,      │
│ (LiquidTerminal.app)   │                    │ types into input(),    │
│                        │                    │ sees tracebacks        │
└────────────────────────┘                    └────────────────────────┘
```

### Why two processes

- Editor stays responsive; debugged code cannot block the TUI event loop.
- User-program stdio is isolated from the editor's TUI.
- A crash in user code does not crash the editor.

### Why runner runs inside the external terminal

The user explicitly wants program output in a separate terminal window, and must be able to type inputs there. If the runner ran as a child of the editor with output piped to a log file the user `tail -f`s, stdin would not work (`tail` has no way to forward keystrokes to the runner). By having the terminal app launch the runner directly, the runner inherits the terminal's PTY: stdin, stdout and stderr all behave normally without any PTY plumbing on our side.

Control (breakpoints, step commands, paused/variable events) flows over a **separate** UNIX socket between the editor and the runner. This is independent from the tty, so control messages do not pollute the user-visible output.

## Components

```
jet/
  app.py                 # register DebugPanel in sidebar cycle
  debug/
    __init__.py
    panel.py             # DebugPanel widget (sidebar)
    controller.py        # DebugController (lifecycle, socket, state)
    protocol.py          # message dataclasses + JSON codec
    runner.py            # JetDebugger (bdb.Bdb subclass) + entrypoint
    terminal.py          # external-terminal spawning
  editor.py              # gutter rendering: breakpoint + current-line markers
  settings_panel.py      # add EditorConfig.debug_terminal_command
```

### `protocol.py`

Pure data; no I/O. Defines message dataclasses (see "Protocol" section) and `encode(msg) -> bytes` / `decode(line: bytes) -> Message`. JSON-lines (one JSON object per `\n`-delimited line).

### `runner.py`

Entrypoint: `python -m jet.debug.runner <target_path> <socket_path>`.

- Connects to the editor's listening socket.
- Sends `Ready`.
- Receives initial `SetBreakpoints`.
- Runs the target with `runpy.run_path(target_path, run_name="__main__")` inside an instance of `JetDebugger(bdb.Bdb)`.
- In `user_line(frame)`: if line is a breakpoint or the runner is in a step state, build a `Paused` message with file/line, locals dict, module globals dict, and stack frames; send; block reading the next command from the socket.
- Supported commands: `set_breakpoints`, `continue`, `step_over`, `step_into`, `step_out`, `stop`, `get_frame_vars` (for stack frame navigation).
- On unhandled exception: send `Exception(exc_type, exc_value, traceback_str, file, line)` then `Exited(code=1)`.
- On normal completion: send `Exited(code=0)`.
- After `Exited`, prints `"\n[Debug session ended — press Enter to close]"` and calls `input()`, so the external terminal window stays open until the user dismisses it.

### `controller.py`

`DebugController` owns:
- `state: Literal["idle","starting","running","paused","exited","error"]`
- `breakpoints: dict[Path, set[int]]`
- `current_paused: Paused | None`
- `socket: asyncio.StreamReader/Writer` to the runner
- `runner_proc_token: str` (the socket path acts as the identity; we do NOT have a direct child PID)

Lifecycle:
1. `start(file: Path, buffer_text: str | None)`:
   - If `buffer_text` provided (unsaved or untitled), write to a `tempfile.NamedTemporaryFile(suffix=".py", delete=False)`; remember temp path for cleanup.
   - Pick a unique socket path: `/tmp/jet-debug-<uuid4>.sock`.
   - Open `asyncio` UNIX server, accept one connection.
   - Call `terminal.spawn(cmd_template, runner_argv)`.
   - Await connection within 5 s timeout. On timeout → `error`, notify, cleanup.
   - Read `Ready`. Send `SetBreakpoints` for all known BPs.
   - Send `Continue` to start execution.
   - Transition to `running`.
2. On `Paused` → state `paused`, store payload, post Textual `Paused` message → panel + editor update.
3. On `Exited` / `Exception` → state `exited`, close socket, cleanup temp file. Terminal window remains open (user closes it).
4. `stop()` → send `Stop`, await `Exited` for up to 1 s; if no response, close socket forcibly. Editor leaves read-only mode.
5. `set_breakpoint(file, line, on: bool)`:
   - Update local `breakpoints`.
   - If running/paused, send `SetBreakpoints` for that file (full set).
6. `step_over / step_into / step_out / continue_()`:
   - Only valid when `state == "paused"`. Send corresponding command, transition to `running`.

### `panel.py`

`DebugPanel(Widget)` mirrors `SettingsPanel` style (same width, transparent bg, border-right). Compose:

```
🐞 Debug
[ ▶ Run ]  [ ■ Stop ]
[ ⏵ Continue ]  [ ↷ Step over ]  [ ↘ Step into ]  [ ↖ Step out ]

Status: idle | running | paused (file.py:42) | exited (0)

Locals  (collapsible)
  name    repr
  ...

Globals  (collapsible)
  ...

Breakpoints  (collapsible)
  file.py:12
  file.py:30
```

Buttons that are not valid for the current state are disabled (e.g., `Continue` only enabled when `paused`).

`Locals`/`Globals` rendered with `DataTable` (two columns: name, repr). Globals filter out `__dunder__` names and `ModuleType` values.

The panel does not own state; it reads from `DebugController` and listens for controller-emitted Textual `Message`s (`StateChanged`, `PausedAt`, `ExitedWith`, `ExceptionRaised`). Button presses call methods on the controller.

### `editor.py` — gutter rendering

Subclass updates:
- Add `breakpoints: reactive[frozenset[int]]` and `current_exec_line: reactive[int | None]`.
- Subscribe to controller events via the parent app (no direct coupling: editor receives `set_breakpoints(set)` / `set_current_line(line | None)` calls from the controller when the active file matches).
- Gutter rendering: override `render_line` (or the internal gutter strip method, whichever Textual exposes at the pinned version). Two rules:
  1. If line number `N+1` is in `breakpoints`: render the line-number digits with `Style(color=theme.error)`. If `show_line_numbers=False`: render `●` glyph in a minimum-width gutter (2 cells), same color.
  2. If `current_exec_line == N+1`: render the line-number digits with `Style(color=theme.warning, bold=True)`. If `show_line_numbers=False`: render `▶`.
  3. Both conditions together (BP on current line): warning color wins for the digit, but a `●` is prepended in the gutter margin.
- Mouse handler: `_on_click(event)` — if `event.meta` (Option on macOS, treated as the mac terminal's `meta` flag) AND the debug sidebar is the active sidebar AND the file has a path, toggle BP at the clicked line via `app.debug_controller.set_breakpoint(self.path, line, on=not present)`.

Fallback for environments where Textual does not surface Option-as-meta: `Ctrl+B` while the cursor is in the editor and the debug sidebar is active toggles BP on the cursor line. This is documented in README.

When the debugger is `paused`, the editor enters read-only (`self.read_only = True`) so the user cannot edit code that no longer matches what the runner is executing. On `exited`/`stop`, read-only is cleared.

### `terminal.py`

```python
def spawn(cmd_template: str, runner_argv: list[str]) -> None:
    """
    cmd_template uses Python str-format with key {cmd}, which is replaced by
    a properly-shell-quoted version of:
        python -m jet.debug.runner <target> <socket>
    """
```

Default template (in `EditorConfig.debug_terminal_command`):
```
osascript -e 'tell application "LiquidTerminal" to do script "{cmd}"'
```

The user can change this in the Settings sidebar (free-text input). Examples documented:
- macOS Terminal.app: `osascript -e 'tell application "Terminal" to do script "{cmd}"'`
- iTerm2: `osascript -e 'tell application "iTerm" to create window with default profile command "{cmd}"'`
- Linux: `gnome-terminal -- bash -c "{cmd}; read"`

Spawn shells out with `subprocess.Popen(template.format(cmd=shlex.quote(joined)), shell=True)`. Errors → `controller.error("Could not spawn terminal: …")`.

## Protocol (JSON-lines over UNIX socket)

All messages: `{"type": "<name>", ...fields}\n`.

Editor → Runner:
- `set_breakpoints` — `{file: str, lines: [int, ...]}`
- `continue`
- `step_over`
- `step_into`
- `step_out`
- `stop`
- `get_frame_vars` — `{index: int}` (NOT in MVP; reserved for a later stack-navigation feature)

Runner → Editor:
- `ready`
- `paused` — `{file: str, line: int, locals: {name: repr}, globals: {name: repr}, stack: [{file, line, func}, ...]}`
- `exception` — `{file: str, line: int, exc_type: str, exc_value: str, traceback: str}`
- `exited` — `{code: int}`

Variable repr: built with `reprlib.Repr` configured `maxstring=80`, `maxother=80`, `maxlist=maxtuple=maxdict=6`. Globals dict is filtered to drop:
- keys starting with `__` (except keep `__name__` and `__file__` if present),
- values whose type is `types.ModuleType`,
- values whose type is `type` and live in `builtins` (avoid dumping every builtin name).

## Flow

1. User pulses **Run** in DebugPanel.
2. Controller: pick active editor; gather text + path. If unsaved or untitled, write a temp `.py` file.
3. Controller: bind socket, spawn external terminal running the runner.
4. Runner connects → sends `Ready`.
5. Controller sends `SetBreakpoints` then `Continue`.
6. Runner steps through user code; on a BP line or after a step command, sends `Paused`.
7. Editor sidebar shows variables; editor highlights current line; editor goes read-only.
8. User clicks `Continue` / `Step over` / etc. → command sent; runner resumes; state → `running`.
9. Program ends → `Exited`; editor leaves read-only; sidebar shows `exited (code)`. External terminal stays open until user closes.

## Errors

- **Syntax error in target**: runner catches `SyntaxError` before tracing starts, sends `Exception` then `Exited(1)`. Panel shows the message; editor highlights the offending line.
- **Runtime exception**: runner sends `Exception` (caught at top of `runpy`). Traceback also printed to the external terminal's stderr.
- **Runner dies unexpectedly** (segfault, OOM, killed): socket EOF without `Exited` → controller transitions to `exited(code=-1)`, notifies user.
- **External terminal app not installed**: spawn `subprocess.Popen` returns a non-zero exit immediately or raises. Controller transitions to `error`, notifies, suggests changing `debug_terminal_command` in settings.
- **No connection within 5 s**: probably the terminal app failed silently. Controller cancels, notifies "Runner did not connect — check terminal app".
- **Two debug sessions at once**: starting a new one while `state != "idle"` confirms cancel of the previous via toast; on confirm, stops old session first.
- **Unsupported file (non-`.py`)**: Run button disabled.

## Tests

- `tests/test_debug_protocol.py` — round-trip every message type, including unicode and large repr fields.
- `tests/test_debug_runner.py` — spawn the runner against a fixture script using a controlled socket pair (no terminal app). Verify: `ready` arrives, breakpoints fire, `paused` payload contains expected locals/globals, step_over advances one line, exited(0) at end.
- `tests/test_debug_runner_exception.py` — fixture raises `ZeroDivisionError`; verify `exception` then `exited(1)`.
- `tests/test_debug_controller.py` — use mock socket; drive `start` → `Ready` → `Paused` → `Continue` → `Exited`. Mock `terminal.spawn` to no-op.
- `tests/test_debug_panel.py` — Textual `Pilot`: instantiate `DebugPanel` with a fake controller; click Run, Continue, Stop; assert controller methods called and labels update on state change.
- `tests/test_editor_gutter.py` — assign breakpoints and current_exec_line; assert rendered strip contains expected glyph/style markers.

External-terminal spawning is mocked, never invoked in CI.

## Settings additions

`EditorConfig` gains:
```python
debug_terminal_command: str = (
    'osascript -e \'tell application "LiquidTerminal" to do script "{cmd}"\''
)
```

`SettingsPanel` gains an `Input` (multi-line not needed) for this command, with a label and a tiny help line pointing to the docs section in README.

## Sidebar cycling

`JetApp._active_sidebar` becomes `Literal["tree","settings","debug"]`. `action_cycle_sidebars` cycles `tree → settings → debug → tree`. The new sidebar is hidden by default at startup. `compose()` yields `DebugPanel(id="sidebar-debug")` after the settings panel.

## Out of scope (later)

- Conditional breakpoints.
- Watches.
- Multi-file step-into with library code visibility toggle.
- Persisted breakpoints in workspace.
- Linux/Windows default-terminal autodetection (user supplies template).
