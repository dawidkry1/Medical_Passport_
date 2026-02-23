import streamlit as st
import time
import pandas as pd
from supabase import create_client, Client

# --- 1. CORE CONFIGURATION ---
st.set_page_config(page_title="Medical Passport", page_icon="🏥", layout="wide")

# Secure connection to Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
client = create_client(URL, KEY)

# International Equivalency Data
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {
        "UK": "Foundation Year 1",
        "US": "PGY-1 (Intern)",
        "Australia": "Intern",
        "Responsibilities": "Ward based, supervised prescribing, basic procedures."
    },
    "Tier 2: Intermediate (SHO/Resident)": {
        "UK": "FY2 / Core Trainee",
        "US": "PGY-2/3 (Resident)",
        "Australia": "Resident / RMO",
        "Responsibilities": "Front-door assessment, managing acute cases, procedural proficiency."
    },
    "Tier 3: Senior (Registrar/Fellow)": {
        "UK": "ST3+ / Registrar",
        "US": "Chief Resident / Fellow",
        "Australia": "Registrar",
        "Responsibilities": "Leading teams, specialty decision making, independent in core procedures."
    },
    "Tier 4: Expert (Consultant/Attending)": {
        "UK": "Consultant / SAS",
        "US": "Attending Physician",
        "Australia": "Consultant / Specialist",
        "Responsibilities": "Final clinical accountability, service leadership, senior training."
    }
}

# Initialize Session States
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""

# --- DATABASE UTILITIES ---
def fetch_user_data(table_name):
    try:
        res = client.table(table_name).select("*").eq("user_email", st.session_state.user_email).execute()
        return res.data
    except Exception:
        return []

# --- 2. THE PASSPORT DASHBOARD ---
def main_dashboard():
    st.sidebar.title("🏥 Clinical Session")
    st.sidebar.write(f"**Verified Physician:**\n{st.session_state.user_email}")
    
    if st.sidebar.button("🚪 Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

    st.title("🩺 Professional Medical Passport")
    st.caption("International Physician Credential Vault & Equivalency Ledger")
    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🌐 Equivalency",
        "🏥 Rotations", 
        "💉 Procedures", 
        "🔬 Academic/QIP", 
        "🛡️ Vault"
    ])

    # --- TAB 1: GLOBAL EQUIVALENCY ---
    with tab1:
        st.subheader("Global Seniority Mapping")
        st.info("Translate your current local grade into international equivalents.")
        
        selected_tier = st.selectbox("Define Your Standardized Level", list(EQUIVALENCY_MAP.keys()))
        tier_data = EQUIVALENCY_MAP[selected_tier]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("UK Equivalent", tier_data["UK"])
        c2.metric("US Equivalent", tier_data["US"])
        c3.metric("Aus Equivalent", tier_data["Australia"])
        
        st.write(f"**Clinical Responsibility Level:** {tier_data['Responsibilities']}")
        
        if st.button("Update Global Tier on Passport"):
            try:
                # Upsert ensures it creates or updates the user profile
                client.table("profiles").upsert({
                    "user_email": st.session_state.user_email, 
                    "global_tier": selected_tier
                }, on_conflict="user_email").execute()
                st.success("Equivalency Applied Successfully.")
            except Exception as e:
                st.error(f"Error updating profile: {e}. Did you run the SQL migration?")

    # --- TAB 2: ROTATIONS ---
    with tab2:
        st.subheader("Clinical Experience Ledger")
        rotations = fetch_user_data("rotations")
        if rotations:
            df_rot = pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore')
            st.data_editor(df_rot, use_container_width=True, disabled=True)
        
        with st.expander("➕ Log New Placement"):
            with st.form("new_rotation"):
                c1, c2 = st.columns(2)
                h = c1.text_input("Hospital / Institution")
                s = c2.selectbox("Specialty", ["General Medicine", "Surgery", "ICU/Anaesthetics", "Emergency", "Paediatrics", "OBGYN", "Psychiatry", "GP"])
                c3, c4 = st.columns(2)
                d = c3.text_input("Dates (e.g. Aug 24 - Aug 25)")
                r = c4.text_input("Local Grade (e.g. SHO, Resident)")
                if st.form_submit_button("Sync to Passport"):
                    client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": h, "specialty": s, "dates": d, "grade": r}).execute()
                    st.rerun()

    # --- TAB 3: PROCEDURES ---
    with tab3:
        st.subheader("Procedural Logbook")
        procs = fetch_user_data("procedures")
        if procs:
            st.table(pd.DataFrame(procs).drop(columns=['id', 'user_email'], errors='ignore'))

        with st.form("new_procedure"):
            p1, p2, p3 = st.columns([2, 2, 1])
            p_name = p1.text_input("Procedure Name")
            p_level = p2.select_slider("Competency", options=["Observed", "Supervised", "Independent", "Assessor"])
            p_count = p3.number_input("Count", min_value=1)
            if st.form_submit_button("Log Skill"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": p_name, "level": p_level, "count": p_count}).execute()
                st.rerun()

    # --- TAB 4: ACADEMIC & QIP ---
    with tab4:
        st.subheader("Research & Leadership Portfolio")
        projects = fetch_user_data("projects")
        if projects:
            for p in projects:
                with st.container(border=True):
                    st.write(f"**{p['type']}**: {p['title']}")
                    st.caption(f"Role: {p['role']} | Year: {p['year']}")

        with st.expander("➕ Add Project/Publication"):
            with st.form("new_project"):
                p_type = st.selectbox("Category", ["Clinical Audit", "QIP", "Research Publication", "Teaching Program"])
                p_title = st.text_input("Project Title")
                p_role = st.text_input("Role (e.g. First Author)")
                p_year = st.text_input("Year")
                if st.form_submit_button("Submit"):
                    client.table("projects").insert({"user_email": st.session_state.user_email, "type": p_type, "title": p_title, "role": p_role, "year": p_year}).execute()
                    st.rerun()

    # --- TAB 5: DOCUMENT VAULT ---
    with tab5:
        st.subheader("🛡️ Verified Credential Vault")
        uploaded_file = st.file_uploader("Upload Degree/License (PDF/IMG)", type=["pdf", "jpg", "png"])
        
        if uploaded_file:
            safe_email = st.session_state.user_email.replace("@", "_").replace(".", "_")
            file_path = f"{safe_email}/{uploaded_file.name}"
            if st.button("🚀 Secure Upload"):
                try:
                    file_bytes = uploaded_file.getvalue()
                    m_type = "application/pdf" if uploaded_file.type == "application/pdf" else "image/jpeg"
                    client.storage.from_("credentials").upload(path=file_path, file=file_bytes, file_options={"content-type": m_type, "x-upsert": "true"})
                    st.success("Archived.")
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")

        st.divider()
        try:
            safe_email = st.session_state.user_email.replace("@", "_").replace(".", "_")
            files = client.storage.from_("credentials").list(safe_email)
            if files:
                for f in files:
                    if f['name'] == '.emptyFolderPlaceholder': continue
                    col_i, col_f, col_v = st.columns([1, 8, 3])
                    col_i.write("📄" if f['name'].endswith('pdf') else "🖼️")
                    col_f.write(f"**{f['name']}**")
                    res = client.storage.from_("credentials").create_signed_url(f"{safe_email}/{f['name']}", 60)
                    col_v.link_button("👁️ View", res['signedURL'], use_container_width=True)
        except: st.info("Vault empty.")

# --- 3. AUTHENTICATION LOGIC ---
def handle_recovery():
    params = st.query_params
    if params.get("type") == "recovery" and params.get("code"):
        st.title("🛡️ Account Recovery")
        new_p = st.text_input("Set New Password", type="password")
        if st.button("Update & Login"):
            try:
                client.auth.exchange_code_for_session({"auth_code": params.get("code")})
                client.auth.update_user({"password": new_p})
                st.success("Password Updated!")
                time.sleep(2)
                st.query_params.clear()
                st.rerun()
            except Exception as e: st.error(f"Recovery failed: {e}")
        return True
    return False

def login_screen():
    st.title("🏥 Medical Passport Gateway")
    mode = st.radio("Access", ["Login", "Register", "Forgot Password"], horizontal=True)
    st.write("---")
    if mode == "Login":
        e = st.text_input("Work Email")
        p = st.text_input("Password", type="password")
        if st.button("Sign In", use_container_width=True):
            try:
                res = client.auth.sign_in_with_password({"email": e, "password": p})
                if res.session:
                    st.session_state.authenticated = True
                    st.session_state.user_email = e
                    st.rerun()
            except: st.error("Authentication failed.")
    elif mode == "Register":
        reg_e = st.text_input("Work Email")
        reg_p = st.text_input("Password", type="password")
        if st.button("Create Physician Account"):
            try:
                client.auth.sign_up({"email": reg_e, "password": reg_p})
                st.success("Verification email sent!")
            except Exception as e: st.error(f"Error: {e}")
    elif mode == "Forgot Password":
        f_e = st.text_input("Email")
        if st.button("Send Recovery Link"):
            client.auth.reset_password_for_email(f_e, options={"redirect_to": "https://medical-passport.streamlit.app?type=recovery"})
            st.success("Link sent.")

# --- 4. EXECUTION ---
if not handle_recovery():
    if st.session_state.authenticated:
        main_dashboard()
    else:
        login_screen()
