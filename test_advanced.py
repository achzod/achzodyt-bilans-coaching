"""
Tests avances - Coach flows et integration complete
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
import json

# Override DB for testing
import models
models.DB_PATH = "test_advanced.db"

from models import init_platform_db, create_user, create_session
from api import app

# Cleanup
if os.path.exists("test_advanced.db"):
    os.remove("test_advanced.db")

init_platform_db()

# Create test users
coach_id = create_user("coach@advanced.com", "coach123", "Coach Avance", role="coach")
client_id = create_user("client@advanced.com", "client123", "Client Avance", role="client", objectif="perte_gras")

coach_token = create_session(coach_id)
client_token = create_session(client_id)

client = TestClient(app)

results = {"passed": 0, "failed": 0, "errors": []}


def test(name, condition, error_msg=""):
    if condition:
        results["passed"] += 1
        print(f"  [PASS] {name}")
        return True
    else:
        results["failed"] += 1
        results["errors"].append(f"{name}: {error_msg}")
        print(f"  [FAIL] {name}: {error_msg}")
        return False


def test_section(name):
    print(f"\n{'='*60}")
    print(f"TESTING: {name}")
    print('='*60)


# ============ TEST: Coach Dashboard ============
test_section("Coach Dashboard Access")

# Coach can access coach dashboard
response = client.get("/api/coach/dashboard", headers={"Authorization": f"Bearer {coach_token}"})
test("Coach access dashboard", response.status_code == 200)

# Client cannot access coach dashboard
response = client.get("/api/coach/dashboard", headers={"Authorization": f"Bearer {client_token}"})
test("Client blocked from coach dashboard", response.status_code == 403)


# ============ TEST: Full Bilan Flow ============
test_section("Complete Bilan Flow")

# Client submits bilan
bilan_data = {
    "poids": 75.0,
    "energie": 7,
    "sommeil_qualite": 8,
    "sommeil_heures": 7.5,
    "motivation": 8,
    "stress": 3,
    "faim": 6,
    "seances_prevues": 4,
    "seances_faites": 4,
    "respect_calories": 8,
    "nombre_ecarts": 1,
    "hydratation_litres": 2.5,
    "victoires": "J'ai tenu toutes mes seances malgre la fatigue du travail",
    "difficultes": "Difficile de tenir la nutrition le weekend",
    "questions": "Est-ce normal d'avoir plus faim depuis que j'ai augmente l'intensite?"
}

response = client.post("/api/client/bilans",
    headers={"Authorization": f"Bearer {client_token}"},
    json=bilan_data)
test("Client submit complete bilan", response.status_code == 200)
bilan_id = response.json().get('bilan_id')

# Coach sees pending bilan
response = client.get("/api/coach/dashboard", headers={"Authorization": f"Bearer {coach_token}"})
dashboard = response.json()
test("Coach sees pending bilan",
    len(dashboard.get('pending_bilans', [])) >= 1)

# Coach gets bilan detail
response = client.get(f"/api/coach/bilans/{bilan_id}", headers={"Authorization": f"Bearer {coach_token}"})
test("Coach gets bilan detail", response.status_code == 200)
bilan_detail = response.json()
test("Bilan has correct data", bilan_detail.get('bilan', {}).get('poids') == 75.0)

# Coach client list
response = client.get("/api/coach/clients", headers={"Authorization": f"Bearer {coach_token}"})
test("Coach gets client list", response.status_code == 200 and len(response.json().get('clients', [])) >= 1)

# Coach client detail
response = client.get(f"/api/coach/clients/{client_id}", headers={"Authorization": f"Bearer {coach_token}"})
test("Coach gets client detail", response.status_code == 200)


# ============ TEST: Messaging Flow ============
test_section("Messaging Flow")

# Client sends to coach
response = client.post("/api/messages/to-coach",
    headers={"Authorization": f"Bearer {client_token}"},
    data={"body": "Bonjour coach, j'ai une question sur mon programme", "subject": "Question programme"})
test("Client send to coach", response.status_code == 200)

# Coach sees message
response = client.get("/api/messages", headers={"Authorization": f"Bearer {coach_token}"})
messages = response.json()
test("Coach receives message", len(messages.get('messages', [])) >= 1)

# Coach sends to client
# First get coach ID from the system
from models import get_user_by_email
coach_user = get_user_by_email("coach@advanced.com")

response = client.post("/api/messages",
    headers={"Authorization": f"Bearer {coach_token}"},
    json={"to_user_id": client_id, "subject": "Re: Question programme", "body": "Salut! Oui tu peux ajuster..."})
test("Coach sends to client", response.status_code == 200)

# Client sees coach response
response = client.get("/api/messages", headers={"Authorization": f"Bearer {client_token}"})
test("Client receives coach response", len(response.json().get('messages', [])) >= 1)


# ============ TEST: Daily Metrics ============
test_section("Daily Metrics")

from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")

response = client.post("/api/client/daily",
    headers={"Authorization": f"Bearer {client_token}"},
    json={"date": today, "poids": 74.8, "calories": 2200, "energie": 8})
test("Log daily metric", response.status_code == 200)

response = client.get("/api/client/daily", headers={"Authorization": f"Bearer {client_token}"})
test("Get daily metrics", response.status_code == 200 and len(response.json().get('metrics', [])) >= 1)


# ============ TEST: Notifications ============
test_section("Notifications")

response = client.get("/api/notifications", headers={"Authorization": f"Bearer {client_token}"})
test("Client gets notifications", response.status_code == 200)

# Should have notification from coach message
notifs = response.json().get('notifications', [])
test("Client has notification", len(notifs) >= 1)


# ============ TEST: Client Stats ============
test_section("Client Stats")

response = client.get("/api/client/dashboard", headers={"Authorization": f"Bearer {client_token}"})
stats = response.json()
test("Dashboard has total_bilans", 'total_bilans' in stats and stats['total_bilans'] >= 1)
test("Dashboard has last_bilan", 'last_bilan' in stats and stats['last_bilan'] is not None)
test("Dashboard has unread_messages", 'unread_messages' in stats)


# ============ TEST: Error Handling ============
test_section("Error Handling")

# Non-existent bilan
response = client.get("/api/coach/bilans/99999", headers={"Authorization": f"Bearer {coach_token}"})
test("404 for non-existent bilan", response.status_code == 404)

# Non-existent client
response = client.get("/api/coach/clients/99999", headers={"Authorization": f"Bearer {coach_token}"})
test("404 for non-existent client", response.status_code == 404)

# Client trying to access other client's bilan
other_client_id = create_user("other@test.com", "other123", "Other", role="client")
other_token = create_session(other_client_id)
response = client.get(f"/api/client/bilans/{bilan_id}", headers={"Authorization": f"Bearer {other_token}"})
test("Client cannot access other's bilan", response.status_code == 403)


# ============ TEST: HTML Pages ============
test_section("HTML Pages Content")

response = client.get("/")
test("Index has login form", 'login-form' in response.text)
test("Index has register form", 'register-form' in response.text)
test("Index has dashboard elements", 'dashboard-name' in response.text)
test("Index has bilan form", 'bilan-form' in response.text)

response = client.get("/coach")
test("Coach page has dashboard", 'dashboard-view' in response.text)
test("Coach page has bilan view", 'bilan-view' in response.text)
test("Coach page has AI section", 'ai-section' in response.text)


# ============ RESULTS ============
print("\n" + "="*60)
print("ADVANCED TEST RESULTS")
print("="*60)
print(f"\n  PASSED: {results['passed']}")
print(f"  FAILED: {results['failed']}")
print(f"  TOTAL:  {results['passed'] + results['failed']}")

if results['errors']:
    print("\n  ERRORS:")
    for err in results['errors']:
        print(f"    - {err}")

# Cleanup
if os.path.exists("test_advanced.db"):
    os.remove("test_advanced.db")

sys.exit(0 if results['failed'] == 0 else 1)
