/**
 * METLINK — Decision Rules Management Module
 * Handles loading, priority sorting, filtering, creating, editing, and activating/deactivating
 * agricultural harvest advisory rules with strict preservation safety guards.
 */

// Route guard: ensure admin session is active
const currentAdmin = MetlinkAuth.requireAuth();

// Module state
let allRules = [];
let currentEditingRule = null;
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
const actionFilter = document.getElementById('actionFilter');
const showingCountText = document.getElementById('showingCountText');

const tableLoading = document.getElementById('tableLoading');
const tableEmpty = document.getElementById('tableEmpty');
const emptyMessage = document.getElementById('emptyMessage');
const tableWrapper = document.getElementById('tableWrapper');
const rulesTable = document.getElementById('rulesTable');
const rulesTableBody = document.getElementById('rulesTableBody');

const openRuleModalBtn = document.getElementById('openRuleModalBtn');
const ruleModal = document.getElementById('ruleModal');
const ruleModalTitle = document.getElementById('ruleModalTitle');
const ruleModalError = document.getElementById('ruleModalError');
const ruleForm = document.getElementById('ruleForm');
const ruleIdInput = document.getElementById('ruleId');

const ruleNameInput = document.getElementById('ruleName');
const ruleNameError = document.getElementById('ruleNameError');
const maturitySelect = document.getElementById('maturitySelect');
const priceTrendSelect = document.getElementById('priceTrendSelect');
const demandLevelSelect = document.getElementById('demandLevelSelect');

const preservationCheckbox = document.getElementById('preservationCheckbox');
const preservationSafetyNote = document.getElementById('preservationSafetyNote');

const actionSelect = document.getElementById('actionSelect');
const actionError = document.getElementById('actionError');
const waitingPeriodInput = document.getElementById('waitingPeriodInput');
const waitingPeriodError = document.getElementById('waitingPeriodError');

const minQuantityInput = document.getElementById('minQuantityInput');
const minQuantityError = document.getElementById('minQuantityError');
const priorityInput = document.getElementById('priorityInput');
const priorityError = document.getElementById('priorityError');

const modalCancelBtn = document.getElementById('modalCancelBtn');
const modalSubmitBtn = document.getElementById('modalSubmitBtn');

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
 * Update summary strip counts.
 */
function updateSummaryCounts() {
  const total = allRules.length;
  const active = allRules.filter(r => r.is_active).length;
  const inactive = total - active;

  totalCountEl.textContent = String(total);
  activeCountEl.textContent = String(active);
  inactiveCountEl.textContent = String(inactive);
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
 * Format helpers for displayed pill text.
 */
function formatMaturity(val) {
  const m = (val || '').toUpperCase();
  if (m === 'GREEN') return 'Green';
  if (m === 'TURNING') return 'Turning';
  if (m === 'RIPE') return 'Ripe';
  return val || '-';
}

function formatPriceTrend(val) {
  const t = (val || '').toUpperCase();
  if (t === 'RISING') return 'Rising';
  if (t === 'STABLE') return 'Stable';
  if (t === 'FALLING') return 'Falling';
  return val || '-';
}

function formatDemand(val) {
  const d = (val || '').toUpperCase();
  if (d === 'HIGH') return 'High';
  if (d === 'MEDIUM') return 'Medium';
  if (d === 'LOW') return 'Low';
  return val || '-';
}

function formatAction(val) {
  const a = (val || '').toUpperCase();
  if (a === 'SELL_NOW') return 'Sell now';
  if (a === 'STORE_AND_WAIT') return 'Store and wait';
  if (a === 'SEEK_ALTERNATIVE_MARKET') return 'Seek alternative market';
  return val || '-';
}

/**
 * Return array of displayed text strings for searchable fields.
 */
function getSearchText(rule) {
  return [
    rule.rule_name || '',
    formatMaturity(rule.maturity),
    formatPriceTrend(rule.price_trend),
    formatDemand(rule.demand_level),
    formatAction(rule.action)
  ];
}

/**
 * Sort rules by user selection or default (priority ascending, ties by rule_name).
 */
function sortRules(rules) {
  return [...rules].sort((a, b) => {
    if (sortState.key === 'priority') {
      const pA = Number(a.priority);
      const pB = Number(b.priority);
      return sortState.direction === 'asc' ? pA - pB : pB - pA;
    }
    if (sortState.key === 'rule_name') {
      const valA = (a.rule_name || '').trim();
      const valB = (b.rule_name || '').trim();
      const isEmptyA = !valA || valA === '-';
      const isEmptyB = !valB || valB === '-';
      if (isEmptyA && isEmptyB) return 0;
      if (isEmptyA) return 1;
      if (isEmptyB) return -1;
      const cmp = valA.localeCompare(valB, undefined, { sensitivity: 'base', numeric: true });
      return sortState.direction === 'asc' ? cmp : -cmp;
    }

    // Default order
    const pA = Number(a.priority);
    const pB = Number(b.priority);
    if (pA !== pB) return pA - pB;
    return (a.rule_name || '').localeCompare(b.rule_name || '');
  });
}

/**
 * Build a rule table row using safe DOM methods (textContent only).
 */
function createRuleRow(rule, query = '') {
  const tr = document.createElement('tr');
  tr.dataset.ruleId = rule.rule_id;

  // 1. Priority Badge (outline in slate)
  const tdPriority = document.createElement('td');
  const priorityBadge = document.createElement('span');
  priorityBadge.className = 'badge badge-slate pill-w-sm';
  priorityBadge.textContent = `#${rule.priority}`;
  tdPriority.appendChild(priorityBadge);
  tr.appendChild(tdPriority);

  // 2. Rule Name
  const tdName = document.createElement('td');
  tdName.style.fontWeight = '600';
  highlightInto(tdName, rule.rule_name || '-', query);
  tr.appendChild(tdName);

  // 3. Conditions
  const tdConditions = document.createElement('td');
  const conditionsWrap = document.createElement('div');
  conditionsWrap.className = 'conditions-wrap';

  // Line 1: maturity, price trend, demand pills (same width class pill-w-md for all three)
  const pillsWrap = document.createElement('div');
  pillsWrap.className = 'conditions-pills';

  // Maturity pill
  const maturityPill = document.createElement('span');
  const matUpper = (rule.maturity || '').toUpperCase();
  if (matUpper === 'GREEN') maturityPill.className = 'badge badge-green pill-w-md';
  else if (matUpper === 'TURNING') maturityPill.className = 'badge badge-amber pill-w-md';
  else maturityPill.className = 'badge badge-red pill-w-md';
  highlightInto(maturityPill, formatMaturity(rule.maturity), query);
  pillsWrap.appendChild(maturityPill);

  // Price Trend pill
  const trendPill = document.createElement('span');
  const trendUpper = (rule.price_trend || '').toUpperCase();
  if (trendUpper === 'RISING') trendPill.className = 'badge badge-amber pill-w-md';
  else if (trendUpper === 'STABLE') trendPill.className = 'badge badge-slate pill-w-md';
  else trendPill.className = 'badge badge-red pill-w-md';
  highlightInto(trendPill, formatPriceTrend(rule.price_trend), query);
  pillsWrap.appendChild(trendPill);

  // Demand pill
  const demandPill = document.createElement('span');
  const demUpper = (rule.demand_level || '').toUpperCase();
  if (demUpper === 'HIGH') demandPill.className = 'badge badge-green pill-w-md';
  else if (demUpper === 'MEDIUM') demandPill.className = 'badge badge-amber pill-w-md';
  else demandPill.className = 'badge badge-red pill-w-md';
  highlightInto(demandPill, formatDemand(rule.demand_level), query);
  pillsWrap.appendChild(demandPill);

  conditionsWrap.appendChild(pillsWrap);

  // Line 2: Preservation and Min qty on one line (12px gap, nowrap)
  const metaLine = document.createElement('div');
  metaLine.className = 'conditions-meta-line';

  const presSpan = document.createElement('span');
  presSpan.textContent = `Preservation: ${rule.preservation_required ? 'Yes' : 'No'}`;
  metaLine.appendChild(presSpan);

  if (rule.min_quantity_kg !== null && rule.min_quantity_kg !== undefined && rule.min_quantity_kg !== '') {
    const minQtySpan = document.createElement('span');
    minQtySpan.textContent = `Min qty: ${rule.min_quantity_kg} kg`;
    metaLine.appendChild(minQtySpan);
  }

  conditionsWrap.appendChild(metaLine);
  tdConditions.appendChild(conditionsWrap);
  tr.appendChild(tdConditions);

  // 4. Result (Action Badge & Waiting Period)
  const tdResult = document.createElement('td');
  const actionBadge = document.createElement('span');
  const actUpper = (rule.action || '').toUpperCase();

  if (actUpper === 'STORE_AND_WAIT') {
    actionBadge.className = 'badge badge-amber pill-w-xl';
  } else if (actUpper === 'SEEK_ALTERNATIVE_MARKET') {
    actionBadge.className = 'badge badge-blue pill-w-xl';
  } else {
    actionBadge.className = 'badge badge-green pill-w-xl';
  }
  highlightInto(actionBadge, formatAction(rule.action), query);
  tdResult.appendChild(actionBadge);

  const waitMeta = document.createElement('div');
  waitMeta.className = 'result-meta-line';
  if (actUpper === 'STORE_AND_WAIT' && rule.waiting_period_days) {
    waitMeta.textContent = `Wait ${rule.waiting_period_days} days`;
  } else {
    waitMeta.textContent = '\u00A0';
  }
  tdResult.appendChild(waitMeta);
  tr.appendChild(tdResult);

  // 5. Status
  const tdStatus = document.createElement('td');
  const statusBadge = document.createElement('span');
  if (rule.is_active) {
    statusBadge.className = 'badge badge-green badge-status';
    statusBadge.textContent = 'Active';
  } else {
    statusBadge.className = 'badge badge-slate badge-status';
    statusBadge.textContent = 'Inactive';
  }
  tdStatus.appendChild(statusBadge);
  tr.appendChild(tdStatus);

  // 6. Actions
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
  editBtn.addEventListener('click', () => openEditModal(rule));
  actionsWrap.appendChild(editBtn);

  // Activate / Deactivate Button
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'btn btn-outline btn-sm btn-action-toggle';
  if (rule.is_active) {
    toggleBtn.textContent = 'Deactivate';
    toggleBtn.style.color = 'var(--color-danger)';
    toggleBtn.style.borderColor = 'var(--color-danger-border)';
    toggleBtn.addEventListener('click', () => handleDeactivateRule(rule));
  } else {
    toggleBtn.textContent = 'Activate';
    toggleBtn.style.color = 'var(--color-success-text)';
    toggleBtn.style.borderColor = '#a7f3d0';
    toggleBtn.addEventListener('click', () => handleActivateRule(rule));
  }
  actionsWrap.appendChild(toggleBtn);

  tdActions.appendChild(actionsWrap);
  tr.appendChild(tdActions);

  return tr;
}

/**
 * Render filtered & sorted rules into table body.
 */
function renderTable(rules, query = '') {
  rulesTableBody.replaceChildren();

  if (allRules.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No decision rules registered yet.';
    return;
  }

  if (rules.length === 0) {
    tableWrapper.style.display = 'none';
    tableEmpty.style.display = 'block';
    emptyMessage.textContent = 'No decision rules match your filters.';
    return;
  }

  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'block';

  for (const rule of rules) {
    rulesTableBody.appendChild(createRuleRow(rule, query));
  }
}

/**
 * Update aria-sort attributes on sortable table headers.
 */
function updateSortHeaders() {
  const headers = document.querySelectorAll('#rulesTable th[data-sort]');
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
  const headers = document.querySelectorAll('#rulesTable th[data-sort]');
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
  const action = actionFilter.value;

  // 1. Full list -> 2. Dropdown filters
  let filtered = allRules.filter(rule => {
    // Status filter
    if (status === 'active' && !rule.is_active) return false;
    if (status === 'inactive' && rule.is_active) return false;

    // Action filter
    if (action !== 'all' && (rule.action || '').toUpperCase() !== action) {
      return false;
    }

    return true;
  });

  // 3. Search
  if (lowerQuery) {
    filtered = filtered.filter(rule => {
      const searchStrings = getSearchText(rule);
      return searchStrings.some(s => s.toLowerCase().includes(lowerQuery));
    });
  }

  // 4. Sort
  filtered = sortRules(filtered);

  // 5. Render
  showingCountText.textContent = `Showing ${filtered.length} of ${allRules.length} rules`;
  renderTable(filtered, query);
}

/**
 * Alias for backward compatibility.
 */
function applyFilters() {
  applyPipeline();
}

/**
 * Load decision rules list from backend API.
 */
async function loadRules() {
  tableLoading.style.display = 'block';
  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'none';

  try {
    const data = await MetlinkAPI.get('/rules');
    allRules = (data && data.rules) || [];
    updateSummaryCounts();
    applyFilters();
  } catch (err) {
    showErrorBanner(err.message || 'Failed to load decision rules.');
  } finally {
    tableLoading.style.display = 'none';
  }
}

/**
 * Clear a specific field inline error.
 */
function clearFieldError(errorEl, inputEl) {
  errorEl.textContent = '';
  errorEl.style.display = 'none';
  if (inputEl) inputEl.classList.remove('input-error');
}

/**
 * Reset all modal form errors.
 */
function clearModalErrors() {
  ruleModalError.style.display = 'none';
  ruleModalError.textContent = '';

  clearFieldError(ruleNameError, ruleNameInput);
  clearFieldError(actionError, actionSelect);
  clearFieldError(waitingPeriodError, waitingPeriodInput);
  clearFieldError(minQuantityError, minQuantityInput);
  clearFieldError(priorityError, priorityInput);
}

/**
 * Hard Safety Guard:
 * - If preservation_required is unchecked: disable STORE_AND_WAIT option.
 *   If STORE_AND_WAIT was selected, switch to SELL_NOW and show safety note.
 * - Waiting period field is enabled only when action is STORE_AND_WAIT; otherwise clear & disable.
 */
function applySafetyGuard() {
  const isPreserved = preservationCheckbox.checked;
  const currentAction = actionSelect.value;
  const storeOption = actionSelect.querySelector('option[value="STORE_AND_WAIT"]');

  if (!isPreserved) {
    if (storeOption) {
      storeOption.disabled = true;
    }
    if (currentAction === 'STORE_AND_WAIT') {
      actionSelect.value = 'SELL_NOW';
      preservationSafetyNote.textContent = 'Store and wait needs preservation to be available.';
      preservationSafetyNote.style.display = 'block';
    } else {
      preservationSafetyNote.textContent = '';
      preservationSafetyNote.style.display = 'none';
    }
  } else {
    if (storeOption) {
      storeOption.disabled = false;
    }
    preservationSafetyNote.textContent = '';
    preservationSafetyNote.style.display = 'none';
  }

  // Waiting period availability
  if (actionSelect.value === 'STORE_AND_WAIT') {
    waitingPeriodInput.disabled = false;
  } else {
    waitingPeriodInput.disabled = true;
    waitingPeriodInput.value = '';
    clearFieldError(waitingPeriodError, waitingPeriodInput);
  }
}

/**
 * Open shared modal for Create Rule.
 */
function openCreateModal() {
  currentEditingRule = null;
  ruleForm.reset();
  clearModalErrors();

  ruleIdInput.value = '';
  ruleModalTitle.textContent = 'Create Decision Rule';
  modalSubmitBtn.textContent = 'Create Rule';
  modalSubmitBtn.disabled = false;

  preservationCheckbox.checked = false;
  actionSelect.value = 'SELL_NOW';
  priorityInput.value = '1';

  applySafetyGuard();
  ruleModal.showModal();
  ruleNameInput.focus();
}

/**
 * Open shared modal for Edit Rule.
 */
function openEditModal(rule) {
  currentEditingRule = rule;
  ruleForm.reset();
  clearModalErrors();

  ruleIdInput.value = rule.rule_id;
  ruleModalTitle.textContent = 'Edit Decision Rule';
  modalSubmitBtn.textContent = 'Save Changes';
  modalSubmitBtn.disabled = false;

  ruleNameInput.value = rule.rule_name || '';
  maturitySelect.value = (rule.maturity || 'RIPE').toUpperCase();
  priceTrendSelect.value = (rule.price_trend || 'STABLE').toUpperCase();
  demandLevelSelect.value = (rule.demand_level || 'HIGH').toUpperCase();
  preservationCheckbox.checked = Boolean(rule.preservation_required);

  // Apply safety guard first to enable option if preservation is checked
  applySafetyGuard();

  actionSelect.value = (rule.action || 'SELL_NOW').toUpperCase();
  applySafetyGuard();

  if (rule.action === 'STORE_AND_WAIT' && rule.waiting_period_days) {
    waitingPeriodInput.value = rule.waiting_period_days;
  } else {
    waitingPeriodInput.value = '';
  }

  minQuantityInput.value = rule.min_quantity_kg !== null && rule.min_quantity_kg !== undefined
    ? rule.min_quantity_kg
    : '';
  priorityInput.value = rule.priority || '1';

  ruleModal.showModal();
  ruleNameInput.focus();
}

/**
 * Handle form submission (Create or Edit).
 * Re-validates safety guard and inputs; sends full body payload.
 */
async function handleFormSubmit(event) {
  event.preventDefault();
  clearModalErrors();

  let hasError = false;

  const rule_name = ruleNameInput.value.trim();
  const maturity = maturitySelect.value;
  const price_trend = priceTrendSelect.value;
  const demand_level = demandLevelSelect.value;
  const preservation_required = preservationCheckbox.checked;
  const action = actionSelect.value;

  // Validate rule name
  if (!rule_name) {
    ruleNameError.textContent = 'Rule name is required.';
    ruleNameError.style.display = 'block';
    ruleNameInput.classList.add('input-error');
    hasError = true;
  }

  // Hard safety guard check: STORE_AND_WAIT requires preservation
  if (action === 'STORE_AND_WAIT' && !preservation_required) {
    actionError.textContent = 'Store and wait requires preservation to be checked.';
    actionError.style.display = 'block';
    actionSelect.classList.add('input-error');
    hasError = true;
  }

  // Validate waiting period
  let waiting_period_days = null;
  if (action === 'STORE_AND_WAIT') {
    const rawWait = waitingPeriodInput.value.trim();
    const waitNum = Number(rawWait);
    if (!rawWait || isNaN(waitNum) || waitNum < 1 || !Number.isInteger(waitNum)) {
      waitingPeriodError.textContent = 'Waiting period is required and must be a whole number of 1 or more.';
      waitingPeriodError.style.display = 'block';
      waitingPeriodInput.classList.add('input-error');
      hasError = true;
    } else {
      waiting_period_days = waitNum;
    }
  }

  // Validate min quantity
  let min_quantity_kg = null;
  const rawMinQty = minQuantityInput.value.trim();
  if (rawMinQty !== '') {
    const qtyNum = Number(rawMinQty);
    if (isNaN(qtyNum) || qtyNum <= 0) {
      minQuantityError.textContent = 'Minimum quantity must be greater than 0 kg.';
      minQuantityError.style.display = 'block';
      minQuantityInput.classList.add('input-error');
      hasError = true;
    } else {
      min_quantity_kg = qtyNum;
    }
  }

  // Validate priority
  const rawPriority = priorityInput.value.trim();
  const priorityNum = Number(rawPriority);
  if (!rawPriority || isNaN(priorityNum) || priorityNum < 1 || !Number.isInteger(priorityNum)) {
    priorityError.textContent = 'Priority is required and must be a whole number of 1 or more.';
    priorityError.style.display = 'block';
    priorityInput.classList.add('input-error');
    hasError = true;
  }

  if (hasError) return;

  modalSubmitBtn.disabled = true;
  modalSubmitBtn.textContent = 'Saving...';

  try {
    if (currentEditingRule) {
      // Edit: PUT /rules/<id> sending full body
      await MetlinkAPI.put(`/rules/${currentEditingRule.rule_id}`, {
        rule_name,
        maturity,
        price_trend,
        demand_level,
        preservation_required,
        action,
        waiting_period_days,
        min_quantity_kg,
        priority: priorityNum,
        is_active: currentEditingRule.is_active
      });

      ruleModal.close();
      showSuccessBanner(`Decision rule "${rule_name}" updated successfully.`);
    } else {
      // Create: POST /rules
      await MetlinkAPI.post('/rules', {
        rule_name,
        maturity,
        price_trend,
        demand_level,
        preservation_required,
        action,
        waiting_period_days,
        min_quantity_kg,
        priority: priorityNum
      });

      ruleModal.close();
      showSuccessBanner(`Decision rule "${rule_name}" created successfully.`);
    }

    await loadRules();
  } catch (err) {
    const errorMsg = err.message || 'Failed to save decision rule.';
    ruleModalError.textContent = errorMsg;
    ruleModalError.style.display = 'flex';
    showErrorBanner(errorMsg);
  } finally {
    modalSubmitBtn.disabled = false;
    modalSubmitBtn.textContent = currentEditingRule ? 'Save Changes' : 'Create Rule';
  }
}

/**
 * Handle rule deactivation with confirmation.
 * Sends full body with is_active: false.
 */
async function handleDeactivateRule(rule) {
  const confirmed = window.confirm(
    `Deactivate "${rule.rule_name}"? Inactive rules are skipped by the advice engine.`
  );
  if (!confirmed) return;

  try {
    await MetlinkAPI.put(`/rules/${rule.rule_id}`, {
      rule_name: rule.rule_name,
      maturity: rule.maturity,
      price_trend: rule.price_trend,
      demand_level: rule.demand_level,
      preservation_required: rule.preservation_required,
      action: rule.action,
      waiting_period_days: rule.waiting_period_days,
      min_quantity_kg: rule.min_quantity_kg,
      priority: rule.priority,
      is_active: false
    });

    showSuccessBanner(`Rule "${rule.rule_name}" has been deactivated.`);
    await loadRules();
  } catch (err) {
    showErrorBanner(err.message || `Failed to deactivate "${rule.rule_name}".`);
  }
}

/**
 * Handle rule reactivation with confirmation.
 * Sends full body with is_active: true.
 */
async function handleActivateRule(rule) {
  const confirmed = window.confirm(
    `Activate "${rule.rule_name}"? The rule will be evaluated by the advice engine.`
  );
  if (!confirmed) return;

  try {
    await MetlinkAPI.put(`/rules/${rule.rule_id}`, {
      rule_name: rule.rule_name,
      maturity: rule.maturity,
      price_trend: rule.price_trend,
      demand_level: rule.demand_level,
      preservation_required: rule.preservation_required,
      action: rule.action,
      waiting_period_days: rule.waiting_period_days,
      min_quantity_kg: rule.min_quantity_kg,
      priority: rule.priority,
      is_active: true
    });

    showSuccessBanner(`Rule "${rule.rule_name}" has been activated.`);
    await loadRules();
  } catch (err) {
    showErrorBanner(err.message || `Failed to activate "${rule.rule_name}".`);
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
actionFilter.addEventListener('change', () => applyFilters());

// Safety guard triggers on form change
preservationCheckbox.addEventListener('change', applySafetyGuard);
actionSelect.addEventListener('change', applySafetyGuard);

// Modal triggers
openRuleModalBtn.addEventListener('click', openCreateModal);
modalCancelBtn.addEventListener('click', () => ruleModal.close());
ruleForm.addEventListener('submit', handleFormSubmit);

// Initial data load
initSortHeaders();
if (currentAdmin) {
  loadRules();
}
