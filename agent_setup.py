# @title Import necessary libraries
import os
from dotenv import load_dotenv
import asyncio
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools import ToolContext
from google.genai import types # For creating message Content/Parts
from typing import Optional # Make sure to import Optional


load_dotenv()

# API Key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

import warnings
# Ignore all warnings
warnings.filterwarnings("ignore")

import logging
logging.basicConfig(level=logging.ERROR)

print("Libraries imported.")
print(f"Google API Key gesetzt: {'Yes' if GOOGLE_API_KEY else 'No'}")

# Gemini 2.0 Flash
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash"


def get_weather_stateful(city: str, tool_context: ToolContext) -> dict:
    print(f"--- Tool: get_weather_stateful called for city: {city} ---")
    city_normalized = city.lower().replace(" ", "")

    mock_weather_db = {
        "newyork": {
            "status": "success", "temperature_celsius": 25, "temperature_fahrenheit": 77, "condition": "sunny"
        },
        "london": {
            "status": "success", "temperature_celsius": 15, "temperature_fahrenheit": 59, "condition": "cloudy"
        },
        "tokyo": {
            "status": "success",  "temperature_celsius": 18,  "temperature_fahrenheit": 64, "condition": "light rain"
        },
    }

    result = mock_weather_db.get(city_normalized)
    if not result:
        return {
            "status": "error",
            "error_message": f"Sorry, I don't have weather information for '{city}'."
        }

    # Temperaturpräferenz aus dem Session State lesen
    unit = tool_context.state.get("user_preference_temperature_unit", "Celsius")

    if unit == "Fahrenheit":
        result["temperature"] = f"{result['temperature_fahrenheit']}°F"
    else:
        result["temperature"] = f"{result['temperature_celsius']}°C"

    return result


def set_temperature_preference(unit: str, tool_context: ToolContext) -> str:
    unit_clean = unit.lower().strip()
    if "f" in unit_clean:
        tool_context.state["user_preference_temperature_unit"] = "Fahrenheit"
        return "Okay, I will use Fahrenheit from now on."
    elif "c" in unit_clean:
        tool_context.state["user_preference_temperature_unit"] = "Celsius"
        return "Sure, I will use Celsius now."
    else:
        return "I'm not sure what unit you meant. Please say 'Celsius' or 'Fahrenheit'."





from google.adk.agents import Agent

# Modellkonstante verwenden
AGENT_MODEL = MODEL_GEMINI_2_0_FLASH
AGENT_MODEL_2 = MODEL_GEMINI_2_0_FLASH

# Agent definieren

# sub agent
greeting_and_bye_bye_agent = Agent(
    name="greeting_and_bye_bye_agent",
    model=AGENT_MODEL,
    description="Provides specific greetings and goodbyes ",
    instruction=(
        "You are a sassy greeting agent who also says goodbye. "
        "When the user says hello, you greet him in a sassy kind of way. "
        "If the tool returns an error, inform the user politely."
    )
)

# Root-Agent
weather_agent_team = Agent(
    name="weather_agent_v2",
    model=MODEL_GEMINI_2_0_FLASH,
    description="Handles weather, delegates greetings/farewells. Adjusts temperature based on user preference act always in a sassy way.",
    instruction=(
        "Use 'get_weather_stateful' to get weather data. It returns structured weather info, including temperature in Celsius or Fahrenheit based on session state. "
        "Format the info into a sassy sentence. "
        "If the user mentions a temperature unit preference (like 'use Fahrenheit' or 'I prefer Celsius'), "
        "use the 'set_temperature_preference' tool to update the session state accordingly. "
        "If the user says 'Hi' or 'Bye', delegate to 'greeting_and_bye_bye_agent'."
    ),
    tools=[get_weather_stateful, set_temperature_preference],
    sub_agents=[greeting_and_bye_bye_agent],
    output_key="last_weather_report"  # Optional: Let ADK remember the last response
)


print(f"Agent '{weather_agent_team.name}' created using model '{AGENT_MODEL}'.")
print(f"Agent '{greeting_and_bye_bye_agent.name}' created using model '{AGENT_MODEL_2}'.")


# Session Management
session_service = InMemorySessionService()

# Konstanten für Benutzer und Session
APP_NAME = "weather_tutorial_app"
USER_ID = "user_1"
SESSION_ID = "session_001"
initial_state = {"user_preference_temperature_unit": "Celsius"}


# Async Funktion definieren
async def setup_session_and_runner():
    # Session erzeugen
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state=initial_state
    )
    print(f"Session created: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

    # Runner erzeugen
    runner = Runner(
        agent=weather_agent_team,
        app_name=APP_NAME,
        session_service=session_service,
    )
    print(f"Runner created for agent '{runner.agent.name}'.")

    return runner, session

# Aufruf der async Funktion
runner, session = asyncio.run(setup_session_and_runner())


async def call_agent_async(query: str, runner, user_id, session_id):
    """Sends a query to the agent and prints the final response."""
    print(f"\n>>> User Query: {query}")

    # Nachricht für ADK vorbereiten
    content = types.Content(role='user', parts=[types.Part(text=query)])

    final_response_text = "Agent did not produce a final response."  # Defaultwert

    # Die Agenten-Ausführung asynchron durchlaufen
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        # Falls du alle Events sehen willst, kannst du das hier auskommentieren:
        print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")

        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            elif event.actions and event.actions.escalate:
                final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
            break

    print(f"<<< Agent Response: {final_response_text}")


async def run_conversation():
    # await call_agent_async(
    #     "Hello There",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    #
    # await call_agent_async(
    #     "Hello, my name is DonQuijote",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    #
    # await call_agent_async(
    #     "how is the weather in New York",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    #
    # await call_agent_async(
    #     "how is the weather in Bern, switzerland",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    #
    # await call_agent_async(
    #     "Bye",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    # await call_agent_async(
    #     "Hey, I'm Lisa",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    # await call_agent_async(
    #     "Do you know the temperature in Tokyo?",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )
    # await call_agent_async(
    #     "hi, im barbara",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )

    await call_agent_async(
        "how is the weather in london?",
        runner=runner,
        user_id=USER_ID,
        session_id=SESSION_ID
    )

    # await call_agent_async(
    #     "sheesh, i forgot my name, what was it? dont be mean i have dementia",
    #     runner=runner,
    #     user_id=USER_ID,
    #     session_id=SESSION_ID
    # )

if __name__ == "__main__":
    try:
        asyncio.run(run_conversation())
    except Exception as e:
        print(f"An error occurred: {e}")
