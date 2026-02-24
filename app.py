import streamlit as st
import pandas as pd
from supabase import create_client
import google.generativeai as genai
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
        # We use a try-block for the model to prevent the app from crashing on start
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
        except:
            model = None
    else:
        st.error("⚠️ GEMINI_API_KEY missing.")
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

# --- 3. EXTRACTION ENGINE ---
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
    prompt = (
        "Extract all medical career data. "
        "List every hospital and specialty. "
        "Format: 'ITEM: [Specialty] at [Hospital] ([Dates])' "
        f"\n\nCV:\n{full_text[:8000]}"
    )
    try:
        # Re-verify model here to be safe
        active_model = genai.GenerativeModel('gemini-1.5-flash')
        response = active_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"CRITICAL ERROR: {str(e)}"

# --- 4. MAIN DASHBOARD ---
def main_dashboard():
    with st.sidebar:
        st.header("🛂 Clinical Portfolio")
        
        # DEBUG TOOL: List available models
        if st.button("🔍 Scan Available Models"):
            try:
                models = [m.name for m in genai.list_models()]
                st.write("Your API can see:")
                st.write(models)
            except Exception as e:
                st.error(f"Could not list models: {e}")

        st.divider()
        up_file = st.file_uploader("Upload CV", type=['pdf', 'docx'])
        
        if up_file:
            raw_txt = get_raw_text(up_file)
            if raw_txt:
                st.info(f"File Size: {len(raw_txt)} characters.")
                if st.button("🚀 Sync Portfolio"):
                    with st.spinner("Extracting..."):
                        st.session_state.scraped_text = run_unified_scan(raw_txt)
            else:
                st.error("Read Error.")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.title("🩺 Global Medical Passport")

    tabs = st.tabs(["🌐 Equivalency", "🏥 Clinical Records", "🔬 Raw Feed"])

    # 1. EQUIVALENCY
    with tabs[0]:
        st.subheader("International Seniority Mapping")
        
        st.write("This table helps international colleagues understand your current grade.")
        # Static example for now
        st.table(pd.DataFrame([
            {"Region": "UK", "Equivalent": "Foundation Year 2 (SHO)"},
            {"Region": "US", "Equivalent": "PGY-2 (Resident)"},
            {"Region": "Australia", "Equivalent": "Resident Medical Officer"}
        ]))

    # 2. CLINICAL RECORDS
    with tabs[1]:
        st.subheader("Extracted Experiences")
        
        if st.session_state.scraped_text:
            items = [l.replace("ITEM:", "").strip() for l in st.session_state.scraped_text.split('\n') if "ITEM:" in l.upper()]
            if items:
                for item in items:
                    st.write(f"✅ {item}")
            else:
                st.warning("AI connected but found no clinical matches. Check Raw Feed.")
        else:
            st.info("Sync your CV to begin.")

    # 3. RAW FEED
    with tabs[2]:
        st.subheader("AI Diagnostic")
        st.text_area("Response Log", value=st.session_state.scraped_text, height=300)

# --- LOGIN ---
if not st.session_state.authenticated:
    st.title("🏥 Medical Passport Gateway")
    with st.form("login"):
        st.text_input("Email", key="login_email")
        st.text_input("Password", type="password", key="login_password")
        st.form_submit_button("Sign In", on_click=handle_login)
else:
    main_dashboard()
