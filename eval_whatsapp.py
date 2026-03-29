"""
Eval: WhatsApp Adapter Endpoint
Tests the full WhatsApp flow: send message -> get response -> verify persistence.
Run: python eval_whatsapp.py [base_url]
"""

import requests
import json
import sys
import time

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
TEST_PHONE = "+1999EVAL" + str(int(time.time()) % 10000)


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


def test_empty_message():
    """Test 1: Empty text returns a nudge, not an error."""
    print("\n--- Test 1: Empty Message ---")
    r = requests.post(f"{BASE_URL}/whatsapp", json={"from": TEST_PHONE, "text": ""}, timeout=10)
    log(r.status_code == 200, "Returns 200 for empty text", f"status={r.status_code}")
    data = r.json()
    msgs = data.get("messages", [])
    log(len(msgs) >= 1, "Returns at least 1 message", f"messages={msgs}")


def test_small_talk():
    """Test 2: Small talk gets a quick greeting without LLM."""
    print("\n--- Test 2: Small Talk Guard ---")
    start = time.time()
    r = requests.post(f"{BASE_URL}/whatsapp", json={"from": TEST_PHONE, "text": "hey"}, timeout=10)
    elapsed = time.time() - start

    log(r.status_code == 200, "Returns 200", f"status={r.status_code}")
    data = r.json()
    msgs = data.get("messages", [])
    log(len(msgs) >= 1, "Returns greeting message", f"messages={msgs}")
    log(elapsed < 3, f"Fast response (no LLM) in {elapsed:.1f}s", f"elapsed={elapsed:.1f}s")


def test_real_message():
    """Test 3: Real message gets analyzed, stored, and responded to."""
    print("\n--- Test 3: Real Message Flow ---")
    unique = f"eval-wa-{int(time.time())}"
    payload = {
        "from": TEST_PHONE,
        "text": f"I had a great lunch with Meera today, she's such a positive person. {unique}"
    }
    r = requests.post(f"{BASE_URL}/whatsapp", json=payload, timeout=45)
    log(r.status_code == 200, "Returns 200", f"status={r.status_code}")

    data = r.json()
    msgs = data.get("messages", [])
    log(isinstance(msgs, list), "messages is a list", f"type={type(msgs)}")
    log(len(msgs) >= 1, f"At least 1 response message", f"count={len(msgs)}")
    if msgs:
        log(len(msgs[0]) > 10, "First message has substance", f"len={len(msgs[0])}")

    return unique


def test_entry_persisted(unique_marker):
    """Test 4: The message was ingested into the Brain as an entry."""
    print("\n--- Test 4: Entry Persisted in Brain ---")
    r = requests.get(f"{BASE_URL}/api/brain", timeout=15)
    log(r.status_code == 200, "GET /api/brain returns 200")

    data = r.json()
    entries = data.get("entries", [])

    found = any(unique_marker in e.get("content", "") for e in entries)
    log(found, "WhatsApp message found in entries", f"marker={unique_marker}")

    # Check source is 'whatsapp'
    wa_entry = next((e for e in entries if unique_marker in e.get("content", "")), None)
    if wa_entry:
        log(wa_entry.get("source") == "whatsapp", "Entry source is 'whatsapp'", f"source={wa_entry.get('source')}")
        metadata = wa_entry.get("metadata", {})
        log("Meera" in str(metadata.get("people", [])), "LLM detected 'Meera'", f"people={metadata.get('people')}")
    else:
        log(False, "Entry source check", "Entry not found")
        log(False, "People detection check", "Entry not found")


def test_conversation_continuity():
    """Test 5: Send a follow-up and verify the response is context-aware."""
    print("\n--- Test 5: Conversation Continuity ---")
    payload = {
        "from": TEST_PHONE,
        "text": "Tell me more about what you think of that"
    }
    r = requests.post(f"{BASE_URL}/whatsapp", json=payload, timeout=45)
    log(r.status_code == 200, "Follow-up returns 200", f"status={r.status_code}")

    data = r.json()
    msgs = data.get("messages", [])
    log(len(msgs) >= 1, "Follow-up gets response", f"count={len(msgs)}")

    # The response should reference something from context (Meera, lunch, positive)
    all_text = " ".join(msgs).lower()
    has_context = any(word in all_text for word in ["meera", "lunch", "positive", "friend", "connection"])
    log(has_context, "Response references prior context", f"response_preview={all_text[:120]}...")


def test_different_sender_isolation():
    """Test 6: Different phone number has independent conversation."""
    print("\n--- Test 6: Sender Isolation ---")
    other_phone = "+1888OTHER" + str(int(time.time()) % 10000)
    payload = {
        "from": other_phone,
        "text": "This is my first message ever"
    }
    r = requests.post(f"{BASE_URL}/whatsapp", json=payload, timeout=45)
    log(r.status_code == 200, "Different sender returns 200", f"status={r.status_code}")
    data = r.json()
    msgs = data.get("messages", [])
    log(len(msgs) >= 1, "Different sender gets response", f"count={len(msgs)}")


if __name__ == "__main__":
    print("=" * 60)
    print("  ECHO CHAMBRE - WhatsApp Adapter Eval")
    print(f"  Target: {BASE_URL}")
    print("=" * 60)

    test_empty_message()
    test_small_talk()
    marker = test_real_message()
    test_entry_persisted(marker)
    test_conversation_continuity()
    test_different_sender_isolation()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  RESULTS: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)
