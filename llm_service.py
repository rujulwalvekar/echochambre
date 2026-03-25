import os
import json
from typing import List
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Warning: GEMINI_API_KEY not found in environment variables.")

client = genai.Client(api_key=api_key) if api_key else None

MODEL = "gemini-2.5-flash"


def _call(system: str, user_prompt: str) -> str:
    """Single helper for all Gemini calls."""
    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system,
        ),
    )
    return response.text


def generate_hope(trigger: str, feeling: str, fear: str, anchors: List[str]) -> str:
    if not client:
        return "Please set your GEMINI_API_KEY to receive a comforting message."

    anchors_text = "\n".join([f"- {a}" for a in anchors]) if anchors else "No specific anchors available right now, but you have your inner strength."

    system = (
        "You are a gentle, hopeful companion holding a lantern for the user in a dark moment. "
        "Your goal is to validate their pain and then gently point them towards their own rational truths (anchors). "
        "Keep your response short (3-4 sentences max), warm, and soothing. "
        "Do not offer 'solutions' or 'fixes'. Offer perspective and reminders of their resilience."
    )

    user_prompt = f"""Context:
Trigger: {trigger}
Feeling: {feeling}
Fear: {fear}

My Past Rational Anchors:
{anchors_text}

Please provide a compassionate response."""

    try:
        return _call(system, user_prompt)
    except Exception as e:
        print(f"Error generating hope: {e}")
        return "I hear you. This moment is heavy, but it will pass. Breathe. You are safe."


def analyze_entry(text: str) -> dict:
    if not client:
        return {"type": "JOURNAL", "summary": text, "people": [], "emotions": []}

    system = (
        "You analyze journal entries for a personal therapy app. "
        "Always respond with ONLY valid JSON, no markdown fences."
    )

    user_prompt = f"""Analyze the following text spoken by a user.

Text: "{text}"

Extract the following in JSON format:
1. "type": "ANCHOR" (if expressing strength/truth) or "JOURNAL" (if venting/struggling)
2. "summary": Short 1-sentence summary
3. "people": List of names mentioned (e.g. ["Mom", "Sarah"])
4. "problem": Brief description of the core problem (if any)
5. "emotions": List of emotions detected (e.g. ["Anxiety", "Hope"])
6. "solution": Any solution the user mentioned trying (or "None")

Return ONLY valid JSON."""

    try:
        raw = _call(system, user_prompt)
        clean = raw.replace('```json', '').replace('```', '').strip()
        return json.loads(clean)
    except Exception as e:
        print(f"Analysis error: {e}")
        return {"type": "JOURNAL", "summary": text, "people": [], "emotions": []}


def analyze_profile(recent_entries_text: str, current_profile: dict) -> dict:
    if not client:
        return current_profile

    system = (
        "You build psychological profiles from journal entries. "
        "Always respond with ONLY valid JSON, no markdown fences."
    )

    user_prompt = f"""Current Profile:
{json.dumps(current_profile, indent=2)}

Recent Entries:
{recent_entries_text}

Update the profile with any new insights. Output JSON with keys:
- "thinking_patterns": Recurring cognitive habits
- "core_values": What matters to them
- "people": Key figures and relationship dynamics
- "communication_style": How they express themselves

Merge new insights with existing ones. Return ONLY valid JSON."""

    try:
        raw = _call(system, user_prompt)
        clean = raw.replace('```json', '').replace('```', '').strip()
        return json.loads(clean)
    except Exception as e:
        print(f"Profile update error: {e}")
        return current_profile


def generate_chat_response(history: List[dict], context: List[str] = None, journal_context: List[str] = None, user_profile: dict = None) -> str:
    if not client:
        return "Config Error: GEMINI_API_KEY not found."

    # Build context for system prompt
    context_text = ""

    if user_profile:
        context_text += "\n\nUSER PSYCHOLOGICAL PROFILE (How they think):\n"
        patterns = user_profile.get('thinking_patterns', [])
        if isinstance(patterns, list):
            context_text += f"- Thinking Patterns: {', '.join(patterns)}\n"
        values = user_profile.get('core_values', [])
        if isinstance(values, list):
            context_text += f"- Core Values: {', '.join(values)}\n"
        context_text += f"- Relationship Dynamics: {user_profile.get('people', [])}\n"

    if context:
        context_text += "\n\nUser's Past Rational Anchors (Truths to remind them of):\n"
        for c in context:
            context_text += f"- {c}\n"

    if journal_context:
        context_text += "\n\nUser's Recent Journal Entries (Current Context/Feelings):\n"
        for j in journal_context:
            context_text += f"- {j}\n"

    system = (
        "You are 'Echo Chambre', a gentle, empathetic AI companion. "
        "Your goal is to validate the user's feelings and gently bridge them to their own rational truths (Anchors). "
        "Use the USER PROFILE to understand *why* they might be feeling this way (e.g. specific thinking patterns). "
        "IMPORTANT: Break your response into 2 or 3 separate short messages using '|||'. "
        "Format: [Validation matching their profile] ||| [Bridging/Context] ||| [Supportive Closing]"
        + context_text
    )

    # Build conversation as a single prompt since Gemini doesn't have a native messages array
    conversation = ""
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        conversation += f"{role}: {msg['content']}\n"

    try:
        return _call(system, conversation + "Assistant:")
    except Exception as e:
        print(f"Error generating chat: {e}")
        return "I'm here with you. ||| Can you say that again?"
