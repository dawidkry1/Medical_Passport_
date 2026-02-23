import streamlit as st
import pandas as pd
from supabase import create_client
from fpdf import FPDF
import json
import pdfplumber  # Required for the new Import function
import re

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Global Medical Passport", page_icon="🏥", layout="wide")

# (CSS and Supabase Setup remains the same)
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
client = create_client(URL, KEY)

EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {"UK": "Foundation Year 1", "Poland": "Lekarz stażysta", "Responsibilities": "Ward based, supervised prescribing."},
    "Tier 2: Intermediate (SHO/Resident)": {"UK": "FY2 / Core Trainee", "Poland": "Lekarz rezydent (Junior)", "Responsibilities": "Acute assessments, core specialty."},
    "Tier 3: Senior (Registrar/Fellow)": {"UK": "ST3+ / Registrar", "Poland": "Lekarz rezydent (Senior)", "Responsibilities": "Team leadership, specialty decision making."},
    "Tier 4: Expert (Consultant/Attending)": {"UK": "Consultant / SAS", "Poland": "Lekarz specjalista", "Responsibilities": "Final clinical accountability."}
}

COUNTRY_KEY_MAP = {"United Kingdom": "UK", "Poland": "Poland", "United States": "US", "Australia": "Australia"}

# --- 2. NEW: MEDICAL CV PARSER LOGIC ---
def simple_medical_parser(text):
    """A basic heuristic parser to find clinical rotations in raw text."""
    rotations = []
    # Look for common patterns like "Hospital", "Ward", "Department"
    lines = text.split('\n')
    for line in lines:
        if any(key in line.lower() for key in ["hospital", "clinic", "centre", "szpital"]):
            rotations.append({"hospital": line.strip(), "specialty": "Detected from CV", "dates": "Check CV", "grade": "Check CV"})
    return rotations

# --- 3. MAIN DASHBOARD ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

def main_dashboard():
    # Header logic...
    st.title("🩺 Global Medical Passport")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🌐 Equivalency", "🏥 Rotations & Import", "🛡️ Vault", "📄 Export CV"])

    with tab1:
        st.subheader("Global Standing Mapping")
        # (Equivalency logic from previous version)

    with tab2:
        st.subheader("Clinical Experience")
        
        # --- THE NEW IMPORT FUNCTION ---
        with st.expander("🪄 Quick-Start: Import from Legacy CV"):
            st.info("Upload your old PDF CV. We will attempt to identify your hospitals and placements.")
            legacy_file = st.file_uploader("Choose PDF CV", type=['pdf'])
            if legacy_file:
                with pdfplumber.open(legacy_file) as pdf:
                    raw_text = "".join([page.extract_text() for page in pdf.pages])
                
                extracted_data = simple_medical_parser(raw_text)
                
                if extracted_data:
                    st.write("🔍 **Potential Placements Found:**")
                    for i, item in enumerate(extracted_data[:5]): # Show first 5 matches
                        col1, col2, col3 = st.columns(3)
                        h = col1.text_input(f"Hospital {i}", value=item['hospital'], key=f"h_{i}")
                        s = col2.text_input(f"Specialty {i}", value="General Medicine", key=f"s_{i}")
                        if col3.button(f"Add #{i}"):
                            client.table("rotations").insert({
                                "user_email": st.session_state.user_email,
                                "hospital": h, "specialty": s, "dates": "Imported", "grade": "Imported"
                            }).execute()
                            st.toast(f"Added {h}!")
                else:
                    st.warning("We found text, but no clear hospital names. You can copy-paste from below:")
                    st.text_area("Raw CV Text", raw_text, height=150)

        st.divider()
        # (Standard Rotations Table & Form)
        # ... [Rotations display and manual add form] ...

    with tab3:
        st.subheader("🛡️ Credential Vault")
        # (Vault logic from previous version)

    with tab4:
        st.subheader("Generate Portfolio")
        # (Export logic from previous version)

# --- AUTHENTICATION (Form-based for 'Enter' key) ---
def login_screen():
    st.title("🏥 Medical Passport Gateway")
    with st.form("login_form"):
        e = st.text_input("Email")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign In", use_container_width=True):
            try:
                res = client.auth.sign_in_with_password({"email": e, "password": p})
                if res.user:
                    st.session_state.authenticated = True
                    st.session_state.user_email = e
                    st.rerun()
            except: st.error("Login failed.")

if st.session_state.authenticated: main_dashboard()
else: login_screen()
