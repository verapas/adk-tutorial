# @title Import necessary libraries
import os
from dotenv import load_dotenv
import asyncio
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools import ToolContext
from google.genai import types

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from typing import Optional

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from typing import Optional, Dict, Any # For type hints





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


def block_keyword_guardrail(
        callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    agent_name = callback_context.agent_name
    print(f"--- Callback: block_keyword_guardrail running for agent: {agent_name} ---")


    # Finde die letzte echte User-Message (ignoriere "For context")
    last_user_message_text = ""
    if llm_request.contents:
        for content in reversed(llm_request.contents):
            if content.role == 'user' and content.parts and content.parts[0].text:
                msg = content.parts[0].text
                if not msg.startswith("For context"):
                    last_user_message_text = msg
                    break

    print(f"--- Callback: Inspecting last user message: '{last_user_message_text[:100]}...' ---")


    keyword_to_block = "BLOCK"
    if keyword_to_block in last_user_message_text.upper():
        print(f"--- Callback: Found '{keyword_to_block}'. Blocking LLM call! ---")
        callback_context.state["guardrail_block_keyword_triggered"] = True
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"I cannot process this request because it contains the blocked keyword '{keyword_to_block}'.")]
            )
        )
    else:
        print(f"--- Callback: Keyword not found. Allowing LLM call for {agent_name}. ---")
        return None


print("✅ block_keyword_guardrail function defined.")



def block_paris_tool_guardrail(
        tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext
) -> Optional[Dict]:
    """
    Checks if 'get_weather_stateful' is called for 'Paris'.
    If so, blocks the tool execution and returns a specific error dictionary.
    Otherwise, allows the tool call to proceed by returning None.
    """
    tool_name = tool.name
    agent_name = tool_context.agent_name # Agent attempting the tool call
    print(f"--- Callback: block_paris_tool_guardrail running for tool '{tool_name}' in agent '{agent_name}' ---")
    print(f"--- Callback: Inspecting args: {args} ---")

    # --- Guardrail Logic ---
    target_tool_name = "get_weather_stateful" # Match the function name used by FunctionTool
    blocked_city = "paris"

    # Check if it's the correct tool and the city argument matches the blocked city
    if tool_name == target_tool_name:
        city_argument = args.get("city", "") # Safely get the 'city' argument
        if city_argument and city_argument.lower() == blocked_city:
            print(f"--- Callback: Detected blocked city '{city_argument}'. Blocking tool execution! ---")
            # Optionally update state
            tool_context.state["guardrail_tool_block_triggered"] = True
            print(f"--- Callback: Set state 'guardrail_tool_block_triggered': True ---")

            # Return a dictionary matching the tool's expected output format for errors
            # This dictionary becomes the tool's result, skipping the actual tool run.
            return {
                "status": "error",
                "error_message": f"Policy restriction: Weather checks for '{city_argument.capitalize()}' are currently disabled by a tool guardrail."
            }
        else:
            print(f"--- Callback: City '{city_argument}' is allowed for tool '{tool_name}'. ---")
    else:
        print(f"--- Callback: Tool '{tool_name}' is not the target tool. Allowing. ---")


    # If the checks above didn't return a dictionary, allow the tool to execute
    print(f"--- Callback: Allowing tool '{tool_name}' to proceed. ---")
    return None # Returning None allows the actual tool function to run

print("✅ block_paris_tool_guardrail function defined.")


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

    tool_context.state["last_city_checked_stateful"] = city

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



# Sub-Agent für Begrüssungen
greeting_and_bye_bye_agent = Agent(
    name="greeting_and_bye_bye_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    description="Provides specific greetings and goodbyes",
    instruction=(
        "You are a sassy greeting agent who also says goodbye. "
        "When the user says hello, you greet him in a sassy kind of way. "
        "If the tool returns an error, inform the user politely."
    ),
)

# Session-Service für das Tutorial
session_service_stateful = InMemorySessionService()

# Konstanten für Benutzer und Session
APP_NAME = "weather_tutorial_app"
USER_ID_STATEFUL = "user_state_demo"
SESSION_ID_STATEFUL = "session_state_demo_001"


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


# Root-Agent (stateful)
root_agent_stateful = Agent(
    name="weather_agent_v4_stateful",
    model=MODEL_GEMINI_2_0_FLASH,
    description="Main agent: weather with temp pref, delegates greetings/farewells, saves report to state.",
    instruction="Use 'get_weather_stateful' for weather. Respect 'user_preference_temperature_unit'. "
                "Use 'set_temperature_preference' to change it. "
                "Delegate greetings to 'greeting_and_bye_bye_agent'.",
    tools=[get_weather_stateful, set_temperature_preference],
    sub_agents=[greeting_and_bye_bye_agent],
    output_key="last_weather_report",
    before_model_callback=block_keyword_guardrail,
    before_tool_callback=block_paris_tool_guardrail

)

# Runner für den stateful Agent
runner_root_stateful = Runner(
    agent=root_agent_stateful,
    app_name=APP_NAME,
    session_service=session_service_stateful
)

# Session mit initialem State erstellen
initial_state = {"user_preference_temperature_unit": "Celsius"}
asyncio.run(session_service_stateful.create_session(
    app_name=APP_NAME,
    user_id=USER_ID_STATEFUL,
    session_id=SESSION_ID_STATEFUL,
    state=initial_state
))


async def run_stateful_conversation():
    print("\n--- 🧪 Testing Session State: Temp Unit & output_key ---")

    # 1. Wetter in London (Initialwert: Celsius)
    print("--- Turn 1: Wetter in London (Celsius erwartet) ---")
    await call_agent_async(
        query="What's the weather in London?",
        runner=runner_root_stateful,
        user_id=USER_ID_STATEFUL,
        session_id=SESSION_ID_STATEFUL
    )

    # 2. State manuell auf Fahrenheit setzen
    print("\n--- Update: Temperatur-Einheit auf Fahrenheit setzen ---")
    try:
        session_obj = session_service_stateful.sessions[APP_NAME][USER_ID_STATEFUL][SESSION_ID_STATEFUL]
        session_obj.state["user_preference_temperature_unit"] = "Fahrenheit"
        print(f"✅ Neue Einheit gesetzt: {session_obj.state['user_preference_temperature_unit']}")
    except Exception as e:
        print(f"❌ Fehler beim Setzen der Einheit: {e}")

    # 3. Wetter in New York (jetzt Fahrenheit)
    print("\n--- Turn 2: Wetter in New York (Fahrenheit erwartet) ---")
    await call_agent_async(
        query="Tell me the weather in New York.",
        runner=runner_root_stateful,
        user_id=USER_ID_STATEFUL,
        session_id=SESSION_ID_STATEFUL
    )

    # 4. Begrüßung (Test Delegation + Output-Key-Überschreiben)
    print("\n--- Turn 3: Begrüssung senden ---")
    await call_agent_async(
        query="Hi!",
        runner=runner_root_stateful,
        user_id=USER_ID_STATEFUL,
        session_id=SESSION_ID_STATEFUL
    )

    # 5. Session-State inspizieren
    print("\n--- 📦 Session-State anzeigen ---")
    final_state = await session_service_stateful.get_session(
        app_name=APP_NAME,
        user_id=USER_ID_STATEFUL,
        session_id=SESSION_ID_STATEFUL
    )

    print("\n--- ⛔️ Nachricht mit Keyword BLOCK wird durch callback abgefangen ---")
    await call_agent_async(
        query="wie ist das wetter in new york du BLOCK",
        runner=runner_root_stateful,
        user_id=USER_ID_STATEFUL,
        session_id=SESSION_ID_STATEFUL
    )


    print("\n--- testen ob tool-guardrail greift, welcher anfragen an paris unterbindet ---")
    await call_agent_async(
    query="What's the weather in Paris?",
    runner=runner_root_stateful,
    user_id=USER_ID_STATEFUL,
    session_id=SESSION_ID_STATEFUL
)

    if final_state:
        print(f"🔸 Temperaturpräferenz: {final_state.state.get('user_preference_temperature_unit', 'Nicht gesetzt')}")
        print(f"🔸 Letzter Wetter-Report (output_key): {final_state.state.get('last_weather_report', 'Nicht gesetzt')}")
        print(f"🔸 Letzte abgefragte Stadt: {final_state.state.get('last_city_checked_stateful', 'Nicht gesetzt')}")
    else:
        print("❌ Fehler beim Laden des Session-States.")


if __name__ == "__main__":
    try:
        asyncio.run(run_stateful_conversation())
    except Exception as e:
        print(f"An error occurred: {e}")
