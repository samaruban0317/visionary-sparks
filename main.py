import os
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from supabase import create_client, Client
from fastapi.responses import HTMLResponse, StreamingResponse
from typing import List
import json
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
db_admin: Client = create_client(SUPABASE_URL, SERVICE_KEY) if SERVICE_KEY else db

USERNAME_RE = re.compile(r'^[a-z0-9_]{3,20}$')

def compute_age_band(age):
    """Map a real age to the existing cache-compatible age_band buckets.
    Must NEVER change once data exists — these values seed the shared cache key."""
    try:
        a = int(age)
    except (TypeError, ValueError):
        return "college"
    if a <= 14:
        return "u15"
    if a <= 18:
        return "u18"
    if a <= 22:
        return "college"
    return "pro"


# ============================================================
# ROADMAP GENERATION (uses a dedicated Gemini key: GEMINI_KEY_ROADMAP)
# ============================================================
# Falls back to GEMINI_API_KEY if the dedicated key isn't set (e.g. local dev).
ROADMAP_KEY = os.getenv("GEMINI_KEY_ROADMAP") or os.getenv("GEMINI_API_KEY")
roadmap_client = genai.Client(api_key=ROADMAP_KEY)


def require_user(authorization):
    """Validate the Supabase bearer token and return the user_id (str)."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return str(user_response.user.id)


def _extract_json(text):
    """Pull a JSON object out of an LLM response (tolerates ``` fences / prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text).strip()
    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def generate_roadmap_content(profile, title, detail, horizon):
    """One Gemini call → a structured, personalized roadmap (dict for the jsonb column)."""
    age_band  = profile.get("age_band",  "college")
    level     = profile.get("level",     "beginner")
    archetype = profile.get("archetype", "Grinder")
    horizon_word = "long-term (spanning several months)" if horizon == "long" else "short-term (the next few weeks)"

    prompt = (
        "You are a roadmap architect for a student learning app. "
        f"Design a {horizon_word} learning roadmap for this goal: '{title}'. "
        f"Extra context from the student: '{detail or 'none'}'. "
        f"Student profile — age_band: {age_band}, level: {level}, archetype: {archetype}. "
        "Archetype tone — Grinder: disciplined/exam-focused; Innovator: build-by-doing; Dreamer: big-picture long-game. "
        "Return STRICT JSON ONLY (no markdown, no commentary) with this exact shape:\n"
        '{"summary": "one motivating sentence", '
        '"milestones": [{"title": "short milestone name", "timeframe": "e.g. Weeks 1-2", '
        '"focus": "what they build/learn here", "tasks": ["concrete task", "concrete task", "concrete task"], '
        '"resources": ["a specific resource or two"]}]}\n'
        "Make 4 to 6 milestones, ordered from start to goal. Keep every task concrete and doable. "
        "Tune the depth and vocabulary to the student's level."
    )
    resp = roadmap_client.models.generate_content(
        model="gemini-3.1-flash-lite", contents=prompt
    )
    return _extract_json(resp.text.strip())


def _profile_for(user_id):
    res = db_admin.table("user_profiles").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else {}


# ============================================================
# XP ECONOMY (server-authoritative — all XP flows through xp_events)
# ============================================================
IST = timezone(timedelta(hours=5, minutes=30))   # day boundary = midnight IST

# event_type -> (amount, daily cap). cap None = no daily limit.
XP_RULES = {
    "daily_login":   {"amount": 10,  "cap": 1},
    "active_30min":  {"amount": 15,  "cap": 1},
    "task_done":     {"amount": 20,  "cap": 5},
    "reflection":    {"amount": 30,  "cap": 2},
    "quest_cleared": {"amount": 50,  "cap": None},
    "streak_7":      {"amount": 100, "cap": None},
}
DAILY_TASK_COUNT = 3   # tasks surfaced from the roadmap each day

HEARTBEAT_PINGS_NEEDED = 6      # 6 pings * ~5 min = ~30 min active
HEARTBEAT_MIN_GAP_SEC  = 240    # a ping only counts if >4 min since the last one


def _ist_today():
    return datetime.now(IST).date()


def _ist_today_start_iso():
    start_ist = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    return start_ist.astimezone(timezone.utc).isoformat()


def _parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def count_events_today(user_id, event_type):
    start = _ist_today_start_iso()
    r = (db_admin.table("xp_events").select("id")
         .eq("user_id", user_id).eq("event_type", event_type)
         .gte("created_at", start).execute())
    return len(r.data or [])


def award_xp(user_id, event_type, amount, meta=None):
    """Append to the ledger and keep the user_profiles.total_xp mirror in sync."""
    db_admin.table("xp_events").insert({
        "user_id": user_id, "event_type": event_type, "amount": amount, "meta": meta or {}
    }).execute()
    cur = db_admin.table("user_profiles").select("total_xp").eq("user_id", user_id).execute()
    if cur.data:
        new_total = (cur.data[0]["total_xp"] or 0) + amount
        db_admin.table("user_profiles").update({"total_xp": new_total}).eq("user_id", user_id).execute()


def try_award(user_id, event_type, meta=None):
    """Award XP if the daily cap hasn't been hit. Returns a result dict."""
    rule = XP_RULES[event_type]
    if rule["cap"] is not None and count_events_today(user_id, event_type) >= rule["cap"]:
        return {"awarded": False, "amount": 0, "event": event_type, "reason": "daily_cap"}
    award_xp(user_id, event_type, rule["amount"], meta)
    return {"awarded": True, "amount": rule["amount"], "event": event_type}


def compute_login_streak(user_id):
    """Consecutive days (IST) ending today that have a daily_login event."""
    since = (datetime.now(IST) - timedelta(days=120)).astimezone(timezone.utc).isoformat()
    r = (db_admin.table("xp_events").select("created_at")
         .eq("user_id", user_id).eq("event_type", "daily_login")
         .gte("created_at", since).execute())
    days = {_parse_ts(row["created_at"]).astimezone(IST).date() for row in (r.data or [])}
    today, streak, d = _ist_today(), 0, _ist_today()
    while d in days:
        streak += 1
        d -= timedelta(days=1)
    return streak


# ---- Daily tasks: turn a roadmap into today's checkboxes ----

def _flatten_roadmap_tasks(content):
    """Ordered list of task strings across all milestones."""
    tasks = []
    for m in (content or {}).get("milestones", []):
        for t in m.get("tasks", []):
            if isinstance(t, str) and t.strip():
                tasks.append(t.strip())
    return tasks


def ensure_today_tasks(user_id):
    """Idempotently materialize today's daily tasks from the user's active roadmap.
    Walks through the roadmap over days; recycles from the start once exhausted."""
    today = _ist_today().isoformat()
    existing = (db_admin.table("daily_tasks").select("*")
                .eq("user_id", user_id).eq("task_date", today)
                .order("created_at").execute()).data or []
    if existing:
        return existing

    # Most recent active goal → its latest roadmap
    goals = (db_admin.table("goals").select("id")
             .eq("user_id", user_id).eq("status", "active")
             .order("created_at", desc=True).limit(1).execute()).data
    if not goals:
        return []
    goal_id = goals[0]["id"]
    rm = (db_admin.table("roadmaps").select("id,content")
          .eq("goal_id", goal_id).order("version", desc=True).limit(1).execute()).data
    if not rm:
        return []
    roadmap_id, content = rm[0]["id"], rm[0]["content"]

    flat = _flatten_roadmap_tasks(content)
    if not flat:
        return []

    used = {row["title"] for row in (db_admin.table("daily_tasks").select("title")
            .eq("user_id", user_id).eq("roadmap_id", roadmap_id).execute()).data or []}
    pool = [t for t in flat if t not in used] or flat   # recycle if exhausted
    picks = pool[:DAILY_TASK_COUNT]

    rows = [{"user_id": user_id, "roadmap_id": roadmap_id, "task_date": today, "title": t} for t in picks]
    inserted = db_admin.table("daily_tasks").insert(rows).execute().data
    return inserted or []


class StudentRequest(BaseModel):
    raw_prompt: str
    subject: str

@app.post("/bouncer")
def process_incoming_prompt(request: StudentRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = str(user_response.user.id)

    # Fetch the user's real profile; fall back to safe defaults if onboarding isn't done yet
    profile_result = db_admin.table("user_profiles").select("*").eq("user_id", user_id).execute()
    p        = profile_result.data[0] if profile_result.data else {}
    age_band = p.get("age_band",     "college")
    goal     = p.get("current_goal", "general")
    level    = p.get("level",        "beginner")
    archetype = p.get("archetype",   "Grinder")

    if not request.raw_prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    print(f"\n📥 Incoming request from: {user_id}")

    # --- LAYER 1: AI BOUNCER ---
    bouncer_instructions = (
        "You are an AI Bouncer. Read the student message, clean out conversational fluff, "
        "and extract ONLY the core academic question.\n"
        "Classify as 'LOCAL' (greetings/small talk) or 'CACHE' (real study topics).\n"
        "Format: ROUTE | CLEAN_QUESTION\n"
        f"Message: '{request.raw_prompt}'"
    )

    try:
        bouncer_response = ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=bouncer_instructions
        )
        ai_decision = bouncer_response.text.strip()
        if "|" in ai_decision:
            route, clean_text = ai_decision.split("|", 1)
            route      = route.strip()
            clean_text = clean_text.strip().lower()
        else:
            route      = "CACHE"
            clean_text = request.raw_prompt.lower()
    except Exception as e:
        print(f"⚠️ Bouncer Error: {e}")
        route      = "CACHE"
        clean_text = request.raw_prompt.lower()

    if "LOCAL" in route:
        return {
            "route": "LOCAL_RESPONSE",
            "message": "Hey there! Ready to dominate your study session? What topic are we cracking open today?"
        }

    # Normalize and build the segmented cache key
    normalized = re.sub(r'[^a-z0-9 ]', '', clean_text).strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    cache_key  = f"{age_band}|{goal}|{level}|{request.subject}|{normalized}"

    # --- LAYER 2: CACHE CHECK ---
    print(f"🔍 Searching cache for: '{cache_key}'")
    db_response = db.table("mega_cache").select("*").eq("question", cache_key).execute()

    if db_response.data:
        print("⚡ CACHE HIT!")
        return {"route": "SERVED_FROM_CACHE", "message": db_response.data[0]["answer"]}

    # --- LAYER 3: GEMINI GENERATION ---
    print("❌ CACHE MISS! Generating from Gemini...")
    teacher_instructions = (
        f"You are Astra, a personalized AI tutor. "
        f"Student profile: age_band={age_band}, goal={goal}, level={level}, archetype={archetype}. "
        f"Archetype tone — Grinder: sharp, disciplined, exam-focused; "
        f"Innovator: curious, builder examples; Dreamer: big-picture, long-game framing. "
        f"CRITICAL RULES: Never introduce yourself. Never say 'I am Astra' or 'Hello, I am'. "
        f"Jump DIRECTLY to the answer in the first sentence. Keep response under 200 words. "
        f"Subject: {request.subject}. "
        f"Explain this concept for a {level} {age_band} student: '{normalized}'. "
        "Tune vocabulary depth and analogies to their level. Use bolding and bullet points."
    )
    try:
        core_response = ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=teacher_instructions
        )
        generated_answer = core_response.text.strip()
        db.table("mega_cache").insert({"question": cache_key, "answer": generated_answer}).execute()
        return {"route": "GENERATED_NEW_RESPONSE", "message": generated_answer}
    except Exception as e:
        print(f"⚠️ Google API Error: {e}")
        return {
            "route": "LOCAL_RESPONSE",
            "message": "Whoa there! Astra is currently helping a lot of students right now. Take a deep breath and try again in 60 seconds."
        }

# --- THE GAMIFICATION ENGINE ---

class MissionRequest(BaseModel):
    career: str
    subject: str

@app.post("/mission")
def generate_mission(request: MissionRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = str(user_response.user.id)

    profile_result = db_admin.table("user_profiles").select("*").eq("user_id", user_id).execute()
    p        = profile_result.data[0] if profile_result.data else {}
    age_band = p.get("age_band", "college")
    level    = p.get("level",    "beginner")

    print(f"\n🎮 Generating {request.career} mission for {user_id}...")

    game_master_prompt = (
        f"You are a Game Master for an educational RPG. "
        f"The player is a {age_band} student aspiring to be a {request.career}. "
        f"Generate a thrilling, action-packed 3-sentence story scenario where they must use {request.subject} to succeed. "
        f"Match difficulty to their level: {level}. "
        "End the story with a specific, solvable academic question.\n\n"
        "You MUST format your response EXACTLY like this: STORY | QUESTION\n"
        "Example: The bank robber is escaping in a red sports car traveling at 100km/h. You are 50km behind him in the police cruiser. | How many hours will it take to catch him?"
    )

    try:
        response = ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=game_master_prompt
        )
        ai_text = response.text.strip()
        if "|" in ai_text:
            story, question = ai_text.split("|", 1)
        else:
            story    = ai_text
            question = "Solve the problem to advance!"
        return {
            "status": "success",
            "career": request.career,
            "story":  story.strip(),
            "puzzle": question.strip()
        }
    except Exception as e:
        print(f"⚠️ Game Master Error: {e}")
        return {"status": "error", "message": "The criminals jammed our radio! Try requesting the mission again in 60 seconds."}

class MissionSolveRequest(BaseModel):
    puzzle: str
    student_answer: str

@app.post("/solve_mission")
def solve_mission(request: MissionSolveRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = str(user_response.user.id)

    print(f"\n🕵️ Evaluating answer from {user_id}...")

    eval_prompt = (
        f"You are the Game Master. You previously gave the student this puzzle: '{request.puzzle}'.\n"
        f"The student answered: '{request.student_answer}'.\n"
        "Evaluate if their math/logic is correct. Be encouraging!\n"
        "You MUST format your response EXACTLY like this: CORRECT | Your explanation OR INCORRECT | Your explanation."
    )

    try:
        response = ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=eval_prompt
        )
        ai_text = response.text.strip()
        if "|" in ai_text:
            status, feedback = ai_text.split("|", 1)
        else:
            status   = "UNKNOWN"
            feedback = ai_text

        is_correct = "CORRECT" in status.upper() and "INCORRECT" not in status.upper()

        # Award quest XP through the ledger (same +50 from the user's view).
        # Wrapped in its own try/except so a DB hiccup never fails the grading response.
        xp_gain = 0
        if is_correct:
            try:
                res = try_award(user_id, "quest_cleared", {"puzzle": request.puzzle[:200]})
                xp_gain = res["amount"]
                print(f"⭐ +{xp_gain} XP (quest_cleared) for {user_id}")
            except Exception as xp_err:
                print(f"⚠️ XP award failed (non-critical): {xp_err}")

        return {
            "status":     "success",
            "is_correct": is_correct,
            "feedback":   feedback.strip(),
            "xp_gain":    xp_gain
        }
    except Exception as e:
        print(f"⚠️ Grading Error: {e}")
        return {"status": "error", "message": "The grading system is offline. Wait 60 seconds and try again."}

    # --- GOALS + ROADMAPS ---

class GoalCreate(BaseModel):
    title: str
    detail: str | None = None
    horizon: str = "long"            # 'long' or 'short'
    target_date: str | None = None   # ISO date string, optional


def _latest_roadmap(goal_id):
    rows = (db_admin.table("roadmaps").select("*")
            .eq("goal_id", goal_id).order("version", desc=True).limit(1).execute()).data
    return rows[0] if rows else None


def _save_roadmap(user_id, goal, version):
    """Generate + persist a roadmap version for a goal. Returns the stored row."""
    profile = _profile_for(user_id)
    content = generate_roadmap_content(profile, goal["title"], goal.get("detail"), goal["horizon"])
    review_at = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    row = {
        "user_id": user_id,
        "goal_id": goal["id"],
        "horizon": goal["horizon"],
        "content": content,
        "version": version,
        "next_review_at": review_at,
    }
    return db_admin.table("roadmaps").insert(row).execute().data[0]


@app.post("/goals/create")
def create_goal(body: GoalCreate, authorization: str = Header(None)):
    """Declare a goal → store it → generate version 1 of its roadmap (one Gemini call)."""
    user_id = require_user(authorization)
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Goal title is required.")
    if body.horizon not in ("long", "short"):
        raise HTTPException(status_code=400, detail="horizon must be 'long' or 'short'.")

    goal_row = {
        "user_id": user_id,
        "horizon": body.horizon,
        "title": body.title.strip(),
        "detail": (body.detail or "").strip() or None,
        "status": "active",
    }
    if body.target_date:
        goal_row["target_date"] = body.target_date
    goal = db_admin.table("goals").insert(goal_row).execute().data[0]

    try:
        roadmap = _save_roadmap(user_id, goal, version=1)
    except Exception as e:
        print(f"⚠️ Roadmap generation failed: {e}")
        # Goal is saved; the user can retry generation without re-creating the goal.
        return {"goal": goal, "roadmap": None,
                "warning": "Goal saved, but the roadmap couldn't be generated. Try regenerating."}
    return {"goal": goal, "roadmap": roadmap}


@app.get("/goals")
def list_goals(authorization: str = Header(None)):
    """All of the user's goals, each with its latest roadmap version."""
    user_id = require_user(authorization)
    goals = (db_admin.table("goals").select("*")
             .eq("user_id", user_id).order("created_at", desc=True).execute()).data or []
    return {"goals": [{**g, "roadmap": _latest_roadmap(g["id"])} for g in goals]}


class RoadmapRegen(BaseModel):
    goal_id: str

@app.post("/roadmap/regenerate")
def regenerate_roadmap(body: RoadmapRegen, authorization: str = Header(None)):
    """Generate a fresh, version-incremented roadmap for an existing goal."""
    user_id = require_user(authorization)
    g = (db_admin.table("goals").select("*")
         .eq("id", body.goal_id).eq("user_id", user_id).execute()).data
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found.")
    goal = g[0]
    last = _latest_roadmap(goal["id"])
    next_version = (last["version"] + 1) if last else 1
    try:
        roadmap = _save_roadmap(user_id, goal, version=next_version)
    except Exception as e:
        print(f"⚠️ Roadmap regeneration failed: {e}")
        raise HTTPException(status_code=502, detail="Roadmap generation failed. Try again in a moment.")
    return {"roadmap": roadmap}


class GoalStatus(BaseModel):
    goal_id: str
    status: str   # 'active' | 'paused' | 'done'

@app.post("/goals/status")
def update_goal_status(body: GoalStatus, authorization: str = Header(None)):
    """Pause, resume, or complete a goal."""
    user_id = require_user(authorization)
    if body.status not in ("active", "paused", "done"):
        raise HTTPException(status_code=400, detail="Invalid status.")
    res = (db_admin.table("goals").update({"status": body.status})
           .eq("id", body.goal_id).eq("user_id", user_id).execute())
    if not res.data:
        raise HTTPException(status_code=404, detail="Goal not found.")
    return {"status": "success", "goal": res.data[0]}

    # --- DAILY TASKS + XP (the consistency loop) ---

@app.get("/tasks/today")
def tasks_today(authorization: str = Header(None)):
    """Today's checkboxes, lazily materialized from the active roadmap."""
    user_id = require_user(authorization)
    tasks = ensure_today_tasks(user_id)
    done = sum(1 for t in tasks if t["done"])
    return {
        "date": _ist_today().isoformat(),
        "tasks": tasks,
        "done": done,
        "total": len(tasks),
        "has_roadmap": len(tasks) > 0,
    }


class TaskToggle(BaseModel):
    task_id: str
    done: bool

@app.post("/tasks/toggle")
def toggle_task(body: TaskToggle, authorization: str = Header(None)):
    """Check/uncheck a task. XP is awarded once per task (first completion),
    capped server-side; unchecking never claws XP back."""
    user_id = require_user(authorization)
    rows = (db_admin.table("daily_tasks").select("*")
            .eq("id", body.task_id).eq("user_id", user_id).execute()).data
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found.")
    task = rows[0]

    update = {"done": body.done}
    xp = {"awarded": False, "amount": 0, "event": "task_done"}

    # Award only on the first time a task is completed, and only under the daily cap.
    if body.done and not task["xp_awarded"]:
        xp = try_award(user_id, "task_done", {"task_id": body.task_id})
        if xp["awarded"]:
            update["xp_awarded"] = True

    db_admin.table("daily_tasks").update(update).eq("id", body.task_id).execute()
    return {"status": "success", "task_id": body.task_id, "done": body.done, "xp": xp}


@app.post("/xp/login-bonus")
def xp_login_bonus(authorization: str = Header(None)):
    """Daily login XP (idempotent per day) + auto streak_7 bonus on multiples of 7."""
    user_id = require_user(authorization)
    result = try_award(user_id, "daily_login")

    streak = compute_login_streak(user_id)
    bonus = None
    if streak > 0 and streak % 7 == 0 and count_events_today(user_id, "streak_7") == 0:
        award_xp(user_id, "streak_7", XP_RULES["streak_7"]["amount"], {"streak": streak})
        bonus = {"awarded": True, "amount": XP_RULES["streak_7"]["amount"], "streak": streak}

    return {**result, "streak": streak, "streak_bonus": bonus}


@app.post("/xp/heartbeat")
def xp_heartbeat(authorization: str = Header(None)):
    """Frontend pings ~every 5 min while the tab is visible. After 6 spaced
    pings in a day (~30 min) we award active_30min once."""
    user_id = require_user(authorization)

    if count_events_today(user_id, "active_30min") >= 1:
        return {"awarded": False, "event": "active_30min", "pings": HEARTBEAT_PINGS_NEEDED, "capped": True}

    start = _ist_today_start_iso()
    pings = (db_admin.table("xp_events").select("created_at")
             .eq("user_id", user_id).eq("event_type", "heartbeat_ping")
             .gte("created_at", start).order("created_at", desc=True).execute())
    data = pings.data or []
    count = len(data)
    now = datetime.now(timezone.utc)

    # Anti-gaming: ignore pings that arrive faster than the minimum gap.
    if data and (now - _parse_ts(data[0]["created_at"])).total_seconds() < HEARTBEAT_MIN_GAP_SEC:
        return {"awarded": False, "event": "active_30min", "pings": count, "throttled": True}

    db_admin.table("xp_events").insert(
        {"user_id": user_id, "event_type": "heartbeat_ping", "amount": 0, "meta": {}}
    ).execute()
    count += 1

    if count >= HEARTBEAT_PINGS_NEEDED:
        res = try_award(user_id, "active_30min")
        return {**res, "pings": count}
    return {"awarded": False, "event": "active_30min", "pings": count}


class ReflectionRequest(BaseModel):
    text: str

@app.post("/reflect")
def add_reflection(body: ReflectionRequest, authorization: str = Header(None)):
    """Journal entry → +30 XP (max 2/day). The text is kept on the ledger event."""
    user_id = require_user(authorization)
    text = (body.text or "").strip()
    if len(text) < 10:
        raise HTTPException(status_code=400, detail="Write at least a sentence (10+ characters).")
    text = text[:2000]
    res = try_award(user_id, "reflection", {"text": text})
    return {**res, "saved": True}


@app.get("/reflections")
def list_reflections(authorization: str = Header(None)):
    """Recent journal entries (from the XP ledger), newest first."""
    user_id = require_user(authorization)
    rows = (db_admin.table("xp_events").select("created_at,meta")
            .eq("user_id", user_id).eq("event_type", "reflection")
            .order("created_at", desc=True).limit(20).execute()).data or []
    return {"reflections": [
        {"created_at": r["created_at"], "text": (r.get("meta") or {}).get("text", "")}
        for r in rows
    ]}


@app.get("/xp/summary")
def xp_summary(authorization: str = Header(None)):
    """Total XP (sum of ledger via mirror), today's earned XP, streak, and
    remaining daily opportunities — the dopamine loop."""
    user_id = require_user(authorization)

    prof = db_admin.table("user_profiles").select("total_xp").eq("user_id", user_id).execute()
    total_xp = (prof.data[0]["total_xp"] if prof.data else 0) or 0

    start = _ist_today_start_iso()
    today_rows = (db_admin.table("xp_events").select("amount,event_type")
                  .eq("user_id", user_id).gte("created_at", start).execute()).data or []
    today_earned = sum(r["amount"] for r in today_rows)

    used = {}
    for r in today_rows:
        if r["amount"] > 0:
            used[r["event_type"]] = used.get(r["event_type"], 0) + 1

    opportunities, remaining_points = [], 0
    def add_opp(event, label):
        nonlocal remaining_points
        rule = XP_RULES[event]
        cap = rule["cap"] or 1
        left = max(0, cap - used.get(event, 0))
        if left > 0:
            pts = rule["amount"] * left
            remaining_points += pts
            opportunities.append({"event": event, "remaining": left, "points": pts, "label": label(left, pts, rule["amount"])})

    add_opp("daily_login",  lambda n, p, a: f"Open the app today for +{a}")
    add_opp("active_30min", lambda n, p, a: f"Stay active 30 min for +{a}")
    add_opp("task_done",    lambda n, p, a: f"Check {n} more task{'s' if n > 1 else ''} for +{p}")
    add_opp("reflection",   lambda n, p, a: f"Log {n} reflection{'s' if n > 1 else ''} for +{p}")

    return {
        "total_xp": total_xp,
        "today_earned": today_earned,
        "today_remaining_points": remaining_points,
        "streak": compute_login_streak(user_id),
        "opportunities": opportunities,
    }

    # --- CONVERSATIONS + MESSAGES (chat history) ---

def _own_conversation(user_id, conversation_id):
    rows = (db_admin.table("conversations").select("*")
            .eq("id", conversation_id).eq("user_id", user_id).execute()).data
    if not rows:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return rows[0]


class ConversationCreate(BaseModel):
    title: str | None = None

@app.post("/conversations")
def create_conversation(body: ConversationCreate, authorization: str = Header(None)):
    user_id = require_user(authorization)
    row = {"user_id": user_id}
    if body.title and body.title.strip():
        row["title"] = body.title.strip()[:120]
    return db_admin.table("conversations").insert(row).execute().data[0]


@app.get("/conversations")
def list_conversations(authorization: str = Header(None)):
    user_id = require_user(authorization)
    rows = (db_admin.table("conversations").select("*")
            .eq("user_id", user_id).order("created_at", desc=True).limit(50).execute()).data or []
    return {"conversations": rows}


@app.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, authorization: str = Header(None)):
    user_id = require_user(authorization)
    _own_conversation(user_id, conversation_id)
    rows = (db_admin.table("messages").select("*")
            .eq("conversation_id", conversation_id).order("created_at").execute()).data or []
    return {"messages": rows}


class MessageCreate(BaseModel):
    role: str        # 'user' | 'assistant'
    content: str

@app.post("/conversations/{conversation_id}/messages")
def add_message(conversation_id: str, body: MessageCreate, authorization: str = Header(None)):
    user_id = require_user(authorization)
    convo = _own_conversation(user_id, conversation_id)
    if body.role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'assistant'.")
    msg = (db_admin.table("messages").insert({
        "conversation_id": conversation_id,
        "role": body.role,
        "content": (body.content or "")[:8000],
    }).execute()).data[0]
    # Auto-title the conversation from the first user message.
    if body.role == "user" and convo.get("title") in (None, "", "New chat"):
        title = (body.content or "").strip().replace("\n", " ")[:48] or "New chat"
        db_admin.table("conversations").update({"title": title}).eq("id", conversation_id).execute()
    return msg


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, authorization: str = Header(None)):
    user_id = require_user(authorization)
    _own_conversation(user_id, conversation_id)
    db_admin.table("conversations").delete().eq("id", conversation_id).eq("user_id", user_id).execute()
    return {"status": "success"}


    # --- USER MEMORY (facts Astra remembers) ---

@app.get("/memory")
def get_memory(authorization: str = Header(None)):
    user_id = require_user(authorization)
    rows = (db_admin.table("user_memory").select("*")
            .eq("user_id", user_id).order("created_at", desc=True).execute()).data or []
    return {"memory": rows}


class MemoryAdd(BaseModel):
    fact: str

@app.post("/memory")
def add_memory(body: MemoryAdd, authorization: str = Header(None)):
    user_id = require_user(authorization)
    fact = (body.fact or "").strip()[:300]
    if not fact:
        raise HTTPException(status_code=400, detail="Fact cannot be empty.")
    return (db_admin.table("user_memory")
            .insert({"user_id": user_id, "fact": fact, "source": "manual"}).execute()).data[0]


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str, authorization: str = Header(None)):
    user_id = require_user(authorization)
    db_admin.table("user_memory").delete().eq("id", memory_id).eq("user_id", user_id).execute()
    return {"status": "success"}


class MemoryExtract(BaseModel):
    conversation_id: str

@app.post("/memory/extract")
def extract_memory(body: MemoryExtract, authorization: str = Header(None)):
    """One Gemini call over a conversation → durable facts about the student,
    deduped into user_memory. Triggered sparingly by the client (e.g. on New chat)."""
    user_id = require_user(authorization)
    _own_conversation(user_id, body.conversation_id)

    msgs = (db_admin.table("messages").select("role,content")
            .eq("conversation_id", body.conversation_id).order("created_at").execute()).data or []
    if len(msgs) < 2:
        return {"added": 0, "facts": []}

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in msgs[-20:])[:6000]
    existing = {r["fact"].lower() for r in
                (db_admin.table("user_memory").select("fact").eq("user_id", user_id).execute()).data or []}

    prompt = (
        "Extract durable, useful facts about the STUDENT from this conversation — "
        "their goals, level, interests, recurring struggles, and preferences. "
        "Ignore one-off question content and anything not lasting. "
        'Return STRICT JSON ONLY: {"facts": ["short fact", ...]} with at most 5 concise facts '
        '(each a short sentence). If nothing durable, return {"facts": []}.\n\n'
        f"Conversation:\n{transcript}"
    )
    try:
        resp = ai_client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        facts = _extract_json(resp.text.strip()).get("facts", [])
    except Exception as e:
        print(f"⚠️ Memory extraction failed: {e}")
        raise HTTPException(status_code=502, detail="Memory extraction failed.")

    added = []
    for f in facts:
        f = str(f).strip()[:300]
        if f and f.lower() not in existing:
            db_admin.table("user_memory").insert({"user_id": user_id, "fact": f, "source": "chat"}).execute()
            existing.add(f.lower())
            added.append(f)
    return {"added": len(added), "facts": added}

    # --- ASTRA CHAT (personalized, memory-aware, NON-cached) ---

class AstraChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

@app.post("/astra/chat")
def astra_chat(body: AstraChatRequest, authorization: str = Header(None)):
    """Conversational Astra that injects the user's profile, remembered facts,
    and recent message history. Always fresh — deliberately does NOT read or
    write the shared mega_cache (that cache is for /bouncer single questions)."""
    user_id = require_user(authorization)
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    msg = msg[:4000]

    profile   = _profile_for(user_id)
    age_band  = profile.get("age_band", "college")
    goal      = profile.get("current_goal", "general")
    level     = profile.get("level", "beginner")
    archetype = profile.get("archetype", "Grinder")
    name      = profile.get("display_name") or "there"

    # Resolve / create the conversation
    if body.conversation_id:
        convo = _own_conversation(user_id, body.conversation_id)
    else:
        convo = db_admin.table("conversations").insert({"user_id": user_id}).execute().data[0]
    conversation_id = convo["id"]

    # Recent history (before we add the new turn) + remembered facts
    history = (db_admin.table("messages").select("role,content")
               .eq("conversation_id", conversation_id)
               .order("created_at", desc=True).limit(8).execute()).data or []
    history = list(reversed(history))
    mem = (db_admin.table("user_memory").select("fact")
           .eq("user_id", user_id).order("created_at", desc=True).limit(12).execute()).data or []
    facts = [m["fact"] for m in mem]

    # Persist the user's message + auto-title the conversation
    db_admin.table("messages").insert(
        {"conversation_id": conversation_id, "role": "user", "content": msg}
    ).execute()
    if convo.get("title") in (None, "", "New chat"):
        db_admin.table("conversations").update(
            {"title": msg.replace("\n", " ")[:48] or "New chat"}
        ).eq("id", conversation_id).execute()

    mem_block = ("\nWhat you remember about this student:\n- " + "\n- ".join(facts)) if facts else ""
    hist_block = "".join(
        f"{'Student' if h['role'] == 'user' else 'Astra'}: {h['content']}\n" for h in history
    )

    prompt = (
        f"You are Astra, a personalized AI tutor and study companion for {name}. "
        f"Student profile: age_band={age_band}, goal={goal}, level={level}, archetype={archetype}. "
        "Archetype tone — Grinder: sharp, disciplined, exam-focused; "
        "Innovator: curious, builder examples; Dreamer: big-picture, long-game framing. "
        "Never introduce yourself or say 'I am Astra'. Use what you remember to make the reply feel "
        "continuous and personal, but don't list the facts back robotically. "
        "Be warm and concrete, tuned to their level. Keep replies under 220 words; use bold and bullets where useful."
        f"{mem_block}\n\n"
        f"Recent conversation:\n{hist_block}"
        f"Student: {msg}\nAstra:"
    )

    try:
        resp = ai_client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        answer = resp.text.strip()
    except Exception as e:
        print(f"⚠️ Astra chat error: {e}")
        return {"route": "ERROR", "conversation_id": conversation_id,
                "message": "Astra is helping a lot of students right now. Take a breath and try again in 60 seconds."}

    db_admin.table("messages").insert(
        {"conversation_id": conversation_id, "role": "assistant", "content": answer[:8000]}
    ).execute()
    return {"route": "ASTRA_MEMORY", "conversation_id": conversation_id, "message": answer}

    # --- USERNAME AUTH ---

@app.get("/auth/check-username")
def check_username(u: str = ""):
    """Validate format + uniqueness for signup. Returns availability."""
    uname = (u or "").strip().lower()
    if not USERNAME_RE.match(uname):
        return {
            "available": False,
            "valid": False,
            "reason": "Username must be 3-20 chars: lowercase letters, numbers, underscore."
        }
    existing = db_admin.table("user_profiles").select("user_id").eq("username", uname).execute()
    return {"available": not bool(existing.data), "valid": True}


class ResolveRequest(BaseModel):
    login: str

@app.post("/auth/resolve")
def resolve_login(request: ResolveRequest):
    """Given a username OR email, return the email to sign in with.
    If the input already contains '@', it's treated as an email and returned as-is."""
    raw = (request.login or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Login is required.")
    if "@" in raw:
        return {"email": raw}

    uname = raw.lower()
    prof = db_admin.table("user_profiles").select("user_id").eq("username", uname).execute()
    if not prof.data:
        raise HTTPException(status_code=404, detail="No account found for that username.")

    user_id = prof.data[0]["user_id"]
    try:
        user = db_admin.auth.admin.get_user_by_id(user_id)
        email = user.user.email
    except Exception as e:
        print(f"⚠️ resolve_login admin lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Could not resolve account.")
    if not email:
        raise HTTPException(status_code=404, detail="No email on file for that username.")
    return {"email": email}


class OnboardRequest(BaseModel):
    display_name: str
    username: str
    age: int
    current_goal: str = "general"
    archetype: str = "Grinder"
    level: str = "beginner"

@app.post("/onboard")
def onboard(request: OnboardRequest, authorization: str = Header(None)):
    """Create/complete a profile after signup. Computes age_band server-side
    from real age so the Astra cache key stays consistent."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = str(user_response.user.id)

    uname = (request.username or "").strip().lower()
    if not USERNAME_RE.match(uname):
        raise HTTPException(status_code=400, detail="Invalid username format.")
    if not (8 <= request.age <= 60):
        raise HTTPException(status_code=400, detail="Age must be between 8 and 60.")

    # Reject if the username is taken by someone else
    taken = db_admin.table("user_profiles").select("user_id").eq("username", uname).execute()
    if taken.data and str(taken.data[0]["user_id"]) != user_id:
        raise HTTPException(status_code=409, detail="Username already taken.")

    data = {
        "user_id": user_id,
        "display_name": request.display_name.strip() or "Cadet",
        "username": uname,
        "age": request.age,
        "age_band": compute_age_band(request.age),
        "current_goal": request.current_goal,
        "archetype": request.archetype,
        "level": request.level,
    }
    db_admin.table("user_profiles").upsert(data).execute()
    return {"status": "success", "age_band": data["age_band"]}

    # --- SERVE THE FRONTEND UI ---
@app.get("/")
def serve_home():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/index.html")
def serve_home_alias():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/login.html")
def serve_login():
    with open("login.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
    
class ProfileUpdate(BaseModel):
    display_name: str
    current_goal: str
    archetype: str
    age_band: str = "college"
    level: str = "beginner"
    age: int | None = None
    username: str | None = None

@app.get("/profile")
def get_profile(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
    
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Use db_admin to bypass RLS and read the profile
    result = db_admin.table("user_profiles").select("*").eq("user_id", user_response.user.id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found.")
        
    return result.data[0]

class ChatMessage(BaseModel):
    role: str
    content: str

class CareerChatRequest(BaseModel):
    messages: List[ChatMessage]

CAREER_SYSTEM_PROMPT = (
    "You are Classmate AI, a career and study roadmap assistant. "
    "Help students (teens, college, professionals) create actionable "
    "learning plans. Ask about their goal, current level, and time "
    "available. Give specific milestones, resources, and timelines. "
    "Keep responses under 150 words. Be encouraging and practical."
)

@app.post("/career-chat-public")
def career_chat_public(request: CareerChatRequest):
    contents = CAREER_SYSTEM_PROMPT + "\n\n"
    for msg in request.messages:
        role = "Student" if msg.role == "user" else "Classmate AI"
        contents += f"{role}: {msg.content}\n"
    contents += "Classmate AI:"

    def stream_response():
        try:
            for chunk in ai_client.models.generate_content_stream(
                model="gemini-3.1-flash-lite",
                contents=contents
            ):
                if chunk.text:
                    payload = json.dumps({"choices": [{"delta": {"content": chunk.text}}]})
                    yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")

@app.post("/update_profile")
def update_profile(profile: ProfileUpdate, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
        
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = str(user_response.user.id)
    data = {
        "user_id": user_id,
        "display_name": profile.display_name,
        "current_goal": profile.current_goal,
        "archetype": profile.archetype,
        "age_band": profile.age_band,
        "level": profile.level
    }

    # If a real age is supplied, recompute age_band server-side (cache compatibility)
    if profile.age is not None:
        if not (8 <= profile.age <= 60):
            raise HTTPException(status_code=400, detail="Age must be between 8 and 60.")
        data["age"] = profile.age
        data["age_band"] = compute_age_band(profile.age)

    # If a username is supplied, validate format + uniqueness
    if profile.username is not None and profile.username.strip():
        uname = profile.username.strip().lower()
        if not USERNAME_RE.match(uname):
            raise HTTPException(status_code=400, detail="Invalid username format.")
        taken = db_admin.table("user_profiles").select("user_id").eq("username", uname).execute()
        if taken.data and str(taken.data[0]["user_id"]) != user_id:
            raise HTTPException(status_code=409, detail="Username already taken.")
        data["username"] = uname

    # Use db_admin to bypass RLS and save the profile
    result = db_admin.table("user_profiles").upsert(data).execute()
    return {"status": "success"}