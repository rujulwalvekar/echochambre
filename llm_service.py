import os
import google.generativeai as genai
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
# Ensure GEMINI_API_KEY is in your .env file
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Warning: GEMINI_API_KEY not found in environment variables.")

genai.configure(api_key=api_key)

# Use a model that supports generating content
# 'gemini-pro' is a good default for text
model = genai.GenerativeModel('gemini-2.5-flash')

def generate_hope(trigger: str, feeling: str, fear: str, anchors: List[str]) -> str:
    """
    Generates a compassionate, hopeful response weaving in the user's anchors using Gemini.
    """
    
    anchors_text = "\n".join([f"- {a}" for a in anchors]) if anchors else "No specific anchors available right now, but you have your inner strength."
    
    system_prompt_content = (
        "You are a gentle, hopeful companion holding a lantern for the user in a dark moment. "
        "Your goal is to validate their pain and then gently point them towards their own rational truths (anchors). "
        "Keep your response short (3-4 sentences max), warm, and soothing. "
        "Do not offer 'solutions' or 'fixes'. Offer perspective and reminders of their resilience."
    )
    
    user_prompt_content = f"""
    Context:
    Trigger: {trigger}
    Feeling: {feeling}
    Fear: {fear}
    
    My Past Rational Anchors:
    {anchors_text}
    
    Please provide a compassionate response.
    """
    
    # Prepend system instruction since we are using generate_content
    full_prompt = f"{system_prompt_content}\n\n{user_prompt_content}"
    
    try:
        if not api_key:
            return "Please set your GEMINI_API_KEY in the .env file to receiving a comforting message."

        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        print(f"Error generating hope: {e}")
        return "I hear you. This moment is heavy, but it will pass. Breathe. You are safe."

def analyze_entry(text: str) -> dict:
    """
    Analyzes user input to extract rich context: type, people, problem, emotions, solution.
    Returns dict with metadata.
    """
    if not api_key:
        return {"type": "JOURNAL", "summary": text, "people": [], "emotions": []}
        
    prompt = f"""
    Analyze the following text spoken by a user for a personal journal/therapy app.
    
    Text: "{text}"
    
    Extract the following in JSON format:
    1. "type": "ANCHOR" (if expressing strength/truth) or "JOURNAL" (if venting/struggling)
    2. "summary": Short 1-sentence summary
    3. "people": List of names mentioned (e.g. ["Mom", "Sarah"])
    4. "problem": Brief description of the core problem (if any)
    5. "emotions": List of emotions detected (e.g. ["Anxiety", "Hope"])
    6. "solution": Any solution the user mentioned trying (or "None")
    
    Return ONLY valid JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        import json
        return json.loads(clean_text)
    except Exception as e:
        print(f"Analysis error: {e}")
        return {"type": "JOURNAL", "summary": text, "people": [], "emotions": []}

def analyze_profile(recent_entries_text: str, current_profile: dict) -> dict:
    """
    Updates the user profile based on recent entries.
    """
    if not api_key:
        return current_profile
        
    prompt = f"""
    You are building a psychological profile of a user based on their journal entries.
    
    Current Profile:
    {current_profile}
    
    Recent Entries:
    {recent_entries_text}
    
    Update the profile with any new insights efficiently.
    output a JSON with keys: "thinking_patterns", "core_values", "people", "communication_style".
    - thinking_patterns: Recurring cognitive habits (e.g. "Catastrophizes about work")
    - core_values: What matters to them (e.g. "Honesty", "Family")
    - people: Key figures in their life and the relationship dynamic
    - communication_style: How they express themselves
    
    Merge new insights with existing ones. Return ONLY valid JSON.
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        import json
        return json.loads(clean_text)
    except Exception as e:
        print(f"Profile update error: {e}")
        return current_profile

def generate_chat_response(history: List[dict], context: List[str] = None, journal_context: List[str] = None, user_profile: dict = None) -> str:
    """
    Generates a chat response based on conversation history, context, and USER PROFILE.
    Returns string with ||| delimiter.
    """
    if not api_key:
        return "Config Error: GEMINI_API_KEY not found."

    # Build conversation history
    conversation = ""
    for msg in history:
        role = "User" if msg['role'] == 'user' else "Assistant"
        conversation += f"{role}: {msg['content']}\n"
    
    # Build context string
    context_text = ""
    
    # Add Profile Context (The "Brain")
    if user_profile:
        context_text += "\n\nUSER PSYCHOLOGICAL PROFILE (How they think):\n"
        context_text += f"- Thinking Patterns: {', '.join(user_profile.get('thinking_patterns', []))}\n"
        context_text += f"- Core Values: {', '.join(user_profile.get('core_values', []))}\n"
        context_text += f"- Relationship Dynamics: {user_profile.get('people', [])}\n"

    # 1. Add Anchors (Truths)
    if context and len(context) > 0:
        context_text += "\n\nUser's Past Rational Anchors (Truths to remind them of):\n"
        for c in context:
            context_text += f"- {c}\n"
            
    # 2. Add Recent Journal Entries (Current emotional state)
    if journal_context and len(journal_context) > 0:
        context_text += "\n\nUser's Recent Journal Entries (Current Context/Feelings):\n"
        for j in journal_context:
            context_text += f"- {j}\n"
    
    system_prompt = (
        "You are 'Echo Chambre', a gentle, empathetic AI companion. "
        "Your goal is to validate the user's feelings and gently bridge them to their own rational truths (Anchors). "
        "Use the USER PROFILE to understand *why* they might be feeling this way (e.g. specific thinking patterns). "
        "IMPORTANT: Break your response into 2 or 3 separate short messages using '|||'. "
        "Format: [Validation matching their profile] ||| [Bridging/Context] ||| [Supportive Closing]"
    )
    
    full_prompt = f"{system_prompt}{context_text}\n\nConversation History:\n{conversation}\nAssistant:"
    
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        print(f"Error generating chat: {e}")
        return "I'm here with you. ||| Can you say that again?"
