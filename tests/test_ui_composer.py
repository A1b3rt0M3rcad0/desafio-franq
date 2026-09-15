from package.ui.components.composer import ComposerMode, action_label, composer_mode


def test_composer_uses_send_action_without_active_execution() -> None:
    mode = composer_mode(None)
    assert mode == ComposerMode.SEND
    assert action_label(mode) == "➤"


def test_composer_replaces_send_with_stop_for_active_execution() -> None:
    mode = composer_mode("execution-1")
    assert mode == ComposerMode.STOP
    assert action_label(mode) == "■"
