"""Static values shared across the app (labels, colours, option lists)."""

APP_NAME = "Reclaim"
TAGLINE = "One hour at a time. One day at a time."

SMOKING = "smoking"
ALCOHOL = "alcohol"

ADDICTIONS = {
    SMOKING: {
        "label": "Smoking",
        "icon": "🚬",
        "unit": "cigarette",
        "units": "cigarettes",
        "free": "Smoke-free",
        "verb": "Smoked",
    },
    ALCOHOL: {
        "label": "Alcohol",
        "icon": "🍷",
        "unit": "drink",
        "units": "drinks",
        "free": "Alcohol-free",
        "verb": "Drank",
    },
}

# Hourly slot statuses. "untracked" and "upcoming" are never stored – they
# are derived in the UI from the absence of a row / the slot being in the future.
SUCCESS = "success"
CRAVING_RESISTED = "craving_resisted"
CONSUMED = "consumed"
UNTRACKED = "untracked"
UPCOMING = "upcoming"
STORED_STATUSES = (SUCCESS, CRAVING_RESISTED, CONSUMED)

STATUS_META = {
    SUCCESS: {"label": "Free", "icon": "✅", "color": "#3fb68b"},
    CRAVING_RESISTED: {"label": "Craving resisted", "icon": "💪", "color": "#e5b84b"},
    CONSUMED: {"label": "Consumed", "icon": "●", "color": "#e06c6c"},
    UNTRACKED: {"label": "Not tracked", "icon": "·", "color": "#7c8794"},
    UPCOMING: {"label": "Upcoming", "icon": "○", "color": "#5b8def"},
}

TRIGGERS = [
    "Stress", "Boredom", "After eating", "Work pressure", "Social situation",
    "Friends smoking or drinking", "Loneliness", "Anxiety", "Habit", "Other",
]

MOODS = ["Happy", "Calm", "Neutral", "Stressed", "Anxious", "Sad", "Frustrated", "Tired"]
MOOD_EMOJI = {
    "Happy": "😊", "Calm": "😌", "Neutral": "😐", "Stressed": "😣",
    "Anxious": "😟", "Sad": "😢", "Frustrated": "😤", "Tired": "😴",
}

DRINK_OCCASIONS = ["Alone at home", "With friends", "Party / celebration", "Meal", "Work event", "Bar / pub", "Other"]

# beverage -> (typical serving in ml, typical ABV %). Used as editable defaults only.
BEVERAGES = {
    "Beer": (330, 5.0),
    "Strong beer": (500, 8.0),
    "Wine": (150, 12.5),
    "Spirits (peg / shot)": (30, 40.0),
    "Large peg (60 ml)": (60, 40.0),
    "Cocktail": (200, 12.0),
    "Cider": (330, 5.0),
    "Other": (250, 10.0),
}

# Grams of pure alcohol in one "standard drink" – varies by country.
STANDARD_DRINK_GRAMS = {
    "WHO": (10.0, "WHO guideline – 10 g"),
    "IN": (10.0, "India – 10 g"),
    "AU": (10.0, "Australia – 10 g"),
    "EU": (10.0, "Most of Europe – 10 g"),
    "UK": (8.0, "United Kingdom – 8 g (1 unit)"),
    "CA": (13.45, "Canada – 13.45 g"),
    "US": (14.0, "United States – 14 g"),
}
ETHANOL_DENSITY_G_PER_ML = 0.789

DRINKING_FREQUENCY = {
    "daily": ("Every day", 7.0),
    "most_days": ("Most days (5–6 per week)", 5.5),
    "few_per_week": ("A few times a week (2–4)", 3.0),
    "weekly": ("About once a week", 1.0),
    "occasionally": ("Occasionally (a few times a month)", 0.5),
}

CURRENCIES = ["₹", "$", "€", "£", "¥", "A$", "C$", "R", "AED", "SGD"]

# Recovery milestones in hours (used for the dashboard timeline).
MILESTONES = [
    (1, "First hour"), (24, "24 hours"), (72, "3 days"), (168, "7 days"),
    (336, "14 days"), (720, "30 days"), (1440, "60 days"), (2160, "90 days"),
    (4320, "180 days"), (8760, "365 days"),
]

EMERGENCY_NOTE = (
    "If you or someone else has seizures, hallucinations, severe confusion, "
    "chest pain or trouble breathing, call your local emergency number now "
    "(India: 112 · US/Canada: 911 · UK: 999 · EU: 112 · Australia: 000)."
)

# ---------------------------------------------------------------------------
# Phase 2: cravings, journal, savings
# ---------------------------------------------------------------------------
COPING_STRATEGIES = [
    "Breathing exercise", "Relaxation", "Short walk", "Distraction", "Drank water",
    "Called / messaged someone", "Read my reasons", "Waited it out", "Other",
]

DISTRACTIONS = [
    "Drink a full glass of cold water, slowly.",
    "Brush your teeth or chew sugar-free gum.",
    "Text a friend something kind.",
    "Do 20 squats or a 1-minute plank.",
    "Put on one song you love and really listen.",
    "Step outside and name five things you can see.",
    "Tidy one small area for five minutes.",
    "Eat a piece of fruit or a handful of nuts.",
    "Take a hot or cold shower.",
    "Write down three things you're grateful for today.",
    "Play a quick puzzle or word game.",
    "Change rooms – a new place breaks the cue.",
]

ENCOURAGEMENTS = [
    "Cravings peak and pass – most fade within 10–20 minutes.",
    "You don't have to win the whole day. Just this next hour.",
    "Every craving you ride out makes the next one weaker.",
    "This feeling is temporary. Your reasons are not.",
    "You've handled hard moments before. You can handle this one.",
]

RELAXATION_STEPS = [
    "Sit or lie down comfortably and let your shoulders drop.",
    "Clench both fists tightly for 5 seconds… then release and notice the difference.",
    "Lift your shoulders to your ears, hold for 5 seconds… and let them fall.",
    "Scrunch your face tight, hold… then soften your jaw, eyes and forehead.",
    "Tense your stomach, hold… and release with a long breath out.",
    "Press your feet into the floor, hold… and let your legs go heavy.",
    "Breathe slowly for a minute and notice how your body feels now.",
]

WALK_STEPS = [
    "Put your phone on silent and step outside (or walk around your home).",
    "Walk at a comfortable pace for 5–10 minutes.",
    "Breathe in for four steps, out for four steps.",
    "Notice sounds, colours and the feeling of your feet on the ground.",
    "When you return, drink a glass of water before doing anything else.",
]

SAVINGS_ICONS = ["🎯", "📱", "🚲", "✈️", "🏖️", "🛟", "🎁", "🏠", "🎓", "💻", "👟", "🎸"]
