import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_UI_TESTS") != "1",
    reason="browser UI tests are opt-in",
)


def _wait_for_port(host: str, port: int, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"Streamlit did not start on {host}:{port}")


def test_conversation_sidebar_delete_flow_and_selected_contrast(page) -> None:
    port = 8766
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "tests/ui/fixtures/conversation_sidebar_app.py",
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
            "--theme.base=dark",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port("127.0.0.1", port)
        page.goto(f"http://127.0.0.1:{port}")

        active = page.locator('.conversation-item[data-session-id="session-1"]')
        active.wait_for(state="visible")
        styles = active.evaluate(
            """
            (element) => {
              const style = getComputedStyle(element);
              return {
                color: style.color,
                backgroundColor: style.backgroundColor,
                boxShadow: style.boxShadow,
                fontWeight: style.fontWeight,
              };
            }
            """
        )

        assert styles["color"] != "rgb(0, 0, 0)"
        assert styles["backgroundColor"] not in {"rgba(0, 0, 0, 0)", "transparent"}
        assert styles["boxShadow"] != "none"
        assert int(styles["fontWeight"]) >= 600

        active.click(button="right")
        menu = page.locator("#conversation-context-menu")
        menu.wait_for(state="visible")

        page.locator("#conversation-delete-action").click()
        confirmation = page.locator("#conversation-delete-confirm")
        confirmation.wait_for(state="visible")
        assert page.locator("#conversation-context-actions").is_hidden()

        page.locator("#conversation-delete-confirm-action").click()
        page.wait_for_url("**delete_session_id=session-1**")
        assert "delete_session_id=session-1" in page.url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
