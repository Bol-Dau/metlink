/**
 * METLINK — Persistent Resizable & Collapsible Sidebar Module
 * Immediately applies saved width/collapse before first paint,
 * and wires sticky resizer, keyboard shortcuts, collapse toggle, and SVG icons.
 */

// 1. Immediate execution: read localStorage and apply custom width / collapse state
(function initSidebarState() {
  try {
    const savedCollapsed = localStorage.getItem('metlink_sidebar_collapsed');
    if (savedCollapsed === 'true') {
      document.documentElement.setAttribute('data-sidebar', 'collapsed');
    } else {
      const savedWidth = parseInt(localStorage.getItem('metlink_sidebar_width'), 10);
      if (!isNaN(savedWidth) && savedWidth >= 200 && savedWidth <= 340) {
        document.documentElement.style.setProperty('--sidebar-width', `${savedWidth}px`);
      } else {
        document.documentElement.style.setProperty('--sidebar-width', '240px');
      }
    }
  } catch (err) {
    document.documentElement.style.setProperty('--sidebar-width', '240px');
  }
})();

// Helper to get verified current width from localStorage
function getSavedSidebarWidth() {
  try {
    const w = parseInt(localStorage.getItem('metlink_sidebar_width'), 10);
    if (!isNaN(w) && w >= 200 && w <= 340) return w;
  } catch (e) {}
  return 240;
}

// 2. DOM-dependent initialization
document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;

  const sidebarHeader = sidebar.querySelector('.sidebar-header');
  const sidebarNav = sidebar.querySelector('.sidebar-nav');
  const logoutBtn = document.getElementById('logoutBtn');

  // SVG Icons for sidebar navigation items
  const ICONS = {
    'dashboard': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>',
    'farmers': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    'markets': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    'seasons': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    'rules': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>',
    'logs': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
    'admins': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    'logout': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>'
  };

  // Enhance sidebar navigation links with SVG icon and wrapped label
  if (sidebarNav) {
    const links = sidebarNav.querySelectorAll('a.sidebar-link');
    links.forEach(link => {
      const href = (link.getAttribute('href') || '').toLowerCase();
      let iconKey = 'dashboard';
      if (href.includes('farmers')) iconKey = 'farmers';
      else if (href.includes('markets')) iconKey = 'markets';
      else if (href.includes('seasons')) iconKey = 'seasons';
      else if (href.includes('rules')) iconKey = 'rules';
      else if (href.includes('logs')) iconKey = 'logs';

      const labelText = link.textContent.trim();
      link.textContent = '';
      link.title = labelText;

      const iconWrapper = document.createElement('span');
      iconWrapper.className = 'sidebar-icon';
      iconWrapper.innerHTML = ICONS[iconKey] || ICONS.dashboard;
      link.appendChild(iconWrapper);

      const labelSpan = document.createElement('span');
      labelSpan.className = 'sidebar-label';
      labelSpan.textContent = labelText;
      link.appendChild(labelSpan);
    });

    // Inject "Admins" link for super_admin at end of navigation list
    try {
      let currentAdminObj = null;
      if (typeof MetlinkAuth !== 'undefined' && MetlinkAuth.getAdmin) {
        currentAdminObj = MetlinkAuth.getAdmin();
      } else {
        const rawAdmin = localStorage.getItem('metlink_admin');
        if (rawAdmin) currentAdminObj = JSON.parse(rawAdmin);
      }

      if (currentAdminObj && currentAdminObj.role === 'super_admin') {
        if (!sidebarNav.querySelector('a[href$="admins.html"]')) {
          const isAdminsPage = window.location.pathname.endsWith('admins.html') || window.location.pathname.includes('/admins.html');
          const adminLink = document.createElement('a');
          adminLink.href = 'admins.html';
          adminLink.className = isAdminsPage ? 'sidebar-link active' : 'sidebar-link';
          adminLink.title = 'Admins';

          const iconWrapper = document.createElement('span');
          iconWrapper.className = 'sidebar-icon';
          iconWrapper.innerHTML = ICONS.admins;
          adminLink.appendChild(iconWrapper);

          const labelSpan = document.createElement('span');
          labelSpan.className = 'sidebar-label';
          labelSpan.textContent = 'Admins';
          adminLink.appendChild(labelSpan);

          sidebarNav.appendChild(adminLink);
        }
      }
    } catch (e) {}
  }

  // Enhance sign out button with icon and label wrapper
  if (logoutBtn) {
    const logoutText = logoutBtn.textContent.trim() || 'Sign out';
    logoutBtn.textContent = '';
    logoutBtn.title = logoutText;
    logoutBtn.setAttribute('aria-label', logoutText);

    const logoutIcon = document.createElement('span');
    logoutIcon.className = 'sidebar-icon';
    logoutIcon.innerHTML = ICONS.logout;
    logoutBtn.appendChild(logoutIcon);

    const logoutLabel = document.createElement('span');
    logoutLabel.className = 'sidebar-label';
    logoutLabel.textContent = logoutText;
    logoutBtn.appendChild(logoutLabel);
  }

  // Inject collapse/expand toggle button into sidebar header
  let toggleBtn = null;
  if (sidebarHeader) {
    toggleBtn = document.createElement('button');
    toggleBtn.className = 'sidebar-toggle';
    toggleBtn.type = 'button';

    const isCollapsed = document.documentElement.getAttribute('data-sidebar') === 'collapsed';
    toggleBtn.textContent = isCollapsed ? '»' : '«';
    toggleBtn.setAttribute('aria-label', isCollapsed ? 'Expand sidebar' : 'Collapse sidebar');
    toggleBtn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');

    toggleBtn.addEventListener('click', () => {
      const currentlyCollapsed = document.documentElement.getAttribute('data-sidebar') === 'collapsed';
      if (currentlyCollapsed) {
        // Expand: remove collapsed attribute and restore custom saved width
        document.documentElement.removeAttribute('data-sidebar');
        const restoredWidth = getSavedSidebarWidth();
        document.documentElement.style.setProperty('--sidebar-width', `${restoredWidth}px`);
        toggleBtn.textContent = '«';
        toggleBtn.setAttribute('aria-label', 'Collapse sidebar');
        toggleBtn.setAttribute('aria-expanded', 'true');
        try {
          localStorage.setItem('metlink_sidebar_collapsed', 'false');
        } catch (e) {}
      } else {
        // Collapse: activate icon rail
        document.documentElement.setAttribute('data-sidebar', 'collapsed');
        toggleBtn.textContent = '»';
        toggleBtn.setAttribute('aria-label', 'Expand sidebar');
        toggleBtn.setAttribute('aria-expanded', 'false');
        try {
          localStorage.setItem('metlink_sidebar_collapsed', 'true');
        } catch (e) {}
      }
    });

    sidebarHeader.appendChild(toggleBtn);
  }

  // Inject resize handle
  const resizer = document.createElement('div');
  resizer.className = 'sidebar-resizer';
  resizer.setAttribute('role', 'separator');
  resizer.setAttribute('aria-orientation', 'vertical');
  resizer.setAttribute('aria-label', 'Resize sidebar');
  resizer.setAttribute('tabindex', '0');
  sidebar.appendChild(resizer);

  // Resize dragging with pointer capture
  let isDragging = false;

  resizer.addEventListener('pointerdown', (e) => {
    // Disable resizing if sidebar is collapsed
    if (document.documentElement.getAttribute('data-sidebar') === 'collapsed') return;
    if (e.button !== 0) return; // Only primary button

    isDragging = true;
    resizer.setPointerCapture(e.pointerId);
    document.documentElement.classList.add('sidebar-resizing');
  });

  resizer.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    const clientX = e.clientX;
    const clampedWidth = Math.min(340, Math.max(200, clientX));
    document.documentElement.style.setProperty('--sidebar-width', `${clampedWidth}px`);
  });

  function stopResize(e) {
    if (!isDragging) return;
    isDragging = false;
    try {
      resizer.releasePointerCapture(e.pointerId);
    } catch (err) {}
    document.documentElement.classList.remove('sidebar-resizing');

    // Save final width
    const currentVar = document.documentElement.style.getPropertyValue('--sidebar-width');
    const finalWidth = parseInt(currentVar, 10);
    if (!isNaN(finalWidth) && finalWidth >= 200 && finalWidth <= 340) {
      try {
        localStorage.setItem('metlink_sidebar_width', String(finalWidth));
      } catch (err) {}
    }
  }

  resizer.addEventListener('pointerup', stopResize);
  resizer.addEventListener('pointercancel', stopResize);

  // Keyboard navigation on resizer
  resizer.addEventListener('keydown', (e) => {
    if (document.documentElement.getAttribute('data-sidebar') === 'collapsed') return;

    let currentWidth = parseInt(document.documentElement.style.getPropertyValue('--sidebar-width'), 10);
    if (isNaN(currentWidth)) currentWidth = getSavedSidebarWidth();

    let newWidth = currentWidth;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      newWidth = Math.max(200, currentWidth - 10);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      newWidth = Math.min(340, currentWidth + 10);
    } else if (e.key === 'Home') {
      e.preventDefault();
      newWidth = 240;
    }

    if (newWidth !== currentWidth) {
      document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
      try {
        localStorage.setItem('metlink_sidebar_width', String(newWidth));
      } catch (err) {}
    }
  });

  // Double click resets to 240px
  resizer.addEventListener('dblclick', () => {
    if (document.documentElement.getAttribute('data-sidebar') === 'collapsed') return;
    document.documentElement.style.setProperty('--sidebar-width', '240px');
    try {
      localStorage.setItem('metlink_sidebar_width', '240');
    } catch (err) {}
  });
});
