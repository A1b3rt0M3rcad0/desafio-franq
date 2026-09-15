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


def test_activity_panel_uses_vertical_native_scroll_without_overlap(page) -> None:
    port = 8765
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "tests/ui/fixtures/activity_panel_app.py",
            "--server.headless=true",
            f"--server.port={port}",
            "--server.address=127.0.0.1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port("127.0.0.1", port)
        page.goto(f"http://127.0.0.1:{port}")
        marker = page.locator('[data-franq-activity-panel="fixture-execution"]')
        marker.wait_for(state="attached")

        details = marker.locator("xpath=ancestor::details[1]")
        details.locator("summary").click()
        page.wait_for_timeout(300)
        assert details.get_attribute("open") is not None

        metrics = marker.evaluate(
            """
            (marker) => {
              const boundary = marker.closest('details');
              let node = marker.parentElement;
              while (node && node !== boundary) {
                const style = getComputedStyle(node);
                if (['auto', 'scroll', 'overlay'].includes(style.overflowY)) {
                  const titles = Array.from(
                    node.querySelectorAll('[data-testid="stMarkdownContainer"] p')
                  ).filter((element) => element.textContent.includes('Atividade de validação'));
                  const rects = titles.map((element) => {
                    const rect = element.getBoundingClientRect();
                    return { top: rect.top, bottom: rect.bottom };
                  });
                  return {
                    clientHeight: node.clientHeight,
                    scrollHeight: node.scrollHeight,
                    clientWidth: node.clientWidth,
                    scrollWidth: node.scrollWidth,
                    overflowY: style.overflowY,
                    rects,
                  };
                }
                node = node.parentElement;
              }
              return null;
            }
            """
        )

        assert metrics is not None
        assert metrics["scrollHeight"] > metrics["clientHeight"]
        assert metrics["clientHeight"] <= 180
        assert metrics["scrollWidth"] <= metrics["clientWidth"] + 2
        rects = metrics["rects"]
        assert len(rects) >= 10
        for previous, current in zip(rects, rects[1:], strict=False):
            assert current["top"] >= previous["bottom"] - 1

        page.get_by_role("button", name="Adicionar evento").click()
        marker = page.locator('[data-franq-activity-panel="fixture-execution"]')
        marker.wait_for(state="attached")
        details = marker.locator("xpath=ancestor::details[1]")
        page.wait_for_timeout(300)
        assert details.get_attribute("open") is not None
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
