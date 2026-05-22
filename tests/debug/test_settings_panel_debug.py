from jet.settings_panel import EditorConfig


def test_editor_config_has_default_debug_terminal_command():
    cfg = EditorConfig()
    assert "{cmd}" in cfg.debug_terminal_command
    assert "LiquidTerminal" in cfg.debug_terminal_command
