(() => {
  const list = document.getElementById("conversation-list");
  const menu = document.getElementById("conversation-context-menu");
  const deleteAction = document.getElementById("conversation-delete-action");
  const hasMore = __HAS_MORE__;
  const currentLimit = __CURRENT_LIMIT__;
  const pageSize = __PAGE_SIZE__;
  const scrollStorageKey = "franq:conversation-list:scroll-top";
  let menuSessionId = null;
  let loadingMore = false;
  let clickTimer = null;

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

  const hideMenu = () => {
    menu.hidden = true;
    menuSessionId = null;
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
      menuSessionId = item.dataset.sessionId;
      menu.style.left = `${Math.min(event.clientX, window.innerWidth - 128)}px`;
      menu.style.top = `${Math.min(event.clientY, window.innerHeight - 48)}px`;
      menu.hidden = false;
    });
  });

  deleteAction.addEventListener("click", () => {
    if (!menuSessionId) {
      return;
    }
    const target = document.querySelector(
      `.conversation-item[data-session-id="${CSS.escape(menuSessionId)}"]`
    );
    const title = target?.dataset.sessionTitle || "esta conversa";
    if (!window.confirm(`Excluir “${title}”?`)) {
      hideMenu();
      return;
    }
    rememberScroll();
    navigate({ delete_session_id: menuSessionId });
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
})();
