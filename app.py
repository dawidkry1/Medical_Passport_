import streamlit as st
import pandas as pd
from supabase import create_client
from google import genai
from google.genai import types
import pdfplumber
import docx
import json
import re
import time

# --- 1. CORE CONFIG ---
st.set_page_config(page_title="Global Medical Passport", page_icon="🏥", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stAppDeployButton {display:none;}
            [data-testid="stToolbar"] {visibility: hidden !important;}
            [data-testid="stDecoration"] {display:none;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# Connection Setup
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase_client = create_client(URL, KEY)
    
    if "GEMINI_API_KEY" in st.secrets:
        ai_client = genai.Client(
            api_key=st.secrets["GEMINI_API_KEY"],
            http_options={'api_version': 'v1'}
        )
        MODEL_ID = "gemini-1.5-flash" 
    else:
        st.error("⚠️ GEMINI_API_KEY missing.")
except Exception as e:
    st.error(f"Config Error: {e}")

# --- 2. GLOBAL MAPPING DATA ---
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {"UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern", "Poland": "Lekarz stażysta"},
    "Tier 2: Intermediate (SHO/Resident)": {"UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO", "Poland": "Lekarz rezydent (Junior)"},
    "Tier 3: Senior (Registrar/Fellow)": {"UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar", "Poland": "Lekarz rezydent (Senior)"},
    "Tier 4: Expert (Consultant/Attending)": {"UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant / Specialist", "Poland": "Lekarz specjalista"}
}

# --- 3. SESSION STATE ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'raw_debug_output' not in st.session_state:
    st.session_state.raw_debug_output = ""

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 4. THE SCRIBE ENGINE ---
def get_raw_text(file):
    text = ""
    try:
        if file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    text += (page.extract_text() or "") + "\n"
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            text = "\n".join([p.text for p in doc.paragraphs])
        return text.strip()
    except: return ""

def ai_scribe_extract(chunk_text):
    """Minimalist prompt to force the AI to return data."""
    prompt = (
        "Identify every job, clinical rotation, medical procedure, audit, and course in this text. "
        "Return the data as a simple JSON list of objects. "
        "Keys: 'type', 'name', 'place', 'date'. "
        "If you see a doctor's experience, include it. Do not be selective. "
        f"\n\nCV Text: {chunk_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        st.session_state.raw_debug_output += f"\n--- CHUNK ---\n{response.text}"
        return json.loads(response.text)
    except:
        return []

def run_scribe_scan(full_text):
    all_items = []
    st.session_state.raw_debug_output = "" # Reset debug
    # Very small chunks (1500 chars) for maximum focus
    segments = [full_text[i:i+1500] for i in range(0, len(full_text), 1500)]
    prog = st.progress(0)
    
    for idx, seg in enumerate(segments):
        res = ai_scribe_extract(seg)
        # Handle different possible JSON return structures
        if isinstance(res, list):
            all_items.extend(res)
        elif isinstance(res, dict):
            # If AI wrapped it in a key like 'items' or 'data'
            for val in res.values():
                if isinstance(val, list):
                    all_items.extend(val)
        
        prog.progress((idx + 1) / len(segments))
        time.sleep(1)
        
    return all_items

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🏥 Medical Passport")
        st.write(f"Logged in: {st.session_state.user_email}")
        
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        if up_file:
            text_preview = get_raw_text(up_file)
            if text_preview:
                st.info(f"Text detected ({len(text_preview)} chars)")
                if st.button("🚀 Scrape Clinical Data"):
                    with st.spinner("Scribing medical history..."):
                        st.session_state.scraped_data = run_scribe_scan(text_preview)
            else:
                st.error("Reader failed to find text.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    tabs = st.tabs(["🌐 Equivalency", "📋 Clinical Log", "🔬 QIP & Audit", "👨‍🏫 Teaching", "🛠️ System Debug"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Grade Mapping")
        
        profile_db = supabase_client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if profile_db else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Tier", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        target_list = ["UK", "US", "Australia", "Poland"]
        map_data = [{"Jurisdiction": t, "Equivalent Title": EQUIVALENCY_MAP[selected_tier].get(t, "N/A")} for t in target_list]
        st.table(pd.DataFrame(map_data))

    # 2. CLINICAL LOG
    with tabs[1]:
        st.subheader("Clinical Experience & Procedures")
        
        # Filter for anything that looks like a job or procedure
        clinical = [i for i in st.session_state.scraped_data if str(i.get('type', '')).lower() in ['job', 'rotation', 'procedure', 'skill', 'experience', 'placement']]
        if clinical:
            for item in clinical:
                with st.expander(f"🔹 {item.get('name', 'Entry')}"):
                    st.write(f"**Location:** {item.get('place', 'N/A')}")
                    st.write(f"**Date:** {item.get('date', 'N/A')}")
        else:
            st.warning("No clinical items sorted. Check the 'System Debug' tab to see what the AI found.")

    # 3. QIP & AUDIT
    with tabs[2]:
        st.subheader("Quality Improvement")
        
        qips = [i for i in st.session_state.scraped_data if 'audit' in str(i.get('type', '')).lower() or 'qip' in str(i.get('type', '')).lower()]
        for q in qips:
            st.write(f"🔬 **{q.get('name')}** — {q.get('date')}")

    # 4. TEACHING
    with tabs[3]:
        st.subheader("Teaching & Education")
        teach = [i for i in st.session_state.scraped_data if str(i.get('type', '')).lower() in ['teaching', 'education', 'course', 'seminar']]
        for t in teach:
            st.write(f"👨‍🏫 **{t.get('name')}** ({t.get('place')})")

    # 5. SYSTEM DEBUG
    with tabs[4]:
        st.subheader("Raw AI Response Logs")
        st.write("If the tabs are empty, the text below will show you exactly what Gemini sent back.")
        st.code(st.session_state.raw_debug_output)
        st.divider()
        st.subheader("Parsed Objects")
        st.json(st.session_state.scraped_data)

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
