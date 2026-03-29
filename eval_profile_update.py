"""
Eval: Profile Update Pipeline
Tests that the full flow works: ingest entry -> update profile -> verify profile reflects new data.
Run: python eval_profile_update.py
"""

import requests
import json
import sys
import time

BASE_URL = "https://echochambre.vercel.app"
PASS = 0
FAIL = 0


def log(status, test_name, detail=""):
    global PASS, FAIL
    icon = "PASS" if status else "FAIL"
    if status:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{icon}] {test_name}")
    if detail:
        print(f"         {detail}")


def eval_health():
    """Test 1: App is up and responding."""
    print("\n--- Test 1: Health Check ---")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        log(r.status_code == 200, "GET /health returns 200", f"status={r.status_code}")
        data = r.json()
        log(data.get("ok") is True, "/health response has ok=true", f"body={data}")
    except Exception as e:
        log(False, "Health check reachable", str(e))


def eval_ingest():
    """Test 2: Submit a unique entry and verify it's stored."""
    print("\n--- Test 2: Entry Ingestion ---")
    unique_marker = f"eval-marker-{int(time.time())}"
    payload = {"content": f"My colleague Devendra helped me debug a tricky issue today. {unique_marker}"}

    try:
        r = requests.post(f"{BASE_URL}/voice-input", json=payload, timeout=30)
        log(r.status_code == 200, "POST /voice-input returns 200", f"status={r.status_code}")

        data = r.json()
        log(data.get("status") == "success", "Response status is 'success'", f"status={data.get('status')}")
        log(data.get("type") in ("ANCHOR", "JOURNAL"), "Entry classified as ANCHOR or JOURNAL", f"type={data.get('type')}")
        log("analysis" in data, "Analysis returned in response")

        analysis = data.get("analysis", {})
        log(isinstance(analysis.get("emotions"), list), "Emotions is a list", f"emotions={analysis.get('emotions')}")
        log(isinstance(analysis.get("people"), list), "People is a list", f"people={analysis.get('people')}")

        # Check if 'Devendra' was detected
        people = analysis.get("people", [])
        log("Devendra" in people, "LLM detected person 'Devendra'", f"people={people}")

        return unique_marker
    except Exception as e:
        log(False, "Ingestion request completed", str(e))
        return None


def eval_profile_update():
    """Test 3: Call /update-profile and verify it succeeds."""
    print("\n--- Test 3: Profile Update Endpoint ---")
    try:
        r = requests.post(f"{BASE_URL}/update-profile", timeout=30)
        log(r.status_code == 200, "POST /update-profile returns 200", f"status={r.status_code}")

        data = r.json()
        log(data.get("status") == "success", "Profile update status is 'success'", f"status={data.get('status')}")

        profile = data.get("profile", {})
        log(isinstance(profile, dict), "Profile is a dict")
        log("thinking_patterns" in profile, "Profile has thinking_patterns")
        log("core_values" in profile, "Profile has core_values")
        log("people" in profile, "Profile has people")
        log("communication_style" in profile, "Profile has communication_style")

        return profile
    except Exception as e:
        log(False, "Profile update request completed", str(e))
        return None


def eval_profile_reflects_new_entry(profile):
    """Test 4: Verify the profile now includes 'Devendra' from the entry we just added."""
    print("\n--- Test 4: Profile Reflects New Entry ---")
    if not profile:
        log(False, "Profile available for verification", "No profile returned")
        return

    people = profile.get("people", {})
    if isinstance(people, dict):
        log("Devendra" in people, "Profile people includes 'Devendra'", f"people keys={list(people.keys())}")
    elif isinstance(people, list):
        has_devendra = any("Devendra" in str(p) for p in people)
        log(has_devendra, "Profile people includes 'Devendra'", f"people={people}")
    else:
        log(False, "Profile people is dict or list", f"type={type(people)}")


def eval_brain_api():
    """Test 5: Verify /api/brain returns entries and profile."""
    print("\n--- Test 5: Brain API ---")
    try:
        r = requests.get(f"{BASE_URL}/api/brain", timeout=15)
        log(r.status_code == 200, "GET /api/brain returns 200", f"status={r.status_code}")

        data = r.json()
        entries = data.get("entries", [])
        profile = data.get("profile", {})

        log(len(entries) > 0, f"Brain has entries", f"count={len(entries)}")
        log(isinstance(profile, dict) and len(profile) > 0, "Brain has non-empty profile")

        # Check latest entry is our test entry
        if entries:
            latest = entries[0]
            log("Devendra" in latest.get("content", ""), "Latest entry contains 'Devendra'",
                f"content={latest.get('content', '')[:80]}...")
    except Exception as e:
        log(False, "Brain API request completed", str(e))


def eval_chat():
    """Test 6: Chat endpoint responds with profile-aware messages."""
    print("\n--- Test 6: Chat Endpoint ---")
    try:
        payload = {
            "history": [
                {"role": "user", "content": "I'm feeling a bit overwhelmed today"}
            ]
        }
        r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
        log(r.status_code == 200, "POST /chat returns 200", f"status={r.status_code}")

        data = r.json()
        response = data.get("response", [])
        log(isinstance(response, list), "Chat returns list of messages", f"type={type(response)}")
        log(len(response) >= 1, f"Chat returns at least 1 message", f"count={len(response)}")

        if response:
            log(len(response[0]) > 10, "First message has substance", f"len={len(response[0])}")
    except Exception as e:
        log(False, "Chat request completed", str(e))


if __name__ == "__main__":
    print("=" * 60)
    print("  ECHO CHAMBRE - Profile Update Pipeline Eval")
    print("=" * 60)

    eval_health()
    marker = eval_ingest()
    profile = eval_profile_update()
    eval_profile_reflects_new_entry(profile)
    eval_brain_api()
    eval_chat()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  RESULTS: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)
