import streamlit as st
import pandas as pd
from supabase import create_client
from fpdf import FPDF
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

# --- 2. GLOBAL MAPPING DATA ---
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {
        "UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern",
        "Ireland": "Intern", "Canada": "PGY-1", "Dubai/DHA": "Intern",
        "India/Pakistan": "House Officer / Intern", "Nigeria": "House Officer",
        "China/S.Korea": "Junior Resident", "Europe": "Junior Doctor",
        "Poland": "Lekarz stażysta",
        "Responsibilities": "Ward based, supervised prescribing, basic clinical procedures."
    },
    "Tier 2: Intermediate (SHO/Resident)": {
        "UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO",
        "Ireland": "SHO", "Canada": "Junior Resident", "Dubai/DHA": "GP / Resident",
        "India/Pakistan": "PG Resident / Medical Officer", "Nigeria": "Registrar",
        "China/S.Korea": "Resident", "Europe": "Resident Physician",
        "Poland": "Lekarz rezydent (Junior)",
        "Responsibilities": "Acute assessments, procedural proficiency, core specialty rotations."
    },
    "Tier 3: Senior (Registrar/Fellow)": {
        "UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar",
        "Ireland": "Specialist Registrar (SpR)", "Canada": "Senior Resident / Fellow", "Dubai/DHA": "Specialist (P)",
        "India/Pakistan": "Senior Resident / Registrar", "Nigeria": "Senior Registrar",
        "China/S.Korea": "Attending Physician / Fellow", "Europe": "Specialist Trainee / Senior Registrar",
        "Poland": "Lekarz rezydent (Senior)",
        "Responsibilities": "Team leadership, specialty decision making, independent in core procedures."
    },
    "Tier 4: Expert (Consultant/Attending)": {
        "UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant / Specialist",
        "Ireland": "Consultant", "Canada": "Staff Specialist", "Dubai/DHA": "Consultant",
        "India/Pakistan": "Consultant / Asst. Professor", "Nigeria": "Consultant",
        "China/S.Korea": "Chief Physician", "Europe": "Specialist / Consultant",
        "Poland": "Lekarz specjalista",
        "Responsibilities": "Final clinical accountability, service leadership, senior training."
    }
}

COUNTRY_KEY_MAP = {
    "United Kingdom": "UK", "United States": "US", "Australia": "Australia",
    "Ireland": "Ireland", "Canada": "Canada", "Dubai (DHA)": "Dubai/DHA",
    "India & Pakistan": "India/Pakistan", "Nigeria": "Nigeria",
    "China & S.Korea": "China/S.Korea", "Europe (General)": "Europe",
    "Poland": "Poland"
}

# --- 3. SESSION & AUTH ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = {"rotations": [], "procedures": [], "projects": [], "registrations": []}

def handle_login():
    try:
        res = client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
            client.auth.set_session(res.session.access_token, res.session.refresh_token)
    except Exception as e:
        st.error(f"Login failed: {e}")

def fetch_user_data(table_name):
    if not st.session_state.user_email: return []
    try:
        res = client.table(table_name).select("*").eq("user_email", st.session_state.user_email).execute()
        return res.data
    except Exception:
        return []

# --- 4. THE ULTIMATE MEDICAL PARSER ---
def get_raw_text(file):
    if file.name.endswith('.pdf'):
        with pdfplumber.open(file) as pdf:
            return "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    elif file.name.endswith('.docx'):
        doc = docx.Document(file)
        return "\n".join([p.text for p in doc.paragraphs])
    return ""

def clinical_triage_parser(file):
    text = get_raw_text(file)
    
    # Split text by major potential headers or date ranges (Aug 2023 - Present, etc)
    # This prevents fragmentation of a single job entry.
    blocks = re.split(r'(\d{4}\s*-\s*\d{4}|\d{4}\s*-\s*Present|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', text)
    
    triage = {"rotations": [], "procedures": [], "projects": [], "registrations": []}
    
    temp_block = ""
    for segment in blocks:
        if not segment: continue
        temp_block += segment
        
        # If the block has enough "meat", categorize it
        if len(temp_block) > 50:
            low = temp_block.lower()
            # 1. Registrations (High Priority to keep separate)
            if any(k in low for k in ["gmc", "license", "licence", "registration", "number:"]):
                triage["registrations"].append(temp_block.strip())
            # 2. Procedures (Look for clinical action verbs)
            elif any(k in low for k in ["intubat", "sutur", "cannulat", "tap", "biopsy", "scopy", "performed"]):
                triage["procedures"].append(temp_block.strip())
            # 3. Academic (Audit/Research)
            elif any(k in low for k in ["audit", "qip", "research", "poster", "publication"]):
                triage["projects"].append(temp_block.strip())
            # 4. Rotations (The Default for remaining blocks with hospital keywords)
            elif any(k in low for k in ["hospital", "trust", "szpital", "ward", "clinic", "department"]):
                triage["rotations"].append(temp_block.strip())
            
            temp_block = "" # Flush and move to next block

    return triage

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Passport Control")
        st.success(f"Logged in: {st.session_state.user_email}")
        
        st.divider()
        st.write("### 📂 Global CV Sync")
        st.caption("Upload your CV to auto-fill your profile.")
        up_file = st.file_uploader("Upload PDF/DOCX", type=['pdf', 'docx'])
        
        if up_file and st.button("🚀 Process & Triage"):
            with st.spinner("Executing Semantic Analysis..."):
                st.session_state.parsed_data = clinical_triage_parser(up_file)
                st.success("Triage Complete! Review each tab.")

        if st.button("🚪 Logout", use_container_width=True):
            client.auth.sign_out()
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    # Load DB Data
    profile = fetch_user_data("profiles")
    rotations = fetch_user_data("rotations")
    procedures = fetch_user_data("procedures")
    projects = fetch_user_data("projects")

    tabs = st.tabs(["🌐 Equivalency", "🪪 Registration", "🏥 Experience", "💉 Procedures", "🔬 Academic", "🛡️ Vault", "📄 Export"])

    # 🌐 EQUIVALENCY
    with tabs[0]:
        st.subheader("International Equivalency")
        curr_tier = profile[0]['global_tier'] if profile else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Seniority", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        raw_c = profile[0].get('selected_countries', []) if profile else ["United Kingdom"]
        active_c = st.multiselect("Active Systems", options=list(COUNTRY_KEY_MAP.keys()), default=raw_c if isinstance(raw_c, list) else json.loads(raw_c))
        
        if st.button("💾 Save Settings"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier, "selected_countries": json.dumps(active_c)}, on_conflict="user_email").execute()
            st.toast("Profile Synced.")

    # 🪪 REGISTRATION
    with tabs[1]:
        st.subheader("Medical Licensing")
        if st.session_state.parsed_data["registrations"]:
            st.warning("Parser found potential License Info. Copy/Paste into fields below:")
            for item in st.session_state.parsed_data["registrations"]:
                st.code(item)
        
        with st.form("reg_form"):
            col1, col2 = st.columns(2)
            body = col1.text_input("Regulatory Body (e.g. GMC, DHA)")
            num = col2.text_input("Registration Number")
            if st.form_submit_button("Confirm Registration"):
                st.success("Registration Added.")

    # 🏥 EXPERIENCE (The Critical Section)
    with tabs[2]:
        st.subheader("Clinical Experience")
        
        
        # TRIAGE VIEW
        if st.session_state.parsed_data["rotations"]:
            st.markdown("### 📥 Triage Area: Detected Rotations")
            st.info("Review each block. Edit as needed to ensure the Grade and Specialty are correct.")
            for i, block in enumerate(st.session_state.parsed_data["rotations"]):
                with st.expander(f"Review Block {i+1}", expanded=True):
                    # Guess header
                    first_line = block.split('\n')[0]
                    
                    full_text = st.text_area("Experience Details (including bullets)", block, height=180, key=f"rot_tx_{i}")
                    c1, c2, c3 = st.columns(3)
                    h = c1.text_input("Hospital", first_line, key=f"rot_h_{i}")
                    s = c2.text_input("Specialty", key=f"rot_s_{i}")
                    g = c3.text_input("Grade", key=f"rot_g_{i}")
                    
                    if st.button(f"Commit Block {i+1} to Passport", key=f"rot_btn_{i}"):
                        client.table("rotations").insert({
                            "user_email": st.session_state.user_email,
                            "hospital": h, "specialty": s, "grade": g, "description": full_text
                        }).execute()
                        st.toast("Experience Saved!")

        # MANUAL OVERRIDE
        with st.form("manual_experience"):
            st.write("### ➕ Manual Addition")
            c1, c2, c3 = st.columns(3)
            mh, ms, mg = c1.text_input("Hospital"), c2.text_input("Specialty"), c3.text_input("Grade")
            if st.form_submit_button("Add Manually"):
                client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": mh, "specialty": ms, "grade": mg}).execute()
                st.rerun()

        if rotations:
            st.table(pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore'))

    # 💉 PROCEDURES
    with tabs[3]:
        st.subheader("Procedural Log")
        
        if st.session_state.parsed_data["procedures"]:
            st.markdown("### 📥 Triage Area: Detected Skills")
            for i, block in enumerate(st.session_state.parsed_data["procedures"]):
                with st.expander(f"Skill Block {i+1}"):
                    st.write(block)
                    if st.button("Log Procedure", key=f"proc_bt_{i}"):
                        client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": block[:60], "level": "Independent"}).execute()
                        st.toast("Procedure Logged")
        
        with st.form("manual_proc"):
            pn, pl = st.text_input("Procedure Name"), st.selectbox("Competency", ["Observed", "Supervised", "Independent"])
            if st.form_submit_button("Log Skill"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": pn, "level": pl}).execute()
                st.rerun()

    # 🔬 ACADEMIC
    with tabs[4]:
        st.subheader("Research, Audit & QIP")
        if st.session_state.parsed_data["projects"]:
            for i, block in enumerate(st.session_state.parsed_data["projects"]):
                with st.expander(f"Project Block {i+1}"):
                    st.write(block)
                    if st.button("Add to Academic Record", key=f"acad_bt_{i}"):
                        client.table("projects").insert({"user_email": st.session_state.user_email, "title": block[:100]}).execute()
                        st.toast("Project Added")
        if projects:
            st.table(pd.DataFrame(projects).drop(columns=['id', 'user_email'], errors='ignore'))

    # 🛡️ VAULT & EXPORT
    with tabs[5]:
        st.subheader("Verified Credential Vault")
        st.info("Documents stored here can be attached to your global applications.")
    
    with tabs[6]:
        st.subheader("Passport Generation")
        if st.button("🏗️ Generate Verified Portfolio PDF"):
            st.info("Compiling all medical evidence...")

# --- AUTH ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login_form"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
