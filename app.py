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
# Initializing with empty lists to prevent DataFrame errors (Lines 127/184)
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
        res = supabase_client.auth.sign_in_with_password({
            "email": st.session_state.login_email, 
            "password": st.session_state.login_password
        })
        if res.user:
            st.session_state.authenticated = True
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 3. AUTO-POPULATION LOGIC ---
def auto_populate_cv(text):
    """Rule-based extraction for roles, hospitals, and academic work."""
    # Clinical History
    exp_pattern = r"\b(SHO|Registrar|Resident|Fellow|Consultant|Intern|Lekarz|Rezydent|Medical Officer)\b"
    hosp_pattern = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s(?:Hospital|Medical Center|Clinic|Trust|Infirmary))"
    
    found_roles = re.findall(exp_pattern, text, re.IGNORECASE)
    found_hosps = re.findall(hosp_pattern, text)
    
    for i in range(min(len(found_roles), len(found_hosps))):
        st.session_state.portfolio_data["Experience"].append({
            "Role": found_roles[i].upper(), 
            "Location": found_hosps[i], 
            "Source": "Auto-Detected"
        })

    # Procedures
    proc_list = ["Intubation", "Cannulation", "Lumbar Puncture", "Central Line", "Chest Drain", "Suturing"]
    for p in proc_list:
        if p.lower() in text.lower():
            st.session_state.portfolio_data["Procedures"].append({
                "Procedure": p, 
                "Level": "Level 3 (Independent)",
                "Source": "Auto-Detected"
            })

    # Academic / Audit
    if any(x in text.lower() for x in ["audit", "qip", "quality improvement"]):
        st.session_state.portfolio_data["Academic"].append({
            "Type": "Audit/QIP", 
            "Title": "Detected Project", 
            "Source": "Auto-Detected"
        })

def get_raw_text(file):
    try:
        if file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                return "\n".join([page.extract_text() or "" for page in pdf.pages])
        elif file.name.endswith('.docx'):
            doc = docx.Document(file)
            return "\n".join([p.text for p in doc.paragraphs])
    except: return ""

# --- 4. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Passport Control")
        up_file = st.file_uploader("Upload Medical CV", type=['pdf', 'docx'])
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt and st.button("🚀 Auto-Populate from CV"):
                auto_populate_cv(raw_txt)
                st.success("CV Scanned Successfully.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Medical Career Passport")
    
    tabs = st.tabs(["🌐 Equivalency", "🏥 Experience", "💉 Procedures", "🔬 Academic/QIP", "📄 Export"])

    # TAB 1: EQUIVALENCY
    with tabs[0]:
        st.subheader("International Grade Selection")
        
        target_country = st.selectbox("Compare to Jurisdiction:", ["UK (GMC)", "USA (ACGME)", "Australia (AMC)", "Poland (NIL)"])
        
        base = ["Intern / FY1", "SHO / PGY-2", "Registrar / Fellow", "Consultant / Attending"]
        mapping = {
            "UK (GMC)": ["Foundation Year 1", "Foundation Year 2 / SHO", "Registrar (ST3+)", "Consultant"],
            "USA (ACGME)": ["Intern (PGY-1)", "Resident (PGY-2/3)", "Fellow", "Attending Physician"],
            "Australia (AMC)": ["Intern", "Resident (RMO/HMO)", "Registrar", "Consultant / Specialist"],
            "Poland (NIL)": ["Stażysta", "Rezydent (Młodszy)", "Rezydent (Starszy)", "Specjalista"]
        }
        
        eq_df = pd.DataFrame({"Global Tier": base, f"{target_country} Equivalent": mapping[target_country]})
        st.table(eq_df)

    # TAB 2: EXPERIENCE (Line 127 Fix)
    with tabs[1]:
        st.subheader("Clinical Rotations")
        with st.expander("➕ Add Manual Entry"):
            with st.form("add_exp"):
                r = st.text_input("Role")
                l = st.text_input("Hospital")
                if st.form_submit_button("Save"):
                    st.session_state.portfolio_data["Experience"].append({"Role": r, "Location": l, "Source": "Manual"})
        
        if st.session_state.portfolio_data["Experience"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Experience"]))
        else:
            st.info("No experience data found yet.")

    # TAB 3: PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Logbook")
        
        with st.expander("➕ Log Manual Procedure"):
            with st.form("add_proc"):
                p_name = st.text_input("Procedure")
                p_lvl = st.selectbox("Level", ["Level 1 (Observed)", "Level 2 (Supervised)", "Level 3 (Independent)"])
                if st.form_submit_button("Log"):
                    st.session_state.portfolio_data["Procedures"].append({"Procedure": p_name, "Level": p_lvl, "Source": "Manual"})
        
        if st.session_state.portfolio_data["Procedures"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Procedures"]))

    # TAB 4: ACADEMIC (Line 184 Fix)
    with tabs[3]:
        st.subheader("Audits, Teaching & Research")
        
        with st.expander("➕ Add Academic Entry"):
            with st.form("add_acad"):
                a_type = st.selectbox("Type", ["Audit/QIP", "Teaching", "Research", "Publication"])
                a_title = st.text_input("Title")
                if st.form_submit_button("Add Entry"):
                    st.session_state.portfolio_data["Academic"].append({"Type": a_type, "Title": a_title, "Source": "Manual"})
        
        if st.session_state.portfolio_data["Academic"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Academic"]))

    # TAB 5: EXPORT
    with tabs[4]:
        st.subheader("Jurisdictional Export")
        st.write("Choose jurisdictions to include in your verified summary:")
        col1, col2 = st.columns(2)
        with col1:
            inc_uk = st.checkbox("Include UK (GMC) Standards", value=True)
            inc_us = st.checkbox("Include US (ACGME) Standards")
        with col2:
            inc_au = st.checkbox("Include Australia (AMC) Standards")
            inc_pl = st.checkbox("Include Poland (NIL) Standards")

        if st.button("🛠️ Generate Medical Passport"):
            # Create summary dataframe for export
            export_list = st.session_state.portfolio_data["Experience"]
            if export_list:
                df_export = pd.DataFrame(export_list)
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Verified Passport (CSV)", data=csv, file_name="Medical_Passport_Export.csv")
            else:
                st.error("No data available to export.")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
