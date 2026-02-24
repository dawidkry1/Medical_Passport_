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
    st.error(f"Configuration Error: {e}")

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
    st.session_state.parsed_data = {"rotations": [], "procedures": [], "qips": [], "teaching": [], "education": []}

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 4. ENGINE ---
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

def ai_process_chunk(chunk_text):
    prompt = (
        "Extract medical CV data into JSON. Categories: rotations, procedures, qips, teaching, education. "
        "For rotations, find 'specialty' and 'hospital'. For procedures, find 'name' and 'level'. "
        f"\n\nText: {chunk_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except:
        return None

def run_deep_scan(full_text):
    combined = {"rotations": [], "procedures": [], "qips": [], "teaching": [], "education": []}
    segments = [full_text[i:i+3000] for i in range(0, len(full_text), 3000)]
    prog = st.progress(0)
    for idx, seg in enumerate(segments):
        res = ai_process_chunk(seg)
        if res:
            for key in combined.keys():
                if key in res and isinstance(res[key], list):
                    combined[key].extend(res[key])
        prog.progress((idx + 1) / len(segments))
        time.sleep(1)
    return combined

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Portfolio")
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        if up_file:
            raw_text = get_raw_text(up_file)
            if raw_text and st.button("🚀 Run Analysis"):
                st.session_state.parsed_data = run_deep_scan(raw_text)
                st.success("Scan Complete.")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    # Metrics Summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rotations", len(st.session_state.parsed_data.get("rotations", [])))
    c2.metric("Procedures", len(st.session_state.parsed_data.get("procedures", [])))
    c3.metric("Audits/QIPs", len(st.session_state.parsed_data.get("qips", [])))
    c4.metric("Teaching", len(st.session_state.parsed_data.get("teaching", [])))
    
    tabs = st.tabs(["🌐 Equivalency", "🏥 Experience", "💉 Procedures", "🔬 QIP & Audit", "👨‍🏫 Teaching", "📚 Education"])

    # 1. EQUIVALENCY (Defensive Line 127 fix)
    with tabs[0]:
        st.subheader("International Seniority Mapping")
        
        profile_db = supabase_client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        curr_tier = "Tier 1: Junior (Intern/FY1)"
        if profile_db and len(profile_db) > 0:
            curr_tier = profile_db[0].get('global_tier', curr_tier)
            
        selected_tier = st.selectbox("Current Grade", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        targets = ["UK", "US", "Australia", "Poland"]
        
        map_data = []
        for c in targets:
            equiv = EQUIVALENCY_MAP.get(selected_tier, {}).get(c, "N/A")
            map_data.append({"Country": c, "Title": equiv})
        st.table(pd.DataFrame(map_data))

    # 2. EXPERIENCE
    with tabs[1]:
        st.subheader("Clinical Rotations")
        for item in st.session_state.parsed_data.get("rotations", []):
            label = item.get('specialty') or item.get('hospital') or "Medical Placement"
            with st.expander(f"📍 {label}"):
                st.write(item)

    # 3. PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Logbook")
        
        for item in st.session_state.parsed_data.get("procedures", []):
            name = item.get('name') or item.get('procedure') or "Procedure"
            lvl = item.get('level') or "N/A"
            st.write(f"💉 {name} — **{lvl}**")

    # 4. QIP & AUDIT
    with tabs[3]:
        st.subheader("Quality Improvement")
        
        for item in st.session_state.parsed_data.get("qips", []):
            title = item.get('title') or "Audit Project"
            st.write(f"🔬 {title}")

    # 5. TEACHING & EDUCATION (Defensive Line 207 fix)
    with tabs[4]:
        st.subheader("Teaching Portfolio")
        for item in st.session_state.parsed_data.get("teaching", []):
            t_title = item.get('topic') or item.get('title') or "Teaching Session"
            st.write(f"👨‍🏫 {t_title}")
    
    with tabs[5]:
        st.subheader("Education & CME")
        for item in st.session_state.parsed_data.get("education", []):
            e_title = item.get('course') or item.get('title') or "Course"
            st.write(f"📚 {e_title}")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
