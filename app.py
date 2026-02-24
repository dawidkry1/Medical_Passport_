import streamlit as st
import pandas as pd
from supabase import create_client
import google.generativeai as genai
import pdfplumber
import docx
import json
import io
import re

# --- 1. CORE CONFIG & STYLING ---
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
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
client = create_client(URL, KEY)

# Configure Gemini
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. GLOBAL MAPPING DATA ---
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {"UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern", "Poland": "Lekarz stażysta"},
    "Tier 2: Intermediate (SHO/Resident)": {"UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO", "Poland": "Lekarz rezydent (Junior)"},
    "Tier 3: Senior (Registrar/Fellow)": {"UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar", "Poland": "Lekarz rezydent (Senior)"},
    "Tier 4: Expert (Consultant/Attending)": {"UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant / Specialist", "Poland": "Lekarz specjalista"}
}

COUNTRY_KEY_MAP = {"United Kingdom": "UK", "United States": "US", "Australia": "Australia", "Poland": "Poland"}

# --- 3. SESSION & AUTH ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = {"rotations": [], "procedures": [], "qips": [], "teaching": [], "education": [], "publications": []}

def handle_login():
    try:
        res = client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 4. THE AI "CLINICAL BRAIN" PARSER ---
def get_raw_text(file):
    try:
        if file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                return "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            return "\n".join([p.text for p in doc.paragraphs])
    except: return ""

def gemini_ai_parse(text):
    prompt = f"""
    You are a medical recruitment expert. Analyze the following Doctor's CV text and extract the information into a valid JSON object.
    Strictly use these keys: 
    - "rotations" (hospital placements with dates/details)
    - "procedures" (specific clinical skills/procedures performed)
    - "qips" (audits, quality improvement projects, specify if closed loop)
    - "teaching" (sessions led, audience, topics)
    - "education" (conferences, seminars, CME courses, hours)
    - "publications" (research, posters, papers)
    - "registrations" (GMC numbers, licenses, certifications)

    Ensure the output is ONLY the JSON object. Do not add markdown or text.
    CV Text: {text}
    """
    try:
        response = model.generate_content(prompt)
        # Clean response text to ensure it's valid JSON (remove backticks if any)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Parsing Error: {e}")
        return None

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Doctor AI Sync")
        st.write(f"Doctor: **{st.session_state.user_email}**")
        up_file = st.file_uploader("Upload Medical CV", type=['pdf', 'docx'])
        if up_file and st.button("🚀 AI Deep-Scan"):
            with st.spinner("Gemini AI is analyzing clinical domains..."):
                raw_text = get_raw_text(up_file)
                parsed = gemini_ai_parse(raw_text)
                if parsed:
                    st.session_state.parsed_data = parsed
                    st.success("AI Synthesis Complete.")
        
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    tabs = st.tabs([
        "🌐 Equivalency", "🏥 Experience", "💉 Procedures", 
        "🔬 QIP & Audit", "👨‍🏫 Teaching", "📚 Seminars & CME", 
        "📝 Publications", "📄 Export"
    ])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Seniority Mapping")
        profile_db = client.table("profiles").select("*").eq("user_email", st.session_state.user_email).execute().data
        has_profile = len(profile_db) > 0
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if has_profile else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Seniority Level", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        active_c = st.multiselect("Target Systems", options=list(COUNTRY_KEY_MAP.keys()), default=["United Kingdom"])
        
        map_data = [{"Country": c, "Title": EQUIVALENCY_MAP[selected_tier].get(COUNTRY_KEY_MAP[c], "N/A")} for c in active_c]
        st.table(pd.DataFrame(map_data))
        
        if st.button("💾 Save Profile Settings"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier}, on_conflict="user_email").execute()
            st.toast("Profile Synced.")

    # 2. EXPERIENCE
    with tabs[1]:
        st.subheader("Clinical Rotations")
        for i, block in enumerate(st.session_state.parsed_data.get("rotations", [])):
            with st.expander(f"Rotation {i+1}", expanded=True):
                st.write(block)
                if st.button(f"Save Rotation {i+1}", key=f"rb_{i}"):
                    client.table("rotations").insert({"user_email": st.session_state.user_email, "description": str(block)}).execute()

    # 3. PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Logbook")
        
        for i, block in enumerate(st.session_state.parsed_data.get("procedures", [])):
            with st.expander(f"Skill {i+1}"):
                st.write(block)
                lvl = st.selectbox("Competency", ["Observed", "Supervised", "Independent"], key=f"pl_{i}")
                if st.button("Log Procedure", key=f"pb_{i}"):
                    client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": str(block), "level": lvl}).execute()

    # 4. QIP & AUDIT
    with tabs[3]:
        st.subheader("Quality Improvement & Clinical Audits")
        
        for i, block in enumerate(st.session_state.parsed_data.get("qips", [])):
            with st.expander(f"QIP Entry {i+1}"):
                st.write(block)
                if st.button("Save QIP", key=f"qb_{i}"):
                    client.table("projects").insert({"user_email": st.session_state.user_email, "title": str(block), "type": "QIP"}).execute()

    # 5. TEACHING
    with tabs[4]:
        st.subheader("Teaching Portfolio")
        for i, block in enumerate(st.session_state.parsed_data.get("teaching", [])):
            with st.expander(f"Teaching Session {i+1}"):
                st.write(block)
                if st.button("Save Teaching", key=f"tb_{i}"):
                    client.table("teaching").insert({"user_email": st.session_state.user_email, "title": str(block)}).execute()

    # 6. SEMINARS & CME
    with tabs[5]:
        st.subheader("Educational Courses & CPD")
        for i, block in enumerate(st.session_state.parsed_data.get("education", [])):
            with st.expander(f"Education Entry {i+1}"):
                st.write(block)
                if st.button("Log CME", key=f"eb_{i}"):
                    client.table("education").insert({"user_email": st.session_state.user_email, "course": str(block)}).execute()

    # 7. PUBLICATIONS
    with tabs[6]:
        st.subheader("Research & Publications")
        for i, block in enumerate(st.session_state.parsed_data.get("publications", [])):
            with st.expander(f"Detected Publication {i+1}"):
                st.write(block)
                if st.button("Save Publication", key=f"pubb_{i}"):
                    client.table("projects").insert({"user_email": st.session_state.user_email, "title": str(block), "type": "Publication"}).execute()

    # 8. EXPORT
    with tabs[7]:
        st.subheader("Final Portfolio Generation")
        if st.button("🏗️ Build AI-Standardized PDF"):
            st.info("Generating global equivalents and clinical verification...")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
