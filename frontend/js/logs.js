/**
 * METLINK — Activity and System Logs Module
 * Handles accessible tabbed inspection of harvest submissions, SMS dispatch logs,
 * and admin audit trail with URL hash synchronization, search, sorting, and pagination.
 */

// Route guard: ensure admin session is active
const currentAdmin = MetlinkAuth.requireAuth();

// Module state
const cache = {
  submissions: null,
  sms: null,
  audit: null
};

const state = {
  submissions: { page: 1, query: '', sortKey: null, sortDir: null },
  sms: { page: 1, query: '' },
  audit: { page: 1, query: '' }
};

const PAGE_SIZE = 25;
let activeTab = 'submissions';

// DOM References
const adminNameEl = document.getElementById('adminName');
const logoutBtn = document.getElementById('logoutBtn');
const refreshBtn = document.getElementById('refreshBtn');

const alertError = document.getElementById('alertError');
const alertErrorText = document.getElementById('alertErrorText');
const dismissAlertErrorBtn = document.getElementById('dismissAlertErrorBtn');

// Tab buttons & panels
const tabs = {
  submissions: document.getElementById('tab-submissions'),
  sms: document.getElementById('tab-sms'),
  audit: document.getElementById('tab-audit')
};

const panels = {
  submissions: document.getElementById('panel-submissions'),
  sms: document.getElementById('panel-sms'),
  audit: document.getElementById('panel-audit')
};

const searchInputs = {
  submissions: document.getElementById('search-submissions'),
  sms: document.getElementById('search-sms'),
  audit: document.getElementById('search-audit')
};

const showings = {
  submissions: document.getElementById('showing-submissions'),
  sms: document.getElementById('showing-sms'),
  audit: document.getElementById('showing-audit')
};

const loadings = {
  submissions: document.getElementById('loading-submissions'),
  sms: document.getElementById('loading-sms'),
  audit: document.getElementById('loading-audit')
};

const empties = {
  submissions: document.getElementById('empty-submissions'),
  sms: document.getElementById('empty-sms'),
  audit: document.getElementById('empty-audit')
};

const wrappers = {
  submissions: document.getElementById('wrapper-submissions'),
  sms: document.getElementById('wrapper-sms'),
  audit: document.getElementById('wrapper-audit')
};

const tbodies = {
  submissions: document.getElementById('tbody-submissions'),
  sms: document.getElementById('tbody-sms'),
  audit: document.getElementById('tbody-audit')
};

const paginations = {
  submissions: document.getElementById('pagination-submissions'),
  sms: document.getElementById('pagination-sms'),
  audit: document.getElementById('pagination-audit')
};

const pageInfos = {
  submissions: document.getElementById('page-info-submissions'),
  sms: document.getElementById('page-info-sms'),
  audit: document.getElementById('page-info-audit')
};

const prevBtns = {
  submissions: document.getElementById('prev-submissions'),
  sms: document.getElementById('prev-sms'),
  audit: document.getElementById('prev-audit')
};

const nextBtns = {
  submissions: document.getElementById('next-submissions'),
  sms: document.getElementById('next-sms'),
  audit: document.getElementById('next-audit')
};

/**
 * Display a persistent error banner at top of content area.
 */
function showErrorBanner(message) {
  alertErrorText.textContent = message;
  alertError.style.display = 'flex';
}

/**
 * Clear the error banner.
 */
function clearErrorBanner() {
  alertErrorText.textContent = '';
  alertError.style.display = 'none';
}

/**
 * Format timestamp into '15 Nov 2026, 14:32' style safely.
 */
function formatDateTime(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '-';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = d.getDate();
  const month = months[d.getMonth()];
  const year = d.getFullYear();
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  return `${day} ${month} ${year}, ${hours}:${minutes}`;
}

/**
 * Safely highlight occurrences of query in text and insert into element using DOM nodes.
 */
function highlightInto(element, text, query) {
  element.replaceChildren();
  const rawText = text == null ? '' : String(text);
  const trimmed = (query || '').trim();

  if (!trimmed || !rawText) {
    element.textContent = rawText;
    return;
  }

  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  const parts = rawText.split(regex);

  for (const part of parts) {
    if (!part) continue;
    if (part.toLowerCase() === trimmed.toLowerCase()) {
      const mark = document.createElement('mark');
      mark.className = 'search-highlight';
      mark.textContent = part;
      element.appendChild(mark);
    } else {
      element.appendChild(document.createTextNode(part));
    }
  }
}

/**
 * Create a Submissions table row using safe DOM methods and outline pills.
 */
function createSubmissionRow(s, query) {
  const tr = document.createElement('tr');

  // 1. Submitted Time (no highlight)
  const tdDate = document.createElement('td');
  tdDate.textContent = formatDateTime(s.created_at);
  tr.appendChild(tdDate);

  // 2. Farmer & Phone
  const tdFarmer = document.createElement('td');
  const farmerName = document.createElement('div');
  farmerName.style.fontWeight = '600';
  highlightInto(farmerName, s.farmer_name || '-', query);
  tdFarmer.appendChild(farmerName);

  if (s.phone_number) {
    const farmerPhone = document.createElement('div');
    farmerPhone.className = 'condition-meta';
    farmerPhone.style.marginTop = '2px';
    highlightInto(farmerPhone, s.phone_number, query);
    tdFarmer.appendChild(farmerPhone);
  }
  tr.appendChild(tdFarmer);

  // 3. Location
  const tdLoc = document.createElement('td');
  highlightInto(tdLoc, s.location || '-', query);
  tr.appendChild(tdLoc);

  // 4. Tomato Maturity (pill-w-sm: 72px)
  const tdMat = document.createElement('td');
  const matBadge = document.createElement('span');
  const mat = (s.tomato_maturity || '').toUpperCase();
  if (mat === 'GREEN') {
    matBadge.className = 'badge badge-green pill-w-sm';
  } else if (mat === 'TURNING') {
    matBadge.className = 'badge badge-amber pill-w-sm';
  } else if (mat === 'RIPE') {
    matBadge.className = 'badge badge-red pill-w-sm';
  } else {
    matBadge.className = 'badge badge-slate pill-w-sm';
  }
  const matText = s.tomato_maturity ? (s.tomato_maturity.charAt(0).toUpperCase() + s.tomato_maturity.slice(1).toLowerCase()) : '-';
  highlightInto(matBadge, matText, query);
  tdMat.appendChild(matBadge);
  tr.appendChild(tdMat);

  // 5. Quantity (no highlight, standard unit)
  const tdQty = document.createElement('td');
  tdQty.textContent = s.quantity_kg ? `${s.quantity_kg} kg` : '-';
  tr.appendChild(tdQty);

  // 6. Suitable Storage (pill-w-sm: 72px, green for Yes, slate for No)
  const tdPres = document.createElement('td');
  const presBadge = document.createElement('span');
  if (s.has_suitable_preservation) {
    presBadge.className = 'badge badge-green pill-w-sm';
    highlightInto(presBadge, 'Yes', query);
  } else {
    presBadge.className = 'badge badge-slate pill-w-sm';
    highlightInto(presBadge, 'No', query);
  }
  tdPres.appendChild(presBadge);
  tr.appendChild(tdPres);

  // 7. Status (pill-w-md: 92px)
  const tdStatus = document.createElement('td');
  const statusBadge = document.createElement('span');
  const st = (s.status || '').toUpperCase();
  if (st === 'PROCESSED') {
    statusBadge.className = 'badge badge-green pill-w-md';
  } else if (st === 'PENDING') {
    statusBadge.className = 'badge badge-amber pill-w-md';
  } else if (st === 'CANCELLED') {
    statusBadge.className = 'badge badge-red pill-w-md';
  } else {
    statusBadge.className = 'badge badge-slate pill-w-md';
  }
  const statusText = s.status ? (s.status.charAt(0).toUpperCase() + s.status.slice(1).toLowerCase()) : '-';
  highlightInto(statusBadge, statusText, query);
  tdStatus.appendChild(statusBadge);
  tr.appendChild(tdStatus);

  // 8. Advice Result / Recommended Action (pill-w-xl: 200px)
  const tdAdvice = document.createElement('td');
  if (s.recommended_action) {
    const actBadge = document.createElement('span');
    const act = s.recommended_action.toUpperCase();
    let actText = '';
    if (act === 'SELL_NOW') {
      actBadge.className = 'badge badge-green pill-w-xl';
      actText = 'Sell now';
    } else if (act === 'STORE_AND_WAIT') {
      actBadge.className = 'badge badge-amber pill-w-xl';
      actText = 'Store and wait';
    } else if (act === 'SEEK_ALTERNATIVE_MARKET') {
      actBadge.className = 'badge badge-blue pill-w-xl';
      actText = 'Seek alternative market';
    } else {
      actBadge.className = 'badge badge-slate pill-w-xl';
      actText = s.recommended_action;
    }
    highlightInto(actBadge, actText, query);
    tdAdvice.appendChild(actBadge);

    // Second line for "Wait N days" or recommendation reason
    if (s.waiting_period_days) {
      const waitDiv = document.createElement('div');
      waitDiv.className = 'condition-meta';
      waitDiv.style.marginTop = '4px';
      highlightInto(waitDiv, `Wait ${s.waiting_period_days} days`, query);
      tdAdvice.appendChild(waitDiv);
    } else if (s.recommendation_reason) {
      const reasonDiv = document.createElement('div');
      reasonDiv.className = 'condition-meta';
      reasonDiv.style.marginTop = '4px';
      highlightInto(reasonDiv, s.recommendation_reason, query);
      tdAdvice.appendChild(reasonDiv);
    }
  } else {
    tdAdvice.textContent = '-';
  }
  tr.appendChild(tdAdvice);

  return tr;
}

/**
 * Create an SMS Logs table row using safe DOM methods and outline pills.
 */
function createSmsRow(sms, query) {
  const tr = document.createElement('tr');

  // 1. Sent Time (no highlight)
  const tdTime = document.createElement('td');
  tdTime.textContent = formatDateTime(sms.sent_at);
  tr.appendChild(tdTime);

  // 2. Provider ID (truncated with full value in title attribute, '-' when empty)
  const tdProvider = document.createElement('td');
  tdProvider.className = 'desc-cell';
  tdProvider.title = sms.provider_id || '';
  const fullProv = sms.provider_id || '-';
  const dispProv = fullProv.length > 16 ? `${fullProv.slice(0, 16)}...` : fullProv;
  highlightInto(tdProvider, dispProv, query);
  tr.appendChild(tdProvider);

  // 3. Recipient (phone + farmer name)
  const tdRecip = document.createElement('td');
  const phoneDiv = document.createElement('div');
  phoneDiv.style.fontWeight = '600';
  highlightInto(phoneDiv, sms.phone_number || '-', query);
  tdRecip.appendChild(phoneDiv);

  if (sms.farmer_name) {
    const nameDiv = document.createElement('div');
    nameDiv.className = 'condition-meta';
    nameDiv.style.marginTop = '2px';
    highlightInto(nameDiv, sms.farmer_name, query);
    tdRecip.appendChild(nameDiv);
  }
  tr.appendChild(tdRecip);

  // 3. Message Content (truncated to 80 chars, full tooltip)
  const tdMsg = document.createElement('td');
  tdMsg.className = 'desc-cell';
  tdMsg.title = sms.message || '';
  const fullMsg = sms.message || '-';
  const dispMsg = fullMsg.length > 80 ? `${fullMsg.slice(0, 80)}...` : fullMsg;
  highlightInto(tdMsg, dispMsg, query);
  tr.appendChild(tdMsg);

  // 4. Delivery Status (pill-w-md: 92px)
  const tdStatus = document.createElement('td');
  const badge = document.createElement('span');
  const st = (sms.status || '').toUpperCase();
  if (st === 'DELIVERED') {
    badge.className = 'badge badge-green pill-w-md';
  } else if (st === 'FAILED') {
    badge.className = 'badge badge-red pill-w-md';
  } else {
    badge.className = 'badge badge-amber pill-w-md';
  }
  const stText = sms.status ? (sms.status.charAt(0).toUpperCase() + sms.status.slice(1).toLowerCase()) : '-';
  highlightInto(badge, stText, query);
  tdStatus.appendChild(badge);
  tr.appendChild(tdStatus);

  // 5. Delivered At (no highlight)
  const tdDelivered = document.createElement('td');
  tdDelivered.textContent = sms.delivered_at ? formatDateTime(sms.delivered_at) : '-';
  tr.appendChild(tdDelivered);

  return tr;
}

/**
 * Create an Audit Logs table row using safe DOM methods and outline pills.
 */
function createAuditRow(log, query) {
  const tr = document.createElement('tr');

  // 1. Timestamp (no highlight)
  const tdTime = document.createElement('td');
  tdTime.textContent = formatDateTime(log.created_at);
  tr.appendChild(tdTime);

  // 2. Administrator
  const tdAdmin = document.createElement('td');
  tdAdmin.style.fontWeight = '600';
  highlightInto(tdAdmin, log.admin_name || log.username || '-', query);
  tr.appendChild(tdAdmin);

  // 3. Action Badge (pill-w-md: 92px)
  const tdAction = document.createElement('td');
  const badge = document.createElement('span');
  const act = (log.action || '').toUpperCase();
  if (act === 'CREATE' || act === 'ACTIVATE') {
    badge.className = 'badge badge-green pill-w-md';
  } else if (act === 'UPDATE') {
    badge.className = 'badge badge-blue pill-w-md';
  } else if (act === 'DEACTIVATE') {
    badge.className = 'badge badge-red pill-w-md';
  } else {
    badge.className = 'badge badge-slate pill-w-md';
  }
  const actText = act || '-';
  highlightInto(badge, actText, query);
  tdAction.appendChild(badge);
  tr.appendChild(tdAction);

  // 4. Target Entity
  const tdEntity = document.createElement('td');
  highlightInto(tdEntity, log.entity || '-', query);
  tr.appendChild(tdEntity);

  // 5. Record ID (no highlight)
  const tdRecord = document.createElement('td');
  tdRecord.textContent = log.record_id ? `#${log.record_id}` : '-';
  tr.appendChild(tdRecord);

  // 6. Details
  const tdDetails = document.createElement('td');
  tdDetails.className = 'desc-cell';
  tdDetails.title = log.details || '';
  highlightInto(tdDetails, log.details || '-', query);
  tr.appendChild(tdDetails);

  return tr;
}

/**
 * Filter data for a given tab using search query.
 */
function getFilteredData(tabName) {
  const data = cache[tabName] || [];
  const query = state[tabName].query.toLowerCase().trim();

  if (!query) return data;

  if (tabName === 'submissions') {
    return data.filter(item => {
      const fName = (item.farmer_name || '').toLowerCase();
      const phone = (item.phone_number || '').toLowerCase();
      const loc = (item.location || '').toLowerCase();
      const mat = (item.tomato_maturity || '').toLowerCase();
      const storage = item.has_suitable_preservation ? 'yes' : 'no';
      const st = (item.status || '').toLowerCase();
      const act = (item.recommended_action || '').toLowerCase();
      const actPretty = act.replace(/_/g, ' ');
      const reason = (item.recommendation_reason || '').toLowerCase();
      const waitDays = item.waiting_period_days ? `wait ${item.waiting_period_days} days` : '';

      return fName.includes(query) || phone.includes(query) || loc.includes(query) ||
             mat.includes(query) || storage.includes(query) || st.includes(query) ||
             act.includes(query) || actPretty.includes(query) || reason.includes(query) ||
             waitDays.includes(query);
    });
  }

  if (tabName === 'sms') {
    return data.filter(item => {
      const phone = (item.phone_number || '').toLowerCase();
      const name = (item.farmer_name || '').toLowerCase();
      const msg = (item.message || '').toLowerCase();
      const st = (item.status || '').toLowerCase();
      const prov = (item.provider_id || '').toLowerCase();
      return phone.includes(query) || name.includes(query) || msg.includes(query) || st.includes(query) || prov.includes(query);
    });
  }

  if (tabName === 'audit') {
    return data.filter(item => {
      const admin = (item.admin_name || '').toLowerCase();
      const user = (item.username || '').toLowerCase();
      const act = (item.action || '').toLowerCase();
      const entity = (item.entity || '').toLowerCase();
      const det = (item.details || '').toLowerCase();
      return admin.includes(query) || user.includes(query) || act.includes(query) ||
             entity.includes(query) || det.includes(query);
    });
  }

  return data;
}

/**
 * Sort Submissions list according to sortKey and sortDir, or default to newest first.
 */
function getSortedData(tabName, list) {
  if (tabName !== 'submissions') {
    return list;
  }

  if (!state.submissions.sortKey || !state.submissions.sortDir) {
    return [...list].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
  }

  const key = state.submissions.sortKey;
  const factor = state.submissions.sortDir === 'asc' ? 1 : -1;

  return [...list].sort((a, b) => {
    let valA = '';
    let valB = '';

    if (key === 'has_suitable_preservation') {
      valA = a.has_suitable_preservation ? 'Yes' : 'No';
      valB = b.has_suitable_preservation ? 'Yes' : 'No';
    } else {
      valA = a[key] == null ? '' : String(a[key]);
      valB = b[key] == null ? '' : String(b[key]);
    }

    if (!valA && valB) return 1;
    if (valA && !valB) return -1;
    if (!valA && !valB) return 0;

    const cmp = valA.localeCompare(valB, undefined, { sensitivity: 'base' }) * factor;
    if (cmp !== 0) return cmp;
    return new Date(b.created_at || 0) - new Date(a.created_at || 0);
  });
}

/**
 * Update aria-sort attribute on Submissions table headers.
 */
function updateSubmissionsSortHeaders() {
  const headers = document.querySelectorAll('#panel-submissions th[data-sort]');
  headers.forEach(th => {
    const key = th.getAttribute('data-sort');
    if (state.submissions.sortKey === key) {
      th.setAttribute('aria-sort', state.submissions.sortDir === 'asc' ? 'ascending' : 'descending');
    } else {
      th.setAttribute('aria-sort', 'none');
    }
  });
}

/**
 * Toggle sorting on Submissions tab headers.
 */
function handleSubmissionsSort(key) {
  if (state.submissions.sortKey === key) {
    state.submissions.sortDir = state.submissions.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    state.submissions.sortKey = key;
    state.submissions.sortDir = 'asc';
  }
  updateSubmissionsSortHeaders();
  state.submissions.page = 1;
  renderTab('submissions');
}

/**
 * Initialize click and keyboard listeners on Submissions sort headers.
 */
function initSubmissionsSortHeaders() {
  const headers = document.querySelectorAll('#panel-submissions th[data-sort]');
  headers.forEach(th => {
    th.addEventListener('click', () => {
      const key = th.getAttribute('data-sort');
      handleSubmissionsSort(key);
    });
    th.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const key = th.getAttribute('data-sort');
        handleSubmissionsSort(key);
      }
    });
  });
}

/**
 * Render table and pagination for a given tab.
 */
function renderTab(tabName) {
  const tbody = tbodies[tabName];
  const emptyEl = empties[tabName];
  const wrapperEl = wrappers[tabName];
  const paginationEl = paginations[tabName];
  const pageInfoEl = pageInfos[tabName];
  const prevBtn = prevBtns[tabName];
  const nextBtn = nextBtns[tabName];
  const showingEl = showings[tabName];

  tbody.replaceChildren();

  const rawData = cache[tabName] || [];
  const filtered = getFilteredData(tabName);
  const sorted = getSortedData(tabName, filtered);
  const totalFiltered = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));

  if (state[tabName].page > totalPages) {
    state[tabName].page = totalPages;
  }
  const currentPage = state[tabName].page;

  if (rawData.length === 0) {
    wrapperEl.style.display = 'none';
    paginationEl.style.display = 'none';
    emptyEl.style.display = 'block';
    emptyEl.querySelector('p').textContent = `No ${tabName === 'sms' ? 'SMS logs' : tabName} found.`;
    showingEl.textContent = 'Showing 0 of 0';
    return;
  }

  if (totalFiltered === 0) {
    wrapperEl.style.display = 'none';
    paginationEl.style.display = 'none';
    emptyEl.style.display = 'block';
    emptyEl.querySelector('p').textContent = 'No records match your search.';
    showingEl.textContent = `Showing 0 of ${rawData.length}`;
    return;
  }

  emptyEl.style.display = 'none';
  wrapperEl.style.display = 'block';

  // Compute page slice
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, totalFiltered);
  const pageItems = sorted.slice(startIndex, endIndex);
  const currentQuery = state[tabName].query;

  for (const item of pageItems) {
    if (tabName === 'submissions') tbody.appendChild(createSubmissionRow(item, currentQuery));
    else if (tabName === 'sms') tbody.appendChild(createSmsRow(item, currentQuery));
    else if (tabName === 'audit') tbody.appendChild(createAuditRow(item, currentQuery));
  }

  // Update counters & pagination
  showingEl.textContent = `Showing ${startIndex + 1} to ${endIndex} of ${totalFiltered}`;
  pageInfoEl.textContent = `Page ${currentPage} of ${totalPages}`;

  if (totalPages > 1) {
    paginationEl.style.display = 'flex';
    prevBtn.disabled = (currentPage === 1);
    nextBtn.disabled = (currentPage === totalPages);
  } else {
    paginationEl.style.display = 'none';
  }
}

/**
 * Fetch and sort data lazily for a specific tab.
 */
async function loadTabData(tabName) {
  clearErrorBanner();
  const loadingEl = loadings[tabName];
  const wrapperEl = wrappers[tabName];
  const emptyEl = empties[tabName];
  const paginationEl = paginations[tabName];

  loadingEl.style.display = 'block';
  wrapperEl.style.display = 'none';
  emptyEl.style.display = 'none';
  paginationEl.style.display = 'none';

  try {
    let endpoint = '/submissions';
    let dataKey = 'submissions';
    if (tabName === 'sms') {
      endpoint = '/sms-logs';
      dataKey = 'sms_logs';
    } else if (tabName === 'audit') {
      endpoint = '/audit-logs';
      dataKey = 'audit_logs';
    }

    const res = await MetlinkAPI.get(endpoint);
    const list = (res && res[dataKey]) || [];

    // Sort newest first by timestamp field
    if (tabName === 'sms') {
      list.sort((a, b) => new Date(b.sent_at || 0) - new Date(a.sent_at || 0));
    } else {
      list.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    }

    cache[tabName] = list;
    state[tabName].page = 1;
    renderTab(tabName);
  } catch (err) {
    showErrorBanner(err.message || `Failed to load ${tabName} data.`);
  } finally {
    loadingEl.style.display = 'none';
  }
}

/**
 * Switch active tab with URL hash support and accessibility states.
 */
function switchTab(tabName, updateHash = true) {
  if (!tabs[tabName]) tabName = 'submissions';
  activeTab = tabName;

  for (const [key, btn] of Object.entries(tabs)) {
    const isCurrent = (key === tabName);
    btn.setAttribute('aria-selected', isCurrent ? 'true' : 'false');
    btn.setAttribute('tabindex', isCurrent ? '0' : '-1');
    panels[key].hidden = !isCurrent;
  }

  if (updateHash) {
    history.replaceState(null, '', `#${tabName}`);
  }

  // Load lazily if not yet cached
  if (cache[tabName] === null) {
    loadTabData(tabName);
  } else {
    renderTab(tabName);
  }
}

/**
 * Handle keyboard arrow navigation across tabs.
 */
function handleTabKeydown(e) {
  const tabKeys = ['submissions', 'sms', 'audit'];
  const currentIndex = tabKeys.indexOf(activeTab);

  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    const nextIndex = (currentIndex + 1) % tabKeys.length;
    const nextTab = tabKeys[nextIndex];
    tabs[nextTab].focus();
    switchTab(nextTab);
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    const prevIndex = (currentIndex - 1 + tabKeys.length) % tabKeys.length;
    const prevTab = tabKeys[prevIndex];
    tabs[prevTab].focus();
    switchTab(prevTab);
  }
}

/**
 * Initialize active tab from URL hash.
 */
function initTabFromHash() {
  const hash = window.location.hash.replace('#', '').toLowerCase();
  if (hash === 'sms' || hash === 'sms-logs') {
    switchTab('sms', false);
  } else if (hash === 'audit' || hash === 'audit-logs') {
    switchTab('audit', false);
  } else {
    switchTab('submissions', false);
  }
}

// Event Listeners
if (currentAdmin && adminNameEl) {
  adminNameEl.textContent = currentAdmin.full_name || currentAdmin.username;
}

if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    MetlinkAuth.logout();
  });
}

if (dismissAlertErrorBtn) {
  dismissAlertErrorBtn.addEventListener('click', () => {
    clearErrorBanner();
  });
}

// Refresh active tab
refreshBtn.addEventListener('click', () => {
  loadTabData(activeTab);
});

// Tab button clicks and keyboard navigation
for (const [key, btn] of Object.entries(tabs)) {
  btn.addEventListener('click', () => switchTab(key));
  btn.addEventListener('keydown', handleTabKeydown);
}

// Search inputs live filtering
for (const [key, input] of Object.entries(searchInputs)) {
  input.addEventListener('input', () => {
    state[key].query = input.value;
    state[key].page = 1;
    renderTab(key);
  });
}

// Pagination controls
for (const [key, btn] of Object.entries(prevBtns)) {
  btn.addEventListener('click', () => {
    if (state[key].page > 1) {
      state[key].page--;
      renderTab(key);
    }
  });
}

for (const [key, btn] of Object.entries(nextBtns)) {
  btn.addEventListener('click', () => {
    state[key].page++;
    renderTab(key);
  });
}

// Hash change listener
window.addEventListener('hashchange', () => {
  initTabFromHash();
});

// Initialize sorting on Submissions tab
initSubmissionsSortHeaders();

// Initial tab activation
if (currentAdmin) {
  initTabFromHash();
}
