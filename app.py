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
        st.error("⚠️ GEMINI_API_KEY missing in Secrets.")
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

# --- 4. THE AUTOMATED CHUNKING ENGINE ---
def get_raw_text(file):
    try:
        text = ""
        if file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            text = "\n".join([p.text for p in doc.paragraphs])
        # Clean non-essential symbols
        return re.sub(r'[^a-zA-Z0-9\s\.,\-\(\):/]', '', text)
    except: return ""

def process_chunk(chunk_text):
    """Processes a single 2000-char block of the CV."""
    prompt = (
        "Extract medical career data from this CV fragment into JSON. "
        "Keys: rotations, procedures, qips, teaching, education, publications. "
        f"Fragment: {chunk_text}"
    )
    try:
        response = ai_client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        return None

def run_full_analysis(full_text):
    # Reset local data
    combined_results = {k: [] for k in st.session_state.parsed_data.keys()}
    
    # Split text into chunks of 2000 chars (approx 400-500 words)
    chunks = [full_text[i:i+2000] for i in range(0, len(full_text), 2000)]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, chunk in enumerate(chunks):
        status_text.text(f"Analyzing Clinical Block {idx+1} of {len(chunks)}...")
        result = process_chunk(chunk)
        if result:
            for key in combined_results:
                if key in result and isinstance(result[key], list):
                    combined_results[key].extend(result[key])
        
        progress_bar.progress((idx + 1) / len(chunks))
        # Small sleep to respect Free Tier rate limits (RPM)
        time.sleep(2) 
        
    status_text.text("Synthesis Complete!")
    return combined_results

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Sync")
        st.write(f"Logged in: **{st.session_state.user_email}**")
        
        up_file = st.file_uploader("Upload Full Medical CV", type=['pdf', 'docx'])
        if up_file and st.button("🚀 Run Multi-Stage Scan"):
            raw_text = get_raw_text(up_file)
            if raw_text:
                final_data = run_full_analysis(raw_text)
                st.session_state.parsed_data = final_data
                st.success("Full CV Map Generated.")
        
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    tabs = st.tabs(["🌐 Equivalency", "🏥 Experience", "💉 Procedures", "🔬 QIP & Audit", "👨‍🏫 Teaching", "📚 Education", "📄 Export"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Seniority Mapping")
        
        profile_db = supabase_client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if profile_db else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Seniority Tier", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        active_c = st.multiselect("Target Systems", options=["UK", "US", "Australia", "Poland"], default=["UK"])
        map_data = [{"Country": c, "Equivalent Title": EQUIVALENCY_MAP[selected_tier].get(c, "N/A")} for c in active_c]
        st.table(pd.DataFrame(map_data))

    # 2. EXPERIENCE
    with tabs[1]:
        st.subheader("Clinical Rotations")
        for item in st.session_state.parsed_data.get("rotations", []):
            with st.expander(f"📍 {item.get('specialty', 'Rotation')}"):
                st.write(f"**Hospital:** {item.get('hospital')}")
                st.write(f"**Details:** {item.get('description')}")

    # 3. PROCEDURES
    with tabs[2]:
        st.subheader("Logbook")
        
        for item in st.session_state.parsed_data.get("procedures", []):
            st.write(f"💉 {item.get('procedure', item.get('name', 'N/A'))} — **{item.get('level', 'N/A')}**")

    # 4. QIP & AUDIT
    with tabs[3]:
        st.subheader("Quality Improvement")
        
        for item in st.session_state.parsed_data.get("qips", []):
            st.write(f"🔬 **{item.get('title', 'Audit')}**")

    # 5. TEACHING
    with tabs[4]:
        st.subheader("Teaching Portfolio")
        for item in st.session_state.parsed_data.get("teaching", []):
            st.write(f"👨‍🏫 **{item.get('topic', item.get('title', 'N/A'))}**")

    # 6. EDUCATION
    with tabs[5]:
        st.subheader("Courses & Seminars")
        for item in st.session_state.parsed_data.get("education", []):
            st.write(f"📚 {item.get('course', 'Course')} ({item.get('year', 'N/A')})")

    # 7. EXPORT
    with tabs[6]:
        st.button("🏗️ Build Professional Passport PDF")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
