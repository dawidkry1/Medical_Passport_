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
if 'portfolio_data' not in st.session_state:
    st.session_state.portfolio_data = []

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 4. DATA EXTRACTION ENGINE ---
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

def ai_brute_force_extract(chunk_text):
    """The most aggressive prompt possible."""
    prompt = (
        "Copy every medical job, rotation, hospital name, procedure, audit, and course from this text. "
        "Do not leave anything out. Format as a simple JSON list of objects. "
        "Use these exact keys: 'title', 'location', 'date', 'type'. "
        f"\n\nCV Text: {chunk_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        # Attempt to find JSON in the response even if the AI adds text around it
        clean_res = response.text
        if "```json" in clean_res:
            clean_res = clean_res.split("```json")[1].split("```")[0]
        
        data = json.loads(clean_res)
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list): return v
        return []
    except:
        return []

def run_extraction_cycle(full_text):
    results = []
    # Using 1200 character chunks for density balance
    chunks = [full_text[i:i+1200] for i in range(0, len(full_text), 1200)]
    prog = st.progress(0)
    
    for idx, chunk in enumerate(chunks):
        found = ai_brute_force_extract(chunk)
        if found:
            results.extend(found)
        prog.progress((idx + 1) / len(chunks))
        time.sleep(1)
    return results

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Doctor Dashboard")
        st.write(f"User: {st.session_state.user_email}")
        
        up_file = st.file_uploader("Sync CV Data", type=['pdf', 'docx'])
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt and st.button("🚀 Scrape Clinical Data"):
                with st.spinner("Processing medical records..."):
                    st.session_state.portfolio_data = run_extraction_cycle(raw_txt)
                    if st.session_state.portfolio_data:
                        st.success(f"Extracted {len(st.session_state.portfolio_data)} items.")
                    else:
                        st.error("AI returned zero items. Verify CV formatting.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    tabs = st.tabs(["🌐 Equivalency", "🏥 Clinical Experience", "💉 Procedures", "🔬 QIP & Projects", "📄 Raw Data"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Grade Mapping")
        
        profile_db = supabase_client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if profile_db else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Seniority", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        map_data = [{"Country": c, "Title": EQUIVALENCY_MAP[selected_tier].get(c, "N/A")} for c in ["UK", "US", "Australia", "Poland"]]
        st.table(pd.DataFrame(map_data))

    # 2. CLINICAL EXPERIENCE
    with tabs[1]:
        st.subheader("Rotations & Placements")
        # Try to find anything that looks like a job/rotation
        exp = [i for i in st.session_state.portfolio_data if 'type' in i and any(x in str(i['type']).lower() for x in ['job', 'rotation', 'work', 'exp', 'place'])]
        if exp:
            for e in exp:
                with st.expander(f"🏥 {e.get('title', 'Entry')}"):
                    st.write(f"**Location:** {e.get('location', 'N/A')}")
                    st.write(f"**Date:** {e.get('date', 'N/A')}")
        else:
            st.info("No rotations identified. Use the Raw Data tab to see unclassified items.")

    # 3. PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Logbook")
        
        procs = [i for i in st.session_state.portfolio_data if 'type' in i and any(x in str(i['type']).lower() for x in ['proc', 'skill', 'log'])]
        if procs:
            for p in procs:
                st.write(f"💉 **{p.get('title')}** — {p.get('location', 'N/A')}")
        else:
            st.info("No procedures identified.")

    # 4. QIP & PROJECTS
    with tabs[3]:
        st.subheader("Quality Improvement & Research")
        
        qips = [i for i in st.session_state.portfolio_data if 'type' in i and any(x in str(i['type']).lower() for x in ['audit', 'qip', 'research', 'project'])]
        if qips:
            for q in qips:
                st.write(f"🔬 **{q.get('title')}** — {q.get('date', 'N/A')}")
        else:
            st.info("No audits identified.")

    # 5. RAW DATA (The "Catch-All")
    with tabs[4]:
        st.subheader("All Scraped Data")
        st.write("If the categories above are empty, look here. This is every object the AI found.")
        if st.session_state.portfolio_data:
            st.dataframe(pd.DataFrame(st.session_state.portfolio_data), use_container_width=True)
            if st.button("💾 Save All to Cloud"):
                st.toast("Syncing with Supabase...")
        else:
            st.warning("No data found in the current session.")

# --- LOGIN GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
