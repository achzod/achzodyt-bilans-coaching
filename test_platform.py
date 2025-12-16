"""
Test complet de la plateforme coaching
Execute des tests sur tous les endpoints et fonctionnalites
"""

import sys
import os
import json
import time

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test results
results = {"passed": 0, "failed": 0, "errors": []}


def test(name, condition, error_msg=""):
    """Helper pour logger les tests"""
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
    """Header de section"""
    print(f"\n{'='*60}")
    print(f"TESTING: {name}")
    print('='*60)


# ============ TEST 1: Database Models ============
test_section("Database Initialization")

try:
    from models import (
        init_platform_db, create_user, authenticate_user, get_user_by_id,
        get_user_by_email, get_all_clients, create_session, validate_session,
        delete_session, send_message, get_user_messages, submit_bilan,
        get_user_bilans, get_client_stats, get_coach_dashboard
    )
    test("Import models", True)
except Exception as e:
    test("Import models", False, str(e))

try:
    # Clean test DB
    if os.path.exists("test_coaching.db"):
        os.remove("test_coaching.db")

    # Override DB path for testing
    import models
    models.DB_PATH = "test_coaching.db"

    init_platform_db()
    test("Initialize database", True)
except Exception as e:
    test("Initialize database", False, str(e))


# ============ TEST 2: User Management ============
test_section("User Management")

try:
    # Create coach
    coach_id = create_user(
        email="coach@test.com",
        password="coach123",
        name="Coach Test",
        role="coach"
    )
    test("Create coach user", coach_id is not None, f"Got: {coach_id}")
except Exception as e:
    test("Create coach user", False, str(e))
    coach_id = None

try:
    # Create client
    client_id = create_user(
        email="client@test.com",
        password="client123",
        name="Client Test",
        role="client",
        objectif="perte_gras",
        duree_semaines=12
    )
    test("Create client user", client_id is not None, f"Got: {client_id}")
except Exception as e:
    test("Create client user", False, str(e))
    client_id = None

try:
    # Try duplicate email
    dup_id = create_user(
        email="client@test.com",
        password="other",
        name="Dup"
    )
    test("Reject duplicate email", dup_id is None, f"Should be None, got: {dup_id}")
except Exception as e:
    test("Reject duplicate email", False, str(e))

try:
    # Authenticate
    auth_result = authenticate_user("client@test.com", "client123")
    test("Authenticate valid user", auth_result is not None)
except Exception as e:
    test("Authenticate valid user", False, str(e))

try:
    # Wrong password
    wrong_auth = authenticate_user("client@test.com", "wrongpass")
    test("Reject wrong password", wrong_auth is None, f"Should be None, got: {wrong_auth}")
except Exception as e:
    test("Reject wrong password", False, str(e))

try:
    # Get user by ID
    user = get_user_by_id(client_id) if client_id else None
    test("Get user by ID", user is not None and user['email'] == 'client@test.com')
except Exception as e:
    test("Get user by ID", False, str(e))

try:
    # Get user by email
    user = get_user_by_email("coach@test.com")
    test("Get user by email", user is not None and user['role'] == 'coach')
except Exception as e:
    test("Get user by email", False, str(e))

try:
    # Get all clients
    clients = get_all_clients()
    test("Get all clients", len(clients) == 1 and clients[0]['email'] == 'client@test.com')
except Exception as e:
    test("Get all clients", False, str(e))


# ============ TEST 3: Sessions ============
test_section("Session Management")

token = None
try:
    token = create_session(client_id) if client_id else None
    test("Create session", token is not None and len(token) > 20)
except Exception as e:
    test("Create session", False, str(e))

try:
    user = validate_session(token) if token else None
    test("Validate session", user is not None and user['id'] == client_id)
except Exception as e:
    test("Validate session", False, str(e))

try:
    invalid = validate_session("invalid_token_12345")
    test("Reject invalid token", invalid is None, f"Should be None, got: {invalid}")
except Exception as e:
    test("Reject invalid token", False, str(e))


# ============ TEST 4: Messages ============
test_section("Messaging System")

try:
    msg_id = send_message(
        from_user_id=client_id,
        to_user_id=coach_id,
        subject="Test message",
        body="Bonjour coach, ceci est un test!"
    ) if client_id and coach_id else None
    test("Send message", msg_id is not None and msg_id > 0)
except Exception as e:
    test("Send message", False, str(e))

try:
    messages = get_user_messages(coach_id) if coach_id else []
    test("Get user messages", len(messages) >= 1)
except Exception as e:
    test("Get user messages", False, str(e))


# ============ TEST 5: Bilans ============
test_section("Bilan System")

bilan_id = None
try:
    bilan_data = {
        "poids": 78.5,
        "energie": 7,
        "sommeil_qualite": 8,
        "sommeil_heures": 7.5,
        "motivation": 8,
        "stress": 4,
        "seances_prevues": 4,
        "seances_faites": 4,
        "respect_calories": 7,
        "victoires": "J'ai tenu toutes mes seances",
        "questions": "Comment ameliorer mon sommeil?"
    }
    bilan_id = submit_bilan(client_id, bilan_data) if client_id else None
    test("Submit bilan", bilan_id is not None and bilan_id > 0)
except Exception as e:
    test("Submit bilan", False, str(e))

try:
    bilans = get_user_bilans(client_id) if client_id else []
    test("Get user bilans", len(bilans) >= 1)
except Exception as e:
    test("Get user bilans", False, str(e))

try:
    # Second bilan
    bilan_data2 = {
        "poids": 78.0,
        "energie": 8,
        "sommeil_qualite": 7,
        "motivation": 9
    }
    bilan_id2 = submit_bilan(client_id, bilan_data2) if client_id else None
    test("Submit second bilan", bilan_id2 is not None and bilan_id2 > bilan_id)
except Exception as e:
    test("Submit second bilan", False, str(e))


# ============ TEST 6: Stats & Dashboard ============
test_section("Stats & Dashboard")

try:
    stats = get_client_stats(client_id) if client_id else {}
    test("Get client stats",
         stats.get('total_bilans', 0) >= 2 and
         stats.get('last_bilan') is not None)
except Exception as e:
    test("Get client stats", False, str(e))

try:
    dashboard = get_coach_dashboard()
    test("Get coach dashboard",
         dashboard.get('total_clients', 0) >= 1 and
         'pending_bilans' in dashboard)
except Exception as e:
    test("Get coach dashboard", False, str(e))


# ============ TEST 7: API Module ============
test_section("API Module")

try:
    from api import app
    test("Import API app", True)
except Exception as e:
    test("Import API app", False, str(e))

try:
    from fastapi.testclient import TestClient
    client = TestClient(app)
    test("Create test client", True)
except Exception as e:
    test("Create test client", False, str(e))

try:
    # Health check
    response = client.get("/api/health")
    test("API health check", response.status_code == 200 and response.json().get('status') == 'ok')
except Exception as e:
    test("API health check", False, str(e))


# ============ TEST 8: API Auth Endpoints ============
test_section("API Auth Endpoints")

api_token = None
try:
    # Register new user via API
    response = client.post("/api/auth/register", json={
        "email": "apitest@test.com",
        "password": "apitest123",
        "name": "API Test User",
        "objectif": "prise_muscle"
    })
    test("API register", response.status_code == 200 and 'token' in response.json())
    api_token = response.json().get('token')
except Exception as e:
    test("API register", False, str(e))

try:
    # Login
    response = client.post("/api/auth/login", json={
        "email": "apitest@test.com",
        "password": "apitest123"
    })
    test("API login", response.status_code == 200 and 'token' in response.json())
    api_token = response.json().get('token')
except Exception as e:
    test("API login", False, str(e))

try:
    # Get me
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {api_token}"})
    test("API get me", response.status_code == 200 and response.json().get('email') == 'apitest@test.com')
except Exception as e:
    test("API get me", False, str(e))

try:
    # Invalid token
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
    test("API reject invalid token", response.status_code == 401)
except Exception as e:
    test("API reject invalid token", False, str(e))


# ============ TEST 9: API Client Endpoints ============
test_section("API Client Endpoints")

try:
    response = client.get("/api/client/dashboard", headers={"Authorization": f"Bearer {api_token}"})
    test("API client dashboard", response.status_code == 200)
except Exception as e:
    test("API client dashboard", False, str(e))

try:
    response = client.post("/api/client/bilans",
        headers={"Authorization": f"Bearer {api_token}"},
        json={
            "poids": 80.0,
            "energie": 8,
            "sommeil_qualite": 7,
            "motivation": 9,
            "victoires": "Test via API"
        })
    test("API submit bilan", response.status_code == 200 and response.json().get('success'))
except Exception as e:
    test("API submit bilan", False, str(e))

try:
    response = client.get("/api/client/bilans", headers={"Authorization": f"Bearer {api_token}"})
    test("API get bilans", response.status_code == 200 and len(response.json().get('bilans', [])) >= 1)
except Exception as e:
    test("API get bilans", False, str(e))


# ============ TEST 10: API Messages ============
test_section("API Messages")

try:
    response = client.get("/api/messages", headers={"Authorization": f"Bearer {api_token}"})
    test("API get messages", response.status_code == 200 and 'messages' in response.json())
except Exception as e:
    test("API get messages", False, str(e))


# ============ TEST 11: Static Files ============
test_section("Static Files")

try:
    response = client.get("/")
    test("Serve client portal", response.status_code == 200 and "Achzod" in response.text)
except Exception as e:
    test("Serve client portal", False, str(e))

try:
    response = client.get("/coach")
    test("Serve coach dashboard", response.status_code == 200 and "Coach Dashboard" in response.text)
except Exception as e:
    test("Serve coach dashboard", False, str(e))


# ============ TEST 12: AI Assistant Module ============
test_section("AI Assistant Module")

try:
    from ai_assistant import analyze_client_bilan, regenerate_response, generate_quick_response
    test("Import AI assistant", True)
except Exception as e:
    test("Import AI assistant", False, str(e))


# ============ RESULTS ============
print("\n" + "="*60)
print("TEST RESULTS")
print("="*60)
print(f"\n  PASSED: {results['passed']}")
print(f"  FAILED: {results['failed']}")
print(f"  TOTAL:  {results['passed'] + results['failed']}")

if results['errors']:
    print("\n  ERRORS:")
    for err in results['errors']:
        print(f"    - {err}")

# Cleanup
if os.path.exists("test_coaching.db"):
    os.remove("test_coaching.db")

# Exit code
sys.exit(0 if results['failed'] == 0 else 1)
