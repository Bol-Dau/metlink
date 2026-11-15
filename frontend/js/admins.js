/**
 * METLINK — Admins Management Module
 * Provides administrator provisioning, role assignment, profile editing,
 * and account activation/deactivation for super administrators.
 */

// 1. Access guard: enforce super_admin role immediately before any rendering
const currentAdmin = MetlinkAuth.requireAuth();
if (!currentAdmin || currentAdmin.role !== 'super_admin') {
  window.location.replace('dashboard.html');
}

// Module State
let allAdmins = [];
let currentEditingAdmin = null;
let successTimer = null;
const sortState = { key: 'full_name', direction: 'asc' };

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
const superAdminCountEl = document.getElementById('superAdminCount');

const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const roleFilter = document.getElementById('roleFilter');
const showingCountText = document.getElementById('showingCountText');

const tableLoading = document.getElementById('tableLoading');
const tableEmpty = document.getElementById('tableEmpty');
const emptyMessage = document.getElementById('emptyMessage');
const tableWrapper = document.getElementById('tableWrapper');
const adminsTable = document.getElementById('adminsTable');
const adminsTableBody = document.getElementById('adminsTableBody');

// Add Admin Modal Elements
const openAddAdminBtn = document.getElementById('openAddAdminBtn');
const addAdminModal = document.getElementById('addAdminModal');
const addAdminForm = document.getElementById('addAdminForm');
const addModalError = document.getElementById('addModalError');
const addFullNameInput = document.getElementById('addFullName');
const addFullNameError = document.getElementById('addFullNameError');
const addUsernameInput = document.getElementById('addUsername');
const addUsernameError = document.getElementById('addUsernameError');
const addEmailInput = document.getElementById('addEmail');
const addEmailError = document.getElementById('addEmailError');
const addRoleSelect = document.getElementById('addRole');
const addRoleError = document.getElementById('addRoleError');
const addPasswordInput = document.getElementById('addPassword');
const addPasswordError = document.getElementById('addPasswordError');
const addConfirmPasswordInput = document.getElementById('addConfirmPassword');
const addConfirmPasswordError = document.getElementById('addConfirmPasswordError');
const addTogglePasswords = document.getElementById('addTogglePasswords');
const addCancelBtn = document.getElementById('addCancelBtn');
const addSubmitBtn = document.getElementById('addSubmitBtn');

// Edit Admin Modal Elements
const editAdminModal = document.getElementById('editAdminModal');
const editAdminForm = document.getElementById('editAdminForm');
const editModalError = document.getElementById('editModalError');
const editAdminIdInput = document.getElementById('editAdminId');
const editUsernameInput = document.getElementById('editUsername');
const editFullNameInput = document.getElementById('editFullName');
const editFullNameError = document.getElementById('editFullNameError');
const editEmailInput = document.getElementById('editEmail');
const editEmailError = document.getElementById('editEmailError');
const editRoleSelect = document.getElementById('editRole');
const editRoleError = document.getElementById('editRoleError');
const editRoleNotice = document.getElementById('editRoleNotice');
const editCancelBtn = document.getElementById('editCancelBtn');
const editSubmitBtn = document.getElementById('editSubmitBtn');

/**
 * Display topbar administrator name.
 */
if (adminNameEl && currentAdmin) {
  adminNameEl.textContent = currentAdmin.full_name || currentAdmin.username || 'Admin';
}

/**
 * Display temporary success banner (auto-hides after 5s).
 */
function showSuccessBanner(message) {
  if (successTimer) clearTimeout(successTimer);
  alertError.style.display = 'none';
  alertSuccessText.textContent = message;
  alertSuccess.style.display = 'flex';
  successTimer = setTimeout(() => {
    alertSuccess.style.display = 'none';
    alertSuccessText.textContent = '';
  }, 5000);
}

/**
 * Display top-level error banner.
 */
function showErrorBanner(message) {
  if (successTimer) clearTimeout(successTimer);
  alertSuccess.style.display = 'none';
  alertErrorText.textContent = message;
  alertError.style.display = 'flex';
}

/**
 * Format timestamp into '15 Nov 2026' style safely.
 */
function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return '-';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * Format system role string into human-friendly label.
 */
function formatRole(role) {
  if (!role) return '-';
  if (role === 'super_admin') return 'SUPER ADMIN';
  if (role === 'market_analyst') return 'MARKET ANALYST';
  if (role === 'admin') return 'ADMIN';
  return role.toUpperCase();
}

/**
 * Safe substring highlighter using DOM nodes only.
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
 * Update summary strip KPI numbers.
 */
function updateSummaryCounts() {
  const total = allAdmins.length;
  const active = allAdmins.filter(a => a.is_active).length;
  const inactive = total - active;
  const superAdmins = allAdmins.filter(a => a.role === 'super_admin').length;

  totalCountEl.textContent = String(total);
  activeCountEl.textContent = String(active);
  inactiveCountEl.textContent = String(inactive);
  superAdminCountEl.textContent = String(superAdmins);
}

/**
 * Create a single table row using safe DOM methods.
 */
function createAdminRow(admin, query = '') {
  const tr = document.createElement('tr');
  tr.dataset.adminId = admin.admin_id;

  const isSelf = currentAdmin && Number(admin.admin_id) === Number(currentAdmin.admin_id);

  // 1. Name
  const tdName = document.createElement('td');
  tdName.style.fontWeight = '600';
  highlightInto(tdName, admin.full_name || '-', query);
  tr.appendChild(tdName);

  // 2. Username
  const tdUsername = document.createElement('td');
  highlightInto(tdUsername, admin.username || '-', query);
  tr.appendChild(tdUsername);

  // 3. Email
  const tdEmail = document.createElement('td');
  highlightInto(tdEmail, admin.email || '-', query);
  tr.appendChild(tdEmail);

  // 4. Role (outline badge: super_admin green, admin blue, market_analyst amber, shared uniform width 136px)
  const tdRole = document.createElement('td');
  const roleBadge = document.createElement('span');
  if (admin.role === 'super_admin') {
    roleBadge.className = 'badge badge-green admins-role-badge';
  } else if (admin.role === 'admin') {
    roleBadge.className = 'badge badge-blue admins-role-badge';
  } else if (admin.role === 'market_analyst') {
    roleBadge.className = 'badge badge-amber admins-role-badge';
  } else {
    roleBadge.className = 'badge badge-slate admins-role-badge';
  }
  highlightInto(roleBadge, formatRole(admin.role), query);
  tdRole.appendChild(roleBadge);
  tr.appendChild(tdRole);

  // 5. Status (ACTIVE or INACTIVE with standard badge-status pill-w-sm class)
  const tdStatus = document.createElement('td');
  const statusBadge = document.createElement('span');
  if (admin.is_active) {
    statusBadge.className = 'badge badge-success badge-status pill-w-sm';
    statusBadge.textContent = 'Active';
  } else {
    statusBadge.className = 'badge badge-inactive badge-status pill-w-sm';
    statusBadge.textContent = 'Inactive';
  }
  tdStatus.appendChild(statusBadge);
  tr.appendChild(tdStatus);

  // 6. Created date
  const tdCreated = document.createElement('td');
  tdCreated.textContent = formatDate(admin.created_at);
  tr.appendChild(tdCreated);

  // 7. Actions
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
  editBtn.addEventListener('click', () => openEditModal(admin));
  actionsWrap.appendChild(editBtn);

  // Activate / Deactivate Button (or "You" tag for own account)
  if (isSelf) {
    const youTag = document.createElement('span');
    youTag.className = 'admins-you-tag';
    youTag.textContent = 'You';
    actionsWrap.appendChild(youTag);
  } else {
    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn btn-outline btn-sm btn-action-toggle';
    if (admin.is_active) {
      toggleBtn.textContent = 'Deactivate';
      toggleBtn.style.color = 'var(--color-danger)';
      toggleBtn.style.borderColor = 'var(--color-danger-border)';
      toggleBtn.addEventListener('click', () => handleDeactivateAdmin(admin));
    } else {
      toggleBtn.textContent = 'Activate';
      toggleBtn.style.color = 'var(--color-secondary)';
      toggleBtn.style.borderColor = 'var(--color-secondary-border)';
      toggleBtn.addEventListener('click', () => handleActivateAdmin(admin));
    }
    actionsWrap.appendChild(toggleBtn);
  }

  tdActions.appendChild(actionsWrap);
  tr.appendChild(tdActions);

  return tr;
}

/**
 * Filter, search, sort, and render admin records.
 */
function applyPipeline() {
  const query = (searchInput.value || '').trim().toLowerCase();
  const statusVal = statusFilter.value;
  const roleVal = roleFilter.value;

  // 1. Filter
  let filtered = allAdmins.filter(admin => {
    if (statusVal === 'active' && !admin.is_active) return false;
    if (statusVal === 'inactive' && admin.is_active) return false;
    if (roleVal !== 'all' && admin.role !== roleVal) return false;

    if (query) {
      const matchFields = [
        admin.full_name || '',
        admin.username || '',
        admin.email || '',
        formatRole(admin.role)
      ];
      const matches = matchFields.some(txt => txt.toLowerCase().includes(query));
      if (!matches) return false;
    }
    return true;
  });

  // 2. Sort
  filtered.sort((a, b) => {
    let valA = (a[sortState.key] || '').toString().toLowerCase();
    let valB = (b[sortState.key] || '').toString().toLowerCase();
    const cmp = valA.localeCompare(valB);
    return sortState.direction === 'asc' ? cmp : -cmp;
  });

  // 3. Render
  adminsTableBody.replaceChildren();
  showingCountText.textContent = `Showing ${filtered.length} of ${allAdmins.length} admins`;

  if (filtered.length === 0) {
    tableWrapper.style.display = 'none';
    emptyMessage.textContent = allAdmins.length === 0
      ? 'No administrators found.'
      : 'No administrators match your search or filter.';
    tableEmpty.style.display = 'block';
  } else {
    tableEmpty.style.display = 'none';
    tableWrapper.style.display = 'block';
    filtered.forEach(admin => {
      adminsTableBody.appendChild(createAdminRow(admin, query));
    });
  }
}

/**
 * Update aria-sort attribute on table headers (no arrows).
 */
function updateSortHeaders() {
  const headers = document.querySelectorAll('#adminsTable th[data-sort]');
  headers.forEach(th => {
    if (th.dataset.sort === sortState.key) {
      th.setAttribute('aria-sort', sortState.direction === 'asc' ? 'ascending' : 'descending');
    } else {
      th.setAttribute('aria-sort', 'none');
    }
  });
}

/**
 * Handle column header click for sorting.
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
 * Wire keyboard and click listeners on sortable headers.
 */
function initSortHeaders() {
  const headers = document.querySelectorAll('#adminsTable th[data-sort]');
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
 * Fetch administrator list from backend.
 */
async function loadAdmins() {
  tableLoading.style.display = 'block';
  tableEmpty.style.display = 'none';
  tableWrapper.style.display = 'none';

  try {
    const res = await MetlinkAPI.get('/admins');
    allAdmins = (res && res.admins) || [];
    tableLoading.style.display = 'none';
    updateSummaryCounts();
    applyPipeline();
  } catch (err) {
    tableLoading.style.display = 'none';
    if (err.message && (err.message.includes('Super admin access required') || err.message.includes('403'))) {
      window.location.replace('dashboard.html');
      return;
    }
    showErrorBanner(err.message || 'Failed to load administrator accounts.');
  }
}

/**
 * Reset inline errors and styles for Add Admin modal.
 */
function resetAddModal() {
  addAdminForm.reset();
  addModalError.style.display = 'none';
  addModalError.textContent = '';

  [addFullNameInput, addUsernameInput, addEmailInput, addPasswordInput, addConfirmPasswordInput].forEach(inp => {
    inp.classList.remove('input-error');
  });
  [addFullNameError, addUsernameError, addEmailError, addRoleError, addPasswordError, addConfirmPasswordError].forEach(el => {
    el.style.display = 'none';
    el.textContent = '';
  });

  addPasswordInput.type = 'password';
  addConfirmPasswordInput.type = 'password';
  addTogglePasswords.checked = false;

  addSubmitBtn.disabled = false;
  addSubmitBtn.textContent = 'Register Admin';
  addCancelBtn.disabled = false;
}

/**
 * Reset inline errors and styles for Edit Admin modal.
 */
function resetEditModal() {
  editAdminForm.reset();
  editModalError.style.display = 'none';
  editModalError.textContent = '';

  [editFullNameInput, editEmailInput].forEach(inp => {
    inp.classList.remove('input-error');
  });
  [editFullNameError, editEmailError, editRoleError].forEach(el => {
    el.style.display = 'none';
    el.textContent = '';
  });

  editRoleSelect.disabled = false;
  editRoleNotice.style.display = 'none';

  editSubmitBtn.disabled = false;
  editSubmitBtn.textContent = 'Save Changes';
  editCancelBtn.disabled = false;
}

/**
 * Open Edit Modal for a target administrator.
 */
function openEditModal(admin) {
  resetEditModal();
  currentEditingAdmin = admin;

  editAdminIdInput.value = admin.admin_id;
  editUsernameInput.value = admin.username;
  editFullNameInput.value = admin.full_name;
  editEmailInput.value = admin.email;
  editRoleSelect.value = admin.role;

  // Role select is disabled on own row
  const isSelf = currentAdmin && Number(admin.admin_id) === Number(currentAdmin.admin_id);
  if (isSelf) {
    editRoleSelect.disabled = true;
    editRoleNotice.style.display = 'block';
  } else {
    editRoleSelect.disabled = false;
    editRoleNotice.style.display = 'none';
  }

  editAdminModal.showModal();
  editFullNameInput.focus();
}

/**
 * Handle Deactivate action with confirmation prompt.
 */
async function handleDeactivateAdmin(admin) {
  const displayName = admin.full_name || admin.username;
  const confirmed = confirm(`Deactivate ${displayName}? They will no longer be able to sign in. Their records and history are kept.`);
  if (!confirmed) return;

  try {
    const res = await MetlinkAPI.put(`/admins/${admin.admin_id}`, {
      full_name: admin.full_name,
      email: admin.email,
      role: admin.role,
      is_active: false
    });

    if (res && res.admin) {
      const idx = allAdmins.findIndex(a => a.admin_id === admin.admin_id);
      if (idx !== -1) {
        allAdmins[idx] = res.admin;
      }
      updateSummaryCounts();
      applyPipeline();
      showSuccessBanner(`Admin ${displayName} deactivated successfully.`);
    }
  } catch (err) {
    if (err.message && err.message.includes('403')) {
      window.location.replace('dashboard.html');
      return;
    }
    showErrorBanner(err.message || 'Failed to deactivate admin.');
  }
}

/**
 * Handle Activate action with confirmation prompt.
 */
async function handleActivateAdmin(admin) {
  const displayName = admin.full_name || admin.username;
  const confirmed = confirm(`Activate ${displayName}? They will regain access to sign in.`);
  if (!confirmed) return;

  try {
    const res = await MetlinkAPI.put(`/admins/${admin.admin_id}`, {
      full_name: admin.full_name,
      email: admin.email,
      role: admin.role,
      is_active: true
    });

    if (res && res.admin) {
      const idx = allAdmins.findIndex(a => a.admin_id === admin.admin_id);
      if (idx !== -1) {
        allAdmins[idx] = res.admin;
      }
      updateSummaryCounts();
      applyPipeline();
      showSuccessBanner(`Admin ${displayName} activated successfully.`);
    }
  } catch (err) {
    if (err.message && err.message.includes('403')) {
      window.location.replace('dashboard.html');
      return;
    }
    showErrorBanner(err.message || 'Failed to activate admin.');
  }
}

// Event Listeners

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

// Search & Filter event listeners
searchInput.addEventListener('input', applyPipeline);
statusFilter.addEventListener('change', applyPipeline);
roleFilter.addEventListener('change', applyPipeline);

// Add Modal Triggers
openAddAdminBtn.addEventListener('click', () => {
  resetAddModal();
  addAdminModal.showModal();
  addFullNameInput.focus();
});

addCancelBtn.addEventListener('click', () => {
  addAdminModal.close();
});

addTogglePasswords.addEventListener('change', () => {
  const newType = addTogglePasswords.checked ? 'text' : 'password';
  addPasswordInput.type = newType;
  addConfirmPasswordInput.type = newType;
});

// Edit Modal Triggers
editCancelBtn.addEventListener('click', () => {
  editAdminModal.close();
});

// Add Admin Form Submission
addAdminForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  addModalError.style.display = 'none';
  addModalError.textContent = '';

  const fullName = addFullNameInput.value.trim();
  const username = addUsernameInput.value.trim();
  const email = addEmailInput.value.trim();
  const role = addRoleSelect.value.trim();
  const password = addPasswordInput.value;
  const confirmPassword = addConfirmPasswordInput.value;

  let hasError = false;

  if (!fullName) {
    addFullNameError.textContent = 'Full name is required.';
    addFullNameError.style.display = 'block';
    addFullNameInput.classList.add('input-error');
    hasError = true;
  } else {
    addFullNameError.style.display = 'none';
    addFullNameInput.classList.remove('input-error');
  }

  const usernamePattern = /^[a-zA-Z0-9._-]{3,50}$/;
  if (!username) {
    addUsernameError.textContent = 'Username is required.';
    addUsernameError.style.display = 'block';
    addUsernameInput.classList.add('input-error');
    hasError = true;
  } else if (!usernamePattern.test(username)) {
    addUsernameError.textContent = 'Username must be 3-50 chars: letters, digits, dot, underscore, hyphen.';
    addUsernameError.style.display = 'block';
    addUsernameInput.classList.add('input-error');
    hasError = true;
  } else {
    addUsernameError.style.display = 'none';
    addUsernameInput.classList.remove('input-error');
  }

  const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  const emailLower = email.toLowerCase();
  const validEmailDomain = emailLower.endsWith('@metlink.rw') || emailLower.endsWith('@metlink.com');
  if (!email) {
    addEmailError.textContent = 'Email address is required.';
    addEmailError.style.display = 'block';
    addEmailInput.classList.add('input-error');
    hasError = true;
  } else if (!emailPattern.test(email) || email.length > 100) {
    addEmailError.textContent = 'Please enter a valid email address.';
    addEmailError.style.display = 'block';
    addEmailInput.classList.add('input-error');
    hasError = true;
  } else if (!validEmailDomain) {
    addEmailError.textContent = 'Email domain must be @metlink.rw or @metlink.com.';
    addEmailError.style.display = 'block';
    addEmailInput.classList.add('input-error');
    hasError = true;
  } else {
    addEmailError.style.display = 'none';
    addEmailInput.classList.remove('input-error');
  }

  if (!role) {
    addRoleError.textContent = 'Role is required.';
    addRoleError.style.display = 'block';
    hasError = true;
  } else {
    addRoleError.style.display = 'none';
  }

  const passBytes = new TextEncoder().encode(password).length;
  if (!password) {
    addPasswordError.textContent = 'Password is required.';
    addPasswordError.style.display = 'block';
    addPasswordInput.classList.add('input-error');
    hasError = true;
  } else if (password.length < 8) {
    addPasswordError.textContent = 'Password must be at least 8 characters long.';
    addPasswordError.style.display = 'block';
    addPasswordInput.classList.add('input-error');
    hasError = true;
  } else if (passBytes > 72) {
    addPasswordError.textContent = 'Password must not exceed 72 bytes.';
    addPasswordError.style.display = 'block';
    addPasswordInput.classList.add('input-error');
    hasError = true;
  } else {
    addPasswordError.style.display = 'none';
    addPasswordInput.classList.remove('input-error');
  }

  if (!confirmPassword) {
    addConfirmPasswordError.textContent = 'Please confirm the password.';
    addConfirmPasswordError.style.display = 'block';
    addConfirmPasswordInput.classList.add('input-error');
    hasError = true;
  } else if (confirmPassword !== password) {
    addConfirmPasswordError.textContent = 'Passwords do not match.';
    addConfirmPasswordError.style.display = 'block';
    addConfirmPasswordInput.classList.add('input-error');
    hasError = true;
  } else {
    addConfirmPasswordError.style.display = 'none';
    addConfirmPasswordInput.classList.remove('input-error');
  }

  if (hasError) return;

  addSubmitBtn.disabled = true;
  addSubmitBtn.textContent = 'Registering...';
  addCancelBtn.disabled = true;

  try {
    const res = await MetlinkAPI.post('/admins', {
      full_name: fullName,
      username: username,
      email: email,
      role: role,
      temporary_password: password
    });

    addAdminModal.close();
    resetAddModal();

    await loadAdmins();
    const createdName = (res && res.admin && (res.admin.full_name || res.admin.username)) || username;
    showSuccessBanner(`Created admin ${createdName} successfully.`);
  } catch (err) {
    addModalError.textContent = err.message || 'Failed to create administrator.';
    addModalError.style.display = 'block';
    addSubmitBtn.disabled = false;
    addSubmitBtn.textContent = 'Register Admin';
    addCancelBtn.disabled = false;
  }
});

// Edit Admin Form Submission
editAdminForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  editModalError.style.display = 'none';
  editModalError.textContent = '';

  if (!currentEditingAdmin) return;

  const adminId = currentEditingAdmin.admin_id;
  const fullName = editFullNameInput.value.trim();
  const email = editEmailInput.value.trim();
  const isSelf = currentAdmin && Number(adminId) === Number(currentAdmin.admin_id);
  const role = isSelf ? currentEditingAdmin.role : editRoleSelect.value.trim();

  let hasError = false;

  if (!fullName) {
    editFullNameError.textContent = 'Full name is required.';
    editFullNameError.style.display = 'block';
    editFullNameInput.classList.add('input-error');
    hasError = true;
  } else {
    editFullNameError.style.display = 'none';
    editFullNameInput.classList.remove('input-error');
  }

  const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  const editEmailLower = email.toLowerCase();
  const editValidDomain = editEmailLower.endsWith('@metlink.rw') || editEmailLower.endsWith('@metlink.com');
  if (!email) {
    editEmailError.textContent = 'Email address is required.';
    editEmailError.style.display = 'block';
    editEmailInput.classList.add('input-error');
    hasError = true;
  } else if (!emailPattern.test(email) || email.length > 100) {
    editEmailError.textContent = 'Please enter a valid email address.';
    editEmailError.style.display = 'block';
    editEmailInput.classList.add('input-error');
    hasError = true;
  } else if (!editValidDomain) {
    editEmailError.textContent = 'Email domain must be @metlink.rw or @metlink.com.';
    editEmailError.style.display = 'block';
    editEmailInput.classList.add('input-error');
    hasError = true;
  } else {
    editEmailError.style.display = 'none';
    editEmailInput.classList.remove('input-error');
  }

  if (hasError) return;

  editSubmitBtn.disabled = true;
  editSubmitBtn.textContent = 'Saving...';
  editCancelBtn.disabled = true;

  try {
    const res = await MetlinkAPI.put(`/admins/${adminId}`, {
      full_name: fullName,
      email: email,
      role: role,
      is_active: currentEditingAdmin.is_active
    });

    editAdminModal.close();
    resetEditModal();

    await loadAdmins();
    const updatedName = (res && res.admin && (res.admin.full_name || res.admin.username)) || 'Admin';
    showSuccessBanner(`Admin ${updatedName} updated successfully.`);
  } catch (err) {
    editModalError.textContent = err.message || 'Failed to update administrator.';
    editModalError.style.display = 'block';
    editSubmitBtn.disabled = false;
    editSubmitBtn.textContent = 'Save Changes';
    editCancelBtn.disabled = false;
  }
});

// Initialization
initSortHeaders();
loadAdmins();
