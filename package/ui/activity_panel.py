import json
from html import escape

import streamlit.components.v1 as components


ACTIVITY_PANEL_HEIGHT_PX = 156


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
    height_json = json.dumps(ACTIVITY_PANEL_HEIGHT_PX)
    return f"""
(() => {{
  const host = window.parent;
  const doc = host.document;
  const executionId = {execution_json};
  const storageKey = {storage_key_json};
  const panelHeight = {height_json};
  const registry = host.__franqActivityPanels || (host.__franqActivityPanels = {{}});
  const previous = registry[executionId];
  if (previous && previous.cleanup) previous.cleanup();

  const styleId = "franq-activity-panel-style";
  if (!doc.getElementById(styleId)) {{
    const style = doc.createElement("style");
    style.id = styleId;
    style.textContent = `
      .franq-activity-timeline {{
        overflow-y: auto !important;
        overflow-x: hidden !important;
        overscroll-behavior: contain;
        scrollbar-gutter: stable;
        box-sizing: border-box;
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        padding-right: 0.25rem;
      }}
      .franq-activity-timeline * {{
        box-sizing: border-box;
        min-width: 0;
        max-width: 100%;
      }}
      .franq-activity-timeline [data-testid="stVerticalBlock"] {{
        gap: 0.35rem;
      }}
      .franq-activity-timeline [data-testid="stMarkdownContainer"] p {{
        margin: 0;
        font-size: 0.82rem;
        line-height: 1.35;
        overflow-wrap: anywhere;
      }}
      .franq-activity-timeline [data-testid="stCaptionContainer"] {{
        margin: 0;
        font-size: 0.73rem;
        line-height: 1.3;
        overflow-wrap: anywhere;
      }}
      .franq-activity-timeline pre,
      .franq-activity-timeline code {{
        white-space: pre-wrap !important;
        overflow-wrap: anywhere !important;
        word-break: break-word !important;
        overflow-x: hidden !important;
        max-width: 100% !important;
      }}
      .franq-activity-timeline pre {{
        margin: 0.15rem 0 0.25rem 0;
        max-height: 88px;
        font-size: 0.71rem;
      }}
    `;
    doc.head.appendChild(style);
  }}

  let details = null;
  let summary = null;
  let scrollTarget = null;
  let contentObserver = null;
  let detailsObserver = null;
  let bindFrame = null;
  let pinned = true;
  let programmaticScroll = false;
  let restoringOpen = false;
  let preferenceInitialized = false;
  let desiredOpen = false;
  const threshold = 32;

  const findMarker = () => Array.from(
    doc.querySelectorAll("[data-franq-activity-panel]")
  ).find((element) => element.getAttribute("data-franq-activity-panel") === executionId);

  const findScrollTarget = (marker) => {{
    const wrapper = marker.closest('[data-testid="stVerticalBlockBorderWrapper"]');
    if (wrapper) return wrapper;

    const boundary = marker.closest("details");
    let node = marker.parentElement;
    while (node && node !== boundary) {{
      const style = host.getComputedStyle(node);
      if (["auto", "scroll", "overlay"].includes(style.overflowY)) return node;
      node = node.parentElement;
    }}
    return marker.parentElement;
  }};

  const applyScrollContract = (target) => {{
    if (!target) return;
    target.classList.add("franq-activity-timeline");
    target.style.setProperty("height", `${{panelHeight}}px`, "important");
    target.style.setProperty("max-height", `${{panelHeight}}px`, "important");
    target.style.setProperty("overflow-y", "auto", "important");
    target.style.setProperty("overflow-x", "hidden", "important");
    target.style.setProperty("min-width", "0", "important");
    target.style.setProperty("max-width", "100%", "important");
  }};

  const clearScrollContract = (target) => {{
    if (!target) return;
    target.classList.remove("franq-activity-timeline");
    for (const property of [
      "height",
      "max-height",
      "overflow-y",
      "overflow-x",
      "min-width",
      "max-width",
    ]) target.style.removeProperty(property);
  }};

  const distanceFromBottom = () => {{
    if (!scrollTarget) return 0;
    return scrollTarget.scrollHeight - scrollTarget.scrollTop - scrollTarget.clientHeight;
  }};

  const scrollToBottom = () => {{
    if (!scrollTarget) return;
    programmaticScroll = true;
    scrollTarget.scrollTop = scrollTarget.scrollHeight;
    requestAnimationFrame(() => {{ programmaticScroll = false; }});
  }};

  const onScroll = () => {{
    if (programmaticScroll || !scrollTarget) return;
    pinned = distanceFromBottom() <= threshold;
  }};

  const onContentMutation = () => {{
    applyScrollContract(scrollTarget);
    if (pinned && details && details.open) requestAnimationFrame(scrollToBottom);
  }};

  const restoreDesiredOpenState = () => {{
    if (!details || details.open === desiredOpen || restoringOpen) return;
    restoringOpen = true;
    details.open = desiredOpen;
    requestAnimationFrame(() => {{
      restoringOpen = false;
      if (desiredOpen && pinned) scrollToBottom();
    }});
  }};

  const persistUserIntent = () => {{
    if (!details) return;
    desiredOpen = !details.open;
    preferenceInitialized = true;
    host.sessionStorage.setItem(storageKey, desiredOpen ? "1" : "0");
  }};

  const onToggle = () => {{
    if (!details) return;
    if (details.open !== desiredOpen) {{
      requestAnimationFrame(restoreDesiredOpenState);
      return;
    }}
    if (details.open && pinned) requestAnimationFrame(scrollToBottom);
  }};

  const onDetailsMutation = () => {{
    if (details && details.open !== desiredOpen) requestAnimationFrame(restoreDesiredOpenState);
  }};

  const scheduleBind = () => {{
    if (bindFrame !== null) return;
    bindFrame = requestAnimationFrame(() => {{
      bindFrame = null;
      bind();
    }});
  }};

  const unbindDetails = () => {{
    if (detailsObserver) detailsObserver.disconnect();
    detailsObserver = null;
    if (summary) summary.removeEventListener("click", persistUserIntent, true);
    if (details) details.removeEventListener("toggle", onToggle);
    summary = null;
  }};

  const bindDetails = (nextDetails) => {{
    if (nextDetails === details) {{
      restoreDesiredOpenState();
      return;
    }}

    unbindDetails();
    details = nextDetails;
    if (!details) return;

    if (!preferenceInitialized) {{
      const storedOpen = host.sessionStorage.getItem(storageKey);
      desiredOpen = storedOpen === null ? details.open : storedOpen === "1";
      preferenceInitialized = true;
    }}

    summary = details.querySelector(":scope > summary") || details.querySelector("summary");
    if (summary) summary.addEventListener("click", persistUserIntent, true);
    details.addEventListener("toggle", onToggle);

    detailsObserver = new MutationObserver(onDetailsMutation);
    detailsObserver.observe(details, {{
      attributes: true,
      attributeFilter: ["open"],
    }});
    restoreDesiredOpenState();
  }};

  const bind = () => {{
    const marker = findMarker();
    if (!marker) return;

    bindDetails(marker.closest("details"));

    const nextScrollTarget = findScrollTarget(marker);
    if (nextScrollTarget !== scrollTarget) {{
      if (contentObserver) contentObserver.disconnect();
      if (scrollTarget) {{
        scrollTarget.removeEventListener("scroll", onScroll);
        clearScrollContract(scrollTarget);
      }}
      scrollTarget = nextScrollTarget;
      if (scrollTarget) {{
        applyScrollContract(scrollTarget);
        scrollTarget.addEventListener("scroll", onScroll, {{ passive: true }});
        contentObserver = new MutationObserver(onContentMutation);
        contentObserver.observe(scrollTarget, {{
          childList: true,
          subtree: true,
          characterData: true,
        }});
        requestAnimationFrame(scrollToBottom);
      }}
    }} else {{
      applyScrollContract(scrollTarget);
    }}
  }};

  const rootObserver = new MutationObserver(scheduleBind);
  rootObserver.observe(doc.body, {{
    childList: true,
    subtree: true,
  }});
  bind();

  registry[executionId] = {{
    cleanup: () => {{
      rootObserver.disconnect();
      if (contentObserver) contentObserver.disconnect();
      if (bindFrame !== null) cancelAnimationFrame(bindFrame);
      unbindDetails();
      if (scrollTarget) {{
        scrollTarget.removeEventListener("scroll", onScroll);
        clearScrollContract(scrollTarget);
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
