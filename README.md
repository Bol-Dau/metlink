# METLINK

METLINK is a tomato harvest evaluation and market decision-support platform connecting smallholder tomato farmers in Kamonyi District, Rwanda, with wholesale and retail market intelligence across Kigali. Smallholder farmers interact with the platform using basic feature phones via USSD (`*384*...#`) and automated bilingual SMS advisory messages (in English and Kinyarwanda), while Kigali-based market administrators and analysts maintain market prices, evaluate agricultural seasons, and configure prioritized decision rules through a responsive web portal.

> [!NOTE]
> METLINK is a decision-support tool. It does not guarantee prices, buyers, or income.

---

## What It Does

- **Farmer USSD Flow**:
  - Session initiation on basic feature phones via Africa's Talking USSD.
  - Farmer authentication and profile lookup by phone number (`+250` format).
  - Language selection (English or Kinyarwanda).
  - Single-step harvest date entry (`DDMMYYYY`), quantity in kilograms, and maturity stage (green, turning, semi-ripe, ripe).
  - Immediate on-screen confirmation with resilient back navigation (`0`) and token folding.
  - Automated dispatch of bilingual GSM-7 SMS advice (under 160 characters) providing recommended action (`SELL_NOW`, `STORE_AND_WAIT`, `SPLIT_SHIPMENT`), targeted markets, and transport guidelines.
  - *Note on Kinyarwanda copy*: Kinyarwanda text templates require review and validation by a native speaker prior to production deployment.

- **Admin Web Portal**:
  - **Overview Dashboard**: High-level platform KPIs, active season status card, and live audit feed.
  - **Farmers Directory**: Register, view, search, edit, and toggle active status of Kamonyi tomato farmers.
  - **Market Intelligence**: Record and monitor wholesale and retail prices, demand levels, and transport costs for Kigali and local markets.
  - **Agricultural Seasons**: Calibrate Rwandan agricultural season dates (Season A, Season B, Season C).
  - **Decision Rules Engine**: Maintain prioritized harvest decision rules (min quantity, ripeness matching, storage preservation guards).
  - **Activity & System Logs**: Multi-tab inspection view covering Farmer USSD Harvest Submissions, SMS Delivery Dispatches, and Administrative Audit Trails.
  - **Staff & Admins Management**: Account provisioning and role-based access management (restricted to `super_admin`).
  - **Dark Mode**: Persistent dark mode with custom theme toggle, zero flash of unstyled content, and WCAG AA contrast compliance.

---

## Architecture & Directory Tree

```text
metlink/
├── .env.example                      # Template for database, auth, server, and Africa's Talking credentials
├── .gitignore                         # Git exclusion rules for secrets, virtual environments, and build artifacts
├── README.md                          # Platform technical documentation and deployment guide
├── SPEC.md                            # Master technical architecture specification
├── init_db.sh                         # Shell script to recreate, schema-migrate, and seed PostgreSQL
├── requirements.txt                   # Direct Python package dependencies pinned with compatible releases
├── database/
│   ├── connector.py                   # Psycopg 3 connection factory, pooling, and health checks
│   ├── indexes.sql                    # Performance, partial unique, and foreign key indexes
│   ├── run_all.sql                    # Unified database setup script
│   ├── schema.sql                     # PostgreSQL DDL table definitions and automated timestamp triggers
│   ├── seed.sql                       # Initial Kamonyi and Kigali dataset (admins, markets, rules, seasons)
│   └── setup.sql                      # Database and role initialization script
├── backend/
│   ├── app.py                         # Flask application factory, CORS setup, and public endpoints
│   ├── audit.py                       # Structured administrative audit logging helper
│   ├── auth.py                        # JWT generation, bcrypt password hashing, and role-based route decorators
│   ├── routes/
│   │   ├── admin_routes.py            # Administrative CRUD endpoints for farmers, markets, seasons, rules, logs
│   │   ├── auth_routes.py             # Administrator login, profile inspection, password change, and staff management
│   │   └── ussd_routes.py             # Africa's Talking USSD callback and SMS delivery status webhook
│   ├── services/
│   │   ├── engine.py                  # Harvest validation logic, rule matching engine, and storage guards
│   │   ├── farmer_lookup.py           # Rwandan phone normalization (+250) and farmer database lookup
│   │   ├── menus.py                   # USSD menu state machine, navigation stack, and screen generators
│   │   ├── session_store.py           # In-memory stateless token folding and session tracking
│   │   ├── sms_service.py             # Africa's Talking SMS integration, log-only mode, and delivery tracking
│   │   └── templates.py               # GSM-7 bilingual SMS message builders (English & Kinyarwanda)
│   └── tests/
│       ├── manual_sms_probe.py        # Diagnostic script for direct Africa's Talking API verification
│       ├── test_services.py           # Unit tests for lookup, validation, rules, templates, and SMS logging
│       ├── test_ussd_fixes.py         # Regression tests for USSD single-step date entry and delivery logs
│       ├── test_ussd_flow.py          # End-to-end integration tests for USSD sessions with mocked SMS
│       └── test_ussd_navigation.py    # Resilience tests for USSD token folding and back navigation (0)
├── frontend/
│   ├── admins.html                    # Admin portal: staff accounts and role-based access
│   ├── dashboard.html                 # Admin portal: executive dashboard KPIs and quick actions
│   ├── farmers.html                   # Admin portal: farmer registration and profile management
│   ├── index.html                     # Public landing page: market overview and USSD dialing instructions
│   ├── login.html                     # Admin portal: administrator sign-in page
│   ├── logs.html                      # Admin portal: harvest submissions, SMS delivery, and audit history
│   ├── markets.html                   # Admin portal: Kigali and Kamonyi tomato prices and demand
│   ├── rules.html                     # Admin portal: decision rule prioritization and conditions
│   ├── seasons.html                   # Admin portal: Rwandan agricultural season calendars
│   ├── css/
│   │   ├── dark.css                   # Scoped dark theme overrides (:root[data-theme="dark"])
│   │   ├── landing.css                # Styles for public marketing landing page and hero carousel
│   │   ├── layout.css                 # Admin shell layout: sidebar, topbar, cards, and modal dialogs
│   │   └── theme.css                  # Design tokens, color system, typography, tables, and badge components
│   ├── js/
│   │   ├── admins.js                  # Staff table management, role selection, and account creation
│   │   ├── api.js                     # Centralized fetch wrapper, JWT header injection, and 401 handling
│   │   ├── auth.js                    # Admin session persistence, route guard, and sign-out handler
│   │   ├── dashboard.js               # Dashboard summary metrics loader and audit log feed
│   │   ├── farmers.js                 # Farmer CRUD operations, search filters, and status toggle
│   │   ├── landing.js                 # Public live market table and interactive USSD visual simulator
│   │   ├── logs.js                    # Submissions, SMS dispatches, and audit trail tab view controller
│   │   ├── markets.js                 # Market price updates, demand tracking, and modal controls
│   │   ├── rules.js                   # Rule prioritization sorting, condition editor, and active status toggle
│   │   ├── seasons.js                 # Agricultural season date ranges and active season status manager
│   │   └── sidebar.js                 # Collapsible/resizable sidebar navigation and dark mode toggle button
│   └── images/
│       ├── admin-hero.jpg             # Admin header banner photographic imagery
│       ├── hero-1.jpg                 # Public hero carousel slide 1
│       ├── hero-2.jpg                 # Public hero carousel slide 2
│       ├── hero-3.jpg                 # Public hero carousel slide 3
│       ├── hero-4.jpg                 # Public hero carousel slide 4
│       ├── hero-5.jpg                 # Public hero carousel slide 5
│       ├── step-1.jpg                 # How-it-works process card 1
│       ├── step-2.jpg                 # How-it-works process card 2
│       ├── step-3.jpg                 # How-it-works process card 3
│       ├── step-4.jpg                 # How-it-works process card 4
│       └── tomato-harvest.jpg         # Agricultural produce illustrative graphic
└── tests/
    ├── __init__.py                    # Test package indicator
    ├── test_admin_api.py              # HTTP integration tests covering administrative REST endpoints
    └── test_metlink.py                # Standalone test runner hook
```

---

## Prerequisites

- **Python**: Version `3.12+` (compatible with `3.10+`).
- **PostgreSQL**: Version `12+` (developed and tested on PostgreSQL `16`).
- **Web Browser**: Modern Google Chrome or Microsoft Edge.
- **ngrok**: Required for exposing the local Flask backend port to the Africa's Talking sandbox during USSD/SMS testing.

---

## Local Setup from Scratch

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd metlink
   ```

2. **Create and Activate Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```
   Open `.env` in a text editor and fill in your local PostgreSQL credentials and Africa's Talking sandbox keys.

5. **Start PostgreSQL**:
   Ensure PostgreSQL is running locally on port `5432`:
   ```bash
   sudo systemctl start postgresql
   ```

6. **Initialize the Database**:
   > [!CAUTION]
   > **`init_db.sh` drops the public schema and deletes all existing data! Never run it against production or a database containing data you want to keep.**

   Run the automated database build and seed script:
   ```bash
   chmod +x init_db.sh
   ./init_db.sh
   ```
   The script drops and recreates the public schema, applies `schema.sql`, applies `indexes.sql`, seeds reference data via `seed.sql`, and updates the password hashes for the default administrative accounts.

7. **Default Seeded Admin Accounts**:
   The database is populated with two local development accounts:
   - **Super Admin**:
     - Username: `aline.uwase`
     - Role: `super_admin`
     - Email: `aline.uwase@metlink.rw`
     - Default Password: `Admin@1234`
   - **Market Analyst**:
     - Username: `eric.mugisha`
     - Role: `market_analyst`
     - Email: `eric.mugisha@metlink.rw`
     - Default Password: `Analyst@1234`

   *Note: These default credentials are intended strictly for local development and must be rotated or deleted before deploying to production.*

---

## Running Locally

1. **Start the Flask Backend API (Port 5050)**:
   ```bash
   python3 backend/app.py
   ```
   The backend API will start on `http://0.0.0.0:5050`.

   > [!IMPORTANT]
   > During Africa's Talking USSD and SMS simulator tests, **run the server without the debug reloader**. If the Flask auto-reloader detects a file change during an active session, the process restart will terminate background SMS worker threads and cause ngrok to return an HTTP `502 Bad Gateway` to Africa's Talking. To start without the reloader, run:
   > ```bash
   > flask --app backend/app.py run --host 0.0.0.0 --port 5050 --no-reload
   > ```

2. **Serve the Frontend (Port 3000)**:
   In a separate terminal, serve the `frontend/` directory using Python's static HTTP server:
   ```bash
   python3 -m http.server 3000 --directory frontend
   ```

3. **Application URLs**:
   - **Public Landing Page**: [http://localhost:3000/index.html](http://localhost:3000/index.html)
   - **Admin Sign-In**: [http://localhost:3000/login.html](http://localhost:3000/login.html)
   - **Admin Dashboard**: [http://localhost:3000/dashboard.html](http://localhost:3000/dashboard.html)
   - **Farmers Management**: [http://localhost:3000/farmers.html](http://localhost:3000/farmers.html)
   - **Market Prices**: [http://localhost:3000/markets.html](http://localhost:3000/markets.html)
   - **Agricultural Seasons**: [http://localhost:3000/seasons.html](http://localhost:3000/seasons.html)
   - **Decision Rules**: [http://localhost:3000/rules.html](http://localhost:3000/rules.html)
   - **Activity & System Logs**: [http://localhost:3000/logs.html](http://localhost:3000/logs.html)
   - **Admins & Staff**: [http://localhost:3000/admins.html](http://localhost:3000/admins.html)
   - **Backend API Health**: [http://localhost:5050/api/health](http://localhost:5050/api/health)

---

## Africa's Talking Sandbox with ngrok

To simulate the end-to-end USSD session and SMS delivery flow locally:

1. **Create an Africa's Talking Account**:
   - Register at [africastalking.com](https://africastalking.com) and navigate to the **Sandbox** dashboard.
   - Your sandbox username is `sandbox`.
   - Under **Settings -> API Key**, generate a sandbox API key.

2. **Configure Local Environment**:
   In your `.env` file, configure the following values:
   ```dotenv
   AT_USERNAME=sandbox
   AT_API_KEY=your_sandbox_api_key_here
   AT_SENDER_ID=
   SMS_MODE=log_only
   SMS_SANDBOX_AUTO_DELIVERED=false
   AT_WEBHOOK_TOKEN=your_secure_random_token_here
   ```
   - Start with `SMS_MODE=log_only` to verify session logic.
   - When ready to dispatch simulated SMS messages to the Africa's Talking Web Simulator, set `SMS_MODE=live`.
   - Setting `SMS_SANDBOX_AUTO_DELIVERED=true` automatically updates sandbox SMS logs to `DELIVERED` status upon dispatch.

3. **Start ngrok Tunnel**:
   With your Flask backend running on port `5050`, expose it via ngrok:
   ```bash
   ngrok http 5050
   ```
   Note the assigned HTTPS forwarding URL (e.g. `https://example-subdomain.ngrok-free.app`).

4. **Configure Callbacks in Africa's Talking Dashboard**:
   - **USSD Callback**:
     Navigate to **USSD -> Service Codes -> Create Channel** (or edit existing channel). Set the callback URL to:
     ```text
     https://YOUR-NGROK-DOMAIN/api/ussd/callback?token=YOUR_WEBHOOK_TOKEN
     ```
   - **SMS Delivery Reports**:
     Navigate to **SMS -> SMS Callback URLs -> Delivery Reports**. Set the URL to:
     ```text
     https://YOUR-NGROK-DOMAIN/api/webhooks/sms-delivery?token=YOUR_WEBHOOK_TOKEN
     ```
     *(Replace `YOUR-NGROK-DOMAIN` with your active ngrok host and `YOUR_WEBHOOK_TOKEN` with the value of `AT_WEBHOOK_TOKEN` from your `.env`).*

5. **Test in the Africa's Talking Web Simulator**:
   - Open the Africa's Talking **Web Simulator**.
   - **Farmer Registration Requirement**: Before dialing, the phone number must be registered in the METLINK database (register via the admin portal at `http://localhost:3000/farmers.html`).
   - Enter that exact Rwandan phone number in `+250` format (e.g. `+250788123456`) into the simulator phone keypad.
   - Dial your configured USSD service code (e.g. `*384*...#`).
   - Complete the prompt steps: select language, enter harvest date (`DDMMYYYY`), enter quantity, select ripeness, and confirm.
   - **SMS Reception**: Sandbox SMS messages appear exclusively in the Africa's Talking Web Simulator message inbox, not on real mobile devices.
   - **Inspection**: Open the METLINK admin **Logs** page (`http://localhost:3000/logs.html`) under the **SMS Delivery Logs** tab to verify that the message status shows `SENT` with an assigned `ATXid_` provider identifier.
   - *Production Note*: Real-world USSD shortcodes require formal allocation and binding through a licensed Rwandan telecommunications operator (such as MTN Rwanda or Airtel Rwanda).

---

## Deploying Online (Replacing ngrok)

ngrok is intended solely for local development and demonstration. For a production deployment:

1. **Domain & HTTPS**:
   - Bind a registered domain name (e.g. `api.metlink.rw` and `admin.metlink.rw`) configured with a valid SSL/TLS certificate (Let's Encrypt / Cloudflare).

2. **Production WSGI Server**:
   - Do not use the Flask built-in development server (`app.run()`).
   - Run the Flask application behind a production-grade WSGI server such as **Gunicorn**:
     ```bash
     gunicorn -w 4 -b 0.0.0.0:5050 "backend.app:create_app()"
     ```
     *(Note: `gunicorn` is not included in `requirements.txt` to keep development lightweight; install it directly in your production server environment via `pip install gunicorn`).*

3. **Permanent Africa's Talking Callbacks**:
   - In the live Africa's Talking dashboard, configure production callbacks pointing to your permanent HTTPS domain:
     - USSD: `https://api.yourdomain.rw/api/ussd/callback?token=YOUR_PRODUCTION_TOKEN`
     - Delivery Reports: `https://api.yourdomain.rw/api/webhooks/sms-delivery?token=YOUR_PRODUCTION_TOKEN`

4. **Production Environment Variables**:
   - `AT_USERNAME`: Set to your live Africa's Talking account username.
   - `AT_API_KEY`: Set to your live production API key.
   - `AT_SENDER_ID`: Set to your approved alphanumeric sender ID or shortcode.
   - `SMS_MODE`: Set to `live`.
   - `JWT_SECRET`: Generate a cryptographically secure 256-bit key:
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```
   - `DB_USER` / `DB_PASSWORD`: Configure strong dedicated database user credentials.

5. **CORS Configuration**:
   - In [backend/app.py](file:///home/holi/metlink_project_directory/metlink/backend/app.py#L29), restrict allowed origins from wildcard `*` to your production frontend domains:
     ```python
     # Replace:
     CORS(app, resources={r"/api/*": {"origins": "*"}})

     # With:
     CORS(app, resources={r"/api/*": {"origins": ["https://metlink.rw", "https://admin.metlink.rw"]}})
     ```

6. **Frontend API Base URL**:
   - In [frontend/js/api.js](file:///home/holi/metlink_project_directory/metlink/frontend/js/api.js#L7), update the API endpoint:
     ```javascript
     // Replace:
     const API_BASE = 'http://localhost:5050/api';

     // With:
     const API_BASE = 'https://api.metlink.rw/api';
     ```

7. **Database Security & Backups**:
   - Use a managed PostgreSQL instance with automated backups, encryption at rest, and firewall network restrictions.
   - **Never execute `init_db.sh` in production.** Apply incremental SQL schema migrations instead.
   - Rotate or remove the default seeded administrator passwords (`Admin@1234` and `Analyst@1234`).
   - Ensure `.env` is never committed to source control and rotate any credential immediately if compromised.

---

## API Endpoints Summary

| Method | Endpoint Path | Authentication Required | Required Role | Description |
|---|---|---|---|---|
| `GET` | `/api/health` | Public | None | Database connection and service health check |
| `POST` | `/api/auth/login` | Public | None | Admin authentication returning JWT token and profile |
| `POST` | `/api/auth/logout` | JWT Required | Any Admin | Terminates session and logs logout action |
| `GET` | `/api/auth/me` | JWT Required | Any Admin | Returns profile of currently authenticated administrator |
| `POST` | `/api/auth/change-password` | JWT Required | Any Admin | Changes password of authenticated administrator |
| `GET` | `/api/dashboard/summary` | JWT Required | Any Admin | High-level KPI metrics, active season, and recent activity |
| `GET` | `/api/farmers` | JWT Required | Any Admin | List registered farmers with optional search and status filtering |
| `POST` | `/api/farmers` | JWT Required | Any Admin | Register a new farmer with phone normalization |
| `PUT` | `/api/farmers/<id>` | JWT Required | Any Admin | Update farmer details or toggle active status |
| `GET` | `/api/markets` | JWT Required | Any Admin | List all markets with price metrics, demand, and transport |
| `POST` | `/api/markets` | JWT Required | Any Admin | Add a new market intelligence record |
| `PUT` | `/api/markets/<id>` | JWT Required | Any Admin | Update market prices, demand rating, or active status |
| `GET` | `/api/public/markets` | Public | None | Read-only market price summary for public landing page |
| `GET` | `/api/seasons` | JWT Required | Any Admin | List agricultural season definitions and date ranges |
| `POST` | `/api/seasons` | JWT Required | Any Admin | Define a new agricultural season window |
| `PUT` | `/api/seasons/<id>` | JWT Required | Any Admin | Update season date ranges or active evaluation state |
| `GET` | `/api/rules` | JWT Required | Any Admin | List harvest advisory decision rules ordered by priority |
| `POST` | `/api/rules` | JWT Required | Any Admin | Create a new prioritized decision rule |
| `PUT` | `/api/rules/<id>` | JWT Required | Any Admin | Modify rule conditions, advice actions, or active status |
| `GET` | `/api/submissions` | JWT Required | Any Admin | Retrieve farmer USSD harvest submission history |
| `GET` | `/api/sms-logs` | JWT Required | Any Admin | Retrieve SMS dispatch logs, provider IDs, and delivery status |
| `GET` | `/api/audit-logs` | JWT Required | Any Admin | Retrieve chronological record of administrator actions |
| `GET` | `/api/admins` | JWT Required | `super_admin` only | List system administrators and role assignments |
| `POST` | `/api/admins` | JWT Required | `super_admin` only | Provision a new administrator account |
| `PUT` | `/api/admins/<id>` | JWT Required | `super_admin` only | Modify administrator profile, role, or active status |
| `POST` | `/api/ussd/callback` | Webhook Token (Optional) | None | Handles incoming Africa's Talking USSD session events |
| `POST` | `/api/webhooks/sms-delivery` | Webhook Token (Optional) | None | Ingests Africa's Talking SMS delivery status callbacks |

---

## Running the Tests

The repository includes automated test suites covering core business services, USSD navigation, error resilience, and REST endpoints:

1. **Core Business Services Test Suite**:
   ```bash
   .venv/bin/python backend/tests/test_services.py
   ```
   - **What it checks**: Phone normalization, input validation, rule matching priority, fallback rule generation, GSM-7 bilingual SMS templating, and Africa's Talking client mocking.
   - **Prerequisites**: PostgreSQL database running and initialized with seed data.

2. **USSD Flow Integration Test Suite**:
   ```bash
   .venv/bin/python backend/tests/test_ussd_flow.py
   ```
   - **What it checks**: Multi-turn USSD sessions run against the real Flask test client and database, token folding, mock SMS dispatch, and concurrent session isolation. Test farmer records created during the run are automatically cleaned up in foreign-key order.
   - **Prerequisites**: PostgreSQL database running and initialized.

3. **USSD Navigation & Step Machine Test Suite**:
   ```bash
   .venv/bin/python backend/tests/test_ussd_navigation.py
   ```
   - **What it checks**: Pure step machine token folding, zero-lock behavior on invalid tokens, back navigation (`0`), single-step date entry (`DDMMYYYY`), and confirmation screen transitions.
   - **Prerequisites**: PostgreSQL database running and initialized.

4. **USSD Fixes & Simulator Never-Hang Test Suite**:
   ```bash
   .venv/bin/python backend/tests/test_ussd_fixes.py
   ```
   - **What it checks**: Validates that single-step date entry works cleanly, every SMS generates a complete record in `sms_logs`, and session handlers never hang the Africa's Talking simulator.
   - **Prerequisites**: PostgreSQL database running and initialized.

5. **Admin REST API Verification**:
   ```bash
   .venv/bin/python tests/test_admin_api.py
   ```
   - **What it checks**: Verifies unauthenticated 401 blocking, admin authentication, token validation, CRUD operations across all administrative entities, and public market endpoints.
   - **Prerequisites**: Backend server running on `http://localhost:5000` (or `http://localhost:5050`) with database initialized.

6. **Manual SMS Gateway Diagnostic Probe**:
   ```bash
   .venv/bin/python backend/tests/manual_sms_probe.py
   ```
   - **What it checks**: Performs an ad-hoc test dispatch through the Africa's Talking API to verify account credentials and sandbox connectivity.

### Admin Dashboard Maintenance Workflows
Administrators manage system intelligence directly from the dashboard:
- **Decision Rules**: Navigate to [rules.html](http://localhost:3000/rules.html) to adjust rule priority rankings, quantity bounds, target maturity stages, and storage advice. Rules with lower priority numbers are evaluated first.
- **Agricultural Seasons**: Navigate to [seasons.html](http://localhost:3000/seasons.html) to configure calendar date windows for Season A, B, and C. Only one active season applies to incoming harvest evaluations.
- **Market Prices**: Navigate to [markets.html](http://localhost:3000/markets.html) to update daily wholesale and retail pricing benchmarks, buyer demand levels, and transport cost estimates across Kigali and Kamonyi markets.

---

## Troubleshooting

- **Backend Does Not Start (`psycopg.OperationalError: Connection refused`)**:
  - Verify PostgreSQL is running: `sudo systemctl status postgresql`.
  - Check that `.env` contains valid credentials and matches `DB_PORT=5432` and `DB_NAME=metlink_db`.
  - Confirm database initialization was executed: `./init_db.sh`.

- **Webhook Token Mismatch (`HTTP 401 / 403` on USSD Callback)**:
  - If `AT_WEBHOOK_TOKEN` is set in `.env`, the callback URL in Africa's Talking must include the exact query string `?token=YOUR_TOKEN`.
  - If no token validation is desired during initial local testing, leave `AT_WEBHOOK_TOKEN=` empty in `.env`.

- **ngrok Returns `HTTP 502 Bad Gateway`**:
  - Verify the Flask backend is actively running on the exact port forwarded by ngrok (default port: `5050`).
  - Ensure the backend was started with `--no-reload` so background SMS threads do not trigger reloader restarts.

- **SMS Status Remains `SENT` Instead of `DELIVERED`**:
  - The Africa's Talking sandbox does not emit real telecom delivery receipts unless the delivery callback is triggered or `SMS_SANDBOX_AUTO_DELIVERED=true` is enabled in `.env`.
  - Verify that your delivery callback URL is configured in the Africa's Talking dashboard under **SMS -> Delivery Reports**.

- **Farmer Sees "Not Registered" on USSD**:
  - The phone number dialing the USSD code must exist in the `farmers` database table.
  - Register the farmer via the admin portal ([farmers.html](http://localhost:3000/farmers.html)) using the international `+250` format.

---

## License & Credits

- **License**: [LICENSE]
- **Team**: [TEAM OR ORGANIZATION NAME]
- **Contact**: [CONTACT EMAIL]
