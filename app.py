import streamlit as st
import pandas as pd
from supabase import create_client
from google import genai
from google.genai import types
import pdfplumber
import docx
import json
import io
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
if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = {
        "rotations": [], "procedures": [], "qips": [], 
        "teaching": [], "education": [], "publications": []
    }

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 4. IMPROVED EXTRACTION & CHUNKING ---
def get_raw_text_robust(file):
    """Extraction with fallback to catch dense medical layouts."""
    text = ""
    try:
        if file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    # Try layout-aware extraction first
                    page_text = page.extract_text(layout=True)
                    if page_text:
                        text += page_text + "\n"
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            text = "\n".join([p.text for p in doc.paragraphs])
        
        # Clean up only non-printable characters, keep structure
        text = "".join(char for char in text if char.isprintable() or char in '\n\r\t ')
        return text.strip()
    except Exception as e:
        st.error(f"File Read Error: {e}")
        return ""

def process_chunk_v2(chunk_text):
    """Modified prompt to force non-empty lists."""
    prompt = (
        "You are a medical CV parser. Extract all clinical details into a JSON object. "
        "Keys: rotations, procedures, qips, teaching, education, publications. "
        "If you find a rotation, put it in 'rotations'. If you find a skill, put it in 'procedures'. "
        "NEVER leave a list empty if there is data. Format everything as a list of objects. "
        f"Text to parse: {chunk_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        return json.loads(response.text)
    except:
        return None

def run_automated_scan(full_text):
    combined = {k: [] for k in st.session_state.parsed_data.keys()}
    # Smaller chunks (1500 chars) for better focus
    chunks = [full_text[i:i+1500] for i in range(0, len(full_text), 1500)]
    
    prog = st.progress(0)
    for idx, chunk in enumerate(chunks):
        res = process_chunk_v2(chunk)
        if res:
            for key in combined:
                if key in res and isinstance(res[key], list):
                    combined[key].extend(res[key])
        prog.progress((idx + 1) / len(chunks))
        time.sleep(1) # Rate limit protection
    return combined

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Portfolio")
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        
        if up_file:
            raw_text = get_raw_text_robust(up_file)
            if raw_text:
                st.success(f"File loaded: {len(raw_text)} characters.")
                with st.expander("🔍 Preview Extracted Text"):
                    st.text(raw_text[:500] + "...")
                
                if st.button("🚀 Start AI Synthesis"):
                    with st.spinner("Analyzing clinical data..."):
                        st.session_state.parsed_data = run_automated_scan(raw_text)
                        st.success("Synthesis Complete!")
            else:
                st.error("No text could be extracted from this file.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    tabs = st.tabs(["🌐 Equivalency", "🏥 Experience", "💉 Procedures", "🔬 QIP & Audit", "👨‍🏫 Teaching", "📚 Education", "📄 Raw Debug"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Seniority Mapping")
        
        profile_db = supabase_client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if profile_db else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Tier", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        targets = ["UK", "US", "Australia", "Poland"]
        map_data = [{"Country": c, "Title": EQUIVALENCY_MAP[selected_tier].get(c, "N/A")} for c in targets]
        st.table(pd.DataFrame(map_data))

    # 2. EXPERIENCE
    with tabs[1]:
        st.subheader("Clinical Rotations")
        data = st.session_state.parsed_data.get("rotations", [])
        if not data: st.info("Nothing detected. Please check 'Raw Debug' tab.")
        for item in data:
            title = item.get('specialty') or item.get('title') or item.get('role') or "Unknown Role"
            hosp = item.get('hospital') or item.get('location') or "Unknown Hospital"
            with st.expander(f"🏥 {title}"):
                st.write(f"**At:** {hosp} | **Dates:** {item.get('dates', 'N/A')}")
                st.write(item.get('description', ''))

    # 3. PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Logbook")
        
        data = st.session_state.parsed_data.get("procedures", [])
        if not data: st.info("Nothing detected.")
        for item in data:
            name = item.get('name') or item.get('procedure') or item.get('skill', 'Procedure')
            lvl = item.get('level') or item.get('competency', 'N/A')
            st.write(f"💉 {name} — **{lvl}**")

    # 4. QIP & AUDIT
    with tabs[3]:
        st.subheader("Quality Improvement")
        
        data = st.session_state.parsed_data.get("qips", [])
        for item in data:
            st.write(f"🔬 **{item.get('title', 'Project')}**")

    # 5. TEACHING & EDUCATION
    with tabs[4]:
        for item in st.session_state.parsed_data.get("teaching", []):
            st.write(f"👨‍🏫 {item.get('topic') or item.get('title', 'Teaching Session')}")
    
    with tabs[5]:
        for item in st.session_state.parsed_data.get("education", []):
            st.write(f"📚 {item.get('course') or item.get('title', 'Education')} ({item.get('year', 'N/A')})")

    # 6. DEBUG
    with tabs[6]:
        st.write("AI Output JSON:")
        st.json(st.session_state.parsed_data)

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
