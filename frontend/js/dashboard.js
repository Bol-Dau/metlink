/**
 * METLINK — Dashboard Home Module
 * Handles executive KPI rendering, recent audit activity feed,
 * administrator profile presentation, and change-password modal workflow.
 */

// Route guard: ensure admin session is active
const currentAdmin = MetlinkAuth.requireAuth();

// DOM References
const adminNameEl = document.getElementById('adminName');
const logoutBtn = document.getElementById('logoutBtn');

// Feedback Banners
const alertSuccess = document.getElementById('alertSuccess');
const alertSuccessText = document.getElementById('alertSuccessText');
const alertError = document.getElementById('alertError');
const alertErrorText = document.getElementById('alertErrorText');
const dismissAlertErrorBtn = document.getElementById('dismissAlertErrorBtn');

// Hero Profile Elements
const heroFullName = document.getElementById('heroFullName');
const heroUsername = document.getElementById('heroUsername');
const heroEmail = document.getElementById('heroEmail');
const heroRoleBadge = document.getElementById('heroRoleBadge');

// Account Profile Elements
const accFullName = document.getElementById('accFullName');
const accUsername = document.getElementById('accUsername');
const accEmail = document.getElementById('accEmail');
const accRoleBadge = document.getElementById('accRoleBadge');

// Overview Elements
const refreshOverviewBtn = document.getElementById('refreshOverviewBtn');
const retryOverviewBtn = document.getElementById('retryOverviewBtn');
const overviewLoading = document.getElementById('overviewLoading');
const overviewError = document.getElementById('overviewError');
const overviewErrorText = document.getElementById('overviewErrorText');
const overviewContent = document.getElementById('overviewContent');

const kpiActiveFarmers = document.getElementById('kpiActiveFarmers');
const kpiTotalSubmissions = document.getElementById('kpiTotalSubmissions');
const kpiPendingSubmissions = document.getElementById('kpiPendingSubmissions');
const kpiDeliveredSms = document.getElementById('kpiDeliveredSms');
const kpiTotalSms = document.getElementById('kpiTotalSms');

const activeSeasonName = document.getElementById('activeSeasonName');
const activeSeasonDates = document.getElementById('activeSeasonDates');
const activityList = document.getElementById('activityList');
const activityEmpty = document.getElementById('activityEmpty');

// Change Password Dialog Elements
const openChangePasswordBtn = document.getElementById('openChangePasswordBtn');
const changePasswordModal = document.getElementById('changePasswordModal');
const changePasswordForm = document.getElementById('changePasswordForm');
const modalAlertError = document.getElementById('modalAlertError');
const modalAlertErrorText = document.getElementById('modalAlertErrorText');
const currentPasswordInput = document.getElementById('currentPasswordInput');
const currentPasswordError = document.getElementById('currentPasswordError');
const newPasswordInput = document.getElementById('newPasswordInput');
const newPasswordError = document.getElementById('newPasswordError');
const confirmPasswordInput = document.getElementById('confirmPasswordInput');
const confirmPasswordError = document.getElementById('confirmPasswordError');
const togglePasswordsCheckbox = document.getElementById('togglePasswordsCheckbox');
const modalCancelBtn = document.getElementById('modalCancelBtn');
const modalSubmitBtn = document.getElementById('modalSubmitBtn');

let successTimer = null;

/**
 * Display temporary success banner.
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
 * Format date like '01 Feb 2027'.
 */
function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return String(dateStr);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * Populate admin identity across topbar, hero, and account card.
 */
function populateAdminProfile(admin) {
  if (!admin) return;
  const displayName = admin.full_name || admin.username || 'Admin';
  const roleName = (admin.role || 'admin').toUpperCase();

  if (adminNameEl) adminNameEl.textContent = displayName;
  if (heroFullName) heroFullName.textContent = displayName;
  if (heroUsername) heroUsername.textContent = admin.username || '-';
  if (heroEmail) heroEmail.textContent = admin.email || '-';
  if (heroRoleBadge) heroRoleBadge.textContent = roleName;

  if (accFullName) accFullName.textContent = displayName;
  if (accUsername) accUsername.textContent = admin.username || '-';
  if (accEmail) accEmail.textContent = admin.email || '-';
  if (accRoleBadge) accRoleBadge.textContent = roleName;
}

/**
 * Fetch fresh admin profile from /auth/me.
 */
async function loadAdminProfile() {
  try {
    const res = await MetlinkAPI.get('/auth/me');
    if (res && res.admin) {
      populateAdminProfile(res.admin);
      try {
        localStorage.setItem(MetlinkAuth.ADMIN_KEY, JSON.stringify(res.admin));
      } catch (e) {}
    }
  } catch (err) {
    // Fall back silently to stored session admin
    populateAdminProfile(currentAdmin);
  }
}

/**
 * Fetch and render live metrics from GET /dashboard/summary.
 */
async function loadDashboardSummary() {
  overviewLoading.style.display = 'block';
  overviewError.style.display = 'none';
  overviewContent.style.display = 'none';

  try {
    const res = await MetlinkAPI.get('/dashboard/summary');
    const kpis = (res && res.kpis) || {};
    const activeSeason = res && res.active_season;
    const recentActivity = (res && res.recent_activity) || [];

    // 1. KPI Counts
    kpiActiveFarmers.textContent = String(kpis.active_farmers ?? 0);
    kpiTotalSubmissions.textContent = String(kpis.total_submissions ?? 0);
    kpiPendingSubmissions.textContent = String(kpis.pending_submissions ?? 0);
    kpiDeliveredSms.textContent = String(kpis.delivered_sms ?? 0);
    kpiTotalSms.textContent = String(kpis.total_sms ?? 0);

    // 2. Active Season Highlight
    if (activeSeason && activeSeason.season_name) {
      activeSeasonName.textContent = activeSeason.season_name;
      const startFmt = formatDate(activeSeason.start_date);
      const endFmt = formatDate(activeSeason.end_date);
      activeSeasonDates.textContent = (startFmt && endFmt) ? `${startFmt} – ${endFmt}` : (activeSeason.description || '');
    } else {
      activeSeasonName.textContent = 'No active season';
      activeSeasonDates.textContent = 'No active agricultural season currently set.';
    }

    // 3. Recent Activity List
    activityList.replaceChildren();
    if (recentActivity.length === 0) {
      activityEmpty.style.display = 'block';
    } else {
      activityEmpty.style.display = 'none';
      recentActivity.forEach(item => {
        const li = document.createElement('li');
        li.className = 'home-activity-item';

        // Details & Meta info
        const contentDiv = document.createElement('div');
        const detailsDiv = document.createElement('div');
        detailsDiv.style.fontWeight = '600';
        detailsDiv.style.color = 'var(--color-text)';
        detailsDiv.textContent = item.details || `${item.action} on ${item.entity}`;
        contentDiv.appendChild(detailsDiv);

        const metaDiv = document.createElement('div');
        metaDiv.className = 'home-activity-meta';
        metaDiv.textContent = `${item.admin_name || 'Admin'} • ${formatDateTime(item.created_at)}`;
        contentDiv.appendChild(metaDiv);

        li.appendChild(contentDiv);

        // Action outline badge
        const badgeSpan = document.createElement('span');
        const act = (item.action || '').toUpperCase();
        if (act === 'CREATE' || act === 'ACTIVATE') {
          badgeSpan.className = 'badge badge-green pill-w-md';
        } else if (act === 'UPDATE') {
          badgeSpan.className = 'badge badge-blue pill-w-md';
        } else if (act === 'DEACTIVATE') {
          badgeSpan.className = 'badge badge-red pill-w-md';
        } else {
          badgeSpan.className = 'badge badge-slate pill-w-md';
        }
        badgeSpan.textContent = act || '-';
        li.appendChild(badgeSpan);

        activityList.appendChild(li);
      });
    }

    overviewLoading.style.display = 'none';
    overviewContent.style.display = 'block';
  } catch (err) {
    overviewLoading.style.display = 'none';
    overviewContent.style.display = 'none';
    overviewErrorText.textContent = err.message || 'Failed to load system metrics.';
    overviewError.style.display = 'flex';
  }
}

/**
 * Reset inline errors and input styles in Change Password modal.
 */
function resetPasswordForm() {
  changePasswordForm.reset();
  modalAlertError.style.display = 'none';
  modalAlertErrorText.textContent = '';

  currentPasswordError.style.display = 'none';
  currentPasswordError.textContent = '';
  currentPasswordInput.classList.remove('input-error');

  newPasswordError.style.display = 'none';
  newPasswordError.textContent = '';
  newPasswordInput.classList.remove('input-error');

  confirmPasswordError.style.display = 'none';
  confirmPasswordError.textContent = '';
  confirmPasswordInput.classList.remove('input-error');

  currentPasswordInput.type = 'password';
  newPasswordInput.type = 'password';
  confirmPasswordInput.type = 'password';
  togglePasswordsCheckbox.checked = false;

  modalSubmitBtn.disabled = false;
  modalSubmitBtn.textContent = 'Update Password';
  modalCancelBtn.disabled = false;
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

if (refreshOverviewBtn) {
  refreshOverviewBtn.addEventListener('click', loadDashboardSummary);
}

if (retryOverviewBtn) {
  retryOverviewBtn.addEventListener('click', loadDashboardSummary);
}

// Modal open/close handlers
if (openChangePasswordBtn && changePasswordModal) {
  openChangePasswordBtn.addEventListener('click', () => {
    resetPasswordForm();
    changePasswordModal.showModal();
    currentPasswordInput.focus();
  });
}

if (modalCancelBtn && changePasswordModal) {
  modalCancelBtn.addEventListener('click', () => {
    changePasswordModal.close();
  });
}

// Show/hide passwords checkbox toggle
if (togglePasswordsCheckbox) {
  togglePasswordsCheckbox.addEventListener('change', () => {
    const newType = togglePasswordsCheckbox.checked ? 'text' : 'password';
    currentPasswordInput.type = newType;
    newPasswordInput.type = newType;
    confirmPasswordInput.type = newType;
  });
}

// Change Password submission
if (changePasswordForm) {
  changePasswordForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Clear previous errors
    modalAlertError.style.display = 'none';
    modalAlertErrorText.textContent = '';
    currentPasswordError.style.display = 'none';
    currentPasswordInput.classList.remove('input-error');
    newPasswordError.style.display = 'none';
    newPasswordInput.classList.remove('input-error');
    confirmPasswordError.style.display = 'none';
    confirmPasswordInput.classList.remove('input-error');

    const currentPass = currentPasswordInput.value;
    const newPass = newPasswordInput.value;
    const confirmPass = confirmPasswordInput.value;

    let hasClientError = false;

    if (!currentPass) {
      currentPasswordError.textContent = 'Current password is required.';
      currentPasswordError.style.display = 'block';
      currentPasswordInput.classList.add('input-error');
      hasClientError = true;
    }

    if (!newPass) {
      newPasswordError.textContent = 'New password is required.';
      newPasswordError.style.display = 'block';
      newPasswordInput.classList.add('input-error');
      hasClientError = true;
    } else if (newPass.length < 8) {
      newPasswordError.textContent = 'New password must be at least 8 characters long.';
      newPasswordError.style.display = 'block';
      newPasswordInput.classList.add('input-error');
      hasClientError = true;
    } else if (new TextEncoder().encode(newPass).length > 72) {
      newPasswordError.textContent = 'New password must not exceed 72 bytes.';
      newPasswordError.style.display = 'block';
      newPasswordInput.classList.add('input-error');
      hasClientError = true;
    } else if (newPass === currentPass) {
      newPasswordError.textContent = 'New password must differ from current password.';
      newPasswordError.style.display = 'block';
      newPasswordInput.classList.add('input-error');
      hasClientError = true;
    }

    if (!confirmPass) {
      confirmPasswordError.textContent = 'Please confirm your new password.';
      confirmPasswordError.style.display = 'block';
      confirmPasswordInput.classList.add('input-error');
      hasClientError = true;
    } else if (confirmPass !== newPass) {
      confirmPasswordError.textContent = 'Passwords do not match.';
      confirmPasswordError.style.display = 'block';
      confirmPasswordInput.classList.add('input-error');
      hasClientError = true;
    }

    if (hasClientError) return;

    // Send API request with noAuthRedirect: true so 401 does not redirect
    modalSubmitBtn.disabled = true;
    modalSubmitBtn.textContent = 'Saving...';
    modalCancelBtn.disabled = true;

    try {
      const res = await MetlinkAPI.post(
        '/auth/change-password',
        { current_password: currentPass, new_password: newPass },
        { noAuthRedirect: true }
      );

      changePasswordModal.close();
      resetPasswordForm();
      showSuccessBanner((res && res.message) || 'Password updated successfully.');
    } catch (err) {
      modalAlertErrorText.textContent = err.message || 'Failed to update password.';
      modalAlertError.style.display = 'flex';
      modalSubmitBtn.disabled = false;
      modalSubmitBtn.textContent = 'Update Password';
      modalCancelBtn.disabled = false;
    }
  });
}

// Initialize on page load
if (currentAdmin) {
  populateAdminProfile(currentAdmin);
  loadAdminProfile();
  loadDashboardSummary();
}
