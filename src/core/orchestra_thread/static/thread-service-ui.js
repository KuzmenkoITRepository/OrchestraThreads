const state = {
  scope: "active",
  search: "",
  selectedThreadId: null,
  autoRefresh: true,
  threadsByScope: {
    active: [],
    all: [],
  },
};

const elements = {
  autoRefreshToggle: document.getElementById("autoRefreshToggle"),
  refreshButton: document.getElementById("refreshButton"),
  searchInput: document.getElementById("searchInput"),
  scopeSummary: document.getElementById("scopeSummary"),
  threadList: document.getElementById("threadList"),
  globalStatus: document.getElementById("globalStatus"),
  emptyState: document.getElementById("emptyState"),
  detailView: document.getElementById("detailView"),
  heroBadges: document.getElementById("heroBadges"),
  threadTitle: document.getElementById("threadTitle"),
  threadSubtitle: document.getElementById("threadSubtitle"),
  ownerValue: document.getElementById("ownerValue"),
  peerValue: document.getElementById("peerValue"),
  updatedValue: document.getElementById("updatedValue"),
  threadIdValue: document.getElementById("threadIdValue"),
  participantsGrid: document.getElementById("participantsGrid"),
  contextGrid: document.getElementById("contextGrid"),
  relationshipSummary: document.getElementById("relationshipSummary"),
  threadTree: document.getElementById("threadTree"),
  eventsList: document.getElementById("eventsList"),
  tabs: Array.from(document.querySelectorAll(".tab")),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function shortId(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "n/a";
  }
  return text.length > 12 ? `${text.slice(0, 8)}…${text.slice(-4)}` : text;
}

function formatTime(value) {
  if (!value) {
    return "n/a";
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function badge(label, className = "") {
  return `<span class="badge ${className}">${escapeHtml(label)}</span>`;
}

function threadBadges(thread) {
  const items = [
    badge(thread.status, `status-${thread.status}`),
    badge(thread.thread_scope),
  ];
  if (Number(thread.child_thread_count || 0) > 0) {
    items.push(badge(`${thread.child_thread_count} child`));
  }
  if (Number(thread.pending_delivery_count || 0) > 0) {
    items.push(badge(`${thread.pending_delivery_count} pending`));
  }
  return items.join("");
}

function renderThreadList() {
  const threads = state.threadsByScope[state.scope] || [];
  const search = state.search.trim().toLowerCase();
  const filtered = threads.filter((thread) => {
    if (!search) {
      return true;
    }
    const haystack = [
      thread.thread_id,
      thread.root_thread_id,
      thread.parent_thread_id,
      thread.status,
      thread.owner_agent_slug,
      thread.roles?.peer_agent_slug,
      thread.agents?.owner?.display_name,
      thread.agents?.peer?.display_name,
      thread.pair_label,
      thread.last_event?.message_preview,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(search);
  });

  elements.scopeSummary.textContent = `${filtered.length} thread(s)`;
  if (!filtered.length) {
    elements.threadList.innerHTML = `<div class="empty-placeholder">No threads match the current view.</div>`;
    return;
  }

  elements.threadList.innerHTML = filtered
    .map((thread) => {
      const selectedClass = thread.thread_id === state.selectedThreadId ? "is-selected" : "";
      const lastEvent = thread.last_event;
      const meta = `${thread.agents.owner.display_name} owns • ${thread.agents.peer.display_name} peer`;
      return `
        <button class="thread-card ${selectedClass}" type="button" data-thread-id="${escapeHtml(thread.thread_id)}">
          <div class="thread-card-top">
            <div class="badge-row">${threadBadges(thread)}</div>
            <span class="badge">${escapeHtml(shortId(thread.thread_id))}</span>
          </div>
          <div class="thread-card-title">${escapeHtml(thread.pair_label)}</div>
          <div class="thread-card-subtitle">${escapeHtml(meta)}</div>
          <div class="thread-card-bottom">
            <span class="badge">events ${escapeHtml(thread.event_count)}</span>
            <span class="badge">updated ${escapeHtml(formatTime(thread.updated_at))}</span>
          </div>
          <div class="thread-card-preview">${
            lastEvent
              ? `${escapeHtml(lastEvent.event_kind)} • ${escapeHtml(lastEvent.message_preview)}`
              : "No events yet."
          }</div>
        </button>
      `;
    })
    .join("");

  elements.threadList.querySelectorAll("[data-thread-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const threadId = button.getAttribute("data-thread-id");
      if (threadId) {
        selectThread(threadId);
      }
    });
  });
}

function renderParticipants(thread) {
  const roles = [
    { label: "Owner", card: thread.agents.owner },
    { label: "Peer", card: thread.agents.peer },
    { label: "Participant A", card: thread.agents.participant_a },
    { label: "Participant B", card: thread.agents.participant_b },
  ];
  elements.participantsGrid.innerHTML = roles
    .map(({ label, card }) => `
      <div class="detail-chip">
        <small>${escapeHtml(label)}</small>
        <strong>${escapeHtml(card.display_name || card.slug)}</strong>
        <div class="badge-row">
          ${badge(card.slug, "mono")}
          ${badge(card.agent_type)}
          ${badge(card.backend_type)}
          ${badge(card.active ? "active" : "inactive")}
        </div>
      </div>
    `)
    .join("");
}

function renderContext(thread, related) {
  const rows = [
    ["Status", thread.status],
    ["Root Thread", thread.root_thread_id || "n/a"],
    ["Parent Thread", thread.parent_thread_id || "n/a"],
    ["Events", thread.event_count ?? "0"],
    ["Pending Delivery", thread.pending_delivery_count ?? "0"],
    ["Last Activity", formatTime(thread.last_activity_at)],
    ["Last Sender", thread.last_message_sender_agent_slug || "n/a"],
    ["Created", formatTime(thread.created_at)],
    ["Updated", formatTime(thread.updated_at)],
    ["Terminal At", formatTime(thread.terminal_at)],
    ["Parent Exists", related.parent_thread ? "yes" : "no"],
    ["Child Threads", String((related.child_threads || []).length)],
  ];
  elements.contextGrid.innerHTML = rows
    .map(([label, value]) => `
      <div>
        <dt>${escapeHtml(label)}</dt>
        <dd class="${String(value).length > 24 ? "mono" : ""}">${escapeHtml(value)}</dd>
      </div>
    `)
    .join("");
}

function renderRelationshipSummary(thread, related) {
  const cards = [
    {
      label: "Root Thread",
      value: related.root_thread ? shortId(related.root_thread.thread_id) : "n/a",
      extra: related.root_thread ? related.root_thread.pair_label : "Missing",
    },
    {
      label: "Parent Thread",
      value: related.parent_thread ? shortId(related.parent_thread.thread_id) : "none",
      extra: related.parent_thread ? related.parent_thread.pair_label : "This thread is root",
    },
    {
      label: "Child Threads",
      value: String((related.child_threads || []).length),
      extra: (related.child_threads || []).length ? "Direct descendants available below" : "No direct children",
    },
  ];
  elements.relationshipSummary.innerHTML = cards
    .map((card) => `
      <div class="relationship-card">
        <small>${escapeHtml(card.label)}</small>
        <strong>${escapeHtml(card.value)}</strong>
        <div class="thread-card-subtitle">${escapeHtml(card.extra)}</div>
      </div>
    `)
    .join("");
}

function renderThreadTree(related) {
  const group = related.root_group || [];
  if (!group.length) {
    elements.threadTree.innerHTML = `<div class="empty-placeholder">No related threads found.</div>`;
    return;
  }

  const byParent = new Map();
  for (const thread of group) {
    const key = thread.parent_thread_id || "__root__";
    const bucket = byParent.get(key) || [];
    bucket.push(thread);
    byParent.set(key, bucket);
  }

  const root = group.find((thread) => thread.thread_id === thread.root_thread_id) || group[0];

  function renderNode(thread, depth = 0) {
    const children = byParent.get(thread.thread_id) || [];
    const selectedClass = thread.thread_id === state.selectedThreadId ? "is-selected" : "";
    return `
      <div class="${depth > 0 ? "tree-level" : ""}">
        <div class="tree-thread ${selectedClass}" data-thread-tree-id="${escapeHtml(thread.thread_id)}">
          <div class="tree-thread-head">
            <strong>${escapeHtml(thread.pair_label)}</strong>
            ${badge(thread.status, `status-${thread.status}`)}
          </div>
          <div class="tree-thread-meta">
            ${escapeHtml(shortId(thread.thread_id))} • owner ${escapeHtml(thread.agents.owner.display_name)}
          </div>
        </div>
        ${children.map((child) => renderNode(child, depth + 1)).join("")}
      </div>
    `;
  }

  elements.threadTree.innerHTML = renderNode(root, 0);
  elements.threadTree.querySelectorAll("[data-thread-tree-id]").forEach((node) => {
    node.addEventListener("click", () => {
      const threadId = node.getAttribute("data-thread-tree-id");
      if (threadId) {
        selectThread(threadId);
      }
    });
  });
}

function renderEvents(events) {
  if (!events.length) {
    elements.eventsList.innerHTML = `<div class="empty-placeholder">No events in this thread yet.</div>`;
    return;
  }
  elements.eventsList.innerHTML = events
    .map((event) => {
      const kindClass =
        event.event_kind === "notification"
          ? `kind-notification-${event.notification_status || "generic"}`
          : `kind-${event.event_kind}`;
      const badges = [
        badge(
          event.event_kind === "notification"
            ? `notification:${event.notification_status || "unknown"}`
            : event.event_kind,
          kindClass
        ),
      ];
      if (event.interrupts_runtime || event.requires_action) {
        badges.push(badge("interrupts runtime"));
      }
      if (event.requires_response) {
        badges.push(badge("requires response"));
      }
      if (event.pending_delivery) {
        badges.push(badge("pending delivery"));
      }
      if (event.delivery_attempt_count) {
        badges.push(badge(`attempts ${event.delivery_attempt_count}`));
      }
      return `
        <article class="event-card">
          <div class="event-card-header">
            <div>
              <div class="badge-row">${badges.join("")}</div>
              <div class="event-route">
                <strong>${escapeHtml(event.from_agent.display_name)}</strong>
                <span>→</span>
                <strong>${escapeHtml(event.to_agent.display_name)}</strong>
              </div>
              <div class="event-meta">
                <span class="mono">#${escapeHtml(event.sequence_no)}</span>
                <span>${escapeHtml(formatTime(event.created_at))}</span>
              </div>
            </div>
            <time datetime="${escapeHtml(event.created_at || "")}">${escapeHtml(formatTime(event.created_at))}</time>
          </div>
          <pre class="event-body">${escapeHtml(event.message_text || "")}</pre>
          ${
            event.last_delivery_error
              ? `<div class="thread-card-preview">delivery error: ${escapeHtml(event.last_delivery_error)}</div>`
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function renderThreadDetail(payload) {
  const thread = payload.thread;
  const related = payload.related || {};
  elements.emptyState.hidden = true;
  elements.detailView.hidden = false;

  elements.heroBadges.innerHTML = threadBadges(thread);
  elements.threadTitle.textContent = thread.pair_label;
  elements.threadSubtitle.textContent = `${thread.thread_scope} thread • owner ${thread.agents.owner.display_name} • peer ${thread.agents.peer.display_name}`;
  elements.ownerValue.textContent = `${thread.agents.owner.display_name} (${thread.owner_agent_slug})`;
  elements.peerValue.textContent = `${thread.agents.peer.display_name} (${thread.roles.peer_agent_slug || "n/a"})`;
  elements.updatedValue.textContent = formatTime(thread.updated_at);
  elements.threadIdValue.textContent = thread.thread_id;

  renderParticipants(thread);
  renderContext(thread, related);
  renderRelationshipSummary(thread, related);
  renderThreadTree(related);
  renderEvents(payload.events || []);
}

async function fetchJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const payload = await response.json();
  if (!response.ok || payload.success === false) {
    const message = payload.error || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function refreshThreads({ keepDetail = true } = {}) {
  try {
    elements.globalStatus.textContent = "Refreshing thread list…";
    const payload = await fetchJson(`/api/v1/threads?scope=${encodeURIComponent(state.scope)}&limit=400`);
    state.threadsByScope[state.scope] = payload.threads || [];
    if (
      state.selectedThreadId &&
      keepDetail &&
      !state.threadsByScope[state.scope].some((thread) => thread.thread_id === state.selectedThreadId) &&
      state.scope === "active"
    ) {
      state.selectedThreadId = null;
    }
    renderThreadList();
    elements.globalStatus.textContent = `Updated ${formatTime(new Date().toISOString())}`;
    if (state.selectedThreadId) {
      await loadThreadDetail(state.selectedThreadId);
    } else {
      elements.emptyState.hidden = false;
      elements.detailView.hidden = true;
    }
  } catch (error) {
    elements.globalStatus.textContent = `Failed to load threads: ${error.message}`;
  }
}

async function loadThreadDetail(threadId) {
  try {
    const payload = await fetchJson(`/api/v1/threads/${encodeURIComponent(threadId)}?limit=400`);
    renderThreadDetail(payload);
    window.location.hash = `thread=${threadId}`;
  } catch (error) {
    elements.globalStatus.textContent = `Failed to load thread ${shortId(threadId)}: ${error.message}`;
  }
}

async function selectThread(threadId) {
  state.selectedThreadId = threadId;
  renderThreadList();
  await loadThreadDetail(threadId);
}

function applyTab(scope) {
  state.scope = scope;
  elements.tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.scope === scope);
  });
  refreshThreads({ keepDetail: true });
}

function readThreadIdFromHash() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash.startsWith("thread=")) {
    return null;
  }
  return decodeURIComponent(hash.slice("thread=".length));
}

function bindEvents() {
  elements.tabs.forEach((tab) => {
    tab.addEventListener("click", () => applyTab(tab.dataset.scope));
  });

  elements.refreshButton.addEventListener("click", () => refreshThreads({ keepDetail: true }));

  elements.searchInput.addEventListener("input", (event) => {
    state.search = event.target.value || "";
    renderThreadList();
  });

  elements.autoRefreshToggle.addEventListener("change", (event) => {
    state.autoRefresh = Boolean(event.target.checked);
  });

  window.addEventListener("hashchange", async () => {
    const threadId = readThreadIdFromHash();
    if (threadId && threadId !== state.selectedThreadId) {
      state.selectedThreadId = threadId;
      await loadThreadDetail(threadId);
      renderThreadList();
    }
  });
}

async function bootstrap() {
  bindEvents();
  const threadIdFromHash = readThreadIdFromHash();
  if (threadIdFromHash) {
    state.selectedThreadId = threadIdFromHash;
  }
  await refreshThreads({ keepDetail: false });
  if (state.selectedThreadId) {
    await loadThreadDetail(state.selectedThreadId);
  }
  window.setInterval(() => {
    if (state.autoRefresh) {
      refreshThreads({ keepDetail: true });
    }
  }, 5000);
}

bootstrap();
