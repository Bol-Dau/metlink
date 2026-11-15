/**
 * METLINK Authentication Manager
 * Handles admin session management, login, logout, and route guarding.
 */

const MetlinkAuth = {
  TOKEN_KEY: 'metlink_token',
  ADMIN_KEY: 'metlink_admin',

  /**
   * Authenticate admin with username and password.
   * Calls POST /auth/login with auth=false, stores credentials, and returns the admin profile.
   * @param {string} username
   * @param {string} password
   * @returns {Promise<Object>} The admin profile object
   */
  async login(username, password) {
    const data = await MetlinkAPI.post('/auth/login', { username, password }, { auth: false });
    if (data && data.token) {
      localStorage.setItem(this.TOKEN_KEY, data.token);
    }
    if (data && data.admin) {
      localStorage.setItem(this.ADMIN_KEY, JSON.stringify(data.admin));
    }
    return data ? data.admin : null;
  },

  /**
   * Log out admin: notify backend, clear local storage keys, and redirect to login.html.
   */
  async logout() {
    try {
      await MetlinkAPI.post('/auth/logout');
    } catch (err) {
      // Ignore errors during logout per specification
    } finally {
      localStorage.removeItem(this.TOKEN_KEY);
      localStorage.removeItem(this.ADMIN_KEY);
      window.location.href = 'login.html';
    }
  },

  /**
   * Retrieve the stored JWT token.
   * @returns {string|null}
   */
  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  /**
   * Retrieve the stored admin object.
   * @returns {Object|null}
   */
  getAdmin() {
    const raw = localStorage.getItem(this.ADMIN_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (err) {
      return null;
    }
  },

  /**
   * Check whether the user is logged in.
   * @returns {boolean}
   */
  isLoggedIn() {
    return Boolean(this.getToken());
  },

  /**
   * Route guard for protected pages.
   * If no token is present, redirects to login.html; otherwise returns the admin object.
   * @returns {Object|null}
   */
  requireAuth() {
    if (!this.isLoggedIn()) {
      window.location.href = 'login.html';
      return null;
    }
    return this.getAdmin();
  },

  /**
   * Redirect logged-in users away from guest pages (e.g. login.html) to dashboard.html.
   */
  redirectIfLoggedIn() {
    if (this.isLoggedIn()) {
      window.location.href = 'dashboard.html';
    }
  }
};

window.MetlinkAuth = MetlinkAuth;
