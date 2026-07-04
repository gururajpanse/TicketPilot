import os
import asyncio
from google import genai

async def main():
    # Load .env file manually
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v

    api_key = os.environ.get("GOOGLE_API_KEY")
    print(f"API Key start: {api_key[:15] if api_key else 'None'}")
    client = genai.Client(api_key=api_key)
    
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash-lite"]
    for model in models:
        try:
            print(f"Testing {model}...")
            response = client.models.generate_content(
                model=model,
                contents="Hello, reply with only one word 'success'."
            )
            print(f"  Result: {response.text.strip()}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
