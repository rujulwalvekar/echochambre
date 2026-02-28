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

class WhatsAppRequest(BaseModel):
    # Pydantic v2-compatible aliasing: accept JSON key "from"
    from_: str = __import__("pydantic").Field(alias="from")
    text: str

    model_config = {
        "populate_by_name": True,
    }

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    recent_anchors = database.get_recent_anchors()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "anchors": recent_anchors
    })

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/speech-test", response_class=HTMLResponse)
async def speech_test(request: Request):
    return templates.TemplateResponse("speech_test.html", {"request": request})

@app.get("/brain", response_class=HTMLResponse)
async def brain_page(request: Request):
    return templates.TemplateResponse("brain.html", {"request": request})

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

class IngestRequest(BaseModel):
    from_: str = __import__("pydantic").Field(alias="from")
    text: str
    kind: str | None = None

    model_config = {
        "populate_by_name": True,
    }

# ... existing routes ...

def infer_entry_type(text: str, explicit_kind: str | None = None) -> str:
    if explicit_kind:
        k = explicit_kind.strip().upper()
        if k in {"ANCHOR", "JOURNAL"}:
            return k

    t = (text or "").strip()
    tl = t.lower()

    # Explicit anchor prefixes
    for prefix in ("anchor:", "truth:", "remember:"):
        if tl.startswith(prefix):
            return "ANCHOR"

    return "JOURNAL"


@app.post("/ingest")
async def ingest(data: IngestRequest):
    """No-LLM ingest endpoint. Always stores the entry; safe to use when Gemini is rate-limited."""
    text = (data.text or "").strip()
    peer = (data.from_ or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    entry_type = infer_entry_type(text, data.kind)

    metadata = {
        "source": "whatsapp",
        "from": peer,
        "is_question": text.endswith("?"),
    }

    # Store as an entry (brain memory)
    database.add_entry(text, entry_type, metadata=metadata)

    # Store in conversation history too (best-effort)
    try:
        database.add_conversation_message(peer or "unknown", "user", text)
    except Exception:
        pass

    return JSONResponse(content={"ok": True, "type": entry_type})


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

    # Retrieve context relevant to the latest user message:
    # candidate set + LLM rerank (prevents unrelated recency bias)
    latest_user_text = history_dicts[-1]["content"] if history_dicts else ""

    anchor_cands = database.get_recent_entries('ANCHOR', limit=50)
    journal_cands = database.get_recent_entries('JOURNAL', limit=50)

    picked = llm_service.select_relevant_memory_ids(
        latest_user_text=latest_user_text,
        anchor_candidates=anchor_cands,
        journal_candidates=journal_cands,
        max_anchors=3,
        max_journals=2,
    )

    a_by_id = {int(a['id']): a for a in anchor_cands if a.get('id') is not None}
    j_by_id = {int(j['id']): j for j in journal_cands if j.get('id') is not None}

    anchor_texts = [a_by_id[i]['content'] for i in picked.get('anchor_ids', []) if i in a_by_id]
    journal_texts = [j_by_id[i]['content'] for i in picked.get('journal_ids', []) if i in j_by_id]

    # Fallback: FTS search
    if not anchor_texts:
        anchors = database.search_entries(latest_user_text, 'ANCHOR', limit=4)
        anchor_texts = [a["content"] for a in anchors]
    if not journal_texts:
        journals = database.search_entries(latest_user_text, 'JOURNAL', limit=4)
        journal_texts = [j["content"] for j in journals]

    # Fetch User Profile
    user_profile = database.get_profile()

    response_text = llm_service.generate_chat_response(
        history_dicts,
        context=anchor_texts,
        journal_context=journal_texts,
        user_profile=user_profile,
    )

    # Split by delimiter to get multiple messages
    messages = [msg.strip() for msg in response_text.split("|||") if msg.strip()]

    return JSONResponse(content={"response": messages})


@app.post("/whatsapp")
async def whatsapp(request: WhatsAppRequest):
    """Adapter endpoint: lets OpenClaw (or any client) use EchoChambre chat over WhatsApp.

    Input: {"from": "+E164", "text": "..."}
    Output: {"messages": ["...", "..."]}

    Reliability goals (hackathon): respond fast; never hang.
    """

    import asyncio

    peer = request.from_.strip()
    text = request.text.strip()
    if not peer or not text:
        raise HTTPException(status_code=400, detail="'from' and 'text' are required")

    # Small-talk guard: don't drag heavy context into short pings like "hey".
    text_l = text.lower().strip()
    if len(text_l) < 10 and ("?" not in text_l) and text_l in {"hey", "hi", "hello", "yo", "sup"}:
        msg = "Hey. What's on your mind right now-do you want to vent, reflect, or make a decision?"
        try:
            database.add_conversation_message(peer, "assistant", msg)
        except Exception:
            pass
        return JSONResponse(content={"messages": [msg]})

    # Load last N turns for this peer (DB may be slow/unavailable on cold starts)
    try:
        convo = database.get_conversation(peer, limit=20)
        history_dicts = [{"role": m["role"], "content": m["content"]} for m in convo]
    except Exception:
        history_dicts = []

    # Append current user message
    history_dicts.append({"role": "user", "content": text})

    # Persist user message (best-effort)
    try:
        database.add_conversation_message(peer, "user", text)
    except Exception:
        pass

    # WhatsApp: prefer stable, low-latency retrieval.
    # Use FTS anchors; include journals only when the user message clearly calls for emotional/relationship context.
    try:
        anchors = database.search_entries(text, 'ANCHOR', limit=4)
        anchor_texts = [a["content"] for a in anchors]
    except Exception:
        anchor_texts = []

    # Journal gating (avoid dragging unrelated recency like "Ashish" into a neutral planning message)
    journal_texts = []
    try:
        text_l = text.lower()
        journal_triggers = [
            "ashish", "breakup", "heart", "hurt", "betray", "promise", "relationship", "love", "anx", "anxiety",
            "sad", "depressed", "panic", "overwhelmed", "stress", "stressed",
        ]
        if any(t in text_l for t in journal_triggers):
            journals = database.search_entries(text, 'JOURNAL', limit=3)
            journal_texts = [j["content"] for j in journals]
    except Exception:
        journal_texts = []

    try:
        user_profile = database.get_profile()
    except Exception:
        user_profile = {}

    async def _gen():
        return await asyncio.to_thread(
            llm_service.generate_chat_response,
            history_dicts,
            context=anchor_texts,
            journal_context=journal_texts,
            user_profile=user_profile,
        )

    try:
        # Hard timeout so OpenClaw doesn't hang waiting on Vercel cold start / LLM latency.
        response_text = await asyncio.wait_for(_gen(), timeout=20.0)
        messages = [msg.strip() for msg in response_text.split("|||") if msg.strip()]
        if not messages:
            messages = ["I'm here. Can you say that again?"]
    except asyncio.TimeoutError:
        messages = ["I'm here with you-give me a few seconds, then send that again."]
    except Exception:
        messages = ["Something glitched on my side. Try again in a minute."]

    # Persist assistant messages
    for msg in messages:
        database.add_conversation_message(peer, "assistant", msg)

    return JSONResponse(content={"messages": messages})
