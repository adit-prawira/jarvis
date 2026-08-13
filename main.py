import asyncio
import os

from dotenv import load_dotenv

from infrastructure.opencode.brain_client import OpenCodeBrain


async def main() -> None:
    load_dotenv()
    password = os.getenv("OPENCODE_SERVER_PASSWORD")
    if not password:
        print("ERROR: OPENCODE_SERVER_PASSWORD not set in .env")
        return

    brain = OpenCodeBrain(
        base_url="http://127.0.0.1:4096",
        password=password,
    )
    try:
        result = await brain.send_turn("Hello, who are you?")
        print(result.text)
    finally:
        await brain.close()


asyncio.run(main())
