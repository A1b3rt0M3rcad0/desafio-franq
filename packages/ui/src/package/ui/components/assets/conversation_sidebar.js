export default function(component) {
  const { data, parentElement } = component;
  const list = parentElement.querySelector("#conversation-list");
  const menu = parentElement.querySelector("#conversation-context-menu");
  const menuActions = parentElement.querySelector("#conversation-context-actions");
  const deleteAction = parentElement.querySelector("#conversation-delete-action");
  const deleteConfirm = parentElement.querySelector("#conversation-delete-confirm");
  const deleteCancel = parentElement.querySelector("#conversation-delete-cancel");
  const deleteConfirmAction = parentElement.querySelector(
    "#conversation-delete-confirm-action"
  );

  if (!list || !menu || !menuActions || !deleteAction || !deleteConfirm ||
      !deleteCancel || !deleteConfirmAction) {
    return;
  }

  const sessions = Array.isArray(data?.sessions) ? data.sessions : [];
  const activeSessionId = String(data?.active_session_id || "");
  const hasMore = Boolean(data?.has_more);
  const currentLimit = Number(data?.current_limit || 20);
  const pageSize = Number(data?.page_size || 20);
  const scrollStorageKey = "franq:conversation-list:scroll-top";
  let menuSessionId = null;
  let loadingMore = false;
  let clickTimer = null;

  const navigate = (changes) => {
    const url = new URL(window.location.href);
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "") {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, String(value));
      }
    });
    window.location.href = url.toString();
  };

  const rememberScroll = () => {
    try {
      window.sessionStorage.setItem(scrollStorageKey, String(list.scrollTop));
    } catch (_) {
      // Scroll persistence is optional.
    }
  };

  const restoreScroll = () => {
    try {
      const stored = Number(window.sessionStorage.getItem(scrollStorageKey) || "0");
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

    editor.onclick = (event) => event.stopPropagation();
    editor.ondblclick = (event) => event.stopPropagation();
    editor.oncontextmenu = (event) => event.stopPropagation();
    editor.onkeydown = (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        restore();
      }
    };
    editor.onblur = restore;

    titleNode.replaceWith(editor);
    editor.focus();
    editor.select();
  };

  const createConversationItem = (session) => {
    const sessionId = String(session?.id || "");
    if (!sessionId) {
      return null;
    }
    const title = String(session?.title || "Conversa");
    const item = document.createElement("button");
    item.type = "button";
    item.className = "conversation-item";
    if (sessionId === activeSessionId) {
      item.classList.add("is-active");
      item.setAttribute("aria-current", "page");
    }
    item.dataset.sessionId = sessionId;
    item.dataset.sessionTitle = title;
    item.title = title;

    const titleNode = document.createElement("span");
    titleNode.className = "conversation-item-title";
    titleNode.textContent = title;
    item.appendChild(titleNode);

    item.onclick = () => {
      if (item.querySelector(".conversation-title-editor")) {
        return;
      }
      if (clickTimer) {
        window.clearTimeout(clickTimer);
      }
      clickTimer = window.setTimeout(() => {
        rememberScroll();
        navigate({
          session_id: sessionId,
          execution_id: null,
          new_conversation: null,
        });
      }, 180);
    };

    item.ondblclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (clickTimer) {
        window.clearTimeout(clickTimer);
        clickTimer = null;
      }
      beginRename(item);
    };

    item.oncontextmenu = (event) => {
      if (item.querySelector(".conversation-title-editor")) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      openMenu(item, event);
    };
    return item;
  };

  list.replaceChildren();
  sessions.forEach((session) => {
    const item = createConversationItem(session);
    if (item) {
      list.appendChild(item);
    }
  });

  deleteAction.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!menuSessionId) {
      return;
    }
    menuActions.hidden = true;
    deleteConfirm.hidden = false;
  };

  deleteCancel.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    hideMenu();
  };

  deleteConfirmAction.onclick = (event) => {
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
  };

  list.onclick = (event) => {
    if (event.target === list) {
      hideMenu();
    }
  };

  list.onscroll = () => {
    rememberScroll();
    if (!hasMore || loadingMore) {
      return;
    }
    const remaining = list.scrollHeight - list.scrollTop - list.clientHeight;
    if (remaining <= 48) {
      loadingMore = true;
      navigate({ sessions_limit: currentLimit + pageSize });
    }
  };

  window.requestAnimationFrame(restoreScroll);
}
