import streamlit as st
import pandas as pd
from supabase import create_client
import pdfplumber
import docx
import re

# --- 1. CORE CONFIG ---
st.set_page_config(page_title="Global Medical Passport", page_icon="🏥", layout="wide")

# Connection Setup
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase_client = create_client(URL, KEY)
except Exception as e:
    st.error(f"Configuration Error: {e}")

# --- 2. SESSION STATE ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'detected_roles' not in st.session_state:
    st.session_state.detected_roles = []

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 3. AUTO-DETECTION ENGINE (REGEX) ---
def extract_clinical_data(text):
    """Detects medical roles and hospitals using pattern matching."""
    # Pattern 1: Seniority/Role (e.g., SHO, Registrar, Resident, Consultant)
    role_pattern = r"\b(SHO|Senior House Officer|Registrar|Resident|Fellow|Consultant|Intern|FY1|FY2|ST\d|CT\d)\b"
    
    # Pattern 2: Typical Hospital Keywords
    hospital_pattern = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s(?:Hospital|Medical Center|Clinic|Infirmary|Trust))"
    
    # Pattern 3: Dates (e.g., 2022 - 2024 or Aug 2021)
    date_pattern = r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|20\d{2})[-–\s]+(?:Present|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|20\d{2}))\b"

    roles = re.findall(role_pattern, text, re.IGNORECASE)
    hospitals = re.findall(hospital_pattern, text)
    
    # Clean and pair findings
    findings = []
    unique_hospitals = list(set(hospitals))
    unique_roles = list(set(roles))
    
    for i in range(min(len(unique_roles), len(unique_hospitals))):
        findings.append({
            "Role": unique_roles[i].upper(),
            "Institution": unique_hospitals[i],
            "Status": "Detected"
        })
    
    return findings

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
        return text
    except: return ""

# --- 4. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Portfolio")
        st.info("Currently using **Rule-Based Detection** (Offline/Stable)")
        
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt:
                st.success("File Processed")
                if st.button("🔍 Auto-Detect Career"):
                    st.session_state.detected_roles = extract_clinical_data(raw_txt)

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    tabs = st.tabs(["🌐 Seniority Mapping", "🏥 Clinical Experience", "📊 Career Metrics"])

    # 1. EQUIVALENCY (The Doctor-to-Doctor View)
    with tabs[0]:
        st.subheader("International Grade Comparison")
        st.write("Ensuring your CV translates correctly for international medical boards.")
        
        comparison_data = [
            {"Region": "UK (GMC)", "Equivalent": "Foundation Year 2 (SHO)", "Level": "Generalist"},
            {"Region": "US (ACGME)", "Equivalent": "PGY-2 Resident", "Level": "Specialty Training"},
            {"Region": "Australia (AMC)", "Equivalent": "RMO (Resident)", "Level": "Hospital Medical Officer"}
        ]
        st.table(pd.DataFrame(comparison_data))

    # 2. CLINICAL EXPERIENCE (The Auto-Detected results)
    with tabs[1]:
        st.subheader("Auto-Detected Clinical History")
        if st.session_state.detected_roles:
            df_roles = pd.DataFrame(st.session_state.detected_roles)
            st.dataframe(df_roles, use_container_width=True)
            st.success(f"Detected {len(st.session_state.detected_roles)} distinct clinical entries.")
        else:
            st.info("Upload your CV to see your clinical timeline automatically populated.")

    # 3. METRICS
    with tabs[2]:
        st.subheader("Clinical Summary")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Detected Hospitals", len(set([d['Institution'] for d in st.session_state.detected_roles])))
        with col2:
            st.metric("Detected Seniority Levels", len(set([d['Role'] for d in st.session_state.detected_roles])))

# --- LOGIN GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
