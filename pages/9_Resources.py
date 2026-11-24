"""Health & Safety – emergency guidance and support lines.

Phase 4 expands this into a full education section. The safety content is
included from day one because the onboarding screening links here.
"""

import streamlit as st

from components.cards import page_header, section
from components.navigation import require_context
from utils.constants import EMERGENCY_NOTE

require_context()

page_header("Health & Safety", "Reclaim supports your recovery – it doesn't replace medical care.",
            eyebrow="Support")

st.error(f"**In an emergency:** {EMERGENCY_NOTE}", icon="🚑")

section("Alcohol withdrawal can be dangerous")
st.markdown(
    """
If your body has become dependent on alcohol, stopping suddenly can cause **withdrawal**, which can be
life-threatening. Please **speak to a doctor before stopping or sharply cutting down** if you:

- drink every day or almost every day, or have been drinking heavily for weeks or longer
- have had shaking, sweating, nausea, anxiety, a racing heart or trouble sleeping when you cut down
- need a drink in the morning to feel steady
- have ever had a seizure, hallucinations or severe confusion after stopping

**Get emergency help immediately** for seizures, hallucinations (seeing, hearing or feeling things that aren't
there), severe confusion, a very high temperature, or chest pain.

A doctor can help you withdraw safely, sometimes with medication or supervised care. Breathing exercises and
self-help tools are useful for everyday cravings, but they are **not** a treatment for withdrawal.
"""
)

section("Support lines", "Free, confidential help. Numbers can change – check your local health service if one doesn't connect.")
c1, c2 = st.columns(2)
with c1:
    st.markdown(
        """
**🇮🇳 India**
- National Tobacco Quitline: **1800-11-2356**
- Tele-MANAS (mental health, 24×7): **14416**
- Emergency: **112**

**🇺🇸 United States**
- SAMHSA National Helpline (24/7): **1-800-662-4357**
- Quitline: **1-800-QUIT-NOW**
- Crisis line: **988** · Emergency: **911**
"""
    )
with c2:
    st.markdown(
        """
**🇬🇧 United Kingdom**
- NHS Smokefree helpline: **0300 123 1044**
- Drinkline: **0300 123 1110**
- Emergency: **999**

**🇦🇺 Australia**
- Quitline: **13 78 48**
- National Alcohol and Other Drug Hotline: **1800 250 015**
- Emergency: **000**
"""
    )

section("A note on this app")
st.caption("Reclaim provides tracking and general wellbeing information. It does not diagnose conditions, "
           "prescribe treatment or promise specific health outcomes. Please talk to a healthcare professional "
           "about your situation.")
