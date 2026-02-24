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
if 'master_list' not in st.session_state:
    st.session_state.master_list = []

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 4. THE ULTIMATE SCRAPER ---
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

def ai_unfiltered_scrape(chunk_text):
    """Extreme extraction prompt."""
    prompt = (
        "Extract all clinical data from this CV. "
        "Find every hospital, department, specialty, procedure, and project. "
        "Return a JSON object with one key: 'items', which is a list. "
        "Each item needs: 'label', 'category' (choose from: Rotation, Procedure, QIP, Education), 'date', and 'desc'. "
        "If you see a date next to a medical term, include it. "
        f"\n\nCV Text: {chunk_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
        return data.get("items", [])
    except:
        return []

def run_total_scan(full_text):
    all_found = []
    # Very small 1000-char chunks to ensure the AI misses nothing
    segments = [full_text[i:i+1000] for i in range(0, len(full_text), 1000)]
    prog = st.progress(0)
    
    for idx, seg in enumerate(segments):
        res = ai_unfiltered_scrape(seg)
        if res:
            all_found.extend(res)
        prog.progress((idx + 1) / len(segments))
        time.sleep(1) # Safety for free tier
    return all_found

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Portfolio")
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        if up_file:
            raw = get_raw_text(up_file)
            if raw and st.button("🚀 Execute Clinical Scrape"):
                with st.spinner("Extracting doctor data..."):
                    st.session_state.master_list = run_total_scan(raw)
                    if st.session_state.master_list:
                        st.success(f"Captured {len(st.session_state.master_list)} clinical items.")
                    else:
                        st.error("No items captured. Check the System Tab.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    tabs = st.tabs(["🌐 Equivalency", "🏥 Clinical Records", "🔬 QIP & Projects", "📊 Raw System Data"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Grade Mapping")
        
        profile_db = supabase_client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if profile_db else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Tier", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        target_list = ["UK", "US", "Australia", "Poland"]
        map_data = [{"Jurisdiction": t, "Equivalent Title": EQUIVALENCY_MAP[selected_tier].get(t, "N/A")} for t in target_list]
        st.table(pd.DataFrame(map_data))

    # 2. CLINICAL RECORDS
    with tabs[1]:
        st.subheader("Extracted Experiences & Procedures")
        
        records = [i for i in st.session_state.master_list if i.get('category') in ['Rotation', 'Procedure', 'Education']]
        if records:
            for r in records:
                icon = "💉" if r.get('category') == 'Procedure' else "🏥"
                with st.expander(f"{icon} {r.get('label', 'Record')}"):
                    st.write(f"**Date:** {r.get('date', 'N/A')}")
                    st.write(f"**Details:** {r.get('desc', 'N/A')}")
        else:
            st.info("Clinical history will appear here once scraped.")

    # 3. QIP & PROJECTS
    with tabs[2]:
        st.subheader("Quality Improvement & Research")
        
        qips = [i for i in st.session_state.master_list if i.get('category') == 'QIP']
        if qips:
            for q in qips:
                st.write(f"🔬 **{q.get('label')}** — {q.get('date')}")
        else:
            st.info("Audit data will appear here.")

    # 4. RAW DATA (The backup)
    with tabs[3]:
        st.subheader("System Diagnostic")
        if st.session_state.master_list:
            st.write("The following items were found by the AI:")
            st.dataframe(pd.DataFrame(st.session_state.master_list), use_container_width=True)
        else:
            st.warning("The AI is returning no data. Check if your API key is active and that the file text is readable in the sidebar.")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
