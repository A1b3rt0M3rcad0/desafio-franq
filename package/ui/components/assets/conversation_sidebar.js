(() => {
  const list = document.getElementById("conversation-list");
  const menu = document.getElementById("conversation-context-menu");
  const menuActions = document.getElementById("conversation-context-actions");
  const deleteAction = document.getElementById("conversation-delete-action");
  const deleteConfirm = document.getElementById("conversation-delete-confirm");
  const deleteCancel = document.getElementById("conversation-delete-cancel");
  const deleteConfirmAction = document.getElementById("conversation-delete-confirm-action");
  const hasMore = __HAS_MORE__;
  const currentLimit = __CURRENT_LIMIT__;
  const pageSize = __PAGE_SIZE__;
  const scrollStorageKey = "franq:conversation-list:scroll-top";
  let menuSessionId = null;
  let loadingMore = false;
  let clickTimer = null;

  const parseRgb = (value) => {
    const match = String(value || "").match(/rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (!match) {
      return null;
    }
    return [Number(match[1]), Number(match[2]), Number(match[3])];
  };

  const isDark = (value) => {
    const rgb = parseRgb(value);
    if (!rgb) {
      return true;
    }
    const [red, green, blue] = rgb.map((channel) => channel / 255);
    const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    return luminance < 0.5;
  };

  const syncTheme = () => {
    try {
      const parentDocument = window.parent.document;
      const sidebar = parentDocument.querySelector('[data-testid="stSidebar"]');
      const source = sidebar || parentDocument.body;
      const sourceStyle = window.parent.getComputedStyle(source);
      const rootStyle = window.parent.getComputedStyle(parentDocument.documentElement);
      const dark = isDark(sourceStyle.backgroundColor);
      const textColor = sourceStyle.color || (dark ? "#f5f5f5" : "#262730");
      const primary = rootStyle.getPropertyValue("--primary-color").trim() || "#ff4b4b";

      document.documentElement.style.setProperty("--franq-text-color", textColor);
      document.documentElement.style.setProperty("--franq-accent", primary);
      document.documentElement.style.setProperty(
        "--franq-hover-bg",
        dark ? "rgba(255, 255, 255, 0.07)" : "rgba(0, 0, 0, 0.055)"
      );
      document.documentElement.style.setProperty(
        "--franq-active-bg",
        dark ? "rgba(255, 255, 255, 0.13)" : "rgba(0, 0, 0, 0.09)"
      );
      document.documentElement.style.setProperty(
        "--franq-active-border",
        dark ? "rgba(255, 255, 255, 0.16)" : "rgba(0, 0, 0, 0.13)"
      );
      document.documentElement.style.setProperty(
        "--franq-menu-bg",
        sourceStyle.backgroundColor || (dark ? "#262730" : "#ffffff")
      );
      document.documentElement.style.setProperty(
        "--franq-menu-border",
        dark ? "rgba(255, 255, 255, 0.12)" : "rgba(0, 0, 0, 0.14)"
      );
    } catch (_) {
      // Defaults in CSS keep the component readable if the parent theme cannot be inspected.
    }
  };

  const navigate = (changes) => {
    const url = new URL(window.parent.location.href);
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "") {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, String(value));
      }
    });
    window.parent.location.href = url.toString();
  };

  const rememberScroll = () => {
    if (!list) {
      return;
    }
    try {
      window.parent.sessionStorage.setItem(scrollStorageKey, String(list.scrollTop));
    } catch (_) {
      // Scroll persistence is a progressive enhancement.
    }
  };

  const restoreScroll = () => {
    if (!list) {
      return;
    }
    try {
      const stored = Number(window.parent.sessionStorage.getItem(scrollStorageKey) || "0");
      if (Number.isFinite(stored) && stored > 0) {
        list.scrollTop = stored;
      }
    } catch (_) {
      // The list remains usable if storage is unavailable.
    }
  };

  const resetMenuView = () => {
    menuActions.hidden = false;
    deleteConfirm.hidden = true;
    deleteConfirmAction.disabled = false;
    deleteConfirmAction.textContent = "Excluir";
  };

  const hideMenu = () => {
    menu.hidden = true;
    menuSessionId = null;
    resetMenuView();
  };

  const openMenu = (item, event) => {
    menuSessionId = item.dataset.sessionId;
    resetMenuView();
    menu.hidden = false;

    const menuWidth = Math.max(menu.offsetWidth, 164);
    const menuHeight = Math.max(menu.offsetHeight, 44);
    const maxLeft = Math.max(4, window.innerWidth - menuWidth - 4);
    const maxTop = Math.max(4, window.innerHeight - menuHeight - 4);
    menu.style.left = `${Math.max(4, Math.min(event.clientX, maxLeft))}px`;
    menu.style.top = `${Math.max(4, Math.min(event.clientY, maxTop))}px`;
  };

  const beginRename = (item) => {
    const titleNode = item.querySelector(".conversation-item-title");
    if (!titleNode || item.querySelector(".conversation-title-editor")) {
      return;
    }

    const currentTitle = item.dataset.sessionTitle || titleNode.textContent || "";
    const editor = document.createElement("input");
    editor.type = "text";
    editor.className = "conversation-title-editor";
    editor.value = currentTitle;
    editor.maxLength = 120;
    editor.setAttribute("aria-label", "Renomear conversa");

    const restore = () => {
      if (editor.isConnected) {
        editor.replaceWith(titleNode);
      }
    };

    const commit = () => {
      const normalized = editor.value.trim().replace(/\s+/g, " ");
      if (!normalized || normalized === currentTitle) {
        restore();
        return;
      }
      rememberScroll();
      navigate({
        rename_session_id: item.dataset.sessionId,
        rename_session_title: normalized,
      });
    };

    editor.addEventListener("click", (event) => event.stopPropagation());
    editor.addEventListener("dblclick", (event) => event.stopPropagation());
    editor.addEventListener("contextmenu", (event) => event.stopPropagation());
    editor.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        restore();
      }
    });
    editor.addEventListener("blur", restore);

    titleNode.replaceWith(editor);
    editor.focus();
    editor.select();
  };

  document.querySelectorAll(".conversation-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (item.querySelector(".conversation-title-editor")) {
        return;
      }
      if (clickTimer) {
        window.clearTimeout(clickTimer);
      }
      clickTimer = window.setTimeout(() => {
        rememberScroll();
        navigate({
          session_id: item.dataset.sessionId,
          execution_id: null,
          new_conversation: null,
        });
      }, 180);
    });

    item.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (clickTimer) {
        window.clearTimeout(clickTimer);
        clickTimer = null;
      }
      beginRename(item);
    });

    item.addEventListener("contextmenu", (event) => {
      if (item.querySelector(".conversation-title-editor")) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      openMenu(item, event);
    });
  });

  deleteAction.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!menuSessionId) {
      return;
    }
    menuActions.hidden = true;
    deleteConfirm.hidden = false;
  });

  deleteCancel.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    hideMenu();
  });

  deleteConfirmAction.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!menuSessionId) {
      return;
    }
    deleteConfirmAction.disabled = true;
    deleteConfirmAction.textContent = "Excluindo...";
    rememberScroll();
    navigate({
      delete_session_id: menuSessionId,
      rename_session_id: null,
      rename_session_title: null,
    });
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) {
      hideMenu();
    }
  });

  window.addEventListener("blur", hideMenu);

  if (list) {
    window.requestAnimationFrame(restoreScroll);
    list.addEventListener("scroll", () => {
      rememberScroll();
      if (!hasMore || loadingMore) {
        return;
      }
      const remaining = list.scrollHeight - list.scrollTop - list.clientHeight;
      if (remaining <= 48) {
        loadingMore = true;
        navigate({ sessions_limit: currentLimit + pageSize });
      }
    });
  }

  syncTheme();
  try {
    const parentRoot = window.parent.document.documentElement;
    new MutationObserver(syncTheme).observe(parentRoot, {
      attributes: true,
      attributeFilter: ["class", "style"],
    });
  } catch (_) {
    // Theme updates remain optional.
  }
})();
