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


def test_activity_panel_streams_incrementally_without_overlap(page) -> None:
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

        panel = page.locator('[data-franq-activity-panel="fixture-execution"]')
        panel.wait_for(state="attached")
        panel.locator("summary").click()
        page.wait_for_timeout(150)
        assert panel.get_attribute("open") is not None

        page.get_by_role("button", name="Simular stream incremental").click()
        page.wait_for_function(
            """
            () => document.querySelectorAll(
              '[data-franq-activity-panel="fixture-execution"] .franq-activity-item'
            ).length === 20
            """
        )

        panel = page.locator('[data-franq-activity-panel="fixture-execution"]')
        panel.wait_for(state="attached")
        page.wait_for_timeout(150)
        assert panel.get_attribute("open") is not None

        timeline = panel.locator('[data-franq-activity-scroll]')
        metrics = timeline.evaluate(
            """
            (timeline) => {
              const style = getComputedStyle(timeline);
              const rects = Array.from(
                timeline.querySelectorAll('.franq-activity-item')
              ).map((element) => {
                const rect = element.getBoundingClientRect();
                return { top: rect.top, bottom: rect.bottom, height: rect.height };
              });
              return {
                clientHeight: timeline.clientHeight,
                scrollHeight: timeline.scrollHeight,
                clientWidth: timeline.clientWidth,
                scrollWidth: timeline.scrollWidth,
                overflowY: style.overflowY,
                overflowX: style.overflowX,
                rects,
              };
            }
            """
        )

        assert metrics["overflowY"] in {"auto", "scroll", "overlay"}
        assert metrics["overflowX"] == "hidden"
        assert metrics["scrollHeight"] > metrics["clientHeight"]
        assert metrics["clientHeight"] <= 180
        assert metrics["scrollWidth"] <= metrics["clientWidth"] + 2

        rects = metrics["rects"]
        assert len(rects) == 20
        assert all(rect["height"] > 0 for rect in rects)
        for previous, current in zip(rects, rects[1:], strict=False):
            assert current["top"] >= previous["bottom"] - 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
