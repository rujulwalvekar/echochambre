import database
import llm_service
from dotenv import load_dotenv
import json

# Load env variables
load_dotenv()

# Initialize DB if needed
database.init_db()

# User's inputs
inputs = [
    # Past Proof -> Anchor
    "I have survived multiple breakups in the past. Even if it was just time that healed me, the fact is I am still here. I survived.",
    
    # Core Truth -> Anchor
    " I know that when I am not spiraling, I am capable of talking to myself objectively. I can see where the situation is wrong, why it hurts, and whether it's on me or someone else. I am capable of making action plans.",
    
    # Trigger -> Journal
    "I am terrified that I am going to be alone, that I won't love anyone else the way I love certain people, and that people don't understand me or aren't able to love me in the way I deserve.",
    
    # Fear -> Journal
    "My worst fear is that I will have to move on and deal with everything alone, and eventually die alone.",
    
    # Support -> Anchor
    "My mentor would tell me: It's our story and we can write it the way we want to."
]

print("--- Seeding Data ---")

for text in inputs:
    print(f"Processing: {text[:50]}...")
    
    # 1. Analyze (Rich Metadata)
    analysis = llm_service.analyze_entry(text)
    entry_type = analysis.get("type", "JOURNAL")
    
    print(f"  -> Classified as: {entry_type}")
    print(f"  -> Metadata: {analysis}")
    
    # 2. Save
    database.add_entry(text, entry_type, metadata=analysis)

print("\n--- Updating User Profile ---")

# 3. Update Profile based on these new entries
try:
    current_profile = database.get_profile()
    
    # Fetch all just added
    recent_entries = database.get_recent_entries("ALL", limit=10)
    recent_text = "\n".join([e['content'] for e in recent_entries])
    
    updated_profile = llm_service.analyze_profile(recent_text, current_profile)
    database.update_profile(updated_profile)
    
    print("Profile Updated Successfully!")
    print(json.dumps(updated_profile, indent=2))

except Exception as e:
    print(f"Profile update failed: {e}")
