(() => {
  const list = document.getElementById("conversation-list");
  const menu = document.getElementById("conversation-context-menu");
  const deleteAction = document.getElementById("conversation-delete-action");
  const hasMore = __HAS_MORE__;
  const currentLimit = __CURRENT_LIMIT__;
  const pageSize = __PAGE_SIZE__;
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

  const hideMenu = () => {
    menu.hidden = true;
    menuSessionId = null;
  };

  document.querySelectorAll(".conversation-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (clickTimer) {
        window.clearTimeout(clickTimer);
      }
      clickTimer = window.setTimeout(() => {
        navigate({
          session_id: item.dataset.sessionId,
          execution_id: null,
          new_conversation: null,
        });
      }, 180);
    });

    item.addEventListener("dblclick", (event) => {
      event.preventDefault();
      if (clickTimer) {
        window.clearTimeout(clickTimer);
        clickTimer = null;
      }
      const currentTitle = item.dataset.sessionTitle || "";
      const nextTitle = window.prompt("Renomear conversa", currentTitle);
      if (nextTitle === null) {
        return;
      }
      const normalized = nextTitle.trim().replace(/\s+/g, " ");
      if (!normalized || normalized === currentTitle) {
        return;
      }
      navigate({
        rename_session_id: item.dataset.sessionId,
        rename_session_title: normalized,
      });
    });

    item.addEventListener("contextmenu", (event) => {
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
    navigate({ delete_session_id: menuSessionId });
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) {
      hideMenu();
    }
  });

  window.addEventListener("blur", hideMenu);

  if (list && hasMore) {
    list.addEventListener("scroll", () => {
      if (loadingMore) {
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
