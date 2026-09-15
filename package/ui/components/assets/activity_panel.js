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
  let contentObserver = null;
  let detailsObserver = null;
  let rootObserver = null;
  let bindFrame = null;
  let pinned = true;
  let programmaticScroll = false;
  let restoringOpen = false;
  let desiredOpen = false;
  let preferenceInitialized = false;
  const threshold = 32;

  const findMarker = () => Array.from(
    doc.querySelectorAll('[data-franq-activity-panel]')
  ).find((element) => element.getAttribute('data-franq-activity-panel') === executionId);

  const findVerticalScrollContainer = (marker) => {
    const boundary = marker.closest('details');
    let node = marker.parentElement;
    while (node && node !== boundary) {
      const style = host.getComputedStyle(node);
      if (['auto', 'scroll', 'overlay'].includes(style.overflowY)) return node;
      node = node.parentElement;
    }
    return null;
  };

  const distanceFromBottom = () => {
    if (!scrollTarget) return 0;
    return scrollTarget.scrollHeight - scrollTarget.scrollTop - scrollTarget.clientHeight;
  };

  const scrollToBottom = () => {
    if (!scrollTarget) return;
    programmaticScroll = true;
    scrollTarget.scrollTop = scrollTarget.scrollHeight;
    requestAnimationFrame(() => { programmaticScroll = false; });
  };

  const onScroll = () => {
    if (programmaticScroll || !scrollTarget) return;
    pinned = distanceFromBottom() <= threshold;
  };

  const onContentMutation = () => {
    if (pinned && details && details.open) requestAnimationFrame(scrollToBottom);
  };

  const restoreDesiredOpenState = () => {
    if (!details || details.open === desiredOpen || restoringOpen) return;
    restoringOpen = true;
    details.open = desiredOpen;
    requestAnimationFrame(() => {
      restoringOpen = false;
      if (desiredOpen && pinned) scrollToBottom();
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
    if (details.open && pinned) requestAnimationFrame(scrollToBottom);
  };

  const onDetailsMutation = () => {
    if (details && details.open !== desiredOpen) requestAnimationFrame(restoreDesiredOpenState);
  };

  const scheduleBind = () => {
    if (bindFrame !== null) return;
    bindFrame = requestAnimationFrame(() => {
      bindFrame = null;
      bind();
    });
  };

  const unbindDetails = () => {
    if (detailsObserver) detailsObserver.disconnect();
    detailsObserver = null;
    if (summary) summary.removeEventListener('click', persistUserIntent, true);
    if (details) details.removeEventListener('toggle', onToggle);
    summary = null;
  };

  const bindDetails = (nextDetails) => {
    if (nextDetails === details) {
      restoreDesiredOpenState();
      return;
    }
    unbindDetails();
    details = nextDetails;
    if (!details) return;

    if (!preferenceInitialized) {
      const storedOpen = host.sessionStorage.getItem(storageKey);
      desiredOpen = storedOpen === null ? details.open : storedOpen === '1';
      preferenceInitialized = true;
    }

    summary = details.querySelector(':scope > summary') || details.querySelector('summary');
    if (summary) summary.addEventListener('click', persistUserIntent, true);
    details.addEventListener('toggle', onToggle);
    detailsObserver = new MutationObserver(onDetailsMutation);
    detailsObserver.observe(details, { attributes: true, attributeFilter: ['open'] });
    restoreDesiredOpenState();
  };

  const bindScrollTarget = (nextScrollTarget) => {
    if (nextScrollTarget === scrollTarget) return;
    if (contentObserver) contentObserver.disconnect();
    if (scrollTarget) {
      scrollTarget.removeEventListener('scroll', onScroll);
      scrollTarget.classList.remove('franq-activity-timeline');
    }
    scrollTarget = nextScrollTarget;
    if (!scrollTarget) return;
    scrollTarget.classList.add('franq-activity-timeline');
    scrollTarget.addEventListener('scroll', onScroll, { passive: true });
    contentObserver = new MutationObserver(onContentMutation);
    contentObserver.observe(scrollTarget, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    requestAnimationFrame(scrollToBottom);
  };

  function bind() {
    const marker = findMarker();
    if (!marker) return;
    bindDetails(marker.closest('details'));
    bindScrollTarget(findVerticalScrollContainer(marker));
  }

  rootObserver = new MutationObserver(scheduleBind);
  rootObserver.observe(doc.body, { childList: true, subtree: true });
  bind();

  registry[executionId] = {
    cleanup: () => {
      if (rootObserver) rootObserver.disconnect();
      if (contentObserver) contentObserver.disconnect();
      if (detailsObserver) detailsObserver.disconnect();
      if (bindFrame !== null) cancelAnimationFrame(bindFrame);
      if (summary) summary.removeEventListener('click', persistUserIntent, true);
      if (details) details.removeEventListener('toggle', onToggle);
      if (scrollTarget) {
        scrollTarget.removeEventListener('scroll', onScroll);
        scrollTarget.classList.remove('franq-activity-timeline');
      }
    },
  };
})();
