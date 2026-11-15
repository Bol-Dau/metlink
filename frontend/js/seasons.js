/**
 * METLINK — Agricultural Seasons Management Module
 * Handles viewing, adding, editing, and managing Rwandan agricultural seasons (A, B, C).
 */

// Route guard: ensure admin session is active
const currentAdmin = MetlinkAuth.requireAuth();

// Module state
let allSeasons = [];
let currentEditingSeason = null;
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
const activeSeasonNameEl = document.getElementById('activeSeasonName');

const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const showingCountText = document.getElementById('showingCountText');

const tableLoading = document.getElementById('tableLoading');
const tableEmpty = document.getElementById('tableEmpty');
const emptyMessage = document.getElementById('emptyMessage');
const tableWrapper = document.getElementById('tableWrapper');
const seasonsTable = document.getElementById('seasonsTable');
const seasonsTableBody = document.getElementById('seasonsTableBody');

const openAddSeasonBtn = document.getElementById('openAddSeasonBtn');
const addSeasonModal = document.getElementById('addSeasonModal');
const addSeasonForm = document.getElementById('addSeasonForm');
const addSeasonName = document.getElementById('addSeasonName');
const addSeasonNameError = document.getElementById('addSeasonNameError');
const addStartDate = document.getElementById('addStartDate');
const addStartDateError = document.getElementById('addStartDateError');
const addEndDate = document.getElementById('addEndDate');
const addEndDateError = document.getElementById('addEndDateError');
const addDescription = document.getElementById('addDescription');
const addDescriptionError = document.getElementById('addDescriptionError');
const addIsActive = document.getElementById('addIsActive');
const addCancelBtn = document.getElementById('addCancelBtn');
const addSubmitBtn = document.getElementById('addSubmitBtn');
const addModalError = document.getElementById('addModalError');

const editSeasonModal = document.getElementById('editSeasonModal');
const editSeasonForm = document.getElementById('editSeasonForm');
const editSeasonId = document.getElementById('editSeasonId');
const editSeasonName = document.getElementById('editSeasonName');
const editSeasonNameError = document.getElementById('editSeasonNameError');
const editStartDate = document.getElementById('editStartDate');
const editStartDateError = document.getElementById('editStartDateError');
const editEndDate = document.getElementById('editEndDate');
const editEndDateError = document.getElementById('editEndDateError');
const editDescription = document.getElementById('editDescription');
const editDescriptionError = document.getElementById('editDescriptionError');
const editIsActive = document.getElementById('editIsActive');
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
 * Format ISO date string into '1 Sep 2026' style safely without timezone shifts.
 */
function formatIsoDate(dateStr) {
  if (!dateStr) return '-';
  const clean = String(dateStr).slice(0, 10);
  const parts = clean.split('-');
  if (parts.length === 3) {
    const year = parseInt(parts[0], 10);
    const monthIdx = parseInt(parts[1], 10) - 1;
    const day = parseInt(parts[2], 10);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    if (!isNaN(year) && monthIdx >= 0 && monthIdx < 12 && !isNaN(day)) {
      return `${day} ${months[monthIdx]} ${year}`;
    }
  }

  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '-';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * Update summary strip KPI values.
 */
function updateSummaryCounts() {
  const total = allSeasons.length;
  const activeSeason = allSeasons.find(s => s.is_active);

  totalCountEl.textContent = String(total);
  activeSeasonNameEl.textContent = activeSeason ? activeSeason.season_name : 'None active';
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
 * Return array of displayed text strings for searchable fields only (season_name and description).
 */
function getSearchText(season) {
  return [
    season.season_name || '',
    season.description || ''
  ];
}

/**
 * Build a season table row using safe DOM methods (textContent only).
 */
function createSeasonRow(season, query = '') {
  const tr = document.createElement('tr');
  tr.dataset.seasonId = season.season_id;

  // Season Name
  const tdName = document.createElement('td');
  tdName.style.fontWeight = '600';
  highlightInto(tdName, season.season_name || '-', query);
  tr.appendChild(tdName);

  // Start Date (not searchable, not highlighted)
  const tdStart = document.createElement('td');
  tdStart.textContent = formatIsoDate(season.start_date);
  tr.appendChild(tdStart);

  // End Date (not searchable, not highlighted)
  const tdEnd = document.createElement('td');
  tdEnd.textContent = formatIsoDate(season.end_date);
  tr.appendChild(tdEnd);

  // Description (with truncate & full text kept in title tooltip)
  const tdDesc = document.createElement('td');
  tdDesc.className = 'desc-cell';
  tdDesc.title = season.description || '';
  highlightInto(tdDesc, season.description || '-', query);
  tr.appendChild(tdDesc);

  // Status
  const tdStatus = document.createElement('td');
  const statusBadge = document.createElement('span');
  if (season.is_active) {
    statusBadge.className = 'badge badge-success badge-status';
    statusBadge.textContent = 'Active';
  } else {
    statusBadge.className = 'badge badge-inactive badge-status';
    statusBadge.textContent = 'Inactive';
  }
  tdStatus.appendChild(statusBadge);
  tr.appendChild(tdStatus);

  // Added By (not searchable, not highlighted)
  const tdCreatedBy = document.createElement('td');
  tdCreatedBy.textContent = season.created_by_name || '-';
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
  editBtn.addEventListener('click', () => openEditModal(season));
  actionsWrap.appendChild(editBtn);

  // Activate / Deactivate Button
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'btn btn-outline btn-sm btn-action-toggle';
  if (season.is_active) {
    toggleBtn.textContent = 'Deactivate';
    toggleBtn.style.color = 'var(--color-danger)';
    toggleBtn.style.borderColor = 'var(--color-danger-border)';
    toggleBtn.addEventListener('click', () => handleDeactivateSeason(season));
  } else {
    toggleBtn.textContent = 'Activate';
    toggleBtn.style.color = 'var(--color-success-text)';
    toggleBtn.style.borderColor = '#a7f3d0';
    toggleBtn.addEventListener('click', () => handleActivateSeason(season));
  }
  actionsWrap.appendChild(toggleBtn);

  tdActions.appendChild(actionsWrap);
  tr.appendChild(tdActions);

  return tr;
}

/**
 * Render filtered list into table body.
 */
function renderTable(seasons, query = '') {
  seasonsTableBody.replaceChildren();

  if (allSeasons.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No seasons registered yet.';
    return;
  }

  if (seasons.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No seasons match your filters.';
    return;
  }

  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'block';

  for (const season of seasons) {
    seasonsTableBody.appendChild(createSeasonRow(season, query));
  }
}

/**
 * Pipeline on every render: full list, dropdown filters, search, then render.
 */
function applyPipeline() {
  const query = (searchInput.value || '').trim();
  const lowerQuery = query.toLowerCase();
  const status = statusFilter.value;

  // 1. Full list -> 2. Dropdown filters
  let filtered = allSeasons.filter(season => {
    // Status filter
    if (status === 'active' && !season.is_active) return false;
    if (status === 'inactive' && season.is_active) return false;
    return true;
  });

  // 3. Search (season_name and description only)
  if (lowerQuery) {
    filtered = filtered.filter(season => {
      const searchStrings = getSearchText(season);
      return searchStrings.some(s => s.toLowerCase().includes(lowerQuery));
    });
  }

  // 4. Render
  showingCountText.textContent = `Showing ${filtered.length} of ${allSeasons.length} seasons`;
  renderTable(filtered, query);
}

/**
 * Alias for backward compatibility.
 */
function applyFilters() {
  applyPipeline();
}

/**
 * Load seasons list from backend API.
 */
async function loadSeasons() {
  tableLoading.style.display = 'block';
  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'none';

  try {
    const data = await MetlinkAPI.get('/seasons');
    allSeasons = (data && data.seasons) || [];
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || 'Failed to load seasons list.');
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

  addSeasonNameError.style.display = 'none';
  addSeasonNameError.textContent = '';
  addSeasonName.classList.remove('input-error');

  addStartDateError.style.display = 'none';
  addStartDateError.textContent = '';
  addStartDate.classList.remove('input-error');

  addEndDateError.style.display = 'none';
  addEndDateError.textContent = '';
  addEndDate.classList.remove('input-error');

  addDescriptionError.style.display = 'none';
  addDescriptionError.textContent = '';
  addDescription.classList.remove('input-error');
}

/**
 * Reset inline errors in Edit modal.
 */
function clearEditErrors() {
  editModalError.style.display = 'none';
  editModalError.textContent = '';

  editSeasonNameError.style.display = 'none';
  editSeasonNameError.textContent = '';
  editSeasonName.classList.remove('input-error');

  editStartDateError.style.display = 'none';
  editStartDateError.textContent = '';
  editStartDate.classList.remove('input-error');

  editEndDateError.style.display = 'none';
  editEndDateError.textContent = '';
  editEndDate.classList.remove('input-error');

  editDescriptionError.style.display = 'none';
  editDescriptionError.textContent = '';
  editDescription.classList.remove('input-error');
}

/**
 * Open Add Season modal dialog.
 */
function openAddModal() {
  addSeasonForm.reset();
  clearAddErrors();
  addIsActive.checked = false;
  addSubmitBtn.disabled = false;
  addSubmitBtn.textContent = 'Add Season';

  addSeasonModal.showModal();
  addSeasonName.focus();
}

/**
 * Handle Add Season form submission.
 */
async function handleAddSubmit(event) {
  event.preventDefault();
  clearAddErrors();

  let hasError = false;

  const season_name = addSeasonName.value.trim();
  const start_date = addStartDate.value;
  const end_date = addEndDate.value;
  const rawDescription = addDescription.value.trim();
  const description = rawDescription || 'Agricultural season notes.';
  const is_active = addIsActive.checked;

  if (!season_name) {
    addSeasonNameError.textContent = 'Season name is required.';
    addSeasonNameError.style.display = 'block';
    addSeasonName.classList.add('input-error');
    hasError = true;
  }

  if (!start_date) {
    addStartDateError.textContent = 'Start date is required.';
    addStartDateError.style.display = 'block';
    addStartDate.classList.add('input-error');
    hasError = true;
  }

  if (!end_date) {
    addEndDateError.textContent = 'End date is required.';
    addEndDateError.style.display = 'block';
    addEndDate.classList.add('input-error');
    hasError = true;
  }

  if (start_date && end_date && end_date <= start_date) {
    addEndDateError.textContent = 'End date must be after start date.';
    addEndDateError.style.display = 'block';
    addEndDate.classList.add('input-error');
    hasError = true;
  }

  if (hasError) return;

  // Active season warning if another season is currently active
  if (is_active) {
    const currentActive = allSeasons.find(s => s.is_active);
    if (currentActive) {
      const proceed = window.confirm(
        `Another season (${currentActive.season_name}) is currently active. Continue?`
      );
      if (!proceed) return;
    }
  }

  addSubmitBtn.disabled = true;
  addSubmitBtn.textContent = 'Saving...';

  try {
    await MetlinkAPI.post('/seasons', {
      season_name,
      start_date,
      end_date,
      description,
      is_active
    });

    addSeasonModal.close();
    showSuccessBanner(`Season "${season_name}" added successfully.`);
    await loadSeasons();
  } catch (err) {
    const errorMsg = err.message || 'Failed to add season.';
    addModalError.textContent = errorMsg;
    addModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    addSubmitBtn.disabled = false;
    addSubmitBtn.textContent = 'Add Season';
  }
}

/**
 * Open Edit Season modal dialog.
 */
function openEditModal(season) {
  currentEditingSeason = season;
  editSeasonForm.reset();
  clearEditErrors();

  editSeasonId.value = season.season_id;
  editSeasonName.value = season.season_name || '';
  editStartDate.value = String(season.start_date).slice(0, 10);
  editEndDate.value = String(season.end_date).slice(0, 10);
  editDescription.value = season.description || '';
  editIsActive.checked = Boolean(season.is_active);

  editSubmitBtn.disabled = false;
  editSubmitBtn.textContent = 'Save Changes';

  editSeasonModal.showModal();
  editSeasonName.focus();
}

/**
 * Handle Edit Season form submission.
 * Sends full body: { season_name, start_date, end_date, description, is_active }
 */
async function handleEditSubmit(event) {
  event.preventDefault();
  if (!currentEditingSeason) return;
  clearEditErrors();

  let hasError = false;

  const season_name = editSeasonName.value.trim();
  const start_date = editStartDate.value;
  const end_date = editEndDate.value;
  const rawDescription = editDescription.value.trim();
  const description = rawDescription || 'Agricultural season notes.';
  const is_active = editIsActive.checked;

  if (!season_name) {
    editSeasonNameError.textContent = 'Season name is required.';
    editSeasonNameError.style.display = 'block';
    editSeasonName.classList.add('input-error');
    hasError = true;
  }

  if (!start_date) {
    editStartDateError.textContent = 'Start date is required.';
    editStartDateError.style.display = 'block';
    editStartDate.classList.add('input-error');
    hasError = true;
  }

  if (!end_date) {
    editEndDateError.textContent = 'End date is required.';
    editEndDateError.style.display = 'block';
    editEndDate.classList.add('input-error');
    hasError = true;
  }

  if (start_date && end_date && end_date <= start_date) {
    editEndDateError.textContent = 'End date must be after start date.';
    editEndDateError.style.display = 'block';
    editEndDate.classList.add('input-error');
    hasError = true;
  }

  if (hasError) return;

  // Active season warning if user is activating and another season is currently active
  if (is_active) {
    const otherActive = allSeasons.find(
      s => s.is_active && s.season_id !== currentEditingSeason.season_id
    );
    if (otherActive) {
      const proceed = window.confirm(
        `Another season (${otherActive.season_name}) is currently active. Continue?`
      );
      if (!proceed) return;
    }
  }

  editSubmitBtn.disabled = true;
  editSubmitBtn.textContent = 'Saving...';

  try {
    await MetlinkAPI.put(`/seasons/${currentEditingSeason.season_id}`, {
      season_name,
      start_date,
      end_date,
      description,
      is_active
    });

    editSeasonModal.close();
    showSuccessBanner(`Season "${season_name}" updated successfully.`);
    await loadSeasons();
  } catch (err) {
    const errorMsg = err.message || 'Failed to update season.';
    editModalError.textContent = errorMsg;
    editModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    editSubmitBtn.disabled = false;
    editSubmitBtn.textContent = 'Save Changes';
  }
}

/**
 * Handle season deactivation with confirmation.
 * Sends full body with is_active: false.
 */
async function handleDeactivateSeason(season) {
  const confirmed = window.confirm(`Deactivate ${season.season_name}?`);
  if (!confirmed) return;

  try {
    await MetlinkAPI.put(`/seasons/${season.season_id}`, {
      season_name: season.season_name,
      start_date: String(season.start_date).slice(0, 10),
      end_date: String(season.end_date).slice(0, 10),
      description: season.description || 'Agricultural season notes.',
      is_active: false
    });

    showSuccessBanner(`${season.season_name} has been deactivated.`);
    await loadSeasons();
  } catch (err) {
    showErrorBanner(err.message || `Failed to deactivate ${season.season_name}.`);
  }
}

/**
 * Handle season activation with confirmation and existing active season warning.
 * Sends full body with is_active: true.
 */
async function handleActivateSeason(season) {
  const otherActive = allSeasons.find(
    s => s.is_active && s.season_id !== season.season_id
  );

  let confirmMsg = `Activate ${season.season_name}?`;
  if (otherActive) {
    confirmMsg = `Another season (${otherActive.season_name}) is currently active. Continue?`;
  }

  const confirmed = window.confirm(confirmMsg);
  if (!confirmed) return;

  try {
    await MetlinkAPI.put(`/seasons/${season.season_id}`, {
      season_name: season.season_name,
      start_date: String(season.start_date).slice(0, 10),
      end_date: String(season.end_date).slice(0, 10),
      description: season.description || 'Agricultural season notes.',
      is_active: true
    });

    showSuccessBanner(`${season.season_name} has been activated.`);
    await loadSeasons();
  } catch (err) {
    showErrorBanner(err.message || `Failed to activate ${season.season_name}.`);
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

// Add modal triggers
openAddSeasonBtn.addEventListener('click', openAddModal);
addCancelBtn.addEventListener('click', () => addSeasonModal.close());
addSeasonForm.addEventListener('submit', handleAddSubmit);

// Edit modal triggers
editCancelBtn.addEventListener('click', () => editSeasonModal.close());
editSeasonForm.addEventListener('submit', handleEditSubmit);

// Initial data load
if (currentAdmin) {
  loadSeasons();
}
