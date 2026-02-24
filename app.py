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

# --- 3. AUTO-DETECTION ENGINE ---
def auto_populate_cv(text):
    """Rule-based extraction for clinical markers."""
    exp_pattern = r"\b(SHO|Registrar|Resident|Fellow|Consultant|Intern|Lekarz|Rezydent|Attending|Specialist|HMO|RMO)\b"
    hosp_pattern = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s(?:Hospital|Medical Center|Clinic|Trust|Infirmary))"
    
    found_roles = re.findall(exp_pattern, text, re.IGNORECASE)
    found_hosps = re.findall(hosp_pattern, text)
    
    for i in range(min(len(found_roles), len(found_hosps))):
        st.session_state.portfolio_data["Experience"].append({
            "Entry": found_roles[i].upper(), 
            "Details": found_hosps[i], 
            "Category": "Clinical Rotation",
            "Source": "Auto-Detected"
        })

    proc_list = ["Intubation", "Cannulation", "Lumbar Puncture", "Central Line", "Chest Drain", "Suturing"]
    for p in proc_list:
        if p.lower() in text.lower():
            st.session_state.portfolio_data["Procedures"].append({
                "Entry": p, "Details": "Level 3 (Competent)", "Category": "Skill", "Source": "Auto"
            })

    if any(x in text.lower() for x in ["audit", "qip", "research", "teaching"]):
        st.session_state.portfolio_data["Academic"].append({
            "Entry": "Portfolio Evidence", "Details": "Identified in CV", "Category": "Academic", "Source": "Auto"
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
        st.header("🛂 Portfolio Sync")
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt and st.button("🚀 Sync All Categories"):
                auto_populate_cv(raw_txt)
                st.success("CV Data Parsed.")

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")
    
    tabs = st.tabs(["🌐 Dynamic Equivalency", "🏥 Experience", "💉 Procedures", "🔬 Academic/QIP", "📄 Export"])

    # TAB 1: DYNAMIC EQUIVALENCY
    with tabs[0]:
        st.subheader("Jurisdictional Seniority Engine")
        
        
        # 1. Choose Countries
        available_countries = ["UK (GMC)", "USA (ACGME)", "Australia (AMC)", "Poland (NIL)", "Middle East (DHA)", "Canada (RCPSC)"]
        selected_countries = st.multiselect("Select Countries to Compare:", available_countries, default=["UK (GMC)", "Poland (NIL)"])
        
        # 2. Choose Grade
        tier_options = ["Intern / Stażysta", "Junior Doctor (SHO / Rezydent)", "Specialty Trainee (Registrar)", "Senior (Consultant / Specjalista)"]
        my_grade = st.selectbox("Select Your Current Grade:", tier_options)
        
        # Mapping Data
        master_mapping = {
            "Intern / Stażysta": {
                "UK (GMC)": "Foundation Year 1 (FY1)",
                "USA (ACGME)": "Intern (PGY-1)",
                "Australia (AMC)": "Intern",
                "Poland (NIL)": "Stażysta",
                "Middle East (DHA)": "Intern",
                "Canada (RCPSC)": "Junior Resident"
            },
            "Junior Doctor (SHO / Rezydent)": {
                "UK (GMC)": "FY2 / SHO",
                "USA (ACGME)": "Resident (PGY-2)",
                "Australia (AMC)": "RMO / HMO",
                "Poland (NIL)": "Rezydent (Młodszy)",
                "Middle East (DHA)": "Resident / GP",
                "Canada (RCPSC)": "Resident (PGY-2)"
            },
            "Specialty Trainee (Registrar)": {
                "UK (GMC)": "Registrar (ST3+)",
                "USA (ACGME)": "Senior Resident / Fellow",
                "Australia (AMC)": "Registrar",
                "Poland (NIL)": "Rezydent (Starszy)",
                "Middle East (DHA)": "Registrar",
                "Canada (RCPSC)": "Senior Resident"
            },
            "Senior (Consultant / Specjalista)": {
                "UK (GMC)": "Consultant",
                "USA (ACGME)": "Attending Physician",
                "Australia (AMC)": "Consultant / Specialist",
                "Poland (NIL)": "Specjalista",
                "Middle East (DHA)": "Consultant",
                "Canada (RCPSC)": "Staff Physician"
            }
        }
        
        if selected_countries:
            results = {"Jurisdiction": [], "Equivalent Grade": []}
            for country in selected_countries:
                results["Jurisdiction"].append(country)
                results["Equivalent Grade"].append(master_mapping[my_grade][country])
            
            st.table(pd.DataFrame(results))
            st.success(f"Verified: Your status as a **{my_grade}** translates as shown above.")
        else:
            st.warning("Please select at least one country to see the equivalency mapping.")

    # TAB 2: EXPERIENCE (Manual + Auto)
    with tabs[1]:
        st.subheader("Clinical Rotations")
        with st.expander("➕ Add Manual Entry"):
            with st.form("exp_form"):
                e_role = st.text_input("Role")
                e_hosp = st.text_input("Hospital")
                if st.form_submit_button("Save"):
                    st.session_state.portfolio_data["Experience"].append({"Entry": e_role, "Details": e_hosp, "Category": "Manual Rotation", "Source": "Manual"})
        
        if st.session_state.portfolio_data["Experience"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Experience"]))

    # TAB 3: PROCEDURES
    with tabs[2]:
        st.subheader("Procedural Competency")
        
        with st.expander("➕ Log Procedure"):
            with st.form("proc_form"):
                p_name = st.text_input("Procedure Name")
                p_lvl = st.selectbox("Level", ["Level 1 (Observed)", "Level 2 (Supervised)", "Level 3 (Independent)"])
                if st.form_submit_button("Log"):
                    st.session_state.portfolio_data["Procedures"].append({"Entry": p_name, "Details": p_lvl, "Category": "Manual Skill", "Source": "Manual"})
        
        if st.session_state.portfolio_data["Procedures"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Procedures"]))

    # TAB 4: ACADEMIC/QIP
    with tabs[3]:
        st.subheader("Research & Audits")
        
        with st.expander("➕ Add Academic Activity"):
            with st.form("acad_form"):
                a_type = st.selectbox("Type", ["Audit/QIP", "Research", "Teaching", "Publication"])
                a_title = st.text_input("Title/Description")
                if st.form_submit_button("Add to Passport"):
                    st.session_state.portfolio_data["Academic"].append({"Entry": a_type, "Details": a_title, "Category": "Manual Academic", "Source": "Manual"})
        
        if st.session_state.portfolio_data["Academic"]:
            st.table(pd.DataFrame(st.session_state.portfolio_data["Academic"]))

    # TAB 5: EXPORT
    with tabs[4]:
        st.subheader("Generate Tailored CV Summary")
        st.write("The exported file will include equivalency statements for:")
        for c in selected_countries:
            st.write(f"✅ {c}")
            
        if st.button("🛠️ Export Final Passport"):
            all_data = []
            for cat in st.session_state.portfolio_data.values():
                all_data.extend(cat)
            
            if all_data:
                # Add the selected equivalencies to the export data
                for country in selected_countries:
                    all_data.append({
                        "Entry": f"{country} Equivalency", 
                        "Details": master_mapping[my_grade][country], 
                        "Category": "Jurisdictional Statement", 
                        "Source": "System Calculated"
                    })
                
                df_export = pd.DataFrame(all_data)
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Tailored CV (CSV)", data=csv, file_name="Tailored_Medical_Passport.csv")
            else:
                st.error("No clinical data to export.")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
