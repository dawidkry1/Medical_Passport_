import streamlit as st
import time
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
import io

# --- 1. CORE CONFIGURATION ---
st.set_page_config(page_title="Medical Passport", page_icon="🏥", layout="wide")

# Secure connection to Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
client = create_client(URL, KEY)

EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {
        "UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern",
        "Responsibilities": "Ward based, supervised prescribing, basic procedures."
    },
    "Tier 2: Intermediate (SHO/Resident)": {
        "UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO",
        "Responsibilities": "Front-door assessment, managing acute cases, procedural proficiency."
    },
    "Tier 3: Senior (Registrar/Fellow)": {
        "UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar",
        "Responsibilities": "Leading teams, specialty decision making, independent in core procedures."
    },
    "Tier 4: Expert (Consultant/Attending)": {
        "UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant / Specialist",
        "Responsibilities": "Final clinical accountability, service leadership, senior training."
    }
}

# --- 2. PDF GENERATOR LOGIC ---
class MedicalCV(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Professional Medical Portfolio / CV', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 8, 'Standardized Clinical Credential Document', 0, 1, 'C')
        self.ln(10)

    def section_header(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 10, f" {title}", 0, 1, 'L', fill=True)
        self.ln(3)

def generate_pdf(email, profile, rotations, procedures, projects):
    pdf = MedicalCV()
    pdf.add_page()
    
    # Profile & Equivalency
    tier = profile[0]['global_tier'] if profile else "Not Declared"
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, f"Physician: {email}", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"Global Seniority Tier: {tier}", 0, 1)
    if tier in EQUIVALENCY_MAP:
        eq = EQUIVALENCY_MAP[tier]
        pdf.set_font('Arial', 'I', 9)
        pdf.cell(0, 6, f"Mapped Equivalents: UK: {eq['UK']} | US: {eq['US']} | AUS: {eq['Australia']}", 0, 1)
    pdf.ln(5)

    # Rotations
    pdf.section_header("Clinical Experience & Rotations")
    for r in rotations:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"{r['hospital']} - {r['specialty']}", 0, 1)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 6, f"Role: {r['grade']} | Dates: {r['dates']}", 0, 1)
        pdf.ln(2)

    # Procedures
    pdf.ln(5)
    pdf.section_header("Procedural Competency Logbook")
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(80, 8, "Procedure", 1)
    pdf.cell(60, 8, "Competency Level", 1)
    pdf.cell(30, 8, "Lifetime Count", 1, 1)
    pdf.set_font('Arial', '', 9)
    for p in procedures:
        pdf.cell(80, 8, str(p['procedure']), 1)
        pdf.cell(60, 8, str(p['level']), 1)
        pdf.cell(30, 8, str(p['count']), 1, 1)

    # Academic
    pdf.ln(10)
    pdf.section_header("Academic Portfolio & QIPs")
    for pr in projects:
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, f"{pr['type']}: {pr['title']}", 0, 1)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 6, f"Role: {pr['role']} ({pr['year']})", 0, 1)
        pdf.ln(2)

    return pdf.output(dest='S').encode('latin-1')

# --- 3. DASHBOARD LOGIC ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def fetch_user_data(table_name):
    try:
        res = client.table(table_name).select("*").eq("user_email", st.session_state.user_email).execute()
        return res.data
    except: return []

def main_dashboard():
    st.sidebar.title("🏥 Clinical Session")
    st.sidebar.write(f"Logged in: {st.session_state.user_email}")
    if st.sidebar.button("Log Out"):
        st.session_state.authenticated = False
        st.rerun()

    st.title("🩺 Medical Passport Dashboard")
    
    # Global Data Fetch
    profile = fetch_user_data("profiles")
    rotations = fetch_user_data("rotations")
    procedures = fetch_user_data("procedures")
    projects = fetch_user_data("projects")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🌐 Equivalency", "🏥 Rotations", "💉 Procedures", "🔬 Academic", "📄 Export CV"])

    with tab1:
        st.subheader("International Seniority Mapping")
        current_tier = profile[0]['global_tier'] if profile else list(EQUIVALENCY_MAP.keys())[0]
        selected_tier = st.selectbox("Current Tier", list(EQUIVALENCY_MAP.keys()), index=list(EQUIVALENCY_MAP.keys()).index(current_tier) if current_tier in EQUIVALENCY_MAP else 0)
        if st.button("Save Tier"):
            client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier}, on_conflict="user_email").execute()
            st.success("Saved"); st.rerun()

    with tab2:
        st.subheader("Experience Ledger")
        if rotations: st.table(pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_rot"):
            h, s, d, g = st.text_input("Hospital"), st.text_input("Specialty"), st.text_input("Dates"), st.text_input("Grade")
            if st.form_submit_button("Add Rotation"):
                client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": h, "specialty": s, "dates": d, "grade": g}).execute()
                st.rerun()

    with tab3:
        st.subheader("Procedural Log")
        if procedures: st.table(pd.DataFrame(procedures).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_proc"):
            n, l, c = st.text_input("Procedure"), st.selectbox("Level", ["Observed", "Supervised", "Independent"]), st.number_input("Count", 1)
            if st.form_submit_button("Log Procedure"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": n, "level": l, "count": c}).execute()
                st.rerun()

    with tab4:
        st.subheader("Projects & Research")
        if projects: st.table(pd.DataFrame(projects).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_proj"):
            t, title, r, y = st.selectbox("Type", ["Audit", "Research", "QIP"]), st.text_input("Title"), st.text_input("Role"), st.text_input("Year")
            if st.form_submit_button("Add Project"):
                client.table("projects").insert({"user_email": st.session_state.user_email, "type": t, "title": title, "role": r, "year": y}).execute()
                st.rerun()

    with tab5:
        st.subheader("Generate Professional CV")
        st.write("Click below to compile all logged data into a formal PDF document.")
        if st.button("🏗️ Compile Medical CV"):
            try:
                pdf_bytes = generate_pdf(st.session_state.user_email, profile, rotations, procedures, projects)
                st.download_button(label="⬇️ Download PDF CV", data=pdf_bytes, file_name=f"Medical_Passport_{st.session_state.user_email.split('@')[0]}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error generating PDF: {e}")

# --- 4. AUTHENTICATION ---
def login_screen():
    st.title("🏥 Medical Passport Gateway")
    e, p = st.text_input("Email"), st.text_input("Password", type="password")
    c1, c2 = st.columns(2)
    if c1.button("Login"):
        try:
            res = client.auth.sign_in_with_password({"email": e, "password": p})
            if res.session:
                st.session_state.authenticated = True
                st.session_state.user_email = e
                st.rerun()
        except: st.error("Failed")
    if c2.button("Register"):
        client.auth.sign_up({"email": e, "password": p})
        st.info("Check email")

if st.session_state.authenticated:
    main_dashboard()
else:
    login_screen()
