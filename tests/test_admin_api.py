import json
import urllib.error
import urllib.request

BASE = "http://localhost:5000/api"
passed = 0
total = 0


def req(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    r = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def check(label, condition, detail=""):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print(f"[PASS] {label}")
    else:
        print(f"[FAIL] {label} -> {detail}")


print("=" * 60)
print("METLINK ADMIN API FULL VERIFICATION")
print("=" * 60)

# 1. Security & Authentication
st, res = req("GET", "/dashboard/summary")
check("Security: Block unauthenticated dashboard access (401)", st == 401, res)

st, res = req("POST", "/auth/login", {"username": "aline.uwase", "password": "WrongPassword"})
check("Auth: Reject wrong admin password (401)", st == 401, res)

st, res = req("POST", "/auth/login", {"username": "aline.uwase", "password": "Admin@1234"})
check("Auth: Admin login with valid credentials (200)", st == 200 and "token" in res, res)
token = res.get("token")

# 2. Public Landing Page Endpoint
st, res = req("GET", "/public/markets")
check("Landing Page: Fetch public active market prices (200)", st == 200 and len(res.get("markets", [])) > 0, res)

# 3. Farmer Registration & Update
st, res = req("POST", "/farmers", {
    "phone_number": "+250788776655",
    "name": "Claude Niyonzima",
    "location": "Runda",
    "preferred_language": "rw"
}, token=token)
check("Farmers: Register new farmer (201)", st == 201, res)
farmer_id = res.get("farmer", {}).get("farmer_id")

st, res = req("POST", "/farmers", {
    "phone_number": "+250788776655",
    "name": "Duplicate Farmer",
    "location": "Runda"
}, token=token)
check("Farmers: Reject duplicate phone number (409)", st == 409, res)

st, res = req("PUT", f"/farmers/{farmer_id}", {"location": "Gacurabwenge", "is_active": False}, token=token)
check("Farmers: Update & deactivate farmer (200)", st == 200 and res.get("farmer", {}).get("location") == "Gacurabwenge", res)

# 4. Market Information Create & Update
st, res = req("POST", "/markets", {
    "market_name": "Kamonyi Central Market",
    "location": "Kamonyi",
    "average_price_per_kg": 580,
    "demand_level": "HIGH",
    "source": "Field Survey"
}, token=token)
check("Markets: Add new market price (201)", st == 201, res)
market_id = res.get("market", {}).get("market_id")

st, res = req("PUT", f"/markets/{market_id}", {"average_price_per_kg": 610, "demand_level": "MEDIUM"}, token=token)
check("Markets: Update existing market price (200)", st == 200 and res.get("market", {}).get("average_price_per_kg") == 610.0, res)

# 5. Seasonal Information Create & Update
st, res = req("POST", "/seasons", {
    "season_name": "Season B 2027 Test",
    "start_date": "2027-02-01",
    "end_date": "2027-05-31",
    "description": "Main rainy season test entry.",
    "is_active": False
}, token=token)
check("Seasons: Add new agricultural season (201)", st == 201, res)
season_id = res.get("season", {}).get("season_id")

st, res = req("PUT", f"/seasons/{season_id}", {"description": "Updated rainy season notes."}, token=token)
check("Seasons: Update seasonal information (200)", st == 200, res)

# 6. Decision Rules Create, Safety Guard & Update
st, res = req("POST", "/rules", {
    "rule_name": "Unsafe Wait Rule",
    "maturity": "RIPE",
    "price_trend": "RISING",
    "demand_level": "HIGH",
    "preservation_required": False,
    "action": "STORE_AND_WAIT",
    "waiting_period_days": 5
}, token=token)
check("Rules Safety: Block STORE_AND_WAIT without preservation (400)", st == 400, res)

st, res = req("POST", "/rules", {
    "rule_name": "Green Bulk Hold Rule",
    "maturity": "GREEN",
    "price_trend": "RISING",
    "demand_level": "HIGH",
    "preservation_required": True,
    "action": "STORE_AND_WAIT",
    "waiting_period_days": 6,
    "min_quantity_kg": 300,
    "priority": 2
}, token=token)
check("Rules: Create valid decision rule (201)", st == 201, res)
rule_id = res.get("rule", {}).get("rule_id")

st, res = req("PUT", f"/rules/{rule_id}", {"is_active": False, "priority": 5}, token=token)
check("Rules: Update & deactivate decision rule (200)", st == 200 and res.get("rule", {}).get("is_active") is False, res)

# 7. Audit Trail Verification
st, res = req("GET", "/audit-logs", token=token)
logs = res.get("audit_logs", [])
check("Audit Logs: Verify admin changes were recorded (200)", st == 200 and len(logs) >= 8, res)

print("=" * 60)
score = round((passed / total) * 100, 1) if total else 0
print(f"RESULT: {passed}/{total} checks passed ({score}%)")
print("=" * 60)
