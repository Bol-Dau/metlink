/**
 * METLINK API Client
 * Centralized fetch wrapper, base URL configuration, JWT authorization header management,
 * and standard HTTP error handling.
 */

const API_BASE = 'http://localhost:5000/api';

const MetlinkAPI = {
  baseUrl: API_BASE,

  /**
   * Main request helper for interacting with the METLINK backend.
   * @param {string} path - Endpoint path (e.g. '/auth/login' or '/farmers')
   * @param {Object} options - Request options: { method, body, auth }
   * @returns {Promise<any>}
   */
  async request(path, { method = 'GET', body = null, auth = true, noAuthRedirect = false } = {}) {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const url = `${this.baseUrl}${cleanPath}`;
    const isLoginCall = cleanPath === '/auth/login';

    const headers = {
      'Accept': 'application/json'
    };

    if (body !== null && body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }

    if (auth) {
      const token = localStorage.getItem('metlink_token');
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    const fetchOptions = {
      method: (method || 'GET').toUpperCase(),
      headers
    };

    if (body !== null && body !== undefined) {
      fetchOptions.body = typeof body === 'string' ? body : JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(url, fetchOptions);
    } catch (networkErr) {
      throw new Error('Cannot reach the server. Check that the backend is running.');
    }

    let data = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch (jsonErr) {
        data = null;
      }
    } else {
      try {
        const text = await response.text();
        if (text) {
          data = { message: text };
        }
      } catch (textErr) {
        data = null;
      }
    }

    // On HTTP 401 for any request except the login call: clear session and redirect (unless opted out)
    if (response.status === 401 && !isLoginCall) {
      if (noAuthRedirect) {
        const errorMsg = (data && (data.error || data.message)) || 'Current password is incorrect.';
        throw new Error(errorMsg);
      }
      localStorage.removeItem('metlink_token');
      localStorage.removeItem('metlink_admin');
      window.location.href = 'login.html';
      return null;
    }

    // On other non-OK responses, throw an Error with the server's message or friendly fallback
    if (!response.ok) {
      const errorMsg = (data && (data.error || data.message)) || `Request failed with status ${response.status}`;
      throw new Error(errorMsg);
    }

    return data;
  },

  /**
   * HTTP GET shortcut
   */
  get(path, options = {}) {
    return this.request(path, { ...options, method: 'GET' });
  },

  /**
   * HTTP POST shortcut
   */
  post(path, body = null, options = {}) {
    return this.request(path, { ...options, method: 'POST', body });
  },

  /**
   * HTTP PUT shortcut
   */
  put(path, body = null, options = {}) {
    return this.request(path, { ...options, method: 'PUT', body });
  }
};

window.MetlinkAPI = MetlinkAPI;
