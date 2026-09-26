"""
Edge Case & Stress Test Suite for Alley Overseas Bot
====================================================
Tests unusual, malicious, and edge-case inputs to prove the bot never crashes.
"""

import asyncio
import os
import sys
import main

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sent_replies = []

async def mock_send(phone: str, text: str):
    sent_replies.append(text)

main.send_message = mock_send

async def run_edge_case_tests():
    phone = "919000000000"
    print("=" * 60)
    print("🧪 RUNNING ADVANCED EDGE-CASE & STRESS TESTS")
    print("=" * 60)

    # Test 1: User sends gibberish on first message
    print("\n1️⃣ Testing random first message (e.g. 'tell me about visa'):")
    await main.handle_message(phone, "tell me about visa")
    assert "Question 1 of 7" in sent_replies[-1], "Failed on non-standard start"
    print("   ✅ Bot gracefully starts with Welcome + Question 1.")

    # Test 2: User enters invalid option (text instead of number)
    print("\n2️⃣ Testing invalid input on Question 1 (typed 'Canada' instead of 3):")
    await main.handle_message(phone, "Canada")
    assert "Please reply with a *number*" in sent_replies[-1]
    print("   ✅ Bot gently reminded user to reply with a number.")

    # Test 3: User enters number out of range (e.g. 99)
    print("\n3️⃣ Testing out-of-range number (typed '99'):")
    await main.handle_message(phone, "99")
    assert "Invalid choice" in sent_replies[-1]
    print("   ✅ Bot rejected 99 and re-asked Question 1.")

    # Test 4: User selects valid option 3 (Canada)
    print("\n4️⃣ Testing valid option (typed '3'):")
    await main.handle_message(phone, "3")
    assert "Question 2 of 7" in sent_replies[-1]
    print("   ✅ Advanced to Question 2.")

    # Test 5: User triggers emergency mid-chat restart
    print("\n5️⃣ Testing mid-conversation 'restart' keyword:")
    await main.handle_message(phone, "restart")
    assert "Question 1 of 7" in sent_replies[-1]
    print("   ✅ Bot successfully reset back to Question 1.")

    # Test 6: Fast forward to Multi-Select Question 7
    print("\n6️⃣ Fast forwarding to Question 7...")
    await main.handle_message(phone, "1") # Q1: UK
    await main.handle_message(phone, "2") # Q2: Masters
    await main.handle_message(phone, "3") # Q3: Sept
    await main.handle_message(phone, "3") # Q4: Bachelors
    await main.handle_message(phone, "1") # Q5: IELTS
    await main.handle_message(phone, "2") # Q6: 15-25L

    # Test 7: Messy multi-select input (e.g. "1,   4 & 5 + 99")
    print("\n7️⃣ Testing messy multi-select formatting ('1,   4 & 5 + 99'):")
    await main.handle_message(phone, "1,   4 & 5 + 99")
    assert "Please enter your *full name*" in sent_replies[-1]
    # Check that it extracted valid options (1, 4, 5) and ignored 99
    assert main.sessions[phone]["data"]["help_type"] == "University Selection, Visa Assistance, Education Loan"
    print("   ✅ Successfully parsed '1, 4, 5' and ignored invalid '99'!")

    # Test 8: Single character / empty text validation
    print("\n8️⃣ Testing empty/short text on Name field (entered '.'):")
    await main.handle_message(phone, ".")
    assert "valid response" in sent_replies[-1]
    print("   ✅ Bot rejected 1-character input on Name field.")

    # Complete name and city
    await main.handle_message(phone, "Aarav Mehta")
    await main.handle_message(phone, "Ahmedabad")

    # Test 9: User types after completion
    print("\n9️⃣ Testing post-completion message:")
    await main.handle_message(phone, "when will you call?")
    assert "already submitted" in sent_replies[-1]
    print("   ✅ Bot correctly recognizes completed lead state.")

    # Test 10: Special keyword CALL
    print("\n🔟 Testing CALL keyword:")
    await main.handle_message(phone, "CALL")
    assert "Call Back Requested" in sent_replies[-1]
    print("   ✅ Special keyword CALL responded with priority message.")

    print("\n" + "=" * 60)
    print("🎉 ALL 10 EDGE-CASE & STRESS TESTS PASSED WITH ZERO CRASHES!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_edge_case_tests())
