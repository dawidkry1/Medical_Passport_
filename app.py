import streamlit as st
import time
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
import io

# --- 1. CORE CONFIGURATION ---
st.set_page_config(page_title="Medical Passport", page_icon="🏥", layout="wide")

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
client = create_client(URL, KEY)

# EXPANDED GLOBAL MAPPING
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {
        "UK": "Foundation Year 1", 
        "US": "PGY-1 (Intern)", 
        "Australia": "Intern",
        "Ireland": "Intern",
        "Canada": "PGY-1 (Junior Resident)",
        "EU/International": "Junior Doctor / Intern",
        "Responsibilities": "Ward based, supervised prescribing, basic clinical procedures."
    },
    "Tier 2: Intermediate (SHO/Resident)": {
        "UK": "FY2 / Core Trainee", 
        "US": "PGY-2/3 (Resident)", 
        "Australia": "Resident / RMO",
        "Ireland": "Senior House Officer (SHO)",
        "Canada": "Junior Resident (R2/R3)",
        "EU/International": "Resident Physician",
        "Responsibilities": "Acute assessments, procedural proficiency, core specialty rotations."
    },
    "Tier 3: Senior (Registrar/Fellow)": {
        "UK": "ST3+ / Registrar", 
        "US": "Chief Resident / Fellow", 
        "Australia": "Registrar",
        "Ireland": "Registrar / Specialist Registrar",
        "Canada": "Senior Resident / Fellow",
        "EU/International": "Specialist Trainee / Senior Registrar",
        "Responsibilities": "Team leadership, specialty decision making, independent in core procedures."
    },
    "Tier 4: Expert (Consultant/Attending)": {
        "UK": "Consultant / SAS", 
        "US": "Attending Physician", 
        "Australia": "Consultant / Specialist",
        "Ireland": "Consultant",
        "Canada": "Staff Physician / Specialist",
        "EU/International": "Specialist / Consultant",
        "Responsibilities": "Final clinical accountability, service leadership, senior training."
    }
}

# --- 2. PROFESSIONAL PDF GENERATOR ---
class MedicalCV(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Professional Medical Portfolio', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 8, 'Verified Clinical Credential Document', 0, 1, 'C')
        self.ln(10)

    def section_header(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 10, f" {title}", 0, 1, 'L', fill=True)
        self.ln(3)

def generate_pdf(email, profile, rotations, procedures, projects, selected_countries):
    pdf = MedicalCV()
    pdf.add_page()
    
    # Physician Identity
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, f"Physician: {email}", 0, 1)
    
    # Professional Standing (Filtered by Country)
    tier_key = profile[0]['global_tier'] if profile else None
    if tier_key in EQUIVALENCY_MAP:
        data = EQUIVALENCY_MAP[tier_key]
        pdf.section_header("Professional Standing & International Equivalency")
        pdf.set_font('Arial', 'B', 11)
        
        # Mapping Display logic
        country_keys = {
            "United Kingdom": "UK", "United States": "US", "Australia": "Australia",
            "Ireland": "Ireland", "Canada": "Canada", "EU/International": "EU/International"
        }
        
        for display_name in selected_countries:
            key = country_keys[display_name]
            pdf.cell(0, 7, f"{display_name} Equivalent: {data[key]}", 0, 1)
            
        pdf.ln(2)
        pdf.set_font('Arial', 'I', 10)
        pdf.multi_cell(0, 6, f"Scope of Practice: {data['Responsibilities']}")
    else:
        pdf.section_header("Professional Standing")
        pdf.cell(0, 7, "Clinical Grade: Pending Selection", 0, 1)
    
    pdf.ln(5)

    # Clinical Experience
    pdf.section_header("Clinical Experience & Placements")
    for r in rotations:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"{r['hospital']} - {r['specialty']}", 0, 1)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 6, f"Local Grade: {r['grade']} | Dates: {r['dates']}", 0, 1)
        pdf.ln(2)

    # Procedural Logbook
    pdf.ln(5)
    pdf.section_header("Procedural Logbook Summary")
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(80, 8, "Procedure", 1)
    pdf.cell(60, 8, "Competency Level", 1)
    pdf.cell(30, 8, "Count", 1, 1)
    pdf.set_font('Arial', '', 9)
    for p in procedures:
        pdf.cell(80, 8, str(p['procedure']), 1)
        pdf.cell(60, 8, str(p['level']), 1)
        pdf.cell(30, 8, str(p['count']), 1, 1)

    # Academic/QIP
    pdf.ln(10)
    pdf.section_header("Academic Portfolio, Research & QIP")
    for pr in projects:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"{pr['type']}: {pr['title']}", 0, 1)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 6, f"Role: {pr['role']} ({pr['year']})", 0, 1)
        pdf.ln(2)

    return pdf.output(dest='S').encode('latin-1')

# --- 3. DATABASE UTILITIES ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""

def fetch_user_data(table_name):
    try:
        res = client.table(table_name).select("*").eq("user_email", st.session_state.user_email).execute()
        return res.data
    except: return []

# --- 4. THE PASSPORT DASHBOARD ---
def main_dashboard():
    st.sidebar.title("🏥 Clinical Session")
    st.sidebar.write(f"Logged in: {st.session_state.user_email}")
    if st.sidebar.button("Log Out"):
        st.session_state.authenticated = False
        st.rerun()

    st.title("🩺 Professional Medical Passport")
    st.caption("International Physician Credential Vault & Global Equivalency Ledger")

    profile = fetch_user_data("profiles")
    rotations = fetch_user_data("rotations")
    procedures = fetch_user_data("procedures")
    projects = fetch_user_data("projects")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🌐 Equivalency", "🏥 Rotations", "💉 Procedures", "🔬 Academic", "🛡️ Vault", "📄 Export CV"
    ])

    with tab1:
        st.subheader("Global Standing Mapping")
        st.info("Your selection here defines your clinical 'weight' when translated into other healthcare systems.")
        current_tier = profile[0]['global_tier'] if profile else list(EQUIVALENCY_MAP.keys())[0]
        try:
            t_idx = list(EQUIVALENCY_MAP.keys()).index(current_tier)
        except: t_idx = 0
        
        selected_tier = st.selectbox("Define Your Clinical Standing", list(EQUIVALENCY_MAP.keys()), index=t_idx)
        t_data = EQUIVALENCY_MAP[selected_tier]
        
        # Grid display for visual confirmation
        st.write("### International Comparison Preview")
        c1, c2, c3 = st.columns(3)
        c1.metric("UK", t_data["UK"])
        c2.metric("US", t_data["US"])
        c3.metric("Canada", t_data["Canada"])
        
        c4, c5, c6 = st.columns(3)
        c4.metric("Australia", t_data["Australia"])
        c5.metric("Ireland", t_data["Ireland"])
        c6.metric("EU/Int.", t_data["EU/International"])
        
        if st.button("💾 Lock Standing to Passport"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier}, on_conflict="user_email").execute()
            st.success("Global Standing Updated."); st.rerun()

    with tab2:
        st.subheader("Clinical Experience Ledger")
        if rotations: st.table(pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_rot"):
            h, s, d, g = st.text_input("Hospital"), st.text_input("Specialty"), st.text_input("Dates (e.g. Aug 2024 - Feb 2025)"), st.text_input("Local Grade")
            if st.form_submit_button("Add Rotation"):
                client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": h, "specialty": s, "dates": d, "grade": g}).execute()
                st.rerun()

    with tab3:
        st.subheader("Procedural Log")
        if procedures: 
            df_p = pd.DataFrame(procedures).drop(columns=['id', 'user_email'], errors='ignore')
            st.table(df_p)
        with st.form("add_proc"):
            n, l, c = st.text_input("Procedure Name"), st.selectbox("Independence Level", ["Observed", "Supervised", "Independent", "Assessor"]), st.number_input("Lifetime Count", 1)
            if st.form_submit_button("Log Procedure"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": n, "level": l, "count": c}).execute()
                st.rerun()

    with tab4:
        st.subheader("Academic, QIP & Research")
        if projects: st.table(pd.DataFrame(projects).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_proj"):
            t = st.selectbox("Category", ["Clinical Audit", "Research", "QIP", "Teaching", "Leadership"])
            title, r, y = st.text_input("Project Title"), st.text_input("Your Role"), st.text_input("Year")
            if st.form_submit_button("Sync Project"):
                client.table("projects").insert({"user_email": st.session_state.user_email, "type": t, "title": title, "role": r, "year": y}).execute()
                st.rerun()

    with tab5:
        st.subheader("🛡️ Verified Credential Vault")
        uploaded_file = st.file_uploader("Upload Degree/License/Registration", type=["pdf", "jpg", "png"])
        if uploaded_file and st.button("🚀 Secure Upload"):
            safe_email = st.session_state.user_email.replace("@", "_").replace(".", "_")
            client.storage.from_("credentials").upload(f"{safe_email}/{uploaded_file.name}", uploaded_file.getvalue(), {"x-upsert": "true"})
            st.success("File Archived in Secure Vault."); st.rerun()

    with tab6:
        st.subheader("Generate Targeted Clinical Portfolio")
        st.write("Select which medical systems to display on your PDF header:")
        
        country_options = ["United Kingdom", "United States", "Canada", "Australia", "Ireland", "EU/International"]
        selected_countries = st.multiselect(
            "Target Jurisdictions:",
            options=country_options,
            default=["United Kingdom"]
        )
        
        if st.button("🏗️ Compile Professional CV"):
            if selected_countries:
                try:
                    pdf_bytes = generate_pdf(st.session_state.user_email, profile, rotations, procedures, projects, selected_countries)
                    st.download_button(label="⬇️ Download Professional PDF", data=pdf_bytes, file_name=f"Medical_Passport_Targeted.pdf", mime="application/pdf")
                except Exception as e:
                    st.error(f"Error compiling PDF: {e}")
            else:
                st.error("Please select at least one jurisdiction.")

# --- 5. AUTHENTICATION ---
def login_screen():
    st.title("🏥 Medical Passport Gateway")
    e, p = st.text_input("Work Email"), st.text_input("Password", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Login"):
        try:
            res = client.auth.sign_in_with_password({"email": e, "password": p})
            if res.session:
                st.session_state.authenticated, st.session_state.user_email = True, e
                st.rerun()
        except: st.error("Login failed. Check email/password.")
    if c2.button("Register"):
        client.auth.sign_up({"email": e, "password": p})
        st.info("Verification email sent.")

if st.session_state.authenticated:
    main_dashboard()
else:
    login_screen()
