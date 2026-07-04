import asyncio
import json
from app.agent import workflow
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

async def main():
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="ticket-pilot")
    runner = Runner(agent=workflow, session_service=session_service, app_name="ticket-pilot")
    
    payload = {
        "title": "Help! Account locked out after multiple attempts",
        "description": "I cannot login to my account. My password was wrong. Please reset it.",
        "user": "alice@company.com",
        "priority": "Medium"
    }
    
    message = types.Content(
        role="user", 
        parts=[types.Part.from_text(text=json.dumps(payload))]
    )
    
    print("--- Running Workflow ---")
    events = []
    async for event in runner.run_async(
        new_message=message,
        user_id="test_user",
        session_id=session.id,
    ):
        events.append(event)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"Event text: {part.text}")
        if event.output:
            print(f"Workflow output: {json.dumps(event.output, indent=2)}")
            
    print("\n--- Final Session State ---")
    print(json.dumps(session.state, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
