/**
 * METLINK — Farmers Management Module
 * Handles loading, filtering, registering, editing, and activating/deactivating farmers.
 */

// Route guard: ensure admin session is active
const currentAdmin = MetlinkAuth.requireAuth();

// Module state
let allFarmers = [];
let currentEditingFarmer = null;
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
const inactiveCountEl = document.getElementById('inactiveCount');

const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const showingCountText = document.getElementById('showingCountText');

const tableLoading = document.getElementById('tableLoading');
const tableEmpty = document.getElementById('tableEmpty');
const emptyMessage = document.getElementById('emptyMessage');
const tableWrapper = document.getElementById('tableWrapper');
const farmersTable = document.getElementById('farmersTable');
const farmersTableBody = document.getElementById('farmersTableBody');

const openRegisterBtn = document.getElementById('openRegisterBtn');
const registerModal = document.getElementById('registerModal');
const registerForm = document.getElementById('registerForm');
const regPhoneInput = document.getElementById('regPhone');
const regPhoneError = document.getElementById('regPhoneError');
const regNameInput = document.getElementById('regName');
const regLocationInput = document.getElementById('regLocation');
const regLanguageSelect = document.getElementById('regLanguage');
const regCancelBtn = document.getElementById('regCancelBtn');
const regSubmitBtn = document.getElementById('regSubmitBtn');
const registerModalError = document.getElementById('registerModalError');

const editModal = document.getElementById('editModal');
const editForm = document.getElementById('editForm');
const editFarmerIdInput = document.getElementById('editFarmerId');
const editPhoneInput = document.getElementById('editPhone');
const editNameInput = document.getElementById('editName');
const editLocationInput = document.getElementById('editLocation');
const editLanguageSelect = document.getElementById('editLanguage');
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
 * Clear top-level feedback alerts.
 */
function clearBanners() {
  if (successTimer) {
    clearTimeout(successTimer);
  }
  alertSuccess.style.display = 'none';
  alertSuccessText.textContent = '';
  alertError.style.display = 'none';
  alertErrorText.textContent = '';
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
 * Normalize and validate Rwandan phone number.
 * Accepts: 0788123456, 788123456, +250788123456, or with whitespace.
 * Valid 9-digit prefix: 72, 73, 78, 79.
 * Returns { valid: boolean, normalized?: string, error?: string }.
 */
function validateRwandanPhone(rawInput) {
  if (!rawInput || !rawInput.trim()) {
    return { valid: false, error: 'Phone number is required.' };
  }

  let cleaned = rawInput.replace(/[\s\-\(\)]/g, '');

  if (cleaned.startsWith('+250')) {
    cleaned = cleaned.slice(4);
  } else if (cleaned.startsWith('250')) {
    cleaned = cleaned.slice(3);
  } else if (cleaned.startsWith('0')) {
    cleaned = cleaned.slice(1);
  }

  if (!/^\d{9}$/.test(cleaned)) {
    return {
      valid: false,
      error: 'Phone number must be a 9-digit Rwandan mobile number (e.g. 0788123456).'
    };
  }

  const prefix = cleaned.slice(0, 2);
  if (!['72', '73', '78', '79'].includes(prefix)) {
    return {
      valid: false,
      error: 'Valid Rwandan mobile numbers start with 72, 73, 78, or 79.'
    };
  }

  return {
    valid: true,
    normalized: `+250${cleaned}`
  };
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
 * Return array of displayed text strings for searchable fields.
 */
function getSearchText(farmer) {
  return [
    farmer.name || '',
    farmer.phone_number || '',
    farmer.location || '',
    farmer.registered_by_name || '-',
    formatDate(farmer.registered_at)
  ];
}

/**
 * Update summary strip KPI numbers.
 */
function updateSummaryCounts() {
  const total = allFarmers.length;
  const active = allFarmers.filter(f => f.is_active).length;
  const inactive = total - active;

  totalCountEl.textContent = String(total);
  activeCountEl.textContent = String(active);
  inactiveCountEl.textContent = String(inactive);
}

/**
 * Build a table row using safe DOM methods (textContent only).
 */
function createFarmerRow(farmer, query = '') {
  const tr = document.createElement('tr');
  tr.dataset.farmerId = farmer.farmer_id;

  // Name
  const tdName = document.createElement('td');
  tdName.style.fontWeight = '600';
  highlightInto(tdName, farmer.name || '-', query);
  tr.appendChild(tdName);

  // Phone
  const tdPhone = document.createElement('td');
  highlightInto(tdPhone, farmer.phone_number || '-', query);
  tr.appendChild(tdPhone);

  // Location
  const tdLocation = document.createElement('td');
  highlightInto(tdLocation, farmer.location || '-', query);
  tr.appendChild(tdLocation);

  // Language
  const tdLang = document.createElement('td');
  const langBadge = document.createElement('span');
  langBadge.className = 'badge badge-primary badge-lang';
  langBadge.textContent = (farmer.preferred_language || 'rw').toUpperCase();
  tdLang.appendChild(langBadge);
  tr.appendChild(tdLang);

  // Status
  const tdStatus = document.createElement('td');
  const statusBadge = document.createElement('span');
  if (farmer.is_active) {
    statusBadge.className = 'badge badge-success badge-status';
    statusBadge.textContent = 'Active';
  } else {
    statusBadge.className = 'badge badge-inactive badge-status';
    statusBadge.textContent = 'Inactive';
  }
  tdStatus.appendChild(statusBadge);
  tr.appendChild(tdStatus);

  // Registered By
  const tdRegBy = document.createElement('td');
  highlightInto(tdRegBy, farmer.registered_by_name || '-', query);
  tr.appendChild(tdRegBy);

  // Registered On
  const tdRegAt = document.createElement('td');
  highlightInto(tdRegAt, formatDate(farmer.registered_at), query);
  tr.appendChild(tdRegAt);

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
  editBtn.addEventListener('click', () => openEditModal(farmer));
  actionsWrap.appendChild(editBtn);

  // Activate / Deactivate Button
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'btn btn-outline btn-sm btn-action-toggle';
  if (farmer.is_active) {
    toggleBtn.textContent = 'Deactivate';
    toggleBtn.style.color = 'var(--color-danger)';
    toggleBtn.style.borderColor = 'var(--color-danger-border)';
    toggleBtn.addEventListener('click', () => handleDeactivateFarmer(farmer));
  } else {
    toggleBtn.textContent = 'Activate';
    toggleBtn.style.color = 'var(--color-success-text)';
    toggleBtn.style.borderColor = '#a7f3d0';
    toggleBtn.addEventListener('click', () => handleActivateFarmer(farmer));
  }
  actionsWrap.appendChild(toggleBtn);

  tdActions.appendChild(actionsWrap);
  tr.appendChild(tdActions);

  return tr;
}

/**
 * Render filtered list into table body.
 */
function renderTable(farmers, query = '') {
  farmersTableBody.replaceChildren();

  if (allFarmers.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No farmers registered yet.';
    return;
  }

  if (farmers.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No farmers match your filters.';
    return;
  }

  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'block';

  for (const farmer of farmers) {
    farmersTableBody.appendChild(createFarmerRow(farmer, query));
  }
}

/**
 * Update aria-sort attributes on sortable table headers.
 */
function updateSortHeaders() {
  const headers = document.querySelectorAll('#farmersTable th[data-sort]');
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
  const headers = document.querySelectorAll('#farmersTable th[data-sort]');
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

  // 1. Full list -> 2. Dropdown filters
  let filtered = allFarmers.filter(farmer => {
    if (status === 'active' && !farmer.is_active) return false;
    if (status === 'inactive' && farmer.is_active) return false;
    return true;
  });

  // 3. Search
  if (lowerQuery) {
    filtered = filtered.filter(farmer => {
      const searchStrings = getSearchText(farmer);
      return searchStrings.some(s => s.toLowerCase().includes(lowerQuery));
    });
  }

  // 4. Sort
  if (sortState.key && sortState.direction) {
    const { key, direction } = sortState;
    filtered = filtered.slice().sort((a, b) => {
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
  showingCountText.textContent = `Showing ${filtered.length} of ${allFarmers.length} farmers`;
  renderTable(filtered, query);
}

/**
 * Alias for backward compatibility.
 */
function applyFilters() {
  applyPipeline();
}

/**
 * Load farmers list from backend API.
 */
async function loadFarmers() {
  tableLoading.style.display = 'block';
  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'none';

  try {
    const data = await MetlinkAPI.get('/farmers');
    allFarmers = (data && data.farmers) || [];
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || 'Failed to load farmers list.');
  } finally {
    tableLoading.style.display = 'none';
  }
}

/**
 * Show inline phone validation error in register modal.
 */
function showPhoneError(msg) {
  regPhoneError.textContent = msg;
  regPhoneError.style.display = 'block';
  regPhoneInput.classList.add('input-error');
}

/**
 * Clear inline phone validation error in register modal.
 */
function clearPhoneError() {
  regPhoneError.textContent = '';
  regPhoneError.style.display = 'none';
  regPhoneInput.classList.remove('input-error');
}

/**
 * Open Register Farmer modal dialog.
 */
function openRegisterModal() {
  registerForm.reset();
  clearPhoneError();
  registerModalError.style.display = 'none';
  registerModalError.textContent = '';
  regSubmitBtn.disabled = false;
  regSubmitBtn.textContent = 'Register Farmer';

  registerModal.showModal();
  regPhoneInput.focus();
}

/**
 * Handle Register Farmer submission.
 */
async function handleRegisterSubmit(event) {
  event.preventDefault();
  clearPhoneError();
  registerModalError.style.display = 'none';
  registerModalError.textContent = '';

  const rawPhone = regPhoneInput.value;
  const validation = validateRwandanPhone(rawPhone);
  if (!validation.valid) {
    showPhoneError(validation.error);
    regPhoneInput.focus();
    return;
  }

  const name = regNameInput.value.trim();
  const location = regLocationInput.value.trim();
  const preferred_language = regLanguageSelect.value;

  if (!name || !location) {
    registerModalError.textContent = 'All fields are required.';
    registerModalError.style.display = 'flex';
    return;
  }

  regSubmitBtn.disabled = true;
  regSubmitBtn.textContent = 'Saving...';

  try {
    const res = await MetlinkAPI.post('/farmers', {
      phone_number: validation.normalized,
      name,
      location,
      preferred_language
    });

    registerModal.close();
    showSuccessBanner(`Farmer "${name}" registered successfully.`);

    // Reload list to ensure registered_by_name and all fields are synced
    await loadFarmers();
  } catch (err) {
    const errorMsg = err.message || 'Failed to register farmer.';
    registerModalError.textContent = errorMsg;
    registerModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    regSubmitBtn.disabled = false;
    regSubmitBtn.textContent = 'Register Farmer';
  }
}

/**
 * Open Edit Farmer modal dialog.
 */
function openEditModal(farmer) {
  currentEditingFarmer = farmer;
  editForm.reset();
  editModalError.style.display = 'none';
  editModalError.textContent = '';

  editFarmerIdInput.value = farmer.farmer_id;
  editPhoneInput.value = farmer.phone_number || '';
  editNameInput.value = farmer.name || '';
  editLocationInput.value = farmer.location || '';
  editLanguageSelect.value = farmer.preferred_language || 'rw';

  editSubmitBtn.disabled = false;
  editSubmitBtn.textContent = 'Save Changes';

  editModal.showModal();
  editNameInput.focus();
}

/**
 * Handle Edit Farmer submission.
 */
async function handleEditSubmit(event) {
  event.preventDefault();
  if (!currentEditingFarmer) return;

  editModalError.style.display = 'none';
  editModalError.textContent = '';

  const name = editNameInput.value.trim();
  const location = editLocationInput.value.trim();
  const preferred_language = editLanguageSelect.value;

  if (!name || !location) {
    editModalError.textContent = 'Full name and location are required.';
    editModalError.style.display = 'flex';
    return;
  }

  editSubmitBtn.disabled = true;
  editSubmitBtn.textContent = 'Saving...';

  try {
    const res = await MetlinkAPI.put(`/farmers/${currentEditingFarmer.farmer_id}`, {
      name,
      location,
      preferred_language,
      is_active: currentEditingFarmer.is_active
    });

    const updatedFarmer = res.farmer;
    // Update farmer in memory
    const index = allFarmers.findIndex(f => f.farmer_id === currentEditingFarmer.farmer_id);
    if (index !== -1) {
      allFarmers[index] = {
        ...allFarmers[index],
        name: updatedFarmer.name,
        location: updatedFarmer.location,
        preferred_language: updatedFarmer.preferred_language,
        is_active: updatedFarmer.is_active
      };
    }

    editModal.close();
    showSuccessBanner(`Farmer "${name}" updated successfully.`);
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    const errorMsg = err.message || 'Failed to update farmer.';
    editModalError.textContent = errorMsg;
    editModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    editSubmitBtn.disabled = false;
    editSubmitBtn.textContent = 'Save Changes';
  }
}

/**
 * Handle farmer deactivation with confirmation.
 */
async function handleDeactivateFarmer(farmer) {
  const message = `Deactivate ${farmer.name}? They will stop receiving advice but their records are kept.`;
  const confirmed = window.confirm(message);
  if (!confirmed) return;

  try {
    const res = await MetlinkAPI.put(`/farmers/${farmer.farmer_id}`, {
      name: farmer.name,
      location: farmer.location,
      preferred_language: farmer.preferred_language,
      is_active: false
    });

    const index = allFarmers.findIndex(f => f.farmer_id === farmer.farmer_id);
    if (index !== -1) {
      allFarmers[index].is_active = false;
    }

    showSuccessBanner(`${farmer.name} has been deactivated.`);
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || `Failed to deactivate ${farmer.name}.`);
  }
}

/**
 * Handle farmer reactivation with confirmation.
 */
async function handleActivateFarmer(farmer) {
  const message = `Activate ${farmer.name}? They will resume receiving advice.`;
  const confirmed = window.confirm(message);
  if (!confirmed) return;

  try {
    const res = await MetlinkAPI.put(`/farmers/${farmer.farmer_id}`, {
      name: farmer.name,
      location: farmer.location,
      preferred_language: farmer.preferred_language,
      is_active: true
    });

    const index = allFarmers.findIndex(f => f.farmer_id === farmer.farmer_id);
    if (index !== -1) {
      allFarmers[index].is_active = true;
    }

    showSuccessBanner(`${farmer.name} has been activated.`);
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || `Failed to activate ${farmer.name}.`);
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

// Search and filter inputs
searchInput.addEventListener('input', () => applyFilters());
statusFilter.addEventListener('change', () => applyFilters());

// Live validation on phone typing
regPhoneInput.addEventListener('input', () => {
  clearPhoneError();
});

// Modal triggers & actions
openRegisterBtn.addEventListener('click', openRegisterModal);
regCancelBtn.addEventListener('click', () => registerModal.close());
registerForm.addEventListener('submit', handleRegisterSubmit);

editCancelBtn.addEventListener('click', () => editModal.close());
editForm.addEventListener('submit', handleEditSubmit);

// Initial load
initSortHeaders();
if (currentAdmin) {
  loadFarmers();
}
