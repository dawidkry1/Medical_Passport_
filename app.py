import streamlit as st
import pandas as pd
from supabase import create_client
import google.generativeai as genai  # Switched to the more stable standard library
import pdfplumber
import docx
import time

# --- 1. CORE CONFIG ---
st.set_page_config(page_title="Global Medical Passport", page_icon="🏥", layout="wide")

# Connection Setup
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase_client = create_client(URL, KEY)
    
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        st.error("⚠️ GEMINI_API_KEY missing from secrets.")
except Exception as e:
    st.error(f"Config Error: {e}")

# --- 2. SESSION STATE ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'scraped_text' not in st.session_state:
    st.session_state.scraped_text = ""

def handle_login():
    try:
        res = supabase_client.auth.sign_in_with_password({"email": st.session_state.login_email, "password": st.session_state.login_password})
        if res.user:
            st.session_state.authenticated = True
            st.session_state.user_email = res.user.email
    except Exception as e:
        st.error(f"Login failed: {e}")

# --- 3. THE EXTRACTION ENGINE ---
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
        return text.strip()
    except: return ""

def run_unified_scan(full_text):
    """One single high-instruction call."""
    prompt = (
        "You are an expert medical recruiter. Extract all information from this CV. "
        "List every job, hospital, specialty, and clinical procedure you find. "
        "For each item, start a new line with the word 'ITEM:' followed by the details. "
        "Include dates if found. If no clinical data is found, output 'EMPTY'. "
        f"\n\nCV CONTENT:\n{full_text[:8000]}" # Sending first 8k chars to stay safe
    )
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"API ERROR: {str(e)}"

# --- 4. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Portfolio")
        
        # Handshake Test
        if st.button("🧪 Test AI Connection"):
            try:
                test_res = model.generate_content("Say 'System Online'")
                st.success(f"AI Response: {test_res.text}")
            except Exception as e:
                st.error(f"Connection Failed: {e}")

        st.divider()
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt:
                st.info(f"Detected {len(raw_txt)} characters.")
                if st.button("🚀 Sync Medical Portfolio"):
                    with st.spinner("Analyzing Clinical History..."):
                        st.session_state.scraped_text = run_unified_scan(raw_txt)
                        st.success("Analysis Finished.")
            else:
                st.error("Could not read text from file.")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    tabs = st.tabs(["🌐 Equivalency", "🏥 Clinical Records", "🔬 Raw AI Feed"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Grade Mapping")
        
        # (Equivalency Table Logic simplified for this debug version)
        st.info("Mapping will update once CV is processed.")

    # 2. CLINICAL RECORDS
    with tabs[1]:
        st.subheader("Extracted Experiences & Procedures")
        
        if st.session_state.scraped_text:
            lines = st.session_state.scraped_text.split('\n')
            items = [l.replace("ITEM:", "").strip() for l in lines if "ITEM:" in l.upper()]
            
            if items:
                for idx, item in enumerate(items):
                    st.write(f"🔹 {item}")
            else:
                st.warning("AI responded but found no clinical items. Check the Raw AI Feed.")
        else:
            st.info("Upload and Sync your CV to see your clinical history.")

    # 3. RAW AI FEED
    with tabs[2]:
        st.subheader("Diagnostic Output")
        if st.session_state.scraped_text:
            st.text_area("Full AI Response:", value=st.session_state.scraped_text, height=400)
        else:
            st.write("Waiting for CV sync...")

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
