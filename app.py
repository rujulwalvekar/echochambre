from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import database
import llm_service
from typing import List
import os

app = FastAPI(title="The Echo Chamber")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup_event():
    database.init_db()


# --- Models ---

class IngestRequest(BaseModel):
    content: str
    source: str = "web"

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


# --- Pages ---

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


@app.get("/health")
async def health():
    return {"ok": True}


# --- API ---

@app.get("/api/brain")
async def get_brain_data():
    entries = database.get_recent_entries("ALL", limit=50)
    profile = database.get_profile()
    return JSONResponse(content={"entries": entries, "profile": profile})


@app.post("/api/ingest")
async def ingest(data: IngestRequest):
    """Frontend-agnostic ingestion. Any source can POST thoughts here."""
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # 1. Classify + analyze
    analysis = llm_service.analyze_entry(data.content)
    entry_type = analysis.get("type", "JOURNAL")
    summary = analysis.get("summary", data.content)

    # 2. Generate embedding
    embedding = llm_service.get_embedding(data.content)

    # 3. Store with embedding and source
    database.add_entry(
        data.content, entry_type, metadata=analysis,
        embedding=embedding if embedding else None,
        source=data.source
    )

    # 4. Profile update every 5 entries
    try:
        entry_count = database.get_entry_count()
        if entry_count % 5 == 0:
            current_profile = database.get_profile()
            recent_entries = database.get_recent_entries("ALL", limit=10)
            recent_text = "\n".join([e['content'] for e in recent_entries])
            updated_profile = llm_service.analyze_profile(recent_text, current_profile)
            database.update_profile(updated_profile)
            print(f"Profile updated at entry #{entry_count}")
    except Exception as e:
        print(f"Profile update failed: {e}")

    return JSONResponse(content={
        "status": "success",
        "type": entry_type,
        "summary": summary,
        "analysis": analysis
    })


@app.post("/voice-input")
async def process_voice_input(data: IngestRequest):
    """Backward-compatible wrapper for the web frontend."""
    data.source = "voice"
    return await ingest(data)


@app.post("/anchors")
async def create_anchor(anchor: AnchorRequest):
    if not anchor.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    embedding = llm_service.get_embedding(anchor.content)
    database.add_entry(anchor.content, 'ANCHOR', embedding=embedding if embedding else None)

    anchors = database.get_recent_anchors()
    return JSONResponse(content={"anchors": anchors})


@app.post("/hope")
async def find_hope(hope: HopeRequest):
    random_anchors = database.get_random_anchors(limit=5)
    response_text = llm_service.generate_hope(
        trigger=hope.trigger,
        feeling=hope.feeling,
        fear=hope.fear,
        anchors=random_anchors
    )
    return JSONResponse(content={"response": response_text})


@app.post("/chat")
async def chat(request: ChatRequest):
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.history]

    # Get the latest user message for semantic search
    latest_user_text = ""
    for msg in reversed(history_dicts):
        if msg["role"] == "user":
            latest_user_text = msg["content"]
            break

    # Vector similarity search for relevant context
    if latest_user_text:
        query_embedding = llm_service.get_embedding(latest_user_text)
        if query_embedding:
            relevant_anchors = database.search_entries_vector(query_embedding, 'ANCHOR', limit=4)
            relevant_journals = database.search_entries_vector(query_embedding, 'JOURNAL', limit=4)
        else:
            relevant_anchors = database.get_recent_entries('ANCHOR', limit=3)
            relevant_journals = database.get_recent_entries('JOURNAL', limit=3)
    else:
        relevant_anchors = database.get_recent_entries('ANCHOR', limit=3)
        relevant_journals = database.get_recent_entries('JOURNAL', limit=3)

    anchor_texts = [a["content"] for a in relevant_anchors]
    journal_texts = [j["content"] for j in relevant_journals]
    user_profile = database.get_profile()

    response_text = llm_service.generate_chat_response(
        history_dicts,
        context=anchor_texts,
        journal_context=journal_texts,
        user_profile=user_profile
    )

    messages = [msg.strip() for msg in response_text.split("|||") if msg.strip()]

    # Persist conversation
    try:
        database.add_conversation_message("web", "user", latest_user_text)
        for msg in messages:
            database.add_conversation_message("web", "assistant", msg)
    except Exception as e:
        print(f"Conversation persistence failed: {e}")

    return JSONResponse(content={"response": messages})
