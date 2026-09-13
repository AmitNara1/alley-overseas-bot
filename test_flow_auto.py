"""
Automated End-to-End Flow Test for Alley Overseas WhatsApp Bot
==============================================================
Runs automated simulation of a complete user journey and asserts
that the lead is properly captured and formatted.
"""

import asyncio
import os
import csv
import sys
import main

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

captured_messages = []

async def mock_send_message(phone: str, text: str):
    captured_messages.append(text)

main.send_message = mock_send_message

async def test_full_lead_flow():
    test_phone = "918888888888"
    
    # Clean previous test csv if needed
    if os.path.exists(main.LEADS_FILE):
        os.remove(main.LEADS_FILE)

    print(">> Step 1: User sends 'Hi'")
    await main.handle_message(test_phone, "Hi")
    assert "Welcome to *Alley Overseas*" in captured_messages[-1]
    assert "Question 1 of 7" in captured_messages[-1]
    print("  [OK] Welcome + Q1 Country sent successfully.")

    print(">> Step 2: User chooses 2 (USA)")
    await main.handle_message(test_phone, "2")
    assert "Question 2 of 7" in captured_messages[-1]
    print("  [OK] Q2 Study Level sent successfully.")

    print(">> Step 3: User chooses 2 (Master's)")
    await main.handle_message(test_phone, "2")
    assert "Question 3 of 7" in captured_messages[-1]
    print("  [OK] Q3 Intake sent successfully.")

    print(">> Step 4: User chooses 3 (Sept Intake)")
    await main.handle_message(test_phone, "3")
    assert "Question 4 of 7" in captured_messages[-1]
    print("  [OK] Q4 Qualification sent successfully.")

    print(">> Step 5: User chooses 3 (Bachelor's)")
    await main.handle_message(test_phone, "3")
    assert "Question 5 of 7" in captured_messages[-1]
    print("  [OK] Q5 English Test sent successfully.")

    print(">> Step 6: User chooses 1 (IELTS)")
    await main.handle_message(test_phone, "1")
    assert "Question 6 of 7" in captured_messages[-1]
    print("  [OK] Q6 Budget sent successfully.")

    print(">> Step 7: User chooses 2 (Rs. 15-25 Lakhs)")
    await main.handle_message(test_phone, "2")
    assert "Question 7 of 7" in captured_messages[-1]
    print("  [OK] Q7 Help Type sent successfully.")

    print(">> Step 8: User chooses multiple: '1, 3, 4' (University, Scholarship, Visa)")
    await main.handle_message(test_phone, "1, 3, 4")
    assert "Please enter your *full name*" in captured_messages[-1]
    print("  [OK] Lead Capture: Name requested after multi-selection.")

    print(">> Step 9: User enters Name 'Kewal Malde'")
    await main.handle_message(test_phone, "Kewal Malde")
    assert "Please enter your *email address*" in captured_messages[-1]
    print("  [OK] Lead Capture: Email requested.")

    print(">> Step 10: User enters Email 'kewal@example.com'")
    await main.handle_message(test_phone, "kewal@example.com")
    assert "Please enter your *mobile number*" in captured_messages[-1]
    print("  [OK] Lead Capture: Mobile requested.")

    print(">> Step 11: User enters Mobile '9876543210'")
    await main.handle_message(test_phone, "9876543210")
    assert "Please enter your *city*" in captured_messages[-1]
    print("  [OK] Lead Capture: City requested.")

    print(">> Step 12: User enters City 'Mumbai'")
    await main.handle_message(test_phone, "Mumbai")
    assert "Thank You!" in captured_messages[-1]
    print("  [OK] Complete Thank You message sent.")

    # Check CSV file contents
    assert os.path.exists(main.LEADS_FILE), "leads.csv was not created!"
    with open(main.LEADS_FILE, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1, f"Expected 1 lead, found {len(reader)}"
        lead = reader[0]
        print("\n=== Saved Lead Data in CSV ===")
        for k, v in lead.items():
            print(f"  * {k}: {v}")
        
        assert lead["name"] == "Kewal Malde"
        assert lead["email"] == "kewal@example.com"
        assert lead["country"] == "USA 🇺🇸"
        assert lead["study_level"] == "Master's"
        assert lead["help_type"] == "University Selection, Scholarship Guidance, Visa Assistance"
        assert lead["city"] == "Mumbai"

    print("\n>>> ALL 12 STEPS (INCLUDING MULTI-SELECT) PASSED WITH 100% ACCURACY! <<<")

if __name__ == "__main__":
    asyncio.run(test_full_lead_flow())
