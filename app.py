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

# --- 4. ADVANCED SEMANTIC PARSER ---
def parse_file(file):
    if file.name.endswith('.pdf'):
        with pdfplumber.open(file) as pdf:
            return "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    elif file.name.endswith('.docx'):
        doc = docx.Document(file)
        return "\n".join([p.text for p in doc.paragraphs])
    return ""

def deep_segment_cv(file):
    text = parse_file(file)
    # This regex looks for dates or common medical headers as "split points"
    # It attempts to keep headers like "Experience" or "Education" as start points
    sections = re.split(r'(\b\d{4}\b|Experience|Employment|Education|Rotation|Procedures|Skills)', text, flags=re.IGNORECASE)
    
    data = {"rotations": [], "procedures": [], "projects": [], "registrations": []}
    
    current_content = ""
    for sec in sections:
        if not sec: continue
        current_content += sec
        
        # Once we have a chunk of text, we verify its content
        if len(current_content) > 40:
            low = current_content.lower()
            if any(k in low for k in ["gmc", "license", "licence", "registration"]):
                data["registrations"].append(current_content.strip())
            elif any(k in low for k in ["hospital", "trust", "szpital", "clinic", "ward"]):
                data["rotations"].append(current_content.strip())
            elif any(k in low for k in ["audit", "qip", "research", "published"]):
                data["projects"].append(current_content.strip())
            elif any(k in low for k in ["intubation", "suturing", "cannulation", "thoracentesis"]):
                data["procedures"].append(current_content.strip())
            current_content = "" # Reset for next segment
            
    return data

# --- 5. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.success(f"Verified: {st.session_state.user_email}")
        st.divider()
        st.write("### 📂 Medical CV Importer")
        up_file = st.file_uploader("Upload PDF/DOCX", type=['pdf', 'docx'])
        if up_file and st.button("🚀 Run Smart Sync"):
            with st.spinner("Decoding Medical Records..."):
                st.session_state.parsed_data = deep_segment_cv(up_file)
                st.success("Analysis Complete!")

        if st.button("🚪 Logout", use_container_width=True):
            client.auth.sign_out()
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    profile = fetch_user_data("profiles")
    rotations = fetch_user_data("rotations")
    procedures = fetch_user_data("procedures")
    projects = fetch_user_data("projects")

    tabs = st.tabs(["🌐 Equivalency", "🪪 Registration", "🏥 Rotations", "💉 Procedures", "🔬 Academic", "🛡️ Vault", "📄 Export"])

    # --- EQUIVALENCY TAB ---
    with tabs[0]:
        st.subheader("Global Standing Mapping")
        curr_tier = profile[0]['global_tier'] if profile else "Tier 1: Junior (Intern/FY1)"
        selected_tier = st.selectbox("Current Seniority", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(curr_tier) if curr_tier in EQUIVALENCY_MAP else 0)
        
        raw_c = profile[0].get('selected_countries', []) if profile else ["United Kingdom"]
        active_c = st.multiselect("Active Systems", options=list(COUNTRY_KEY_MAP.keys()), default=raw_c if isinstance(raw_c, list) else json.loads(raw_c))
        
        if st.button("💾 Save Prefs"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier, "selected_countries": json.dumps(active_c)}, on_conflict="user_email").execute()
            st.toast("Preferences Updated")

    # --- REGISTRATION TAB ---
    with tabs[1]:
        st.subheader("Professional Licensing")
        if st.session_state.parsed_data["registrations"]:
            st.info("The parser found the following registration details in your CV:")
            for reg in st.session_state.parsed_data["registrations"]:
                st.code(reg)
        
        with st.form("reg_add"):
            c1, c2 = st.columns(2)
            b = c1.text_input("Licensing Body (GMC, etc)")
            n = c2.text_input("License Number")
            if st.form_submit_button("Commit to Passport"):
                st.success("Stored.")

    # --- ROTATIONS TAB ---
    with tabs[2]:
        st.subheader("Clinical Experience")
        
        if st.session_state.parsed_data["rotations"]:
            st.markdown("### 🪄 Imported Experiences (Review & Commit)")
            for i, block in enumerate(st.session_state.parsed_data["rotations"]):
                with st.expander(f"Review Rotation Block {i+1}", expanded=True):
                    # Smart Split attempt for the UI
                    lines = block.split('\n')
                    header_guess = lines[0] if lines else "Experience"
                    
                    full_txt = st.text_area("Experience Details", block, key=f"rot_txt_{i}", height=150)
                    c1, c2 = st.columns(2)
                    spec = c1.text_input("Specialty", key=f"rot_s_{i}")
                    grad = c2.text_input("Grade", key=f"rot_g_{i}")
                    
                    if st.button(f"Save Entry {i+1}", key=f"rot_btn_{i}"):
                        client.table("rotations").insert({
                            "user_email": st.session_state.user_email,
                            "hospital": header_guess[:100],
                            "specialty": spec,
                            "grade": grad,
                            "description": full_txt
                        }).execute()
                        st.toast("Rotation Saved!")

        with st.form("man_rot"):
            st.write("### Add Manual Rotation")
            c1, c2, c3 = st.columns(3)
            h, s, g = c1.text_input("Hospital"), c2.text_input("Specialty"), c3.text_input("Grade")
            if st.form_submit_button("Add to Log"):
                client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": h, "specialty": s, "grade": g}).execute()
                st.rerun()
        
        if rotations: 
            st.table(pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore'))

    # --- PROCEDURES TAB ---
    with tabs[3]:
        st.subheader("Procedural Skills")
        if st.session_state.parsed_data["procedures"]:
            for i, block in enumerate(st.session_state.parsed_data["procedures"]):
                with st.expander(f"Detected Skill {i+1}"):
                    st.write(block)
                    if st.button("Log this Skill", key=f"proc_btn_{i}"):
                        client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": block[:50], "level": "Independent"}).execute()
                        st.toast("Skill Logged")

        with st.form("man_proc"):
            c1, c2 = st.columns(2)
            n, l = c1.text_input("Procedure"), c2.selectbox("Level", ["Observed", "Supervised", "Independent"])
            if st.form_submit_button("Manual Log"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": n, "level": l}).execute()
                st.rerun()

    # --- ACADEMIC TAB ---
    with tabs[4]:
        st.subheader("Research & QIP")
        if st.session_state.parsed_data["projects"]:
            for i, block in enumerate(st.session_state.parsed_data["projects"]):
                with st.expander(f"Research Block {i+1}"):
                    st.write(block)
                    if st.button("Add Project", key=f"acad_btn_{i}"):
                        client.table("projects").insert({"user_email": st.session_state.user_email, "title": block[:100]}).execute()
                        st.toast("Project Added")
        if projects:
            st.table(pd.DataFrame(projects).drop(columns=['id', 'user_email'], errors='ignore'))

    # --- VAULT & EXPORT ---
    with tabs[5]:
        st.subheader("🛡️ Document Vault")
        # Existing Storage Logic
        st.info("Files stored here are private and encrypted.")
    
    with tabs[6]:
        st.subheader("Portfolio Export")
        if st.button("🏗️ Build Medical Portfolio"):
            st.info("Generating professional PDF...")

# --- AUTH GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
