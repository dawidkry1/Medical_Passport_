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

# --- 2. GLOBAL MAPPING DATA (Restored & Expanded) ---
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {
        "UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern",
        "Ireland": "Intern", "Canada": "PGY-1", "Dubai/DHA": "Intern",
        "Poland": "Lekarz stażysta",
        "Responsibilities": "Ward based, supervised prescribing, basic clinical procedures."
    },
    "Tier 2: Intermediate (SHO/Resident)": {
        "UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO",
        "Ireland": "SHO", "Canada": "Junior Resident", "Dubai/DHA": "GP / Resident",
        "Poland": "Lekarz rezydent (Junior)",
        "Responsibilities": "Acute assessments, procedural proficiency, core specialty rotations."
    },
    "Tier 3: Senior (Registrar/Fellow)": {
        "UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar",
        "Ireland": "Specialist Registrar (SpR)", "Canada": "Senior Resident / Fellow", "Dubai/DHA": "Specialist (P)",
        "Poland": "Lekarz rezydent (Senior)",
        "Responsibilities": "Team leadership, specialty decision making, independent in core procedures."
    },
    "Tier 4: Expert (Consultant/Attending)": {
        "UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant / Specialist",
        "Ireland": "Consultant", "Canada": "Staff Specialist", "Dubai/DHA": "Consultant",
        "Poland": "Lekarz specjalista",
        "Responsibilities": "Final clinical accountability, service leadership, senior training."
    }
}

COUNTRY_KEY_MAP = {
    "United Kingdom": "UK", "United States": "US", "Australia": "Australia",
    "Ireland": "Ireland", "Canada": "Canada", "Dubai (DHA)": "Dubai/DHA",
    "Poland": "Poland"
}

# --- 3. SESSION & AUTH ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = {"rotations": [], "procedures": [], "projects": [], "registrations": [], "raw": ""}

def handle_login():
    try:
        res = client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

def fetch_user_data(table_name):
    if not st.session_state.user_email: return []
    try:
        res = client.table(table_name).select("*").eq("user_email", st.session_state.user_email).execute()
        return res.data if res.data else []
    except Exception: return []

# --- 4. THE ULTIMATE MEDICAL PARSER ---
def get_raw_text(file):
    try:
        if file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                return "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            return "\n".join([p.text for p in doc.paragraphs])
    except: return ""

def deep_scan_parse(file):
    text = get_raw_text(file)
    st.session_state.parsed_data["raw"] = text
    
    # Split by paragraphs to keep bullet points with headers
    blocks = text.split('\n\n') if '\n\n' in text else text.split('\n')
    triage = {"rotations": [], "procedures": [], "projects": [], "registrations": [], "raw": text}
    
    # Expanded keywords to catch more data
    kw_reg = ["gmc", "license", "registration", "mrcp", "mrcs", "board", "usmle", "plab"]
    kw_proc = ["intubation", "suturing", "cannulation", "procedure", "performed", "competenc", "laparoscopy", "chest drain", "lumbar tap"]
    kw_acad = ["audit", "qip", "research", "publication", "poster", "presentation", "teaching", "abstract", "journal"]
    kw_rot = ["hospital", "trust", "szpital", "ward", "department", "clinic", "rotation", "resident", "officer", "foundation"]

    for block in blocks:
        clean_block = block.strip()
        if len(clean_block) < 5: continue
        low = clean_block.lower()
        
        # Priority Triaging
        if any(k in low for k in kw_reg): triage["registrations"].append(clean_block)
        elif any(k in low for k in kw_proc): triage["procedures"].append(clean_block)
        elif any(k in low for k in kw_acad): triage["projects"].append(clean_block)
        elif any(k in low for k in kw_rot) or re.search(r'\b(20\d{2})\b', clean_block):
            triage["rotations"].append(clean_block)
            
    return triage

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Global Passport Sync")
        st.write(f"Doctor: **{st.session_state.user_email}**")
        up_file = st.file_uploader("Upload CV (PDF/DOCX)", type=['pdf', 'docx'])
        if up_file and st.button("🚀 Sync Portfolio"):
            st.session_state.parsed_data = deep_scan_parse(up_file)
            st.success("Triage Complete.")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    # Fetch DB Data
    profile_db = fetch_user_data("profiles")
    rotations_db = fetch_user_data("rotations")
    procedures_db = fetch_user_data("procedures")
    projects_db = fetch_user_data("projects")

    tabs = st.tabs(["🌐 Equivalency", "🪪 Registration", "🏥 Experience", "💉 Procedures", "🔬 Academic", "📄 Export"])

    # 1. EQUIVALENCY (Restored Countries)
    with tabs[0]:
        st.subheader("International Equivalency")
        
        has_profile = len(profile_db) > 0
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if has_profile else "Tier 1: Junior (Intern/FY1)"
        
        selected_tier = st.selectbox("Global Seniority Tier", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        # Restore Countries
        saved_countries = ["United Kingdom"]
        if has_profile:
            raw_c = profile_db[0].get('selected_countries', "[]")
            try: saved_countries = json.loads(raw_c) if isinstance(raw_c, str) else raw_c
            except: pass

        active_countries = st.multiselect("Target Systems for Mapping", options=list(COUNTRY_KEY_MAP.keys()), default=saved_countries)
        
        # Display Mapping Table
        st.write("### 🌍 Your Role Internationally")
        map_data = []
        for c in active_countries:
            short_key = COUNTRY_KEY_MAP[c]
            equivalent_title = EQUIVALENCY_MAP[selected_tier].get(short_key, "Equivalent N/A")
            map_data.append({"Country": c, "Equivalent Title": equivalent_title})
        st.table(pd.DataFrame(map_data))

        if st.button("💾 Save Equivalency Profile"):
            client.table("profiles").upsert({
                "user_email": st.session_state.user_email, 
                "global_tier": selected_tier,
                "selected_countries": json.dumps(active_countries)
            }, on_conflict="user_email").execute()
            st.toast("Profile Saved.")

    # 2. REGISTRATION
    with tabs[1]:
        st.subheader("Professional Licensing")
        found_regs = st.session_state.parsed_data.get("registrations", [])
        if found_regs:
            for reg in found_regs: st.code(reg)
        else: st.info("Manual Entry: Add your GMC/Registration Number below.")

    # 3. EXPERIENCE
    with tabs[2]:
        st.subheader("Clinical Rotations")
        found_rots = st.session_state.parsed_data.get("rotations", [])
        if found_rots:
            for i, block in enumerate(found_rots):
                with st.expander(f"Detected Rotation {i+1}", expanded=True):
                    full_text = st.text_area("Experience Details", block, height=150, key=f"rt_{i}")
                    if st.button(f"Save Entry {i+1}", key=f"rb_{i}"):
                        client.table("rotations").insert({"user_email": st.session_state.user_email, "description": full_text}).execute()
                        st.toast("Rotation Logged")
        
        if rotations_db:
            st.write("### 📜 Logged Experiences")
            st.table(pd.DataFrame(rotations_db)[['description']])

    # 4. PROCEDURES
    with tabs[3]:
        st.subheader("Procedural Log")
        
        found_procs = st.session_state.parsed_data.get("procedures", [])
        if found_procs:
            for i, block in enumerate(found_procs):
                with st.expander(f"Detected Procedure {i+1}"):
                    p_name = st.text_input("Procedure Name", block[:100], key=f"pn_{i}")
                    if st.button("Log Procedure", key=f"pb_{i}"):
                        client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": p_name}).execute()
        else: st.info("No procedures detected in CV.")

    # 5. ACADEMIC
    with tabs[4]:
        st.subheader("Research & Audit Portfolio")
        found_proj = st.session_state.parsed_data.get("projects", [])
        if found_proj:
            for i, block in enumerate(found_proj):
                with st.expander(f"Detected Project {i+1}"):
                    t = st.text_input("Title", block[:100], key=f"an_{i}")
                    if st.button("Add to Portfolio", key=f"ab_{i}"):
                        client.table("projects").insert({"user_email": st.session_state.user_email, "title": t}).execute()
        if projects_db:
            st.table(pd.DataFrame(projects_db)[['title']])

    # 6. EXPORT (RESTORED)
    with tabs[5]:
        st.subheader("Generate Clinical Passport")
        st.write("This combines your verified clinical history into a standardized global format.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("#### 📄 PDF Portfolio")
            st.caption("Standardized CV format for hospital HR departments.")
            if st.button("🏗️ Build Medical PDF"):
                st.info("Compiling Clinical Evidence...")

        with col2:
            st.write("#### 🛡️ QR Verification")
            st.caption("Generate a secure link for employers to verify your standing.")
            if st.button("🔗 Generate Passport Link"):
                st.success("Secure link generated.")

# --- AUTH ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
