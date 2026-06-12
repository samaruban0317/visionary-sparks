import os
import re
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from supabase import create_client, Client
from fastapi.responses import HTMLResponse
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

        # Increment total_xp in DB on a correct answer.
        # Wrapped in its own try/except so a DB hiccup never fails the grading response.
        if is_correct:
            try:
                cur = db_admin.table("user_profiles").select("total_xp").eq("user_id", user_id).execute()
                if cur.data:
                    new_xp = cur.data[0]["total_xp"] + 50
                    db_admin.table("user_profiles").update({"total_xp": new_xp}).eq("user_id", user_id).execute()
                    print(f"⭐ XP → {new_xp} for {user_id}")
            except Exception as xp_err:
                print(f"⚠️ XP update failed (non-critical): {xp_err}")

        return {
            "status":     "success",
            "is_correct": is_correct,
            "feedback":   feedback.strip()
        }
    except Exception as e:
        print(f"⚠️ Grading Error: {e}")
        return {"status": "error", "message": "The grading system is offline. Wait 60 seconds and try again."}
    
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

@app.post("/update_profile")
def update_profile(profile: ProfileUpdate, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing auth token")
        
    token = authorization.replace("Bearer ", "")
    user_response = db.auth.get_user(token)
    
    if not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    data = {
        "user_id": user_response.user.id,
        "display_name": profile.display_name,
        "current_goal": profile.current_goal,
        "archetype": profile.archetype,
        "age_band": profile.age_band,
        "level": profile.level
    }
    
    # Use db_admin to bypass RLS and save the profile
    result = db_admin.table("user_profiles").upsert(data).execute()
    return {"status": "success"}