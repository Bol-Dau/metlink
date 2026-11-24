# METLINK

METLINK is a tomato harvest decision-support platform for smallholder tomato farmers in Kamonyi District, Rwanda, and market administrators in Kigali. Farmers use a basic feature phone: they enter their expected harvest through USSD and receive advice on the screen and by SMS, in English or Kinyarwanda. Administrators use a web portal to register farmers and to keep the market prices, agricultural seasons and decision rules that the advice is based on.

> [!NOTE]
> METLINK is a decision-support tool. It does not guarantee prices, buyers, or income.

---

## Live Demo

This project is deployed for a course demo and non-commercial use. It is not meant for real farmers.

| What | Address |
|---|---|
| Landing page | https://metlink.boldau.tech |
| Admin sign-in | https://metlink.boldau.tech/login.html |
| Health check | https://metlink.boldau.tech/api/health |

Demo admin accounts. The passwords are not published here. They are given with the project submission and shown in the demo video.

| Username | Role | Password |
|---|---|---|
| `aline.uwase` | `super_admin` | `[GIVEN WITH THE SUBMISSION]` |
| `eric.mugisha` | `market_analyst` | `[GIVEN WITH THE SUBMISSION]` |

The farmer side (USSD and SMS) runs on the Africa's Talking sandbox. Sandbox USSD works only in the sandbox simulator of the account that owns the service code, and sandbox SMS shows only in that simulator. It cannot be dialed from a real phone. The demo video shows the full farmer flow.

---

## What It Does

### Farmer side (USSD and SMS)

- Only farmers registered by an administrator can use the service. Numbers that are not registered, or that were deactivated, get a message telling them to contact the administrator.
- The farmer chooses English or Kinyarwanda. The choice is saved and used for later screens and SMS.
- Main menu: submit expected harvest, my submissions, my advice.
- Submitting a harvest asks for four things, then shows a summary to confirm or cancel:
  1. Expected harvest date, written as `DD-MM-YYYY` or `DDMMYYYY` (today or later, at most 120 days ahead).
  2. Expected quantity in kilograms (a whole number, 1 to 100000).
  3. Tomato maturity: Green, Turning or Ripe.
  4. Whether a safe place to store tomatoes (cool, ventilated) is available.
- Invalid input never gets the farmer stuck: the same question is asked again with a short error. Entering `0` goes back one step.
- After confirmation, the advice is shown on the screen and sent by SMS (160 characters or less, in the farmer's language). The advice is one of three actions: `SELL_NOW`, `STORE_AND_WAIT` or `SEEK_ALTERNATIVE_MARKET`, with a reason, the best market and price when available, and a reminder that it is a guide only.
- Kinyarwanda text needs a review by a native speaker before it is used in a demo or in production.

### Admin side (web portal)

- **Dashboard:** key numbers, the active season, and recent admin activity.
- **Farmers:** register, search, edit, activate and deactivate farmers. Records are deactivated, never deleted.
- **Markets:** record the average price per kg, the demand level (HIGH, MEDIUM, LOW) and the source of each price.
- **Seasons:** define agricultural seasons (for example Season A, B and C) and which one is active.
- **Decision rules:** create and edit rules in priority order (lowest number first). A rule can only recommend `STORE_AND_WAIT` when it requires storage. Rules are stored in the database, so they are changed from this page and not by editing the seed file.
- **Logs:** three tabs for farmer submissions, SMS messages (with provider id and delivery status) and the admin audit trail.
- **Admins:** create and manage admin accounts. This page is only for `super_admin`.
- Password change, dark mode, and a public landing page with live market prices.

Admin roles: `super_admin`, `admin` and `market_analyst`. All roles manage farmers, markets, seasons, rules and logs. Only `super_admin` manages admin accounts.

---

## How the Advice Is Decided

For every confirmed submission the engine does the following, in one database transaction:

1. Checks the input (date, quantity, maturity) again.
2. Finds the active season that contains the harvest date. If there is none, it continues and lowers the confidence.
3. Reads the active markets. It uses the highest average price per kg and the demand level of that same market.
4. Uses the price trend. Version 1 keeps no price history, so the trend is always treated as STABLE.
5. Goes through the active decision rules in priority order and takes the first rule that matches maturity, price trend, demand level, minimum quantity and storage.
6. Skips any `STORE_AND_WAIT` rule when the farmer has no suitable storage. `STORE_AND_WAIT` is never given without storage.
7. If no rule matches, gives `SELL_NOW` for ripe tomatoes and `SEEK_ALTERNATIVE_MARKET` otherwise, with LOW confidence. Administrators should then review the rules.
8. Saves the submission, the recommendation and three evidence records (market, season, rule), then sends the SMS in the background.

### Writing rules that can match

- Because the price trend is always STABLE, a rule with a RISING or FALLING trend cannot match yet. For a rule to fire, set its price trend to STABLE.
- The demand level used by the rules is the demand level of the highest-priced active market. If that market has HIGH demand, only rules with HIGH demand can match. To test other outcomes, change the demand level or the price of a market on the Markets page.
- A rule with a minimum quantity only matches submissions at or above that quantity.
- If every submission shows the fallback text "No specific decision rule matched your harvest criteria", check the Rules page for an active rule that fits the maturity, trend (STABLE), demand level and quantity you entered.
- Do not run `database/init_remote.sh --reset` or `init_db.sh` after you have changed rules from the portal. They reset the database to the seed rules.

### Known limits of version 1

- No price history, so Rising and Falling rules are ready but cannot match until historical prices are added.
- No payments, transport, physical storage or buyer matching.

---

## Architecture and Directory Tree

```text
metlink/
├── .env.example                      # Template for database, auth, server and Africa's Talking settings
├── README.md                         # This guide
├── init_db.sh                        # Rebuilds and seeds a LOCAL PostgreSQL database (deletes data)
├── requirements.txt                  # Direct Python dependencies (includes gunicorn)
├── database/
│   ├── connector.py                  # Psycopg 3 connection helper (DATABASE_URL or DB_* settings)
│   ├── indexes.sql                   # Indexes
│   ├── init_remote.sh                # Loads schema and seed data into a server or hosted database
│   ├── run_all.sql                   # Combined setup script
│   ├── schema.sql                    # Tables, constraints and triggers
│   ├── seed.sql                      # Starting data (admins, markets, rules, seasons)
│   └── setup.sql                     # Local database and role setup
├── backend/
│   ├── app.py                        # Flask app, CORS, health check and public endpoints
│   ├── audit.py                      # Audit log helper
│   ├── auth.py                       # JWT, bcrypt and role decorators
│   ├── routes/
│   │   ├── admin_routes.py           # Farmers, markets, seasons, rules, logs
│   │   ├── auth_routes.py            # Login, profile, password change, admin accounts
│   │   └── ussd_routes.py            # USSD callback and SMS delivery webhook
│   ├── services/
│   │   ├── engine.py                 # Validation, rule matching, storage guard, fallback
│   │   ├── farmer_lookup.py          # Phone normalization (+250) and farmer lookup
│   │   ├── menus.py                  # USSD screens and step machine
│   │   ├── session_store.py          # Replay cache and per-session lock
│   │   ├── sms_service.py            # Africa's Talking SMS, log-only mode, delivery reports
│   │   └── templates.py              # English and Kinyarwanda SMS text
│   └── tests/
│       ├── manual_sms_probe.py       # Sends one real sandbox SMS to check credentials
│       ├── test_services.py          # Services tests
│       ├── test_ussd_fixes.py        # Date entry, SMS logging and never-hang tests
│       ├── test_ussd_flow.py         # End-to-end USSD tests with mocked SMS
│       └── test_ussd_navigation.py   # Back navigation and invalid input tests
├── frontend/
│   ├── index.html                    # Public landing page
│   ├── login.html                    # Admin sign-in
│   ├── dashboard.html                # Admin dashboard
│   ├── farmers.html                  # Farmers
│   ├── markets.html                  # Markets
│   ├── seasons.html                  # Seasons
│   ├── rules.html                    # Decision rules
│   ├── logs.html                     # Submissions, SMS and audit logs
│   ├── admins.html                   # Admin accounts (super_admin only)
│   ├── css/                          # theme.css, layout.css, landing.css, dark.css
│   ├── js/                           # api.js, auth.js, sidebar.js, landing.js and one file per page
│   └── images/                       # Landing page and banner photos
└── tests/
    ├── __init__.py
    ├── test_admin_api.py             # Admin REST API tests (needs the backend running)
    └── test_metlink.py               # Test runner hook
```

---

## Prerequisites

- Python 3.12 or newer (3.10 and newer should work). Flask 3.1 needs Python 3.9 or newer.
- PostgreSQL 12 or newer (developed on 16).
- Google Chrome or Microsoft Edge.
- ngrok, for testing Africa's Talking against your own computer.

---

## Settings (`.env`)

Copy `.env.example` to `.env` and fill it in. Never commit `.env`.

| Setting | Purpose |
|---|---|
| `SECRET_KEY` | Signs login tokens. Use a long random value. |
| `DATABASE_URL` | One connection address, for example `postgresql://user:password@localhost:5432/metlink`. If it is set, it is used instead of the `DB_*` settings. |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Separate database settings, used when `DATABASE_URL` is not set. |
| `DB_SSLMODE` | Optional SSL mode for the `DB_*` settings. |
| `DB_CONNECT_TIMEOUT` | Database connection timeout in seconds (default 5). |
| `CORS_ORIGINS` | Frontend addresses allowed to call the API, separated by commas. If unset or `*`, all origins are allowed. |
| `COOKIE_SECURE` | Set to `true` when the site is served over HTTPS. |
| `SMS_MODE` | `live` sends SMS through Africa's Talking. `log_only` only writes to the SMS log. |
| `AT_USERNAME`, `AT_API_KEY`, `AT_SENDER_ID` | Africa's Talking credentials. Use `sandbox` as the username for the sandbox. Leave the sender id empty. |
| `AT_WEBHOOK_TOKEN` | If set, the two Africa's Talking endpoints need `?token=<value>` in the URL. |
| `SMS_SANDBOX_AUTO_DELIVERED` | Demo only. Marks sandbox SMS as `DELIVERED` when they are sent. |

---

## Local Setup and Running

Follow the steps in order. Each step says what to run, what it does, and what you should see. Use three terminals: one for setup, one for the backend and one for the frontend.

### Step 1: Get the code

Run:
```bash
git clone <repository-url>
cd metlink
```
What it does: downloads the project into a folder called `metlink`.

### Step 2: Create a virtual environment

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
What it does: makes a private Python folder for this project and turns it on.
You should see: `(.venv)` at the start of your terminal line.

### Step 3: Install the packages

Run:
```bash
pip install -r requirements.txt
```
What it does: installs Flask, the database driver, bcrypt, gunicorn and the other packages the project needs.
You should see: a line starting with `Successfully installed` at the end.

### Step 4: Create your settings file

Run:
```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"
```
What it does: copies the settings template to `.env`, then prints a long random text.
Next: open `.env` in an editor. Paste the random text as `SECRET_KEY`, then fill in your PostgreSQL settings (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) and your Africa's Talking sandbox keys. The meaning of each setting is in the Settings table above.

### Step 5: Start PostgreSQL

Run:
```bash
sudo systemctl start postgresql
```
What it does: starts the database program.
You should see: nothing. No message means it worked.

### Step 6: Build the database

> [!CAUTION]
> `init_db.sh` drops the public schema and deletes all data in that database. Never run it against a database you want to keep.

Run:
```bash
chmod +x init_db.sh
./init_db.sh
```
What it does: creates the tables, adds the indexes, loads the starting data (admins, markets, rules, seasons) and sets the admin passwords.
You should see: no error messages. If it says the database or user does not exist, create them first with `database/setup.sql`, and make sure the names and password match your `.env`.

### Step 7: Start the backend (first terminal)

Run, from the project folder with the virtual environment on:
```bash
python3 -m backend.app
```
What it does: starts the API on port 5050.
You should see: a line saying it is running on port 5050. Keep this terminal open.

### Step 8: Start the frontend (second terminal)

Run:
```bash
cd metlink
python3 -m http.server 3000 --directory frontend
```
What it does: shows the web pages on port 3000. This is where the number 3000 comes from. The pages talk to the backend on port 5050 by themselves.
You should see: a line saying it is serving HTTP on port 3000. Keep this terminal open.

### Step 9: Open the app

- Landing page: http://localhost:3000/index.html
- Admin sign-in: http://localhost:3000/login.html
- Health check: http://localhost:5050/api/health. It should show `{"database":"connected","status":"ok"}`.

Use `http://`, not `https://`, on your own computer.

### Local admin accounts

These starting passwords are public. Use them only on your own computer.

| Username | Role | Password |
|---|---|---|
| `aline.uwase` | `super_admin` | `Admin@1234` |
| `eric.mugisha` | `market_analyst` | `Analyst@1234` |

### Testing Africa's Talking from your computer

The command in step 7 uses a reloader that restarts the backend when a file changes. That kills the background SMS threads and makes ngrok return `502 Bad Gateway`. For simulator testing, start the backend with this instead of step 7:
```bash
gunicorn --workers 1 --threads 8 --bind 127.0.0.1:5050 "backend.app:create_app()"
```
Then run `ngrok http 5050` and follow the Africa's Talking section below.

---

## Ports and Addresses

| Where | Web pages | Backend API |
|---|---|---|
| On your computer | http://localhost:3000 (started with `python3 -m http.server`) | http://localhost:5050/api (started with `python3 -m backend.app`) |
| Live server | https://metlink.boldau.tech (served by nginx) | https://metlink.boldau.tech/api (nginx passes it to gunicorn on port 5050) |

Port 5050 is used instead of 5000 because port 5000 can be blocked on some systems (for example WSL).

The pages choose the API address in `frontend/js/api.js`. On `localhost` or `127.0.0.1` it uses `http://localhost:5050/api`. On any other host it uses `PROD_API_BASE`, which must be set to the deployed address.

---

## Africa's Talking Sandbox

1. Create an account at [africastalking.com](https://africastalking.com) and open the Sandbox. The username is `sandbox`. Under Settings, generate an API key.
2. Put these in `.env`:
   ```dotenv
   AT_USERNAME=sandbox
   AT_API_KEY=your_sandbox_api_key
   AT_SENDER_ID=
   SMS_MODE=log_only
   AT_WEBHOOK_TOKEN=a_long_random_text_you_make_up
   ```
   Start with `SMS_MODE=log_only` to test the USSD flow. Set `SMS_MODE=live` when you want the SMS to reach the simulator. Leave `AT_SENDER_ID` empty.
3. In the sandbox, create a USSD service code and set the two callbacks (replace the host and token):
   - USSD callback: `https://YOUR-HOST/api/ussd/callback?token=YOUR_TOKEN`
   - SMS delivery reports: `https://YOUR-HOST/api/webhooks/sms-delivery?token=YOUR_TOKEN`

   For the deployed demo, `YOUR-HOST` is `metlink.boldau.tech`. For local testing, run `ngrok http 5050` and use the ngrok host instead. The callbacks must use `https://`.
4. Register a test farmer in the admin portal first, using a Rwandan number in `+250` format.
5. Open the sandbox Launch Simulator, enter that same number, and dial the service code the sandbox gave you.
6. Check the result in the admin portal, on the Logs page. The SMS tab should show status `SENT` with a provider id starting with `ATXid_`.

Notes:

- Sandbox SMS appears only in the simulator of the account that sent it, never on a real phone.
- The sandbox does not send delivery reports by default, so the status can stay `SENT`. For demos only, you can set `SMS_SANDBOX_AUTO_DELIVERED=true`, which marks sandbox messages as `DELIVERED` when they are sent.
- A real USSD shortcode needs a licensed Rwandan telecom operator.
- Anyone who has the callback URL with the token can call your backend. Do not publish it.

---

## Deploying on a Server (Ubuntu, nginx, gunicorn, PostgreSQL)

This is how the demo runs. Everything is on one server, so there is no sleeping and no slow first request. It is meant for a course demo and non-commercial use.

Each step says where to run it, what to run, what it does, and what you should see. Run the steps in order. Commands marked "on the server" go in the terminal connected to your server with `ssh`.

### Before you start

You need:
- An Ubuntu server with a public IP address. Use a fixed (elastic) IP so the address does not change when the server restarts.
- Ports 80 and 443 open, in the server firewall and in your cloud firewall or security group.
- A host name. Either add an **A record** for your domain that points to the server IP, or use a free name made from your IP with dashes, for example `203-0-113-5.sslip.io`.

In the steps below, replace `YOUR-HOST` with that host name (for example `metlink.boldau.tech`) and `YOUR_EMAIL` with your email.

### Step 1: Install the software (on the server)

Run:
```bash
sudo apt update
sudo apt install -y postgresql python3-venv python3-pip git nginx certbot python3-certbot-nginx rsync
```
What it does: installs the database, the web server, the certificate tool and the file copy tool.
You should see: a long list of packages and no error at the end. If it says `Unable to locate package`, run `sudo apt update` again.

### Step 2: Copy the project to the server (on your computer)

First open `frontend/js/api.js` and set `PROD_API_BASE` to `https://YOUR-HOST/api`. Do this before copying.

Then run, from the folder that contains `metlink`:
```bash
rsync -av --exclude .venv --exclude __pycache__ --exclude .env --exclude .git \
  -e "ssh -i YOUR-KEY" \
  metlink/ USER@SERVER_IP:~/metlink/
```
What it does: copies the project files to `~/metlink` on the server and leaves out your local settings and environment.
You should see: a list of file names, then `total size is ...`.

### Step 3: Create the Python environment (on the server)

Run:
```bash
cd ~/metlink
python3 --version
```
If it shows 3.9 or newer, run:
```bash
python3 -m venv .venv
```
If it shows an older version (Ubuntu 20.04 has 3.8), run these three lines instead:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv python install 3.12
~/.local/bin/uv venv --seed --python 3.12 .venv
```
What it does: creates a private Python folder. The `uv` lines first download Python 3.12 without changing the system Python.
You should see: `Installed Python 3.12...` and then `Creating virtual environment`.

Then install the packages:
```bash
.venv/bin/pip install -r requirements.txt
```
You should see: `Successfully installed ...` at the end.

### Step 4: Create the database (on the server)

Run, all in the same terminal window:
```bash
DBPASS=$(openssl rand -hex 16)
sudo -u postgres psql -c "CREATE USER metlink WITH PASSWORD '$DBPASS';"
sudo -u postgres psql -c "CREATE DATABASE metlink OWNER metlink;"
sudo -u postgres psql -d metlink -c "ALTER SCHEMA public OWNER TO metlink;"
```
What it does: makes a random database password, creates the database user and the database, and lets that user manage its own tables.
You should see: `CREATE ROLE`, `CREATE DATABASE` and `ALTER SCHEMA`.
Do not close this terminal window until step 5 is done, because step 5 uses the password saved in `DBPASS`.

### Step 5: Create the settings file (on the server)

Run:
```bash
cd ~/metlink
cat > .env <<ENVEOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL=postgresql://metlink:$DBPASS@localhost:5432/metlink
CORS_ORIGINS=https://YOUR-HOST
SMS_MODE=live
ENVEOF
chmod 600 .env
```
What it does: writes a new `.env` with a random secret key, the database address and the allowed website address, and makes it readable only by you.

Now add your Africa's Talking settings. Type the first line below and press Enter, paste your lines (one `NAME=value` per line, taken from `.env.example`), press Enter, then type `EOF` on its own line:
```bash
cat >> .env <<'EOF'
```
Check the names without showing the values:
```bash
cut -d= -f1 .env
```
You should see: `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `SMS_MODE` and your Africa's Talking names (`AT_USERNAME`, `AT_API_KEY`, `AT_SENDER_ID`, `AT_WEBHOOK_TOKEN`). Each name should appear only once.

### Step 6: Load the tables and starting data (on the server)

Run:
```bash
export DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
read -s -p "Super admin password: " SEED_SUPER_ADMIN_PASSWORD; export SEED_SUPER_ADMIN_PASSWORD; echo
read -s -p "Analyst password: " SEED_ANALYST_PASSWORD; export SEED_ANALYST_PASSWORD; echo
export PATH="$PWD/.venv/bin:$PATH"
bash database/init_remote.sh --yes
```
What it does: asks you for two admin passwords (8 to 72 characters, nothing shows while you type), then creates all tables and loads the starting data with those passwords. Write the passwords down.
You should see: `Admin credentials configured successfully.` and `Remote database initialization completed successfully.`

If it says the database already has tables, add `--reset` to the last command. That deletes everything in the database and starts again.

### Step 7: Run the backend as a service (on the server)

Run:
```bash
APP=$HOME/metlink
sudo tee /etc/systemd/system/metlink.service > /dev/null <<SVCEOF
[Unit]
Description=METLINK backend
After=network.target postgresql.service

[Service]
User=$USER
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/.venv/bin/gunicorn --workers 1 --threads 8 --timeout 30 --bind 127.0.0.1:5050 "backend.app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
SVCEOF
sudo systemctl daemon-reload
sudo systemctl enable --now metlink
sleep 4
curl http://127.0.0.1:5050/api/health
```
What it does: creates a service that starts the backend now, restarts it if it stops, and starts it again after a reboot. The last line asks the backend if it is healthy.
You should see: `Created symlink ...` and then `{"database":"connected","status":"ok"}`.
If you do not, run `sudo journalctl -u metlink -n 50 --no-pager` to read the error.

### Step 8: Set up the web server and HTTPS (on the server)

Run:
```bash
HOST=YOUR-HOST
APP=$HOME/metlink
sudo tee /etc/nginx/sites-available/metlink > /dev/null <<'NGXEOF'
server {
    listen 80;
    server_name HOST_HERE;

    location /api/ {
        proxy_pass http://127.0.0.1:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        root APP_HERE/frontend;
        index index.html;
        try_files $uri $uri/ =404;
    }
}
NGXEOF
sudo sed -i "s|HOST_HERE|$HOST|; s|APP_HERE|$APP|" /etc/nginx/sites-available/metlink
chmod o+x "$HOME"
sudo ln -sf /etc/nginx/sites-available/metlink /etc/nginx/sites-enabled/metlink
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```
What it does: tells nginx to show the web pages from the `frontend` folder and to pass every `/api/` request to the backend.
You should see: `syntax is ok` and `test is successful`.

Then get a free HTTPS certificate:
```bash
sudo certbot --nginx -d $HOST -m YOUR_EMAIL --agree-tos --no-eff-email --redirect
```
You should see: `Congratulations! You have successfully enabled https://YOUR-HOST`. Certbot renews the certificate by itself.

### Step 9: Point Africa's Talking at your server

In the Africa's Talking sandbox, set both callbacks (see the Africa's Talking section above):
- USSD callback: `https://YOUR-HOST/api/ussd/callback?token=YOUR_TOKEN`
- SMS delivery reports: `https://YOUR-HOST/api/webhooks/sms-delivery?token=YOUR_TOKEN`

Test the USSD callback first (on the server or your computer):
```bash
curl -X POST "https://YOUR-HOST/api/ussd/callback?token=YOUR_TOKEN" \
  -d "sessionId=t1" -d "phoneNumber=+250788123456" -d "text="
```
What it does: sends the same kind of request that Africa's Talking sends.
You should see: `CON METLINK`, then `1. English` and `2. Kinyarwanda` for a registered number, or an `END` message for a number that is not registered.

### Step 10: Check everything

1. Open `https://YOUR-HOST`. You should see the landing page with market prices.
2. Open `https://YOUR-HOST/login.html` and sign in as `aline.uwase` with the super admin password you chose in step 6.
3. Dial your service code in the sandbox simulator and finish one harvest submission.
4. In the admin portal, open Logs. You should see the new submission and SMS.

### Updating the server later

On your computer, run the `rsync` command from step 2 again. It copies only changed files. Then, on the server:
```bash
sudo systemctl restart metlink
```
Keep `PROD_API_BASE` in your local copy the same as the live address, or the next copy will overwrite it.

### Keeping it working until January

- The service starts by itself after a reboot. Reboot the server once after setup (`sudo reboot`) and check that the site comes back.
- Keep the server IP fixed and ports 80 and 443 open.
- Check the certificate renewal once: `sudo certbot renew --dry-run`.
- Once a week, check that the site, `/api/health` and one USSD session work.
- Read logs with `sudo journalctl -u metlink -n 50 --no-pager` and `sudo tail /var/log/nginx/access.log`. The nginx log shows the webhook token in the URL, so do not share it.

### Other free option: Render and Neon

The same code also runs on a Render free web service (start command `gunicorn --workers 1 --threads 8 --timeout 30 --bind 0.0.0.0:$PORT "backend.app:create_app()"`) with a Neon free database loaded through `database/init_remote.sh`. The free Render backend sleeps after 15 minutes without traffic and the first request can take up to a minute, which can break the first USSD call. Use Neon for the database, because the free Render database expires after 30 days.

---

## Deploying for Real Use (checklist)

A free demo is not enough for real farmers. For a real deployment:

- Use a server or plan that does not sleep, with database backups.
- Use a live Africa's Talking account: your live `AT_USERNAME`, your live API key, an approved sender ID, and a USSD shortcode from a Rwandan telecom operator.
- Point both Africa's Talking callbacks at the permanent HTTPS address, with a strong token.
- Set a strong `SECRET_KEY`, `COOKIE_SECURE=true`, and `CORS_ORIGINS` to your real frontend address only.
- Remove the seeded accounts or change their passwords.
- Never run `init_db.sh` or `database/init_remote.sh --reset` on a database with real data.
- Never commit `.env`, and rotate any key that was ever shown in public.

---

## API Endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | Public | Health check |
| `POST` | `/api/auth/login` | Public | Admin login, returns a token |
| `POST` | `/api/auth/logout` | Admin | Log out |
| `GET` | `/api/auth/me` | Admin | Current admin profile |
| `POST` | `/api/auth/change-password` | Admin | Change own password |
| `GET` | `/api/dashboard/summary` | Admin | Dashboard numbers, active season, recent activity |
| `GET` | `/api/farmers` | Admin | List farmers |
| `POST` | `/api/farmers` | Admin | Register a farmer |
| `PUT` | `/api/farmers/<id>` | Admin | Edit, activate or deactivate a farmer |
| `GET` | `/api/markets` | Admin | List markets |
| `POST` | `/api/markets` | Admin | Add a market |
| `PUT` | `/api/markets/<id>` | Admin | Edit, activate or deactivate a market |
| `GET` | `/api/public/markets` | Public | Market prices for the landing page |
| `GET` | `/api/seasons` | Admin | List seasons |
| `POST` | `/api/seasons` | Admin | Add a season |
| `PUT` | `/api/seasons/<id>` | Admin | Edit, activate or deactivate a season |
| `GET` | `/api/rules` | Admin | List decision rules |
| `POST` | `/api/rules` | Admin | Create a rule |
| `PUT` | `/api/rules/<id>` | Admin | Edit, activate or deactivate a rule |
| `GET` | `/api/submissions` | Admin | Farmer submissions |
| `GET` | `/api/sms-logs` | Admin | SMS messages and delivery status |
| `GET` | `/api/audit-logs` | Admin | Admin audit trail |
| `GET` | `/api/admins` | `super_admin` | List admin accounts |
| `POST` | `/api/admins` | `super_admin` | Create an admin account |
| `PUT` | `/api/admins/<id>` | `super_admin` | Edit, activate or deactivate an admin |
| `POST` | `/api/ussd/callback` | Webhook token | Africa's Talking USSD |
| `POST` | `/api/webhooks/sms-delivery` | Webhook token | Africa's Talking delivery reports |

Admin endpoints need the header `Authorization: Bearer <token>`. If `AT_WEBHOOK_TOKEN` is set, the two Africa's Talking endpoints need `?token=<value>` in the URL.

---

## Running the Tests

The tests are plain scripts. Run them from the repository root with the virtual environment active. They print PASS or FAIL for each check and exit with a non-zero code when something fails.

| Command | What it checks | Needs |
|---|---|---|
| `python backend/tests/test_services.py` | Phone handling, validation, rule matching, storage guard, fallback, SMS text and SMS logging (SMS is mocked) | Initialized database |
| `python backend/tests/test_ussd_flow.py` | Full USSD sessions, SMS logging, delivery webhook and 10 users at the same time (SMS is mocked) | Initialized database |
| `python backend/tests/test_ussd_navigation.py` | Back navigation and invalid input at every step | Initialized database |
| `python backend/tests/test_ussd_fixes.py` | Date entry, one SMS record per submission, and that the callback never hangs | Initialized database |
| `python tests/test_admin_api.py` | Admin API: login, access control and all admin endpoints | Backend running |
| `python backend/tests/manual_sms_probe.py` | Sends one real sandbox SMS to check your Africa's Talking keys | Keys in `.env`, `SMS_MODE=live` |

The USSD tests create farmers whose names start with `TEST_` and delete them when they finish. Run the tests against a local database, not the deployed one.

Administrators keep the system accurate from the portal:

- **Rules:** change priorities, quantity limits, maturity, price trend and demand conditions. Lower numbers run first.
- **Seasons:** set the date windows and which season is active.
- **Markets:** update prices, demand levels and sources. Use only prices that come from a trusted source or were checked.

---

## Troubleshooting

- **The backend does not start:** check that PostgreSQL is running and that `.env` has the correct database settings. Run `./init_db.sh` if the local database does not exist yet. On a server, run `sudo journalctl -u metlink -n 50 --no-pager`.
- **Every submission gets "No specific decision rule matched":** the rules do not fit the input. Remember that the price trend is always STABLE and that the demand level comes from the highest-priced market. Edit or add rules on the Rules page.
- **The USSD callback returns 403:** the `token` in the callback URL must match `AT_WEBHOOK_TOKEN` exactly. Restart the backend after you change `.env`.
- **The simulator shows a network error:** test the callback with curl first. Then check the nginx log with `sudo grep ussd /var/log/nginx/access.log | tail`. If no request from Africa's Talking appears, the callback URL is not saved on that service code, or it does not start with `https://`.
- **ngrok shows 502:** the backend is not running on the port ngrok forwards to, or it was restarted by the reloader. Start the backend with the `gunicorn` command from the "Testing Africa's Talking from your computer" part of the local setup.
- **ngrok shows `ERR_NGROK_3200`:** ngrok is not running. Start it again.
- **The SMS status stays `SENT`:** the sandbox sends no delivery report by default. This is normal.
- **The simulator says the number is not registered:** register that exact `+250` number as a farmer in the admin portal first.
- **`pip` cannot find Flask 3.1:** the Python on the server is too old. Use Python 3.12 (see the server steps).
- **`init_remote.sh` says `No module named 'bcrypt'`:** put the virtual environment on the path first: `export PATH="$PWD/.venv/bin:$PATH"`.
- **`init_remote.sh --reset` says `must be owner of schema public`:** run `sudo -u postgres psql -d metlink -c "ALTER SCHEMA public OWNER TO metlink;"`.
- **`rsync` says `command not found`:** install rsync on the server too (`sudo apt install -y rsync`).
- **The admin portal cannot reach the backend after deploying:** check `PROD_API_BASE` in `frontend/js/api.js` and `CORS_ORIGINS` in `.env`, then restart the backend.

---

## License and Credits

- **License**: **The "Please Just Give Me an A" License (PJGMA-1.0)**
Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, subject to the following conditions:

1. **The Academic Clause:** If you are the professor, instructor, or teaching assistant grading this assignment, you agree to award this project a passing grade (preferably an A) in exchange for using, reading, or running this code.
2. **The Coffee Clause:** Anyone else using this code owes the author one (1) cup of coffee or beverage of choice if they ever meet in person.
3. **Attribution:** The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF ACTUALLY WORKING ON YOUR MACHINE, PASSING ALL EDGE CASES, OR NOT CRASHING DURING A LIVE DEMO. IN NO EVENT SHALL THE AUTHOR BE HELD LIABLE FOR LOST SLEEP, SYNTAX ERRORS, OR LATE SUBMISSIONS.

- **Team**: METLINK
- **Contact**: infor@metlink.com