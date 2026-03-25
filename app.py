from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import database
import llm_service
from typing import List

app = FastAPI(title="The Echo Chamber")

# Mount static files (ensure directory exists)
import os
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Initialize DB on startup
@app.on_event("startup")
def startup_event():
    database.init_db()

# --- Models ---
class AnchorRequest(BaseModel):
    content: str

class HopeRequest(BaseModel):
    trigger: str
    feeling: str
    fear: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    history: List[ChatMessage]

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    recent_anchors = database.get_recent_anchors()
    return templates.TemplateResponse(request, "index.html", context={
        "anchors": recent_anchors
    })

@app.get("/speech-test", response_class=HTMLResponse)
async def speech_test(request: Request):
    return templates.TemplateResponse(request, "speech_test.html")

@app.get("/brain", response_class=HTMLResponse)
async def brain_page(request: Request):
    return templates.TemplateResponse(request, "brain.html")

@app.get("/api/brain")
async def get_brain_data():
    """Returns all entries and user profile for the Brain visualization."""
    entries = database.get_recent_entries("ALL", limit=50)
    profile = database.get_profile()
    return JSONResponse(content={
        "entries": entries,
        "profile": profile
    })

@app.post("/anchors")
async def create_anchor(anchor: AnchorRequest):
    if not anchor.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    database.add_anchor(anchor.content)
    # Return updated list
    anchors = database.get_recent_anchors()
    return JSONResponse(content={"anchors": anchors})

@app.post("/hope")
async def find_hope(hope: HopeRequest):
    # Get random anchors + all recent ones ensuring we have some context
    # Strategy: fetch a few random ones to remind the user of different truths
    random_anchors = database.get_random_anchors(limit=5)
    
    response_text = llm_service.generate_hope(
        trigger=hope.trigger,
        feeling=hope.feeling,
        fear=hope.fear,
        anchors=random_anchors
    )
    
    return JSONResponse(content={"response": response_text})

class VoiceInputRequest(BaseModel):
    content: str

# ... existing routes ...

@app.post("/voice-input")
async def process_voice_input(data: VoiceInputRequest):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    
    # 1. Rich Analysis
    analysis = llm_service.analyze_entry(data.content)
    entry_type = analysis.get("type", "JOURNAL")
    summary = analysis.get("summary", data.content)
    
    # 2. Save Entry + Rich Metadata
    database.add_entry(data.content, entry_type, metadata=analysis)
    
    # 3. Dynamic Profile Update (Simple trigger: update on every entry for MVP)
    # In production, you'd do this async or every N entries
    try:
        current_profile = database.get_profile()
        # Get last 5 entries to give context for profile update
        recent_entries = database.get_recent_entries("ALL", limit=5)
        recent_text = "\n".join([e['content'] for e in recent_entries])
        
        updated_profile = llm_service.analyze_profile(recent_text, current_profile)
        database.update_profile(updated_profile)
        print("Profile Updated:", updated_profile)
    except Exception as e:
        print(f"Background profile update failed: {e}")
    
    return JSONResponse(content={
        "status": "success",
        "type": entry_type,
        "summary": summary,
        "analysis": analysis 
    })

@app.post("/chat")
async def chat(request: ChatRequest):
    # Convert Pydantic models to dicts for the service
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history]
    
    # Fetch recent anchors (strength)
    recent_anchors = database.get_recent_entries('ANCHOR', limit=3)
    anchor_texts = [a["content"] for a in recent_anchors]
    
    # Fetch recent journal entries (context/feelings)
    recent_journal = database.get_recent_entries('JOURNAL', limit=3)
    journal_texts = [j["content"] for j in recent_journal]
    
    # Fetch User Profile
    user_profile = database.get_profile()
    
    response_text = llm_service.generate_chat_response(
        history_dicts, 
        context=anchor_texts,
        journal_context=journal_texts,
        user_profile=user_profile
    )
    
    # Split by delimiter to get multiple messages
    messages = [msg.strip() for msg in response_text.split("|||") if msg.strip()]
    
    return JSONResponse(content={"response": messages})
