"""
Automated End-to-End Flow Test for Alley Overseas WhatsApp Bot (v2 — 4-Question Flow)
======================================================================================
Simulates a complete user journey and asserts the lead is properly captured.
"""

import asyncio
import csv
import os
import sys

import main

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

captured_messages: list[str] = []


async def mock_send_message(phone: str, text: str) -> None:
    captured_messages.append(text)
    print(f"  [BOT] {text[:80].replace(chr(10), ' ')}...")


main.send_message = mock_send_message


async def test_full_lead_flow() -> None:
    test_phone = "918888888888"
    captured_messages.clear()

    # Remove any previous test CSV
    if os.path.exists(main.LEADS_FILE):
        os.remove(main.LEADS_FILE)

    # ── Step 1: User says Hi ──────────────────────────────────────────────────
    print("\n>> Step 1: User sends 'Hi'")
    await main.handle_message(test_phone, "Hi", sender_name="Test User")
    assert "Welcome to *Alley Overseas*" in captured_messages[-1], "Expected welcome message"
    assert "Question 1 of 4" in captured_messages[-1], "Expected Q1 of 4"
    print("  [OK] Welcome + Q1 Country sent.")

    # ── Step 2: Country → USA ─────────────────────────────────────────────────
    print("\n>> Step 2: User chooses 2 (USA)")
    await main.handle_message(test_phone, "2")
    assert "Question 2 of 4" in captured_messages[-1], "Expected Q2 of 4"
    print("  [OK] Q2 Study Level sent.")

    # ── Step 3: Study Level → Master's ───────────────────────────────────────
    print("\n>> Step 3: User chooses 2 (Master's)")
    await main.handle_message(test_phone, "2")
    assert "Question 3 of 4" in captured_messages[-1], "Expected Q3 of 4"
    print("  [OK] Q3 Intake sent.")

    # ── Step 4: Intake → Sept ─────────────────────────────────────────────────
    print("\n>> Step 4: User chooses 3 (Sept Intake)")
    await main.handle_message(test_phone, "3")
    assert "Question 4 of 4" in captured_messages[-1], "Expected Q4 of 4"
    print("  [OK] Q4 Budget sent.")

    # ── Step 5: Budget → ₹15-25 Lakhs ────────────────────────────────────────
    print("\n>> Step 5: User chooses 2 (₹15–25 Lakhs)")
    await main.handle_message(test_phone, "2")
    assert "Thank You!" in captured_messages[-1], "Expected Thank You message after Q4"
    print("  [OK] Thank You message sent — flow COMPLETE.")

    # ── CSV Verification ──────────────────────────────────────────────────────
    assert os.path.exists(main.LEADS_FILE), "leads.csv was NOT created!"
    with open(main.LEADS_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1, f"Expected 1 lead row, found {len(rows)}"
    lead = rows[0]

    print("\n=== Saved Lead in CSV ===")
    for k, v in lead.items():
        print(f"  {k}: {v}")

    assert lead["status"] == "Completed", f"Expected Completed, got {lead['status']}"
    assert lead["name"] == "Test User",   f"Expected 'Test User', got {lead['name']}"
    assert lead["country"] == "USA 🇺🇸",  f"Unexpected country: {lead['country']}"
    assert lead["study_level"] == "Master's", f"Unexpected study_level: {lead['study_level']}"
    assert lead["intake"] == "Sept Intake",   f"Unexpected intake: {lead['intake']}"
    assert lead["budget"] == "₹15–25 Lakhs",  f"Unexpected budget: {lead['budget']}"

    print("\n>>> ALL 5 STEPS PASSED — 4-Question zero-friction flow verified! <<<")


async def test_invalid_input_recovery() -> None:
    """User sends garbage, then a valid answer — bot should recover gracefully."""
    test_phone = "919999999999"
    captured_messages.clear()

    main.reset_session(test_phone)

    print("\n>> [Edge] User sends 'Hi' then invalid input 'abc'")
    await main.handle_message(test_phone, "Hi")
    await main.handle_message(test_phone, "abc")
    assert "Please reply with a *number*" in captured_messages[-1], "Expected invalid-input warning"
    print("  [OK] Invalid input warning sent.")

    print(">> [Edge] User now sends valid '1' (UK)")
    await main.handle_message(test_phone, "1")
    assert "Question 2 of 4" in captured_messages[-1]
    print("  [OK] Recovered to Q2 after invalid input.")


async def test_restart() -> None:
    """User types 'restart' mid-flow and gets fresh Q1."""
    test_phone = "917777777777"
    captured_messages.clear()

    await main.handle_message(test_phone, "Hi")
    await main.handle_message(test_phone, "3")  # Canada
    await main.handle_message(test_phone, "restart")
    assert "Welcome to *Alley Overseas*" in captured_messages[-1], "Expected welcome after restart"
    assert "Question 1 of 4" in captured_messages[-1]
    print("  [OK] Restart mid-flow sends fresh Q1.")


async def test_already_done() -> None:
    """User who completed flow gets the ALREADY_DONE message if they message again."""
    test_phone = "916666666666"
    captured_messages.clear()

    main.reset_session(test_phone)
    await main.handle_message(test_phone, "Hi")
    await main.handle_message(test_phone, "1")
    await main.handle_message(test_phone, "1")
    await main.handle_message(test_phone, "1")
    await main.handle_message(test_phone, "1")  # completes flow
    assert "Thank You!" in captured_messages[-1]

    await main.handle_message(test_phone, "Hello again")
    assert "already submitted" in captured_messages[-1], "Expected ALREADY_DONE message"
    print("  [OK] Already-done message sent to returning completed user.")


if __name__ == "__main__":
    asyncio.run(test_full_lead_flow())
    asyncio.run(test_invalid_input_recovery())
    asyncio.run(test_restart())
    asyncio.run(test_already_done())
    print("\n✅ All test suites passed!")
