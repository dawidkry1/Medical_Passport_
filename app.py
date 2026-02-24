import streamlit as st
import pandas as pd
from supabase import create_client
import pdfplumber
import docx
import re
from io import BytesIO

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
if 'portfolio_data' not in st.session_state:
    st.session_state.portfolio_data = {
        "Experience": [],
        "Procedures": [],
        "Academic": []
    }

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 3. AUTO-POPULATION LOGIC ---
def auto_populate_cv(text):
    """Scans CV for clinical history, procedures, and academic work."""
    # 1. Experience Scan
    exp_pattern = r"\b(SHO|Registrar|Resident|Fellow|Consultant|Intern|Lekarz|Rezydent)\b"
    hosp_pattern = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s(?:Hospital|Medical Center|Clinic|Trust))"
    roles = re.findall(exp_pattern, text, re.IGNORECASE)
    hosps = re.findall(hosp_pattern, text)
    
    for i in range(min(len(roles), len(hosps))):
        st.session_state.portfolio_data["Experience"].append({"Role": roles[i].upper(), "Location": hosps[i], "Type": "Clinical"})

    # 2. Procedure Scan
    proc_keywords = ["Intubation", "Cannulation", "Lumbar Puncture", "Catheterization", "Suturing", "Biopsy"]
    for proc in proc_keywords:
        if proc.lower() in text.lower():
            st.session_state.portfolio_data["Procedures"].append({"Procedure": proc, "Level": "Level 3 (Supervised)"})

    # 3. Academic/QIP Scan
    if "audit" in text.lower() or "qip" in text.lower():
        st.session_state.portfolio_data["Academic"].append({"Type": "Audit/QIP", "Title": "Detected from CV", "Role": "Lead"})
    if "publication" in text.lower() or "journal" in text.lower():
        st.session_state.portfolio_data["Academic"].append({"Type": "Publication", "Title": "Detected from CV", "Role": "Author"})

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
        st.header("🛂 Clinical Passport Control")
        up_file = st.file_uploader("Upload CV for Auto-Population", type=['pdf', 'docx'])
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt and st.button("🚀 Auto-Populate All Tabs"):
                auto_populate_cv(raw_txt)
                st.success("CV Scanned! Check tabs for results.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Medical Career Passport")
    
    tabs = st.tabs(["🌐 Seniority Mapping", "🏥 Rotations", "💉 Procedures", "🔬 QIP & Academic", "📄 PDF Export"])

    # TAB 1: SENIORITY MAPPING
    with tabs[0]:
        st.subheader("Global Equivalency Selection")
        
        target_country = st.selectbox("Compare my current grade to:", ["United Kingdom (GMC)", "United States (ACGME)", "Australia (AMC)", "Poland (NIL)"])
        
        # Dynamic comparison table
        base_grades = ["Intern / FY1", "SHO / PGY-2", "Registrar / Fellow", "Consultant / Attending"]
        mapping = {
            "United Kingdom (GMC)": ["Foundation Year 1", "Foundation Year 2 / SHO", "Registrar (ST3+)", "Consultant"],
            "United States (ACGME)": ["Intern (PGY-1)", "Resident (PGY-2/3)", "Fellow", "Attending Physician"],
            "Australia (AMC)": ["Intern", "Resident (RMO/HMO)", "Registrar", "Consultant / Specialist"],
            "Poland (NIL)": ["Stażysta", "Rezydent (Młodszy)", "Rezydent (Starszy)", "Specjalista"]
        }
        
        st.write(f"### Current Comparison: **{target_country}**")
        comp_df = pd.DataFrame({
            "Global Tier": base_grades,
            f"{target_country} Equivalent": mapping[target_country]
        })
        st.table(comp_df)

    # TAB 2: ROTATIONS (Auto + Manual)
    with tabs[1]:
        st.subheader("Clinical Experience")
        with st.expander("➕ Add Experience Manually"):
            with st.form("manual_exp"):
                m_role = st.text_input("Job Title")
                m_hosp = st.text_input("Hospital")
                if st.form_submit_button("Add to Passport"):
                    st.session_state.portfolio_data["Experience"].append({"Role": m_role, "Location": m_hosp, "Type": "Manual Entry"})
        
        if st.session_state.portfolio_data["Experience"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Experience"]))
        else:
            st.info("No rotations found yet.")

    # TAB 3: PROCEDURES (Auto + Manual)
    with tabs[2]:
        st.subheader("Procedural Logbook")
        
        with st.expander("➕ Add Procedure Manually"):
            with st.form("manual_proc"):
                m_proc = st.text_input("Procedure Name")
                m_lvl = st.selectbox("Competency Level", ["Level 1 (Observed)", "Level 2 (Supervised)", "Level 3 (Independent)"])
                if st.form_submit_button("Log Procedure"):
                    st.session_state.portfolio_data["Procedures"].append({"Procedure": m_proc, "Level": m_lvl})
        
        if st.session_state.portfolio_data["Procedures"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Procedures"]))

    # TAB 4: QIP & ACADEMIC
    with tabs[3]:
        st.subheader("Research & Audits")
        
        with st.expander("➕ Add Research/Audit Manually"):
            with st.form("manual_acad"):
                m_type = st.selectbox("Category", ["Audit/QIP", "Publication", "Teaching", "Poster"])
                m_title = st.text_input("Title/Topic")
                if st.form_submit_button("Save Academic Entry"):
                    st.session_state.portfolio_data["Academic"].append({"Type": m_type, "Title": m_title, "Role": "Contributor"})
        
        if st.session_state.portfolio_data["Academic"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Academic"]))

    # TAB 5: PDF EXPORT
    with tabs[4]:
        st.subheader("Export Verified Medical Passport")
        st.write("Select which jurisdictional standards to include in the exported CV:")
        
        export_gmc = st.checkbox("Include UK (GMC) Equivalency", value=True)
        export_amc = st.checkbox("Include Australia (AMC) Equivalency")
        export_us = st.checkbox("Include US (ACGME) Equivalency")
        
        if st.button("🛠️ Generate Exportable CV (PDF)"):
            st.info("Generating PDF format using your selected jurisdictions...")
            # For this MVP, we provide a CSV backup, but a real PDF generator (FPDF) can be added here
            export_df = pd.DataFrame(st.session_state.portfolio_data["Experience"])
            st.download_button("Download Clinical History", data=export_df.to_csv(), file_name="Medical_Passport.csv")
            st.success("Passport Ready for Export.")

# --- LOGIN GATE ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
