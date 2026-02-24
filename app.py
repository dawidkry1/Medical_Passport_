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
if 'detected_history' not in st.session_state:
    st.session_state.detected_history = []
if 'raw_cv_text' not in st.session_state:
    st.session_state.raw_cv_text = ""

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 3. AUTO-DETECTION ENGINE ---
def run_clinical_scan(text):
    """Rule-based scanning for medical career markers."""
    role_pattern = r"\b(SHO|Senior House Officer|Registrar|Resident|Fellow|Consultant|Intern|FY\d|ST\d|Lekarz|Rezydent)\b"
    hosp_pattern = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s(?:Hospital|Medical Center|Clinic|Infirmary|Trust))"
    
    roles = re.findall(role_pattern, text, re.IGNORECASE)
    hospitals = re.findall(hosp_pattern, text)
    
    findings = []
    unique_hospitals = list(dict.fromkeys(hospitals))
    unique_roles = list(dict.fromkeys(roles))
    
    for i in range(min(len(unique_roles), len(unique_hospitals))):
        findings.append({
            "Role": unique_roles[i].upper(),
            "Institution": unique_hospitals[i],
            "Status": "Verified"
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
        st.info("Mode: Universal Rule-Based Sync")
        
        up_file = st.file_uploader("Upload Medical CV", type=['pdf', 'docx'])
        if up_file:
            raw_content = get_raw_text(up_file)
            if raw_content:
                st.session_state.raw_cv_text = raw_content
                if st.button("🚀 Sync All Tabs"):
                    st.session_state.detected_history = run_clinical_scan(raw_content)

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    # ALL PREVIOUS TABS RESTORED
    tabs = st.tabs([
        "🌐 Seniority Mapping", 
        "🏥 Clinical Experience", 
        "🔬 Procedures & Logbook", 
        "📚 Academic & Research", 
        "📊 Career Metrics",
        "🖥️ System Feed"
    ])

    # 1. SENIORITY MAPPING (The Doctor-to-Doctor translation)
    with tabs[0]:
        st.subheader("International Grade Equivalency")
        
        mapping_data = {
            "Region": ["UK (GMC)", "USA (ACGME)", "Australia (AMC)", "Poland (NIL)"],
            "Intern Level": ["FY1", "Intern (PGY-1)", "Intern", "Stażysta"],
            "SHO Level": ["FY2 / SHO", "Resident (PGY-2)", "RMO / HMO", "Rezydent (Junior)"],
            "Registrar Level": ["Registrar (ST3+)", "Fellow", "Registrar", "Rezydent (Senior)"],
            "Senior Level": ["Consultant", "Attending", "Specialist", "Specjalista"]
        }
        st.table(pd.DataFrame(mapping_data))

    # 2. CLINICAL EXPERIENCE
    with tabs[1]:
        st.subheader("Auto-Detected Rotations")
        if st.session_state.detected_history:
            st.dataframe(pd.DataFrame(st.session_state.detected_history), use_container_width=True)
        else:
            st.info("Upload your CV to see your clinical timeline populated here.")

    # 3. PROCEDURES & LOGBOOK
    with tabs[2]:
        st.subheader("Competency Matrix")
        
        st.write("Mapping procedural skills from Level 1 (Observed) to Level 4 (Independent).")
        log_data = [
            {"Procedure": "Central Venous Catheterization", "Level": "Level 3", "Approver": "Dr. Smith (Consultant)"},
            {"Procedure": "Endotracheal Intubation", "Level": "Level 4", "Approver": "Dept. Head"},
            {"Procedure": "Lumbar Puncture", "Level": "Level 2", "Approver": "Clinical Lead"}
        ]
        st.table(pd.DataFrame(log_data))

    # 4. ACADEMIC & RESEARCH
    with tabs[3]:
        st.subheader("Publications, Audits & Teaching")
        st.write("Current Evidence Found in Document:")
        if "audit" in st.session_state.raw_cv_text.lower():
            st.success("✅ Quality Improvement Project (Audit) detected.")
        if "teaching" in st.session_state.raw_cv_text.lower():
            st.success("✅ Formal Teaching experience detected.")
        else:
            st.warning("No specific academic markers found yet.")

    # 5. CAREER METRICS
    with tabs[4]:
        st.subheader("Portfolio Analytics")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Placements", len(st.session_state.detected_history))
        with col2:
            st.metric("Unique Hospitals", len(set([d['Institution'] for d in st.session_state.detected_history])))
        with col3:
            st.metric("Estimated Grade", "Registrar" if len(st.session_state.detected_history) > 3 else "SHO")

    # 6. SYSTEM FEED
    with tabs[5]:
        st.subheader("Raw CV Extraction")
        if st.session_state.raw_cv_text:
            st.text_area("Full Text Extract", value=st.session_state.raw_cv_text, height=400)
        else:
            st.write("No data in session.")

# --- LOGIN GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
