/**
 * METLINK — Markets Management Module
 * Handles viewing, adding, editing, and activating/deactivating Kigali and local tomato market prices.
 */

// Route guard: ensure admin session is active
const currentAdmin = MetlinkAuth.requireAuth();

// Module state
let allMarkets = [];
let currentEditingMarket = null;
let successTimer = null;

// DOM References
const adminNameEl = document.getElementById('adminName');
const logoutBtn = document.getElementById('logoutBtn');

const alertSuccess = document.getElementById('alertSuccess');
const alertSuccessText = document.getElementById('alertSuccessText');
const alertError = document.getElementById('alertError');
const alertErrorText = document.getElementById('alertErrorText');
const dismissAlertErrorBtn = document.getElementById('dismissAlertErrorBtn');

const totalCountEl = document.getElementById('totalCount');
const activeCountEl = document.getElementById('activeCount');
const avgPriceCountEl = document.getElementById('avgPriceCount');

const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const demandFilter = document.getElementById('demandFilter');
const showingCountText = document.getElementById('showingCountText');

const tableLoading = document.getElementById('tableLoading');
const tableEmpty = document.getElementById('tableEmpty');
const emptyMessage = document.getElementById('emptyMessage');
const tableWrapper = document.getElementById('tableWrapper');
const marketsTable = document.getElementById('marketsTable');
const marketsTableBody = document.getElementById('marketsTableBody');

const openAddMarketBtn = document.getElementById('openAddMarketBtn');
const addMarketModal = document.getElementById('addMarketModal');
const addMarketForm = document.getElementById('addMarketForm');
const addMarketName = document.getElementById('addMarketName');
const addMarketNameError = document.getElementById('addMarketNameError');
const addLocation = document.getElementById('addLocation');
const addLocationError = document.getElementById('addLocationError');
const addPrice = document.getElementById('addPrice');
const addPriceError = document.getElementById('addPriceError');
const addDemand = document.getElementById('addDemand');
const addDemandError = document.getElementById('addDemandError');
const addSource = document.getElementById('addSource');
const addSourceError = document.getElementById('addSourceError');
const addCancelBtn = document.getElementById('addCancelBtn');
const addSubmitBtn = document.getElementById('addSubmitBtn');
const addModalError = document.getElementById('addModalError');

const editMarketModal = document.getElementById('editMarketModal');
const editMarketForm = document.getElementById('editMarketForm');
const editMarketId = document.getElementById('editMarketId');
const editMarketName = document.getElementById('editMarketName');
const editMarketNameError = document.getElementById('editMarketNameError');
const editLocation = document.getElementById('editLocation');
const editLocationError = document.getElementById('editLocationError');
const editPrice = document.getElementById('editPrice');
const editPriceError = document.getElementById('editPriceError');
const editDemand = document.getElementById('editDemand');
const editDemandError = document.getElementById('editDemandError');
const editSource = document.getElementById('editSource');
const editSourceError = document.getElementById('editSourceError');
const editCancelBtn = document.getElementById('editCancelBtn');
const editSubmitBtn = document.getElementById('editSubmitBtn');
const editModalError = document.getElementById('editModalError');

/**
 * Display a temporary success banner (auto-dismisses after 5s).
 */
function showSuccessBanner(message) {
  if (successTimer) {
    clearTimeout(successTimer);
  }
  alertError.style.display = 'none';
  alertSuccessText.textContent = message;
  alertSuccess.style.display = 'flex';

  successTimer = setTimeout(() => {
    alertSuccess.style.display = 'none';
    alertSuccessText.textContent = '';
  }, 5000);
}

/**
 * Display a persistent error banner at top of content area.
 */
function showErrorBanner(message) {
  if (successTimer) {
    clearTimeout(successTimer);
  }
  alertSuccess.style.display = 'none';
  alertErrorText.textContent = message;
  alertError.style.display = 'flex';
}

/**
 * Format timestamp into '15 Nov 2026' style.
 */
function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '-';
  const day = d.getDate();
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${day} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * Update summary strip KPI values.
 */
function updateSummaryCounts() {
  const total = allMarkets.length;
  const activeMarkets = allMarkets.filter(m => m.is_active);
  const active = activeMarkets.length;

  const avgPrice = active > 0
    ? Math.round(activeMarkets.reduce((sum, m) => sum + Number(m.average_price_per_kg), 0) / active)
    : 0;

  totalCountEl.textContent = String(total);
  activeCountEl.textContent = String(active);
  avgPriceCountEl.textContent = `${avgPrice} RWF`;
}

/**
 * State for column sorting.
 */
let sortState = { key: null, direction: null };

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
 * Return array of displayed text strings for searchable fields only.
 */
function getSearchText(market) {
  return [
    market.market_name || '',
    market.location || '',
    market.created_by_name || '-'
  ];
}

/**
 * Return appropriate badge class for demand level.
 */
function getDemandBadgeClass(demand) {
  const normalized = (demand || '').toUpperCase();
  if (normalized === 'HIGH') return 'badge badge-success badge-demand badge-demand-high';
  if (normalized === 'MEDIUM') return 'badge badge-warning badge-demand badge-demand-medium';
  if (normalized === 'LOW') return 'badge badge-danger badge-demand badge-demand-low';
  return 'badge badge-info badge-demand';
}

/**
 * Build a market table row using safe DOM methods (textContent only).
 */
function createMarketRow(market, query = '') {
  const tr = document.createElement('tr');
  tr.dataset.marketId = market.market_id;

  // Market Name
  const tdName = document.createElement('td');
  tdName.style.fontWeight = '600';
  highlightInto(tdName, market.market_name || '-', query);
  tr.appendChild(tdName);

  // Location
  const tdLocation = document.createElement('td');
  highlightInto(tdLocation, market.location || '-', query);
  tr.appendChild(tdLocation);

  // Price per kg (not searchable, not highlighted)
  const tdPrice = document.createElement('td');
  tdPrice.style.fontWeight = '600';
  tdPrice.textContent = `${Math.round(market.average_price_per_kg)} RWF`;
  tr.appendChild(tdPrice);

  // Demand
  const tdDemand = document.createElement('td');
  const demandBadge = document.createElement('span');
  demandBadge.className = getDemandBadgeClass(market.demand_level);
  demandBadge.textContent = (market.demand_level || 'MEDIUM').toUpperCase();
  tdDemand.appendChild(demandBadge);
  tr.appendChild(tdDemand);

  // Source
  const tdSource = document.createElement('td');
  tdSource.textContent = market.source || '-';
  tr.appendChild(tdSource);

  // Status
  const tdStatus = document.createElement('td');
  const statusBadge = document.createElement('span');
  if (market.is_active) {
    statusBadge.className = 'badge badge-success badge-status';
    statusBadge.textContent = 'Active';
  } else {
    statusBadge.className = 'badge badge-inactive badge-status';
    statusBadge.textContent = 'Inactive';
  }
  tdStatus.appendChild(statusBadge);
  tr.appendChild(tdStatus);

  // Created On
  const tdCreatedAt = document.createElement('td');
  tdCreatedAt.textContent = formatDate(market.created_at);
  tr.appendChild(tdCreatedAt);

  // Added By
  const tdCreatedBy = document.createElement('td');
  highlightInto(tdCreatedBy, market.created_by_name || '-', query);
  tr.appendChild(tdCreatedBy);

  // Actions
  const tdActions = document.createElement('td');
  const actionsWrap = document.createElement('div');
  actionsWrap.style.display = 'flex';
  actionsWrap.style.gap = 'var(--space-2)';
  actionsWrap.style.alignItems = 'center';

  // Edit Button
  const editBtn = document.createElement('button');
  editBtn.type = 'button';
  editBtn.className = 'btn btn-outline btn-sm btn-action-edit';
  editBtn.textContent = 'Edit';
  editBtn.addEventListener('click', () => openEditModal(market));
  actionsWrap.appendChild(editBtn);

  // Activate / Deactivate Button
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'btn btn-outline btn-sm btn-action-toggle';
  if (market.is_active) {
    toggleBtn.textContent = 'Deactivate';
    toggleBtn.style.color = 'var(--color-danger)';
    toggleBtn.style.borderColor = 'var(--color-danger-border)';
    toggleBtn.addEventListener('click', () => handleDeactivateMarket(market));
  } else {
    toggleBtn.textContent = 'Activate';
    toggleBtn.style.color = 'var(--color-success-text)';
    toggleBtn.style.borderColor = '#a7f3d0';
    toggleBtn.addEventListener('click', () => handleActivateMarket(market));
  }
  actionsWrap.appendChild(toggleBtn);

  tdActions.appendChild(actionsWrap);
  tr.appendChild(tdActions);

  return tr;
}

/**
 * Render filtered list into table body.
 */
function renderTable(markets, query = '') {
  marketsTableBody.replaceChildren();

  if (allMarkets.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No markets registered yet.';
    return;
  }

  if (markets.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No markets match your filters.';
    return;
  }

  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'block';

  for (const market of markets) {
    marketsTableBody.appendChild(createMarketRow(market, query));
  }
}

/**
 * Update aria-sort attributes on sortable table headers.
 */
function updateSortHeaders() {
  const headers = document.querySelectorAll('#marketsTable th[data-sort]');
  headers.forEach(th => {
    if (th.dataset.sort === sortState.key) {
      th.setAttribute('aria-sort', sortState.direction === 'asc' ? 'ascending' : 'descending');
    } else {
      th.setAttribute('aria-sort', 'none');
    }
  });
}

/**
 * Handle clicking or pressing Enter/Space on a sortable column header.
 */
function handleHeaderSort(key) {
  if (sortState.key === key) {
    sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
  } else {
    sortState.key = key;
    sortState.direction = 'asc';
  }
  updateSortHeaders();
  applyPipeline();
}

/**
 * Wire click and keyboard listeners on sortable headers.
 */
function initSortHeaders() {
  const headers = document.querySelectorAll('#marketsTable th[data-sort]');
  headers.forEach(th => {
    const key = th.dataset.sort;
    th.addEventListener('click', () => handleHeaderSort(key));
    th.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleHeaderSort(key);
      }
    });
  });
}

/**
 * Pipeline on every render: full list, dropdown filters, search, sort, then render.
 */
function applyPipeline() {
  const query = (searchInput.value || '').trim();
  const lowerQuery = query.toLowerCase();
  const status = statusFilter.value;
  const demand = demandFilter.value;

  // 1. Full list -> 2. Dropdown filters
  let filtered = allMarkets.filter(market => {
    // Status filter
    if (status === 'active' && !market.is_active) return false;
    if (status === 'inactive' && market.is_active) return false;

    // Demand filter
    if (demand !== 'all' && (market.demand_level || '').toUpperCase() !== demand) {
      return false;
    }

    return true;
  });

  // 3. Search (searchable fields only: market_name, location, created_by_name)
  if (lowerQuery) {
    filtered = filtered.filter(market => {
      const searchStrings = getSearchText(market);
      return searchStrings.some(s => s.toLowerCase().includes(lowerQuery));
    });
  }

  // 4. Sort
  if (sortState.key && sortState.direction) {
    const { key, direction } = sortState;
    filtered = filtered.slice().sort((a, b) => {
      if (key === 'average_price_per_kg') {
        const valA = a[key];
        const valB = b[key];
        const isEmptyA = valA == null || valA === '';
        const isEmptyB = valB == null || valB === '';
        if (isEmptyA && isEmptyB) return 0;
        if (isEmptyA) return 1;
        if (isEmptyB) return -1;
        const numA = Number(valA);
        const numB = Number(valB);
        return direction === 'asc' ? numA - numB : numB - numA;
      }

      const valA = (a[key] == null ? '' : String(a[key])).trim();
      const valB = (b[key] == null ? '' : String(b[key])).trim();
      const isEmptyA = !valA || valA === '-';
      const isEmptyB = !valB || valB === '-';

      if (isEmptyA && isEmptyB) return 0;
      if (isEmptyA) return 1;
      if (isEmptyB) return -1;

      const cmp = valA.localeCompare(valB, undefined, { sensitivity: 'base', numeric: true });
      return direction === 'asc' ? cmp : -cmp;
    });
  }

  // 5. Render
  showingCountText.textContent = `Showing ${filtered.length} of ${allMarkets.length} markets`;
  renderTable(filtered, query);
}

/**
 * Alias for backward compatibility.
 */
function applyFilters() {
  applyPipeline();
}

/**
 * Load markets list from backend API.
 */
async function loadMarkets() {
  tableLoading.style.display = 'block';
  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'none';

  try {
    const data = await MetlinkAPI.get('/markets');
    allMarkets = (data && data.markets) || [];
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || 'Failed to load markets list.');
  } finally {
    tableLoading.style.display = 'none';
  }
}

/**
 * Reset inline errors in Add modal.
 */
function clearAddErrors() {
  addModalError.style.display = 'none';
  addModalError.textContent = '';

  addMarketNameError.style.display = 'none';
  addMarketNameError.textContent = '';
  addMarketName.classList.remove('input-error');

  addLocationError.style.display = 'none';
  addLocationError.textContent = '';
  addLocation.classList.remove('input-error');

  addPriceError.style.display = 'none';
  addPriceError.textContent = '';
  addPrice.classList.remove('input-error');

  addDemandError.style.display = 'none';
  addDemandError.textContent = '';
  addDemand.classList.remove('input-error');

  addSourceError.style.display = 'none';
  addSourceError.textContent = '';
  addSource.classList.remove('input-error');
}

/**
 * Reset inline errors in Edit modal.
 */
function clearEditErrors() {
  editModalError.style.display = 'none';
  editModalError.textContent = '';

  editMarketNameError.style.display = 'none';
  editMarketNameError.textContent = '';
  editMarketName.classList.remove('input-error');

  editLocationError.style.display = 'none';
  editLocationError.textContent = '';
  editLocation.classList.remove('input-error');

  editPriceError.style.display = 'none';
  editPriceError.textContent = '';
  editPrice.classList.remove('input-error');

  editDemandError.style.display = 'none';
  editDemandError.textContent = '';
  editDemand.classList.remove('input-error');

  editSourceError.style.display = 'none';
  editSourceError.textContent = '';
  editSource.classList.remove('input-error');
}

/**
 * Open Add Market modal dialog.
 */
function openAddModal() {
  addMarketForm.reset();
  clearAddErrors();
  addSubmitBtn.disabled = false;
  addSubmitBtn.textContent = 'Add Market';

  addMarketModal.showModal();
  addMarketName.focus();
}

/**
 * Handle Add Market form submission.
 */
async function handleAddSubmit(event) {
  event.preventDefault();
  clearAddErrors();

  let hasError = false;

  const market_name = addMarketName.value.trim();
  const location = addLocation.value.trim();
  const rawPrice = addPrice.value.trim();
  const price = Number(rawPrice);
  const demand_level = addDemand.value;
  const source = addSource.value.trim();

  if (!market_name) {
    addMarketNameError.textContent = 'Market name is required.';
    addMarketNameError.style.display = 'block';
    addMarketName.classList.add('input-error');
    hasError = true;
  }

  if (!location) {
    addLocationError.textContent = 'Location is required.';
    addLocationError.style.display = 'block';
    addLocation.classList.add('input-error');
    hasError = true;
  }

  if (!rawPrice || isNaN(price) || price <= 0) {
    addPriceError.textContent = 'Price must be a positive number greater than 0.';
    addPriceError.style.display = 'block';
    addPrice.classList.add('input-error');
    hasError = true;
  }

  if (!demand_level) {
    addDemandError.textContent = 'Demand level is required.';
    addDemandError.style.display = 'block';
    addDemand.classList.add('input-error');
    hasError = true;
  }

  if (!source) {
    addSourceError.textContent = 'Data source is required.';
    addSourceError.style.display = 'block';
    addSource.classList.add('input-error');
    hasError = true;
  }

  if (hasError) return;

  addSubmitBtn.disabled = true;
  addSubmitBtn.textContent = 'Saving...';

  try {
    await MetlinkAPI.post('/markets', {
      market_name,
      location,
      average_price_per_kg: price,
      demand_level,
      source
    });

    addMarketModal.close();
    showSuccessBanner(`Market "${market_name}" added successfully.`);
    await loadMarkets();
  } catch (err) {
    const errorMsg = err.message || 'Failed to add market.';
    addModalError.textContent = errorMsg;
    addModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    addSubmitBtn.disabled = false;
    addSubmitBtn.textContent = 'Add Market';
  }
}

/**
 * Open Edit Market modal dialog.
 */
function openEditModal(market) {
  currentEditingMarket = market;
  editMarketForm.reset();
  clearEditErrors();

  editMarketId.value = market.market_id;
  editMarketName.value = market.market_name || '';
  editLocation.value = market.location || '';
  editPrice.value = Math.round(market.average_price_per_kg) || '';
  editDemand.value = (market.demand_level || 'MEDIUM').toUpperCase();
  editSource.value = market.source || '';

  editSubmitBtn.disabled = false;
  editSubmitBtn.textContent = 'Save Changes';

  editMarketModal.showModal();
  editMarketName.focus();
}

/**
 * Handle Edit Market form submission.
 * Sends full body: { market_name, location, average_price_per_kg, demand_level, source, is_active }
 */
async function handleEditSubmit(event) {
  event.preventDefault();
  if (!currentEditingMarket) return;
  clearEditErrors();

  let hasError = false;

  const market_name = editMarketName.value.trim();
  const location = editLocation.value.trim();
  const rawPrice = editPrice.value.trim();
  const price = Number(rawPrice);
  const demand_level = editDemand.value;
  const source = editSource.value.trim();

  if (!market_name) {
    editMarketNameError.textContent = 'Market name is required.';
    editMarketNameError.style.display = 'block';
    editMarketName.classList.add('input-error');
    hasError = true;
  }

  if (!location) {
    editLocationError.textContent = 'Location is required.';
    editLocationError.style.display = 'block';
    editLocation.classList.add('input-error');
    hasError = true;
  }

  if (!rawPrice || isNaN(price) || price <= 0) {
    editPriceError.textContent = 'Price must be a positive number greater than 0.';
    editPriceError.style.display = 'block';
    editPrice.classList.add('input-error');
    hasError = true;
  }

  if (!demand_level) {
    editDemandError.textContent = 'Demand level is required.';
    editDemandError.style.display = 'block';
    editDemand.classList.add('input-error');
    hasError = true;
  }

  if (!source) {
    editSourceError.textContent = 'Data source is required.';
    editSourceError.style.display = 'block';
    editSource.classList.add('input-error');
    hasError = true;
  }

  if (hasError) return;

  editSubmitBtn.disabled = true;
  editSubmitBtn.textContent = 'Saving...';

  try {
    const res = await MetlinkAPI.put(`/markets/${currentEditingMarket.market_id}`, {
      market_name,
      location,
      average_price_per_kg: price,
      demand_level,
      source,
      is_active: currentEditingMarket.is_active
    });

    const updatedMarket = res.market;
    const index = allMarkets.findIndex(m => m.market_id === currentEditingMarket.market_id);
    if (index !== -1) {
      allMarkets[index] = {
        ...allMarkets[index],
        ...updatedMarket
      };
    }

    editMarketModal.close();
    showSuccessBanner(`Market "${market_name}" updated successfully.`);
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    const errorMsg = err.message || 'Failed to update market.';
    editModalError.textContent = errorMsg;
    editModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    editSubmitBtn.disabled = false;
    editSubmitBtn.textContent = 'Save Changes';
  }
}

/**
 * Handle market deactivation with confirmation.
 * Sends full body with is_active: false.
 */
async function handleDeactivateMarket(market) {
  const confirmed = window.confirm(
    `Deactivate ${market.market_name}? This market will be excluded from price calculations.`
  );
  if (!confirmed) return;

  try {
    const res = await MetlinkAPI.put(`/markets/${market.market_id}`, {
      market_name: market.market_name,
      location: market.location,
      average_price_per_kg: Number(market.average_price_per_kg),
      demand_level: market.demand_level,
      source: market.source,
      is_active: false
    });

    const index = allMarkets.findIndex(m => m.market_id === market.market_id);
    if (index !== -1) {
      allMarkets[index] = {
        ...allMarkets[index],
        ...res.market
      };
    }

    showSuccessBanner(`${market.market_name} has been deactivated.`);
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || `Failed to deactivate ${market.market_name}.`);
  }
}

/**
 * Handle market reactivation with confirmation.
 * Sends full body with is_active: true.
 */
async function handleActivateMarket(market) {
  const confirmed = window.confirm(
    `Activate ${market.market_name}? This market will be included in price calculations.`
  );
  if (!confirmed) return;

  try {
    const res = await MetlinkAPI.put(`/markets/${market.market_id}`, {
      market_name: market.market_name,
      location: market.location,
      average_price_per_kg: Number(market.average_price_per_kg),
      demand_level: market.demand_level,
      source: market.source,
      is_active: true
    });

    const index = allMarkets.findIndex(m => m.market_id === market.market_id);
    if (index !== -1) {
      allMarkets[index] = {
        ...allMarkets[index],
        ...res.market
      };
    }

    showSuccessBanner(`${market.market_name} has been activated.`);
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || `Failed to activate ${market.market_name}.`);
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
    alertError.style.display = 'none';
    alertErrorText.textContent = '';
  });
}

// Search and filter triggers
searchInput.addEventListener('input', () => applyFilters());
statusFilter.addEventListener('change', () => applyFilters());
demandFilter.addEventListener('change', () => applyFilters());

// Add modal triggers
openAddMarketBtn.addEventListener('click', openAddModal);
addCancelBtn.addEventListener('click', () => addMarketModal.close());
addMarketForm.addEventListener('submit', handleAddSubmit);

// Edit modal triggers
editCancelBtn.addEventListener('click', () => editMarketModal.close());
editMarketForm.addEventListener('submit', handleEditSubmit);

// Initial data load
initSortHeaders();
if (currentAdmin) {
  loadMarkets();
}
