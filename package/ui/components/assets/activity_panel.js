(() => {
  const host = window.parent;
  const doc = host.document;
  const executionId = __EXECUTION_ID_JSON__;
  const storageKey = __STORAGE_KEY_JSON__;
  const registry = host.__franqActivityPanels || (host.__franqActivityPanels = {});
  const previous = registry[executionId];
  if (previous && previous.cleanup) previous.cleanup();

  let details = null;
  let summary = null;
  let scrollTarget = null;
  let rootObserver = null;
  let scrollObserver = null;
  let bindFrame = null;
  let desiredOpen = false;
  let preferenceInitialized = false;
  let restoringOpen = false;
  let pinned = true;
  let savedScrollTop = 0;
  let programmaticScroll = false;
  const threshold = 32;

  const findPanel = () => Array.from(
    doc.querySelectorAll('[data-franq-activity-panel]')
  ).find((element) => element.getAttribute('data-franq-activity-panel') === executionId);

  const distanceFromBottom = () => {
    if (!scrollTarget) return 0;
    return scrollTarget.scrollHeight - scrollTarget.scrollTop - scrollTarget.clientHeight;
  };

  const scrollToBottom = () => {
    if (!scrollTarget) return;
    programmaticScroll = true;
    scrollTarget.scrollTop = scrollTarget.scrollHeight;
    savedScrollTop = scrollTarget.scrollTop;
    requestAnimationFrame(() => { programmaticScroll = false; });
  };

  const restoreScrollPosition = () => {
    if (!scrollTarget) return;
    programmaticScroll = true;
    if (pinned) {
      scrollTarget.scrollTop = scrollTarget.scrollHeight;
      savedScrollTop = scrollTarget.scrollTop;
    } else {
      scrollTarget.scrollTop = Math.min(savedScrollTop, scrollTarget.scrollHeight);
    }
    requestAnimationFrame(() => { programmaticScroll = false; });
  };

  const onScroll = () => {
    if (programmaticScroll || !scrollTarget) return;
    savedScrollTop = scrollTarget.scrollTop;
    pinned = distanceFromBottom() <= threshold;
  };

  const restoreDesiredOpenState = () => {
    if (!details || details.open === desiredOpen || restoringOpen) return;
    restoringOpen = true;
    details.open = desiredOpen;
    requestAnimationFrame(() => {
      restoringOpen = false;
      if (desiredOpen) restoreScrollPosition();
    });
  };

  const persistUserIntent = () => {
    if (!details) return;
    desiredOpen = !details.open;
    preferenceInitialized = true;
    host.sessionStorage.setItem(storageKey, desiredOpen ? '1' : '0');
  };

  const onToggle = () => {
    if (!details) return;
    if (details.open !== desiredOpen) {
      requestAnimationFrame(restoreDesiredOpenState);
      return;
    }
    if (details.open) requestAnimationFrame(restoreScrollPosition);
  };

  const unbind = () => {
    if (summary) summary.removeEventListener('click', persistUserIntent, true);
    if (details) details.removeEventListener('toggle', onToggle);
    if (scrollTarget) scrollTarget.removeEventListener('scroll', onScroll);
    if (scrollObserver) scrollObserver.disconnect();
    summary = null;
    details = null;
    scrollTarget = null;
    scrollObserver = null;
  };

  const bind = () => {
    const nextDetails = findPanel();
    if (!nextDetails) return;
    const nextScrollTarget = nextDetails.querySelector('[data-franq-activity-scroll]');

    if (nextDetails === details && nextScrollTarget === scrollTarget) {
      restoreDesiredOpenState();
      return;
    }

    unbind();
    details = nextDetails;
    summary = details.querySelector(':scope > summary') || details.querySelector('summary');
    scrollTarget = nextScrollTarget;

    if (!preferenceInitialized) {
      const storedOpen = host.sessionStorage.getItem(storageKey);
      desiredOpen = storedOpen === null ? details.open : storedOpen === '1';
      preferenceInitialized = true;
    }

    if (summary) summary.addEventListener('click', persistUserIntent, true);
    details.addEventListener('toggle', onToggle);
    if (scrollTarget) {
      scrollTarget.addEventListener('scroll', onScroll, { passive: true });
      scrollObserver = new MutationObserver(() => {
        if (details && details.open && pinned) requestAnimationFrame(scrollToBottom);
      });
      scrollObserver.observe(scrollTarget, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }

    restoreDesiredOpenState();
    if (details.open) requestAnimationFrame(restoreScrollPosition);
  };

  const scheduleBind = () => {
    if (bindFrame !== null) return;
    bindFrame = requestAnimationFrame(() => {
      bindFrame = null;
      bind();
    });
  };

  rootObserver = new MutationObserver(scheduleBind);
  rootObserver.observe(doc.body, { childList: true, subtree: true });
  bind();

  registry[executionId] = {
    cleanup: () => {
      if (rootObserver) rootObserver.disconnect();
      if (scrollObserver) scrollObserver.disconnect();
      if (bindFrame !== null) cancelAnimationFrame(bindFrame);
      unbind();
    },
  };
})();
