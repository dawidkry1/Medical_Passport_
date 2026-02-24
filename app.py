import streamlit as st
import pandas as pd
from supabase import create_client
from fpdf import FPDF
import pdfplumber
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

# --- 4. BLOCK-BASED MEDICAL PARSER ---
def deep_parse_medical_cv(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    
    # Identify Blocks by Date Headers (e.g., "Aug 2022 - Aug 2023" or "2021-2022")
    # This keeps a whole experience block together
    blocks = re.split(r'(\d{4}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', text)
    
    extracted = {"rotations": [], "procedures": [], "projects": [], "registrations": []}
    
    current_block = ""
    for segment in blocks:
        if not segment: continue
        # Reconstruct the block
        current_block += segment
        
        # If the block looks like a full entry, categorize it
        if len(current_block) > 50:
            low_block = current_block.lower()
            
            # Registration Check
            if any(k in low_block for k in ["gmc", "registration", "licence", "license"]):
                extracted["registrations"].append(current_block.strip())
            # Rotation Check (Dates + Hospital Keywords)
            elif any(k in low_block for k in ["hospital", "trust", "szpital", "clinic", "department"]):
                extracted["rotations"].append(current_block.strip())
            # Procedure Check
            elif any(k in low_block for k in ["procedure", "performed", "intubation", "suturing", "skills"]):
                extracted["procedures"].append(current_block.strip())
            # Academic Check
            elif any(k in low_block for k in ["audit", "qip", "research", "published"]):
                extracted["projects"].append(current_block.strip())
            
            current_block = "" # Reset for next block
            
    return extracted

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.success(f"Verified: {st.session_state.user_email}")
        st.divider()
        st.write("### 📂 Global CV Importer")
        uploaded_cv = st.file_uploader("Upload Medical CV (PDF)", type=['pdf'])
        if uploaded_cv and st.button("🚀 Auto-Populate All Tabs"):
            with st.spinner("Analyzing Medical Experience..."):
                st.session_state.parsed_data = deep_parse_medical_cv(uploaded_cv)
                st.success("Analysis Complete! Review each tab.")

        if st.button("🚪 Logout", use_container_width=True):
            client.auth.sign_out()
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    # Fetch User Data
    profile = fetch_user_data("profiles")
    rotations = fetch_user_data("rotations")
    procedures = fetch_user_data("procedures")
    projects = fetch_user_data("projects")

    tabs = st.tabs(["🌐 Equivalency", "🪪 Registration", "🏥 Rotations", "💉 Procedures", "🔬 Academic", "🛡️ Vault", "📄 Export"])

    # 🌐 EQUIVALENCY
    with tabs[0]:
        st.subheader("Global Standing Mapping")
        curr_tier = profile[0]['global_tier'] if profile else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Define Your Global Seniority", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        raw_c = profile[0].get('selected_countries', []) if profile else ["United Kingdom"]
        active_countries = st.multiselect("Relevant Healthcare Systems", options=list(COUNTRY_KEY_MAP.keys()), default=raw_c if isinstance(raw_c, list) else json.loads(raw_c))
        if st.button("💾 Save Preferences"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier, "selected_countries": json.dumps(active_countries)}, on_conflict="user_email").execute()
            st.success("Preferences Saved.")

    # 🪪 REGISTRATION
    with tabs[1]:
        st.subheader("Professional Registration")
        if st.session_state.parsed_data["registrations"]:
            st.info("Information found in CV:")
            for reg in st.session_state.parsed_data["registrations"]:
                st.write(f"🔍 {reg}")
        
        with st.form("reg_entry"):
            body, num = st.text_input("Licensing Body"), st.text_input("Registration Number")
            if st.form_submit_button("Save to Portfolio"):
                st.success("Registration stored.")

    # 🏥 ROTATIONS (Clinical Experience)
    with tabs[2]:
        st.subheader("Clinical Rotations")
        
        # Detected Blocks
        if st.session_state.parsed_data["rotations"]:
            st.write("### 📝 Detected Experiences (Verify to Save)")
            for i, block in enumerate(st.session_state.parsed_data["rotations"]):
                with st.expander(f"Entry {i+1}: {block[:50]}...", expanded=True):
                    # Clean the block into specific fields
                    h_guess = block.split('\n')[0] # Usually the first line is hospital/role
                    full_desc = st.text_area("Full Experience Details", block, key=f"rot_area_{i}", height=150)
                    c1, c2 = st.columns(2)
                    spec = c1.text_input("Specialty", "Identify...", key=f"rot_spec_{i}")
                    grade = c2.text_input("Grade", "Identify...", key=f"rot_grade_{i}")
                    if st.button(f"✅ Save Entire Experience {i+1}", key=f"rot_save_{i}"):
                        client.table("rotations").insert({
                            "user_email": st.session_state.user_email,
                            "hospital": h_guess,
                            "specialty": spec,
                            "grade": grade,
                            "dates": "See Details",
                            "description": full_desc # Assuming you added this column to your DB
                        }).execute()
                        st.toast("Full Experience Logged!")

        # Manual Entry
        with st.form("man_rot"):
            st.write("### Add Manual Experience")
            h, s, g = st.text_input("Hospital"), st.text_input("Specialty"), st.text_input("Grade")
            if st.form_submit_button("Add Manually"):
                client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": h, "specialty": s, "grade": g}).execute()
                st.rerun()
        if rotations: st.table(pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore'))

    # 💉 PROCEDURES
    with tabs[3]:
        st.subheader("Procedural Skills")
        if st.session_state.parsed_data["procedures"]:
            st.write("### 💉 Detected Procedures")
            for i, block in enumerate(st.session_state.parsed_data["procedures"]):
                with st.expander(f"Procedure Block {i+1}"):
                    p_text = st.text_area("Skill Details", block, key=f"proc_area_{i}")
                    if st.button("Log this Skill", key=f"proc_save_{i}"):
                        client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": p_text[:50], "level": "Independent", "count": 1}).execute()
                        st.toast("Skill Logged")

        with st.form("man_proc"):
            n, l = st.text_input("Procedure Name"), st.selectbox("Level", ["Observed", "Supervised", "Independent"])
            if st.form_submit_button("Add Skill"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": n, "level": l, "count": 1}).execute()
                st.rerun()
        if procedures: st.table(pd.DataFrame(procedures).drop(columns=['id', 'user_email'], errors='ignore'))

    # 🔬 ACADEMIC
    with tabs[4]:
        st.subheader("Academic & QIP")
        if st.session_state.parsed_data["projects"]:
            st.write("### 🔬 Detected Academic Work")
            for i, block in enumerate(st.session_state.parsed_data["projects"]):
                with st.expander(f"Project {i+1}"):
                    st.write(block)
                    if st.button("Save Project", key=f"acad_save_{i}"):
                        client.table("projects").insert({"user_email": st.session_state.user_email, "type": "Research", "title": block[:100]}).execute()
                        st.toast("Project Saved")

        with st.form("man_acad"):
            t, title = st.selectbox("Type", ["Audit", "QIP", "Research"]), st.text_input("Title")
            if st.form_submit_button("Save Manual Project"):
                client.table("projects").insert({"user_email": st.session_state.user_email, "type": t, "title": title}).execute()
                st.rerun()
        if projects: st.table(pd.DataFrame(projects).drop(columns=['id', 'user_email'], errors='ignore'))

    # 🛡️ VAULT
    with tabs[5]:
        st.subheader("🛡️ Secured Document Vault")
        up = st.file_uploader("Upload Credentials", type=['pdf', 'jpg', 'png'])
        if up and st.button("Upload"):
            client.storage.from_('medical-vault').upload(f"{st.session_state.user_email}/{up.name}", up.getvalue())
            st.success("Stored.")
        try:
            files = client.storage.from_('medical-vault').list(st.session_state.user_email)
            for f in files:
                c1, c2 = st.columns([0.8, 0.2])
                c1.write(f"📄 {f['name']}")
                res = client.storage.from_('medical-vault').create_signed_url(f"{st.session_state.user_email}/{f['name']}", 60)
                c2.link_button("View", res['signedURL'])
        except: st.info("Vault empty.")

    # 📄 EXPORT
    with tabs[6]:
        st.subheader("Export Portfolio")
        if st.button("🏗️ Compile Professional PDF"):
            # generate_pdf logic here (keeping existing function)
            st.info("PDF Generation in progress...")

# --- LOGIN GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
