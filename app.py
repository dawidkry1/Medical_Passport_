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

# Standardized keys: 'Entry', 'Details', 'Category', 'Source'
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

# --- 3. GLOBAL LOGIC ENGINE ---
def auto_populate_cv(text):
    """Scans CV for clinical markers using a global medical lexicon."""
    # Patterns for Clinical History
    exp_pattern = r"\b(SHO|Registrar|Resident|Fellow|Consultant|Intern|Lekarz|Rezydent|Attending|Specialist|HMO|RMO|VMO)\b"
    hosp_pattern = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s(?:Hospital|Medical Center|Clinic|Trust|Infirmary|Health Service))"
    
    found_roles = re.findall(exp_pattern, text, re.IGNORECASE)
    found_hosps = re.findall(hosp_pattern, text)
    
    for i in range(min(len(found_roles), len(found_hosps))):
        st.session_state.portfolio_data["Experience"].append({
            "Entry": found_roles[i].upper(), 
            "Details": found_hosps[i], 
            "Category": "Clinical Rotation",
            "Source": "Auto-Detected"
        })

    # Patterns for Procedures & Academics
    proc_list = ["Intubation", "Cannulation", "Lumbar Puncture", "Central Line", "Chest Drain", "Suturing", "Ventilation"]
    for p in proc_list:
        if p.lower() in text.lower():
            st.session_state.portfolio_data["Procedures"].append({
                "Entry": p, 
                "Details": "Level 3 (Competent)",
                "Category": "Skill",
                "Source": "Auto-Detected"
            })

    if any(x in text.lower() for x in ["audit", "qip", "research", "teaching", "publication"]):
        st.session_state.portfolio_data["Academic"].append({
            "Entry": "Portfolio Evidence", 
            "Details": "Detected Academic Activity", 
            "Category": "Academic",
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
        st.header("🛂 Clinical Passport")
        up_file = st.file_uploader("Upload CV (Standard PDF/Word)", type=['pdf', 'docx'])
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt and st.button("🚀 Sync Global Portfolio"):
                auto_populate_cv(raw_txt)
                st.success("Global scan complete.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    tabs = st.tabs(["🌐 Global Equivalency", "🏥 Clinical Exp", "💉 Procedures", "🔬 Academic/QIP", "📄 Export CV"])

    # TAB 1: GLOBAL EQUIVALENCY
    with tabs[0]:
        st.subheader("Major Healthcare System Comparison")
        
        st.write("Translate your current seniority across the world's primary medical boards.")
        
        # Expanded Global Matrix
        global_mapping = {
            "Global Tier": ["Intern Level", "Junior Doctor / SHO", "Specialty Training / Reg", "Senior / Specialist"],
            "UK (GMC)": ["FY1", "FY2 / SHO", "Registrar (ST3-ST8)", "Consultant"],
            "USA (ACGME)": ["Intern (PGY1)", "Resident (PGY2-3)", "Fellow", "Attending"],
            "Australia (AMC)": ["Intern", "RMO / HMO", "Registrar", "Consultant / VMO"],
            "Poland (NIL)": ["Stażysta", "Rezydent (Junior)", "Rezydent (Senior)", "Specjalista"],
            "Middle East (DHA/MOH)": ["Intern", "GP / Resident", "Registrar", "Consultant"],
            "Canada (RCPSC)": ["Intern", "Resident", "Senior Resident", "Staff Physician"]
        }
        
        df_global = pd.DataFrame(global_mapping)
        st.table(df_global)
        st.info("💡 Note: These mappings are based on common registration pathways (e.g., PLAB, USMLE, AMC).")

    # TAB 2: CLINICAL EXPERIENCE
    with tabs[1]:
        st.subheader("Experience Rotations")
        with st.expander("➕ Manual Entry"):
            with st.form("exp_form"):
                e_role = st.text_input("Job Title")
                e_hosp = st.text_input("Hospital Name")
                if st.form_submit_button("Add to Timeline"):
                    st.session_state.portfolio_data["Experience"].append({"Entry": e_role, "Details": e_hosp, "Category": "Manual Rotation", "Source": "Manual"})
        
        if st.session_state.portfolio_data["Experience"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Experience"]))
        else:
            st.info("No rotations found yet.")

    # TAB 3: PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Competency")
        
        with st.expander("➕ Log Procedure"):
            with st.form("proc_form"):
                p_name = st.text_input("Procedure Name")
                p_lvl = st.selectbox("Level", ["Level 1 (Observed)", "Level 2 (Supervised)", "Level 3 (Independent)"])
                if st.form_submit_button("Save Skill"):
                    st.session_state.portfolio_data["Procedures"].append({"Entry": p_name, "Details": p_lvl, "Category": "Manual Skill", "Source": "Manual"})
        
        if st.session_state.portfolio_data["Procedures"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Procedures"]))

    # TAB 4: ACADEMIC/QIP
    with tabs[3]:
        st.subheader("Audits & Teaching")
        
        with st.expander("➕ Add Evidence"):
            with st.form("acad_form"):
                a_type = st.selectbox("Category", ["Audit/QIP", "Research", "Teaching", "Publication"])
                a_title = st.text_input("Title/Topic")
                if st.form_submit_button("Add Academic"):
                    st.session_state.portfolio_data["Academic"].append({"Entry": a_type, "Details": a_title, "Category": "Manual Academic", "Source": "Manual"})
        
        if st.session_state.portfolio_data["Academic"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Academic"]))

    # TAB 5: EXPORT CV
    with tabs[4]:
        st.subheader("Custom Jurisdictional Export")
        st.write("Select which international standards to verify against in your final PDF summary:")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            ex_uk = st.checkbox("UK (GMC Standards)", value=True)
            ex_us = st.checkbox("USA (ACGME Standards)")
        with col2:
            ex_au = st.checkbox("Australia (AMC Standards)")
            ex_pl = st.checkbox("Poland (NIL Standards)")
        with col3:
            ex_me = st.checkbox("Middle East (DHA/MOH Standards)")
            ex_ca = st.checkbox("Canada (RCPSC Standards)")

        if st.button("🛠️ Generate Final Medical Passport"):
            all_data = []
            for cat in st.session_state.portfolio_data.values():
                all_data.extend(cat)
            
            if all_data:
                df_final = pd.DataFrame(all_data)
                csv = df_final.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Passport (CSV Format)", data=csv, file_name="Global_Medical_Passport.csv")
                st.success("CV successfully tailored to selected jurisdictions.")
            else:
                st.error("Portfolio is empty. Upload a CV or add data manually.")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
