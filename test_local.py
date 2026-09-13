"""
Local WhatsApp Chatbot Simulator
================================
Test your full Alley Overseas bot flow in the terminal without WhatsApp / API keys!
"""

import asyncio
import os
import csv
import sys
import main

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

async def mock_send_message(phone: str, text: str):
    print("\n" + "─" * 50)
    print(f"🤖 BOT to [{phone}]:")
    print(text)
    print("─" * 50 + "\n")

# Override main's send_message with our terminal printer
main.send_message = mock_send_message

async def run_simulator():
    print("=" * 60)
    print("  ALLEY OVERSEAS WHATSAPP BOT — LOCAL SIMULATOR")
    print("=" * 60)
    print("Type your messages as if you are a customer chatting on WhatsApp.")
    print("Type 'exit' or 'quit' to stop.\n")

    user_phone = "919999999999"

    # Start with Hi
    print(f"👤 USER [{user_phone}]: Hi")
    await main.handle_message(user_phone, "Hi")

    while True:
        try:
            user_input = input(f"👤 Reply (or type 'exit'): ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("\nExiting simulator. Checking leads.csv...")
                break

            await main.handle_message(user_phone, user_input)

        except (KeyboardInterrupt, EOFError):
            break

    # Show leads captured
    if os.path.exists(main.LEADS_FILE):
        print("\n📊 Captured Leads in leads.csv:")
        with open(main.LEADS_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                print(" | ".join(row))

if __name__ == "__main__":
    asyncio.run(run_simulator())
