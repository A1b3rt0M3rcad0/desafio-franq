import streamlit.components.v1 as components


def mount_sticky_chat_scroll() -> None:
    """Keep the chat pinned to the bottom until the user intentionally scrolls up.

    The behavior lives in the browser because scroll position is presentation state.
    A hard refresh intentionally starts pinned to the newest message.
    """

    components.html(
        """
<script>
(() => {
  const host = window.parent;
  const doc = host.document;
  const previous = host.__franqStickyScroll;
  if (previous && previous.cleanup) previous.cleanup();

  const main = doc.querySelector('[data-testid="stMain"]')
    || doc.querySelector('[data-testid="stAppViewContainer"]')
    || doc.scrollingElement;
  if (!main) return;

  const scrollTarget = main.scrollHeight > main.clientHeight
    ? main
    : (doc.scrollingElement || main);
  const threshold = 64;
  let pinned = true;
  let programmatic = false;

  const distanceFromBottom = () =>
    scrollTarget.scrollHeight - scrollTarget.scrollTop - scrollTarget.clientHeight;

  const scrollToBottom = () => {
    programmatic = true;
    scrollTarget.scrollTop = scrollTarget.scrollHeight;
    requestAnimationFrame(() => { programmatic = false; });
  };

  const onScroll = () => {
    if (programmatic) return;
    pinned = distanceFromBottom() <= threshold;
  };

  const observer = new MutationObserver(() => {
    if (pinned) requestAnimationFrame(scrollToBottom);
  });

  scrollTarget.addEventListener('scroll', onScroll, { passive: true });
  observer.observe(main, { childList: true, subtree: true, characterData: true });

  requestAnimationFrame(() => requestAnimationFrame(scrollToBottom));

  host.__franqStickyScroll = {
    cleanup: () => {
      observer.disconnect();
      scrollTarget.removeEventListener('scroll', onScroll);
    }
  };
})();
</script>
        """,
        height=0,
        width=0,
    )
