import json
from html import escape

import streamlit.components.v1 as components


ACTIVITY_PANEL_HEIGHT_PX = 176


def activity_panel_storage_key(execution_id: str) -> str:
    return f"franq:execution:{execution_id}:activities-open"


def activity_panel_marker(execution_id: str) -> str:
    safe_execution_id = escape(execution_id, quote=True)
    return (
        f'<span data-franq-activity-panel="{safe_execution_id}" '
        'aria-hidden="true" style="display:none"></span>'
    )


def build_activity_panel_script(execution_id: str) -> str:
    execution_json = _javascript_string(execution_id)
    storage_key_json = _javascript_string(activity_panel_storage_key(execution_id))
    return f"""
(() => {{
  const host = window.parent;
  const doc = host.document;
  const executionId = {execution_json};
  const storageKey = {storage_key_json};
  const registry = host.__franqActivityPanels || (host.__franqActivityPanels = {{}});
  const previous = registry[executionId];
  if (previous && previous.cleanup) previous.cleanup();

  const styleId = "franq-activity-panel-style";
  if (!doc.getElementById(styleId)) {{
    const style = doc.createElement("style");
    style.id = styleId;
    style.textContent = `
      .franq-activity-timeline {{
        scrollbar-gutter: stable;
        padding-right: 0.25rem;
      }}
      .franq-activity-timeline [data-testid="stVerticalBlock"] {{
        gap: 0.28rem;
      }}
      .franq-activity-timeline [data-testid="stMarkdownContainer"] p {{
        margin: 0;
        font-size: 0.84rem;
        line-height: 1.28;
      }}
      .franq-activity-timeline [data-testid="stCaptionContainer"] {{
        margin: 0;
        font-size: 0.74rem;
        line-height: 1.22;
      }}
      .franq-activity-timeline pre {{
        margin: 0.15rem 0 0.25rem 0;
        max-height: 92px;
        font-size: 0.72rem;
      }}
    `;
    doc.head.appendChild(style);
  }}

  let details = null;
  let scrollTarget = null;
  let contentObserver = null;
  let bindFrame = null;
  let pinned = true;
  let programmatic = false;
  const threshold = 36;

  const findMarker = () => Array.from(
    doc.querySelectorAll("[data-franq-activity-panel]")
  ).find((element) => element.getAttribute("data-franq-activity-panel") === executionId);

  const findScrollableAncestor = (marker) => {{
    const boundary = marker.closest("details");
    let node = marker.parentElement;
    while (node && node !== boundary) {{
      const overflowY = host.getComputedStyle(node).overflowY;
      if (["auto", "scroll", "overlay"].includes(overflowY)) return node;
      node = node.parentElement;
    }}
    return marker.parentElement;
  }};

  const distanceFromBottom = () => {{
    if (!scrollTarget) return 0;
    return scrollTarget.scrollHeight - scrollTarget.scrollTop - scrollTarget.clientHeight;
  }};

  const scrollToBottom = () => {{
    if (!scrollTarget) return;
    programmatic = true;
    scrollTarget.scrollTop = scrollTarget.scrollHeight;
    requestAnimationFrame(() => {{ programmatic = false; }});
  }};

  const onScroll = () => {{
    if (programmatic || !scrollTarget) return;
    pinned = distanceFromBottom() <= threshold;
  }};

  const onContentMutation = () => {{
    if (pinned && details && details.open) requestAnimationFrame(scrollToBottom);
  }};

  const scheduleBind = () => {{
    if (bindFrame !== null) return;
    bindFrame = requestAnimationFrame(() => {{
      bindFrame = null;
      bind();
    }});
  }};

  const onToggle = () => {{
    if (!details) return;
    host.sessionStorage.setItem(storageKey, details.open ? "1" : "0");
    if (details.open && pinned) requestAnimationFrame(scrollToBottom);
    scheduleBind();
  }};

  const bind = () => {{
    const marker = findMarker();
    if (!marker) return;

    const nextDetails = marker.closest("details");
    if (nextDetails !== details) {{
      if (details) details.removeEventListener("toggle", onToggle);
      details = nextDetails;
      if (details) {{
        const storedOpen = host.sessionStorage.getItem(storageKey);
        if (storedOpen !== null) details.open = storedOpen === "1";
        details.addEventListener("toggle", onToggle);
      }}
    }}

    const nextScrollTarget = findScrollableAncestor(marker);
    if (nextScrollTarget !== scrollTarget) {{
      if (contentObserver) contentObserver.disconnect();
      if (scrollTarget) {{
        scrollTarget.removeEventListener("scroll", onScroll);
        scrollTarget.classList.remove("franq-activity-timeline");
      }}
      scrollTarget = nextScrollTarget;
      if (scrollTarget) {{
        scrollTarget.classList.add("franq-activity-timeline");
        scrollTarget.addEventListener("scroll", onScroll, {{ passive: true }});
        contentObserver = new MutationObserver(onContentMutation);
        contentObserver.observe(scrollTarget, {{
          childList: true,
          subtree: true,
          characterData: true,
        }});
        requestAnimationFrame(scrollToBottom);
      }}
    }}
  }};

  const rootObserver = new MutationObserver(scheduleBind);
  rootObserver.observe(doc.body, {{ childList: true, subtree: true }});
  bind();

  registry[executionId] = {{
    cleanup: () => {{
      rootObserver.disconnect();
      if (contentObserver) contentObserver.disconnect();
      if (bindFrame !== null) cancelAnimationFrame(bindFrame);
      if (details) details.removeEventListener("toggle", onToggle);
      if (scrollTarget) {{
        scrollTarget.removeEventListener("scroll", onScroll);
        scrollTarget.classList.remove("franq-activity-timeline");
      }}
    }},
  }};
}})();
"""


def mount_activity_panel_behavior(execution_id: str) -> None:
    components.html(
        f"<script>{build_activity_panel_script(execution_id)}</script>",
        height=0,
        width=0,
    )


def _javascript_string(value: str) -> str:
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
