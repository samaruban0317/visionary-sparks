# -*- coding: utf-8 -*-
"""
Static marketing-page generator for visionarysparks.in.

Why this exists:
  The app (index.html) is auth-gated and visually cloaked, so Googlebot sees
  almost nothing there. These public pages give Google real, crawlable content
  on the apex domain and give first-time visitors somewhere to understand who
  we are before signing up.

How it works:
  One DRY source -> consistent <head>, nav and footer across every page.
  Run:  python tools/build_pages.py
  It writes about.html / features.html / how-it-works.html / faq.html /
  privacy.html / terms.html / contact.html to the repo root (static, no build
  step at runtime — FastAPI just serves the files).

Design matches login.html exactly: dark #0A0A0B, brand #7C3AED, accent #06B6D4,
Tailwind CDN, radial-gradient background, the hex-bolt spark.svg mark.
"""
import os

SITE = "https://visionarysparks.in"
APP = "https://about.visionarysparks.in"
CONTACT_EMAIL = "vsamaruban2425@gmail.com"
YEAR_JS = "<script>document.querySelectorAll('[data-yr]').forEach(e=>e.textContent=new Date().getFullYear());</script>"

# Pages shown in the top nav (slug, label)
NAV = [
    ("features.html", "Features"),
    ("how-it-works.html", "How it works"),
    ("faq.html", "FAQ"),
    ("about.html", "About"),
]


def _clean(slug):
    """Extensionless URL path for a page file (features.html -> features)."""
    return slug[:-5] if slug.endswith(".html") else slug


def head(title, desc, canonical, extra_jsonld="", head_inject=""):
    org_ld = """
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      "name": "Visionary Sparks",
      "url": "%s/",
      "logo": "%s/icon-512.png",
      "description": "Visionary Sparks builds Classmate AI, a personalized AI learning companion for Indian students.",
      "sameAs": ["%s"]
    }""" % (SITE, SITE, APP)
    extra = ("\n    <script type=\"application/ld+json\">%s</script>" % extra_jsonld) if extra_jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">{head_inject}
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{desc}">
    <meta name="author" content="Visionary Sparks">
    <meta name="robots" content="index, follow">
    <meta name="theme-color" content="#0A0A0B">
    <link rel="canonical" href="{canonical}">
    <link rel="icon" href="/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" sizes="48x48" href="/favicon-48x48.png">
    <link rel="icon" type="image/svg+xml" href="/spark.svg">
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
    <link rel="manifest" href="/manifest.json">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Visionary Sparks">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{desc}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:image" content="{SITE}/spark.png">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{desc}">
    <meta name="twitter:image" content="{SITE}/spark.png">
    <script type="application/ld+json">{org_ld}</script>{extra}
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{ darkMode: 'class', theme: {{ extend: {{ colors: {{ background: '#0A0A0B', surface: 'rgba(255,255,255,0.03)', border: 'rgba(255,255,255,0.08)', brand: '#7C3AED', brandHover: '#6D28D9', accent: '#06B6D4' }} }} }} }}
    </script>
    <style>
        body {{ background-color:#0A0A0B; background-image:radial-gradient(at 0% 0%, rgba(124,58,237,0.15) 0px, transparent 50%), radial-gradient(at 100% 100%, rgba(6,182,212,0.1) 0px, transparent 50%); background-attachment:fixed; }}
        .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing:0.05em; }}
        .card {{ background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:1rem; }}
        .prose-vs h2 {{ color:#fff; font-weight:700; font-size:1.35rem; margin-top:2rem; margin-bottom:.6rem; }}
        .prose-vs h3 {{ color:#e5e7eb; font-weight:600; margin-top:1.4rem; margin-bottom:.4rem; }}
        .prose-vs p, .prose-vs li {{ color:#9ca3af; line-height:1.7; }}
        .prose-vs ul {{ list-style:disc; padding-left:1.25rem; margin:.5rem 0; }}
        .prose-vs a {{ color:#a78bfa; }}
    </style>
</head>
<body class="min-h-screen flex flex-col text-gray-200 font-sans antialiased">
"""


def nav(active):
    links = ""
    for slug, label in NAV:
        is_active = "text-white" if slug == active else "text-gray-400 hover:text-white"
        links += f'<a href="/{_clean(slug)}" class="text-sm {is_active} transition-colors">{label}</a>\n'
    return f"""
<header class="sticky top-0 z-30 backdrop-blur-xl bg-black/30 border-b border-border">
  <nav class="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between gap-4">
    <a href="/" class="flex items-center gap-2.5 shrink-0">
      <img src="/spark.svg" alt="Visionary Sparks" class="w-8 h-8 rounded-lg" />
      <span class="font-bold text-white tracking-wide">Visionary Sparks</span>
    </a>
    <div class="hidden md:flex items-center gap-7">
      {links}
    </div>
    <a href="/login.html" class="shrink-0 text-sm font-semibold bg-brand hover:bg-brandHover text-white px-4 py-2 rounded-lg shadow-[0_0_18px_rgba(124,58,237,0.4)] transition-all">Open Classmate AI</a>
  </nav>
</header>
"""


def footer():
    cols = """
    <div>
      <div class="flex items-center gap-2.5 mb-3">
        <img src="/spark.svg" alt="" class="w-7 h-7 rounded-lg" />
        <span class="font-bold text-white">Visionary Sparks</span>
      </div>
      <p class="text-sm text-gray-500 max-w-xs">Classmate AI — a personalized AI study companion for Indian students. Meet Astra. Made in India.</p>
    </div>
    <div>
      <h4 class="mono text-xs text-gray-500 mb-3">PRODUCT</h4>
      <ul class="space-y-2 text-sm">
        <li><a href="/features" class="text-gray-400 hover:text-white">Features</a></li>
        <li><a href="/how-it-works" class="text-gray-400 hover:text-white">How it works</a></li>
        <li><a href="/login.html" class="text-gray-400 hover:text-white">Sign in / Sign up</a></li>
      </ul>
    </div>
    <div>
      <h4 class="mono text-xs text-gray-500 mb-3">COMPANY</h4>
      <ul class="space-y-2 text-sm">
        <li><a href="/about" class="text-gray-400 hover:text-white">About</a></li>
        <li><a href="/faq" class="text-gray-400 hover:text-white">FAQ</a></li>
        <li><a href="/contact" class="text-gray-400 hover:text-white">Contact</a></li>
      </ul>
    </div>
    <div>
      <h4 class="mono text-xs text-gray-500 mb-3">LEGAL</h4>
      <ul class="space-y-2 text-sm">
        <li><a href="/privacy" class="text-gray-400 hover:text-white">Privacy</a></li>
        <li><a href="/terms" class="text-gray-400 hover:text-white">Terms</a></li>
      </ul>
    </div>
    """
    return f"""
<footer class="border-t border-border mt-20">
  <div class="max-w-6xl mx-auto px-5 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
    {cols}
  </div>
  <div class="border-t border-border">
    <div class="max-w-6xl mx-auto px-5 py-5 text-xs text-gray-600 mono flex flex-col sm:flex-row gap-2 justify-between">
      <span>© <span data-yr></span> Visionary Sparks · visionarysparks.in</span>
      <span>Built for learners. Powered by Astra.</span>
    </div>
  </div>
</footer>
{YEAR_JS}
</body>
</html>"""


def page(slug, title, desc, body, active=None, extra_jsonld="", canonical=None, head_inject=""):
    canonical = canonical or f"{SITE}/{_clean(slug)}"
    html = head(title, desc, canonical, extra_jsonld, head_inject) + nav(active or slug) + body + footer()
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), slug)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", slug, f"({len(html)} bytes)")


def hero(badge, h1, sub, cta=True):
    cta_html = """
      <div class="mt-8 flex flex-wrap gap-3">
        <a href="/login.html" class="font-semibold bg-brand hover:bg-brandHover text-white px-6 py-3 rounded-lg shadow-[0_0_22px_rgba(124,58,237,0.45)] transition-all">Start free with Astra</a>
        <a href="/how-it-works.html" class="font-semibold border border-border hover:border-brand text-gray-200 px-6 py-3 rounded-lg transition-all">See how it works</a>
      </div>""" if cta else ""
    return f"""
<section class="max-w-6xl mx-auto px-5 pt-16 pb-10 text-center">
  <div class="inline-flex items-center gap-2 mono text-xs text-brand border border-brand/30 rounded-full px-3 py-1 mb-6 bg-brand/10">
    <span class="w-1.5 h-1.5 rounded-full bg-brand"></span> {badge}
  </div>
  <h1 class="text-3xl sm:text-5xl font-bold text-white leading-tight max-w-3xl mx-auto">{h1}</h1>
  <p class="text-gray-400 mt-5 text-base sm:text-lg leading-relaxed max-w-2xl mx-auto">{sub}</p>
  <div class="flex justify-center">{cta_html}</div>
</section>
"""


def feature_card(icon, title, text):
    return f"""<div class="card p-6">
      <div class="text-2xl mb-3">{icon}</div>
      <h3 class="font-semibold text-white mb-1.5">{title}</h3>
      <p class="text-sm text-gray-400 leading-relaxed">{text}</p>
    </div>"""


# ----------------------------------------------------------------------------
# PAGE CONTENT
# ----------------------------------------------------------------------------

def build_about():
    body = hero(
        "ABOUT VISIONARY SPARKS",
        "We believe every student deserves a tutor that actually <span class='text-brand'>knows them</span>.",
        "Visionary Sparks is an India-first education company building Classmate AI — and Astra, an AI tutor that adapts to who you are, not just what you ask.",
        cta=False,
    )
    body += """
<section class="max-w-3xl mx-auto px-5 pb-6 prose-vs">
  <h2>The problem we saw</h2>
  <p>Generic AI tutors give a class topper and a first-generation learner the exact same answer, in the same words, at the same depth. For millions of Indian students — especially Tamil-medium and regional-language learners — that one-size-fits-all answer is often too fast, too abstract, or pitched at the wrong level.</p>
  <h2>What we built</h2>
  <p><strong style="color:#e5e7eb">Classmate AI</strong> is a personalized AI learning companion. Its tutor persona, <strong style="color:#e5e7eb">Astra</strong>, tunes every explanation to four things about you:</p>
  <ul>
    <li><strong>Age band</strong> — vocabulary depth and the kind of analogies that land.</li>
    <li><strong>Goal</strong> — JEE, NEET, Python, placements, or general study framing.</li>
    <li><strong>Level</strong> — beginner or intermediate, so nothing is over- or under-explained.</li>
    <li><strong>Archetype</strong> — Grinder, Innovator or Dreamer, which shapes Astra's tone and motivation.</li>
  </ul>
  <h2>Why it stays affordable</h2>
  <p>Most questions students ask overlap. Classmate AI uses an intelligent, per-segment cache, so popular answers are served instantly at near-zero cost — which is how we can offer it free to start and keep it sustainable as we grow.</p>
  <h2>Where we're headed</h2>
  <p>We started with college and engineering students in India and we're building outward: deeper regional-language support, career discovery through our Pathfinder, and tools that help students stay consistent — not just get answers. We're early, we're independent, and we're building in public.</p>
  <p style="margin-top:1.5rem">Want the longer story and the team behind it? Visit <a href="%s">about.visionarysparks.in</a>.</p>
</section>
<section class="max-w-6xl mx-auto px-5 py-10 grid sm:grid-cols-3 gap-5">
  %s%s%s
</section>
""" % (
        APP,
        feature_card("🎯", "Personal, not generic", "Every answer is tuned to your age, goal, level and learning style."),
        feature_card("🇮🇳", "India-first", "Built for Indian learners, including Tamil-medium and regional-language students."),
        feature_card("∞", "Free to start", "Smart caching keeps costs near zero, so getting started costs you nothing."),
    )
    page("about.html", "About Visionary Sparks — the team behind Classmate AI & Astra",
         "Visionary Sparks is an India-first education company building Classmate AI, a personalized AI tutor (Astra) that adapts every answer to a student's age, goal, level and learning style.",
         body)


def build_features():
    cards = "".join([
        feature_card("✦", "Astra, your AI tutor", "A patient tutor that explains concepts in your words, at your level — and remembers your goal."),
        feature_card("🎚️", "Real personalization", "Answers adapt to your age band, goal (JEE/NEET/Python/placements), level and archetype."),
        feature_card("🗺️", "Personal roadmaps", "Turn a big goal into a clear, step-by-step path with daily tasks you can actually finish."),
        feature_card("⚡", "Daily Spark Challenge", "Three quick questions tuned to you, every day, to keep concepts sharp and earn XP."),
        feature_card("🎮", "Career Quests", "Story-driven missions that connect what you study to where you want to go."),
        feature_card("🔥", "XP & streaks", "A motivation engine that rewards consistency — show up daily, watch your streak grow."),
        feature_card("🧭", "Pathfinder", "Still deciding your goal? Pathfinder helps you explore careers and find direction."),
        feature_card("🌐", "Regional-language friendly", "Designed for Indian learners, including Tamil-medium and regional-language students."),
        feature_card("💸", "Near-zero cost", "Intelligent caching serves common answers instantly, so we can keep it free to start."),
    ])
    body = hero(
        "FEATURES",
        "Everything Astra does to make learning <span class='text-brand'>fit you</span>.",
        "Classmate AI is more than a chatbot. It's a personalized study system — tutor, roadmap, daily practice and motivation in one.",
    )
    body += f"""
<section class="max-w-6xl mx-auto px-5 py-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
  {cards}
</section>
<section class="max-w-3xl mx-auto px-5 py-12 text-center">
  <h2 class="text-2xl font-bold text-white">Ready to meet Astra?</h2>
  <p class="text-gray-400 mt-3">Create a free account and get your first personalized answer in seconds.</p>
  <a href="/login.html" class="inline-block mt-6 font-semibold bg-brand hover:bg-brandHover text-white px-6 py-3 rounded-lg shadow-[0_0_22px_rgba(124,58,237,0.45)] transition-all">Get started free</a>
</section>
"""
    page("features.html", "Features — Classmate AI by Visionary Sparks",
         "Astra explains in your words, builds personal roadmaps, runs a Daily Spark Challenge, Career Quests, XP streaks and Pathfinder — a full personalized study system for Indian students.",
         body)


def build_how():
    step = lambda n, t, d: f"""<div class="card p-6 relative">
      <div class="mono text-xs text-brand mb-2">STEP {n}</div>
      <h3 class="font-semibold text-white mb-1.5">{t}</h3>
      <p class="text-sm text-gray-400 leading-relaxed">{d}</p>
    </div>"""
    body = hero(
        "HOW IT WORKS",
        "How Astra gives <span class='text-brand'>you</span> a different answer.",
        "Two students can ask the same question and get genuinely different explanations. Here's the simple idea behind it.",
        cta=False,
    )
    body += f"""
<section class="max-w-5xl mx-auto px-5 py-6 grid sm:grid-cols-2 gap-5">
  {step(1, "You tell us who you are", "On signup you pick your age, goal, level and archetype. That profile travels with every question you ask.")}
  {step(2, "Astra reads the intent", "A lightweight first pass separates real study questions from small talk, and pulls out the clean academic question.")}
  {step(3, "We check the smart cache", "If a student with your profile already asked something similar, you get a great answer instantly — at near-zero cost.")}
  {step(4, "Astra teaches, tuned to you", "On a fresh question, Astra writes an explanation shaped by your age, goal, level and tone — then saves it for learners like you.")}
</section>
<section class="max-w-3xl mx-auto px-5 py-6 prose-vs">
  <h2>Why personalization matters</h2>
  <p>A 14-year-old starting out and a college student prepping for placements shouldn't get the same paragraph. By caching answers <em>per student segment</em> instead of globally, Classmate AI stays both personal and affordable — personalization doesn't make answers un-cacheable, it just caches them per profile.</p>
  <h2>Built to stay free to start</h2>
  <p>Because common questions are served from cache, the expensive part — generating a brand-new explanation — only happens when it's genuinely needed. That discipline is what lets us offer Classmate AI free to start.</p>
  <div class="mt-8"><a href="/login.html" class="font-semibold bg-brand hover:bg-brandHover text-white px-6 py-3 rounded-lg shadow-[0_0_22px_rgba(124,58,237,0.45)] transition-all">Try it yourself</a></div>
</section>
"""
    page("how-it-works.html", "How Classmate AI works — personalized AI tutoring explained",
         "Classmate AI tunes every answer to your age, goal, level and archetype, and uses smart per-segment caching to stay fast and free to start. Here's the simple idea behind Astra.",
         body)


def build_faq():
    qa = [
        ("What is Classmate AI?", "Classmate AI is a personalized AI learning companion for students. Its tutor, Astra, adapts every explanation to your age, goal, level and learning style — instead of giving everyone the same generic answer."),
        ("Who is Astra?", "Astra is the AI tutor inside Classmate AI. Astra explains concepts in your words and at your level, and adjusts tone based on your chosen archetype — Grinder, Innovator or Dreamer."),
        ("Is Classmate AI free?", "Yes — it's free to start. Intelligent caching keeps our costs near zero, which lets us offer core tutoring without a paywall as we grow."),
        ("Which exams and subjects does it support?", "Classmate AI is built for JEE, NEET, Python and data science, placements, and general study. You set your goal on signup and Astra frames answers around it."),
        ("Does it support Tamil and other regional languages?", "Classmate AI is designed India-first, with Tamil-medium and regional-language learners as a core focus. Language support continues to expand."),
        ("How is this different from a generic AI chatbot?", "A generic chatbot gives everyone the same answer. Classmate AI personalizes by your age, goal, level and archetype, and adds roadmaps, daily challenges, quests and an XP streak system to keep you consistent."),
        ("Do I need to create an account?", "Yes — a free account lets Astra remember your profile so answers stay personalized, and it powers your roadmap, XP and streaks."),
        ("Who builds Classmate AI?", "Classmate AI is built by Visionary Sparks, an independent India-first education company. You can learn more on our About page."),
    ]
    items = ""
    for q, a in qa:
        items += f"""<details class="card p-5 group">
      <summary class="cursor-pointer font-semibold text-white list-none flex justify-between items-center gap-4">
        <span>{q}</span><span class="text-brand text-xl group-open:rotate-45 transition-transform">+</span>
      </summary>
      <p class="text-sm text-gray-400 leading-relaxed mt-3">{a}</p>
    </details>"""
    faq_ld = '{ "@context":"https://schema.org","@type":"FAQPage","mainEntity":[' + ",".join(
        '{"@type":"Question","name":%s,"acceptedAnswer":{"@type":"Answer","text":%s}}' % (_jstr(q), _jstr(a))
        for q, a in qa
    ) + "]}"
    body = hero(
        "FREQUENTLY ASKED",
        "Questions, <span class='text-brand'>answered</span>.",
        "Everything you might want to know about Classmate AI, Astra and Visionary Sparks.",
        cta=False,
    )
    body += f"""
<section class="max-w-3xl mx-auto px-5 py-6 space-y-3">
  {items}
</section>
<section class="max-w-3xl mx-auto px-5 py-10 text-center">
  <p class="text-gray-400">Still have a question? <a href="/contact.html" class="text-brand hover:text-brandHover">Get in touch →</a></p>
</section>
"""
    page("faq.html", "FAQ — Classmate AI by Visionary Sparks",
         "Answers to common questions about Classmate AI and Astra: what it is, whether it's free, which exams it supports, regional-language support, and how it personalizes learning.",
         body, extra_jsonld=faq_ld)


def build_privacy():
    body = _legal_hero("Privacy Policy", "How Visionary Sparks handles your data.")
    body += """
<section class="max-w-3xl mx-auto px-5 py-6 prose-vs">
  <p class="mono text-xs text-gray-500">Last updated: <span data-yr></span></p>
  <p>This Privacy Policy explains what information Classmate AI ("we", "us"), operated by Visionary Sparks, collects and how we use it. By using Classmate AI you agree to this policy.</p>
  <h2>Information we collect</h2>
  <ul>
    <li><strong>Account information</strong> — your email, a username, and the profile you set up (display name, age, goal, level and archetype).</li>
    <li><strong>Learning activity</strong> — the questions you ask Astra, your roadmaps, tasks, challenge results, XP and streaks, so we can personalize and track your progress.</li>
    <li><strong>Technical data</strong> — standard log data needed to operate and secure the service.</li>
  </ul>
  <h2>How we use your information</h2>
  <ul>
    <li>To personalize Astra's answers to your profile.</li>
    <li>To run features like roadmaps, daily challenges, quests, XP and streaks.</li>
    <li>To maintain, secure and improve the service.</li>
  </ul>
  <h2>How your data is stored</h2>
  <p>Account, authentication and profile data are stored using Supabase (our database and authentication provider). AI responses are generated using Google's Gemini models. We do not sell your personal information.</p>
  <h2>Your choices</h2>
  <p>You can request access to or deletion of your account data by contacting us. Closing your account removes your profile from active use.</p>
  <h2>Children</h2>
  <p>Classmate AI is intended for students. If you are under the age of digital consent in your country, please use Classmate AI with the involvement of a parent or guardian.</p>
  <h2>Changes</h2>
  <p>We may update this policy as the product evolves. Material changes will be reflected on this page with a new "last updated" date.</p>
  <h2>Contact</h2>
  <p>Questions about privacy? Email us at <a href="mailto:%s">%s</a> or visit our <a href="/contact.html">contact page</a>.</p>
</section>
""" % (CONTACT_EMAIL, CONTACT_EMAIL)
    page("privacy.html", "Privacy Policy — Visionary Sparks / Classmate AI",
         "How Classmate AI by Visionary Sparks collects, uses and protects your account, profile and learning data.",
         body, active="about.html")


def build_terms():
    body = _legal_hero("Terms of Service", "The rules for using Classmate AI.")
    body += """
<section class="max-w-3xl mx-auto px-5 py-6 prose-vs">
  <p class="mono text-xs text-gray-500">Last updated: <span data-yr></span></p>
  <p>These Terms of Service govern your use of Classmate AI, operated by Visionary Sparks. By creating an account or using the service, you agree to these terms.</p>
  <h2>Your account</h2>
  <p>You are responsible for keeping your login credentials secure and for activity under your account. Provide accurate information when you sign up.</p>
  <h2>Acceptable use</h2>
  <ul>
    <li>Use Classmate AI for learning and personal study.</li>
    <li>Do not misuse, attack, scrape, or attempt to disrupt the service.</li>
    <li>Do not use the service for unlawful purposes or to generate harmful content.</li>
  </ul>
  <h2>AI-generated content</h2>
  <p>Astra's answers are generated by AI and may occasionally be incomplete or incorrect. Always verify important information, especially for exams and high-stakes decisions. Classmate AI is a study aid, not a substitute for professional or academic advice.</p>
  <h2>Availability</h2>
  <p>We work to keep the service available but provide it "as is", without warranties. Features may change as the product evolves.</p>
  <h2>Limitation of liability</h2>
  <p>To the extent permitted by law, Visionary Sparks is not liable for indirect or consequential damages arising from your use of the service.</p>
  <h2>Changes</h2>
  <p>We may update these terms over time. Continued use after changes means you accept the updated terms.</p>
  <h2>Contact</h2>
  <p>Questions about these terms? Email <a href="mailto:%s">%s</a>.</p>
</section>
""" % (CONTACT_EMAIL, CONTACT_EMAIL)
    page("terms.html", "Terms of Service — Visionary Sparks / Classmate AI",
         "The terms that govern your use of Classmate AI by Visionary Sparks, including acceptable use and notes on AI-generated content.",
         body, active="about.html")


def build_contact():
    contact_ld = ('{ "@context":"https://schema.org","@type":"Organization","name":"Visionary Sparks","url":"%s/",'
                  '"contactPoint":{"@type":"ContactPoint","email":"%s","contactType":"customer support"}}'
                  % (SITE, CONTACT_EMAIL))
    body = hero(
        "CONTACT",
        "Let's <span class='text-brand'>talk</span>.",
        "Questions, feedback, partnership ideas, or press — we'd love to hear from you.",
        cta=False,
    )
    body += """
<section class="max-w-3xl mx-auto px-5 py-6 grid sm:grid-cols-2 gap-5">
  <div class="card p-6">
    <div class="text-2xl mb-3">✉️</div>
    <h3 class="font-semibold text-white mb-1.5">Email us</h3>
    <p class="text-sm text-gray-400">For anything at all, reach us at:</p>
    <a href="mailto:%s" class="text-brand hover:text-brandHover text-sm break-all">%s</a>
  </div>
  <div class="card p-6">
    <div class="text-2xl mb-3">🌐</div>
    <h3 class="font-semibold text-white mb-1.5">Learn more</h3>
    <p class="text-sm text-gray-400">The full story of Visionary Sparks lives at:</p>
    <a href="%s" class="text-brand hover:text-brandHover text-sm break-all">about.visionarysparks.in</a>
  </div>
</section>
<section class="max-w-3xl mx-auto px-5 py-10 text-center">
  <p class="text-gray-400">Ready to start learning? <a href="/login.html" class="text-brand hover:text-brandHover">Open Classmate AI →</a></p>
</section>
""" % (CONTACT_EMAIL, CONTACT_EMAIL, APP)
    page("contact.html", "Contact — Visionary Sparks",
         "Get in touch with Visionary Sparks, the team behind Classmate AI and Astra. Questions, feedback, partnerships or press.",
         body, active="about.html", extra_jsonld=contact_ld)


def build_home():
    # Synchronous, render-blocking redirect: if a Supabase auth token exists in
    # localStorage, this is a logged-in user -> send them straight to the app
    # BEFORE the landing paints (no flash). Googlebot / logged-out visitors have
    # empty localStorage, so they fall through and see the full crawlable landing.
    redirect = """
    <script>
    (function(){
      try {
        for (var i = 0; i < localStorage.length; i++) {
          var k = localStorage.key(i);
          if (k && k.indexOf('sb-') === 0 && k.indexOf('-auth-token') !== -1) {
            location.replace('/app'); return;
          }
        }
      } catch (e) {}
    })();
    </script>"""
    home_ld = """{
      "@context": "https://schema.org",
      "@graph": [
        { "@type":"WebSite","name":"Classmate AI by Visionary Sparks","url":"%s/","publisher":{"@type":"Organization","name":"Visionary Sparks"} },
        { "@type":"EducationalApplication","name":"Classmate AI","applicationCategory":"EducationApplication","operatingSystem":"Web","url":"%s/","description":"An AI tutor (Astra) that personalizes every explanation to a student's age, goal, learning level and mother tongue — for JEE, NEET, Python, placements and general study.","offers":{"@type":"Offer","price":"0","priceCurrency":"INR"},"publisher":{"@type":"Organization","name":"Visionary Sparks","url":"%s/"} }
      ]
    }""" % (SITE, SITE, SITE)

    body = f"""
<section class="max-w-6xl mx-auto px-5 pt-20 pb-12 text-center">
  <div class="inline-flex items-center gap-2 mono text-xs text-brand border border-brand/30 rounded-full px-3 py-1 mb-6 bg-brand/10">
    <span class="w-1.5 h-1.5 rounded-full bg-brand"></span> MEET ASTRA · YOUR AI STUDY COMPANION
  </div>
  <h1 class="text-4xl sm:text-6xl font-bold text-white leading-[1.05] max-w-4xl mx-auto">
    The AI tutor that gives <span class="text-brand">you</span> a different answer.
  </h1>
  <p class="text-gray-400 mt-6 text-base sm:text-lg leading-relaxed max-w-2xl mx-auto">
    Generic AI gives everyone the same reply. <strong class="text-gray-200">Classmate AI</strong> tunes every explanation
    to your age, goal, level and learning style — built for Indian students chasing JEE, NEET, Python, placements and beyond.
  </p>
  <div class="mt-9 flex flex-wrap gap-3 justify-center">
    <a href="/login.html" class="font-semibold bg-brand hover:bg-brandHover text-white px-7 py-3.5 rounded-lg shadow-[0_0_24px_rgba(124,58,237,0.5)] transition-all transform hover:scale-[1.03]">Start free with Astra</a>
    <a href="/how-it-works.html" class="font-semibold border border-border hover:border-brand text-gray-200 px-7 py-3.5 rounded-lg transition-all">See how it works</a>
  </div>
  <p class="mono text-xs text-gray-600 mt-5">Free to start · No card needed · Made in India 🇮🇳</p>
</section>

<section class="max-w-6xl mx-auto px-5 py-8 grid sm:grid-cols-3 gap-5">
  {feature_card("🎯", "Personal, not generic", "Answers adapt to your age band, goal, level and archetype — never one-size-fits-all.")}
  {feature_card("🗺️", "A path, not just answers", "Roadmaps, daily tasks, a Daily Spark Challenge, Career Quests and XP streaks keep you moving.")}
  {feature_card("∞", "Free to start", "Smart per-segment caching keeps costs near zero, so getting started costs you nothing.")}
</section>

<section class="max-w-5xl mx-auto px-5 py-12">
  <h2 class="text-2xl sm:text-3xl font-bold text-white text-center">How Classmate AI works</h2>
  <p class="text-gray-400 text-center mt-3 max-w-xl mx-auto">Two students can ask the same question and get genuinely different explanations. Here's the idea.</p>
  <div class="grid sm:grid-cols-2 gap-5 mt-8">
    <div class="card p-6"><div class="mono text-xs text-brand mb-2">STEP 1</div><h3 class="font-semibold text-white mb-1.5">You tell us who you are</h3><p class="text-sm text-gray-400 leading-relaxed">Pick your age, goal, level and archetype. That profile rides with every question.</p></div>
    <div class="card p-6"><div class="mono text-xs text-brand mb-2">STEP 2</div><h3 class="font-semibold text-white mb-1.5">Astra teaches, tuned to you</h3><p class="text-sm text-gray-400 leading-relaxed">Explanations are shaped by your profile — the right depth, the right tone, the right examples.</p></div>
  </div>
  <div class="text-center mt-8"><a href="/how-it-works.html" class="text-brand hover:text-brandHover font-semibold">Read the full breakdown →</a></div>
</section>

<section class="max-w-3xl mx-auto px-5 py-16 text-center">
  <h2 class="text-2xl sm:text-3xl font-bold text-white">Ready to meet Astra?</h2>
  <p class="text-gray-400 mt-3">Create a free account and get your first personalized answer in seconds.</p>
  <a href="/login.html" class="inline-block mt-7 font-semibold bg-brand hover:bg-brandHover text-white px-8 py-4 rounded-lg shadow-[0_0_24px_rgba(124,58,237,0.5)] transition-all transform hover:scale-[1.03]">Get started free</a>
</section>
"""
    page("landing.html",
         "Classmate AI by Visionary Sparks — Your Personalized AI Study Companion",
         "Classmate AI by Visionary Sparks is a personalized AI tutor for Indian students. Meet Astra — every answer tuned to your age, goal, level and mother tongue. Built for JEE, NEET, Python, placements and beyond. Free to start.",
         body, active="__home__", canonical=f"{SITE}/", extra_jsonld=home_ld, head_inject=redirect)


def _legal_hero(title, sub):
    return f"""
<section class="max-w-3xl mx-auto px-5 pt-16 pb-4">
  <h1 class="text-3xl sm:text-4xl font-bold text-white">{title}</h1>
  <p class="text-gray-400 mt-3">{sub}</p>
</section>
"""


def _jstr(s):
    import json
    return json.dumps(s, ensure_ascii=False)


if __name__ == "__main__":
    build_home()
    build_about()
    build_features()
    build_how()
    build_faq()
    build_privacy()
    build_terms()
    build_contact()
    print("done.")
