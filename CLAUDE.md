# CLAUDE.md — Classmate AI · Visionary Sparks
> Read every section before touching any file. This document IS the project brief.

---

## HOW TO START — READ THIS FIRST

Before any task, read these files in order:
1. `main.py` — the full FastAPI backend (endpoints, Gemini calls, Supabase queries)
2. `index2.html` — the new dashboard frontend (this is the target frontend)
3. `index.html` — the old simple frontend (reference only, shows how backend was called before)
4. `requirements.txt` — installed packages

Then re-read this CLAUDE.md. Only then begin the task.
If you are unsure about any architectural decision, refer to the "Architecture" and "Cost Discipline" sections below before proceeding.

---

## What this project is

**Classmate AI** is a personalized AI learning companion for students (primary beachhead: Indian college/engineering students, especially Tamil-medium and regional-language learners).

Company: **Visionary Sparks** · Domain: visionarysparks.in
Deployed at: visionary-sparks-3swm.onrender.com (Render, auto-deploys from GitHub)

The core insight: Generic AI tutors give everyone the same answer. Classmate AI serves answers tuned to the student's age band, goal, learning level, and mother-tongue — powered by intelligent caching so most answers cost ₹0.

The AI tutor persona is named **Astra**.

---

## Product modes (the full vision — build in phases)

### Phase 1 (current build target)
- **Astra Study Mode** — student asks a concept, gets a tuned explanation. Bouncer → cache → Gemini.
- **Quests (RPG Mode)** — career-themed gamified missions that use academic concepts as the "weapon."
- **Personalization** — every response shaped by: age_band, goal, level, archetype.
- **Login / User Accounts** — Supabase Auth (email + password). Each user has a saved profile. Different users → different cache segments → different training data.

### Phase 2 (after Phase 1 is validated with real users)
- **Explorer Mode** — short awareness drops (health, technology, world events). No infinite feed. No comments. Safe.
- **Paths / Roadmaps** — structured learning tracks (Python, JEE, NEET, etc.)
- **Teacher/Class Platform** — B2B layer where a teacher manages a course group, shares materials.

### Phase 3 (future)
- **5-level teaching depth** (simple → mother-tongue blend → analogy → visual Q&A → live animation)
- **Voice access** (floating mic engine — NOT now, it will burn credits fast)
- **3D pre-rendered concept animations**

---

## Personalization system

Every request carries a user profile with these four fields:

| Field | Values | Purpose |
|---|---|---|
| `age_band` | `u15`, `u18`, `college`, `pro` | Vocabulary depth, analogy type |
| `goal` | `JEE`, `NEET`, `python`, `placements`, `general` | Subject framing, examples |
| `level` | `beginner`, `intermediate` | Depth and assumed prior knowledge |
| `archetype` | `Grinder`, `Innovator`, `Dreamer` | Tone and motivational style |

The archetype affects Astra's personality:
- **Grinder** — sharp, disciplined, exam-focused. "Next rep."
- **Innovator** — curious, builder's mindset, project examples. "Let's ship it."
- **Dreamer** — bold, big-picture, long-game energy. "Decades, not days."

---

## Day rhythm (affects UI mode, not backend)

| Day | Mode | Notes |
|---|---|---|
| Monday | Revision & Planning | Low intensity, review |
| Tue / Wed / Thu | Academic Focus | Games locked in UI |
| Friday | Flex · Quests Unlocked | More RPG access |
| Saturday | Health & Movement | Explorer/wellness content |
| Sunday | Explorer Drop | Awareness shorts |

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn |
| AI model | Google Gemini via `google-genai` · model: `gemini-3.1-flash-lite` |
| Database | Supabase (Postgres) |
| Auth | Supabase Auth (email + password, built-in) |
| Frontend | Vanilla HTML/CSS/JS — single file, no build step, no React |
| Hosting | Render (auto-deploy from GitHub `samaruban0317/visionary-sparks`) |

**Do NOT change the AI model** without checking cost implications first. `gemini-3.1-flash-lite` is the budget workhorse. Pricier models only for hard tasks explicitly approved.

---

## File structure

```
visionary-backend/
├── CLAUDE.md           ← this file (project brief for Code)
├── main.py             ← FastAPI app — all endpoints live here
├── index.html          ← OLD frontend (reference only, do not develop further)
├── index2.html         ← NEW dashboard frontend (this is the active frontend)
├── login.html          ← BROKEN — to be deleted and rebuilt inside index2.html
├── requirements.txt    ← fastapi uvicorn pydantic google-genai supabase
└── test_bouncer.py     ← manual tests for the bouncer endpoint
```

---

## Architecture — how a response is built

```
Student types question
        ↓
[/bouncer] — AI Bouncer (gemini-3.1-flash-lite)
  • Classifies: LOCAL (greeting/small talk) or CACHE (real academic topic)
  • Strips emotional/conversational fluff → extracts clean_question
  • Returns LOCAL response instantly (no DB, no Gemini main call)
        ↓ (only for CACHE route)
[Supabase mega_cache lookup]
  • Key: age_band|goal|level|subject|normalized_question
  • HIT → serve instantly, cost = ₹0
  • MISS → continue
        ↓ (only on cache miss)
[Gemini gemini-3.1-flash-lite — teacher mode]
  • Prompt injects: subject, age_band, goal, level, archetype, clean_question
  • Astra persona responds with tuned depth and tone
  • Answer saved to mega_cache under the segmented key
        ↓
Student sees the answer (with route badge: ⚡ CACHE or ✦ FRESH)
```

### Cache key format (critical — do not change)
```
{age_band}|{goal}|{level}|{subject}|{normalized_question}
```
Normalize the question: lowercase, strip punctuation, collapse spaces.
This ensures a "u15/JEE/beginner" and a "college/python/intermediate" student
get different cached answers for the same question.

### Current Supabase tables

**mega_cache**
```sql
question TEXT PRIMARY KEY,   -- the segmented cache key
answer   TEXT                -- Astra's generated response
```
RLS: OFF during development. Must be ON before real users.

**Planned for login phase:**
```sql
-- Supabase Auth handles auth.users automatically (email, password hash, sessions)

-- user_profiles (to be created)
CREATE TABLE user_profiles (
  user_id   UUID PRIMARY KEY REFERENCES auth.users(id),
  name      TEXT,
  age_band  TEXT DEFAULT 'college',
  goal      TEXT DEFAULT 'general',
  level     TEXT DEFAULT 'beginner',
  archetype TEXT DEFAULT 'Grinder',
  xp        INTEGER DEFAULT 0,
  streak    INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);
-- RLS: ON. Each user can only read/update their own row.
```

---

## Login system plan (Phase 1 — build this now)

**Auth provider:** Supabase Auth (email + password). Do NOT build custom auth.

**Flow:**
1. User visits the app → check for active Supabase session.
2. If no session → show login/signup modal (overlay on index2.html, or a minimal login screen).
3. After login → load their profile from `user_profiles`. If none exists (new user), show onboarding (pick archetype, age_band, goal, level) and create the row.
4. All API requests include `user_id` from the session.
5. Backend uses `user_id` for per-user tracking (future) and cache personalization.

**Why login matters for training:**
- 5 different users → 5 different profiles → 5 different cache segments.
- We collect what real segments ask. Invaluable for understanding real usage before scaling.
- Without login, everyone is "user1" — one cache segment, no learning.

**Frontend auth pattern (Supabase JS CDN):**
```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
  const { createClient } = supabase;
  const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  // sign up
  await sb.auth.signUp({ email, password });
  // sign in
  await sb.auth.signInWithPassword({ email, password });
  // get current user
  const { data: { user } } = await sb.auth.getUser();
  // sign out
  await sb.auth.signOut();
</script>
```
SUPABASE_URL and SUPABASE_ANON_KEY go in the frontend as constants (anon key is safe to expose). Never expose the service_role key.

---

## Endpoints (current)

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Serves index.html (change to index2.html when ready) |
| POST | `/bouncer` | Main study route — bouncer → cache → Gemini |
| POST | `/mission` | Generate a career-themed RPG mission |
| POST | `/solve_mission` | Evaluate the student's answer to a mission |

**Request models to upgrade** — add profile fields to StudentRequest:
```python
class StudentRequest(BaseModel):
    user_id: str
    raw_prompt: str
    subject: str
    age_band: str = "college"
    goal: str = "general"
    level: str = "beginner"
    archetype: str = "Grinder"
```

---

## Environment variables (never hardcode, never print, never commit)

```
GEMINI_API_KEY     — Google AI Studio key
SUPABASE_URL       — your Supabase project URL
SUPABASE_KEY       — Supabase anon key (for most backend ops)
```
Render reads these from the dashboard. Locally use a `.env` file + `python-dotenv`.

---

## Cost discipline — survival rules

1. **Always: bouncer → cache → generate.** Never skip the cache check.
2. Cache key MUST include the profile segment. Personalized ≠ uncacheable — it just caches per segment.
3. Do not add any feature that calls Gemini on every keystroke, background poll, or page load.
4. The voice mic / floating mic engine is parked until further notice — it would burn credits catastrophically at scale.
5. Frequently-asked cached questions are worth refreshing during low-traffic windows (weekly job). Mark this as a future task, do not implement now.

---

## Safety — absolute rules

- **Never commit secrets.** Check `.gitignore` includes `.env`.
- **Never run DROP, TRUNCATE, or mass DELETE** without explicit human confirmation in the task prompt.
- **RLS must be ON** for `user_profiles` immediately. Enable it on `mega_cache` before going public.
- **Work on a feature branch** before any large change. Commit a checkpoint before starting.
- The live Render + Supabase connection is a real production system. Treat it as such.
- `CORS allow_origins=["*"]` is development-only. Flag it for tightening before public launch.
- Remove the dev auth bypass (force-verify hack) before real users have accounts.

---

## Common commands

```bash
# install deps
pip install -r requirements.txt

# run locally (backend on port 8000)
uvicorn main:app --reload --port 8000

# open app in browser
start http://localhost:8000

# git — always branch before big work
git checkout -b feature/<name>
git add -A && git commit -m "checkpoint: <description>"
git push origin feature/<name>
# merge to main only when tested → Render auto-deploys
```

---

## Current priorities (build in this order)

1. **Wire index2.html to real backend** — replace all demo/mock fetch functions with real calls to `/bouncer`, `/mission`, `/solve_mission`. Pass profile fields (age_band, goal, level, archetype) in each request body.

2. **Build login system** — Supabase Auth email/password overlay on index2.html. On first login, show archetype/profile onboarding and create a `user_profiles` row. Load profile on session restore. Pass `user_id` in all API requests.

3. **Upgrade StudentRequest** — add age_band, goal, level, archetype. Fix the cache key to the segmented format. Inject profile into the Gemini prompt.

4. **Enable RLS on user_profiles** — immediately when the table is created. Test that user A cannot read user B's profile.

5. **Swap index for index2** — once login + wiring work: update the `/` route in main.py to serve `index2.html`. Delete `index.html` and the old broken `login.html`.

6. **Give to 5 real friends** — only after steps 1-5 are done. Collect what breaks.

---

## What NOT to build right now

- Voice mic engine (credit killer)
- 3D animations (Phase 3)
- Teacher/B2B platform (Phase 2)
- Social/awareness feed (Phase 2)
- Analytics dashboard for students (Phase 2)
- Payment/subscription system (way later)


