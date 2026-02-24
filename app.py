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
    "Tier 1: Junior (Intern/FY1)": {"UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern"},
    "Tier 2: Intermediate (SHO/Resident)": {"UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO"},
    "Tier 3: Senior (Registrar/Fellow)": {"UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar"},
    "Tier 4: Expert (Consultant/Attending)": {"UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant"}
}

COUNTRY_KEY_MAP = {
    "United Kingdom": "UK", "United States": "US", "Australia": "Australia",
    "Ireland": "Ireland", "Canada": "Canada", "Dubai (DHA)": "Dubai/DHA"
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

# --- 4. ADVANCED CLINICAL PARSER ---
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
    
    lines = text.split('\n')
    triage = {"rotations": [], "procedures": [], "projects": [], "registrations": [], "raw": text}
    
    kw_reg = ["gmc", "license", "licence", "registration", "mrcp", "mrcs", "board", "usmle"]
    kw_proc = ["intubation", "suturing", "cannulation", "procedure", "performed", "competenc", "laparoscopy", "clinics", "tap", "drain"]
    kw_acad = ["audit", "qip", "research", "publication", "poster", "presentation", "teaching", "abstract", "journal"]
    kw_rot = ["hospital", "trust", "szpital", "ward", "department", "clinic", "rotation", "trainee", "resident", "officer"]

    current_block = []
    for line in lines:
        clean_line = line.strip()
        if not clean_line: continue
        
        # Break logic: A date or an uppercase header starts a new medical block
        if re.search(r'\b(20\d{2}|19\d{2})\b', clean_line) or (clean_line.isupper() and len(clean_line) > 5):
            if current_block:
                full_block = "\n".join(current_block)
                low = full_block.lower()
                if any(k in low for k in kw_reg): triage["registrations"].append(full_block)
                elif any(k in low for k in kw_proc): triage["procedures"].append(full_block)
                elif any(k in low for k in kw_acad): triage["projects"].append(full_block)
                elif any(k in low for k in kw_rot): triage["rotations"].append(full_block)
            current_block = [clean_line]
        else:
            current_block.append(clean_line)

    if current_block: triage["rotations"].append("\n".join(current_block))
    return triage

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Global Sync")
        st.write(f"Logged in: **{st.session_state.user_email}**")
        up_file = st.file_uploader("Upload Medical CV (PDF/DOCX)", type=['pdf', 'docx'])
        if up_file and st.button("🚀 Run Deep Scan"):
            st.session_state.parsed_data = deep_scan_parse(up_file)
            st.success("Analysis Complete.")
        
        with st.expander("🛠️ Raw Data Debugger"):
            st.text(st.session_state.parsed_data.get("raw", "")[:800])

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    # Pre-fetch DB data for manual displays
    rotations_db = fetch_user_data("rotations")
    procedures_db = fetch_user_data("procedures")
    projects_db = fetch_user_data("projects")
    profile_db = fetch_user_data("profiles")

    tabs = st.tabs(["🌐 Equivalency", "🪪 Registration", "🏥 Experience", "💉 Procedures", "🔬 Academic", "📄 Export"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Seniority Mapping")
        has_profile = len(profile_db) > 0
        curr_tier = profile_db[0].get('global_tier', "Tier 1: Junior (Intern/FY1)") if has_profile else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Global Standing", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        if st.button("💾 Save Profile Status"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier}, on_conflict="user_email").execute()
            st.toast("Profile Synced.")

    # 2. REGISTRATION
    with tabs[1]:
        st.subheader("Medical Licensing & Registrations")
        found_regs = st.session_state.parsed_data.get("registrations", [])
        if found_regs:
            for reg in found_regs: st.code(reg)
        else: st.info("No registration markers found.")

    # 3. EXPERIENCE (Fixing the Cut-offs)
    with tabs[2]:
        st.subheader("Clinical Rotations")
        
        found_rots = st.session_state.parsed_data.get("rotations", [])
        
        if found_rots:
            st.write("### 📥 Imported from CV")
            for i, block in enumerate(found_rots):
                with st.expander(f"Review Entry {i+1}", expanded=True):
                    full_text = st.text_area("Details", block, height=180, key=f"rt_{i}")
                    if st.button(f"Save Rotation {i+1}", key=f"rb_{i}"):
                        client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": full_text.split('\n')[0][:100], "description": full_text}).execute()
                        st.toast("Rotation Saved!")

        st.divider()
        st.write("### 📜 Saved Clinical Record")
        if rotations_db: st.table(pd.DataFrame(rotations_db)[['hospital', 'description']])

    # 4. PROCEDURES
    with tabs[3]:
        st.subheader("Procedural Competency Log")
        
        found_procs = st.session_state.parsed_data.get("procedures", [])
        if found_procs:
            for i, block in enumerate(found_procs):
                with st.expander(f"Detected Skill {i+1}"):
                    st.write(block)
                    if st.button("Add to Log", key=f"pb_{i}"):
                        client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": block[:100]}).execute()
        
        with st.form("manual_proc"):
            st.write("Manual Entry")
            pn = st.text_input("Procedure Name")
            if st.form_submit_button("Log Skill"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": pn}).execute()
                st.rerun()

    # 5. ACADEMIC
    with tabs[4]:
        st.subheader("Academic & Research Portfolio")
        found_projects = st.session_state.parsed_data.get("projects", [])
        if found_projects:
            for i, block in enumerate(found_projects):
                with st.expander(f"Detected Project {i+1}"):
                    st.write(block)
                    if st.button("Confirm Project", key=f"ab_{i}"):
                        client.table("projects").insert({"user_email": st.session_state.user_email, "title": block[:100]}).execute()
        
        if projects_db: st.table(pd.DataFrame(projects_db)[['title']])

    # 6. EXPORT
    with tabs[5]:
        st.subheader("Generate Clinical Passport")
        st.write("Combine all verified rotations, procedures, and research into a single global document.")
        if st.button("🏗️ Build Verified Portfolio"):
            st.success("Compiling data... PDF generation engine active.")

# --- LOGIN GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
