import streamlit as st
import time
import pandas as pd
from supabase import create_client, Client
from fpdf import FPDF
import io
import json

# --- 1. CORE CONFIGURATION ---
st.set_page_config(page_title="Global Medical Passport", page_icon="🩺", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stAppDeployButton {display:none;}
            [data-testid="stToolbar"] {visibility: hidden !important;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
client = create_client(URL, KEY)

# RESTORED FULL MAPPING DATA
EQUIVALENCY_MAP = {
    "Tier 1: Junior (Intern/FY1)": {
        "UK": "Foundation Year 1", "US": "PGY-1 (Intern)", "Australia": "Intern",
        "Ireland": "Intern", "Canada": "PGY-1", "Dubai/DHA": "Intern",
        "India/Pakistan": "House Officer / Intern", "Nigeria": "House Officer",
        "China/S.Korea": "Junior Resident", "Europe": "Junior Doctor",
        "Poland": "Lekarz stażysta",
        "Responsibilities": "Ward based, supervised prescribing, basic clinical procedures."
    },
    "Tier 2: Intermediate (SHO/Resident)": {
        "UK": "FY2 / Core Trainee", "US": "PGY-2/3 (Resident)", "Australia": "Resident / RMO",
        "Ireland": "SHO", "Canada": "Junior Resident", "Dubai/DHA": "GP / Resident",
        "India/Pakistan": "PG Resident / Medical Officer", "Nigeria": "Registrar",
        "China/S.Korea": "Resident", "Europe": "Resident Physician",
        "Poland": "Lekarz rezydent (Junior)",
        "Responsibilities": "Acute assessments, procedural proficiency, core specialty rotations."
    },
    "Tier 3: Senior (Registrar/Fellow)": {
        "UK": "ST3+ / Registrar", "US": "Chief Resident / Fellow", "Australia": "Registrar",
        "Ireland": "Specialist Registrar (SpR)", "Canada": "Senior Resident / Fellow", "Dubai/DHA": "Specialist (P)",
        "India/Pakistan": "Senior Resident / Registrar", "Nigeria": "Senior Registrar",
        "China/S.Korea": "Attending Physician / Fellow", "Europe": "Specialist Trainee / Senior Registrar",
        "Poland": "Lekarz rezydent (Senior)",
        "Responsibilities": "Team leadership, specialty decision making, independent in core procedures."
    },
    "Tier 4: Expert (Consultant/Attending)": {
        "UK": "Consultant / SAS", "US": "Attending Physician", "Australia": "Consultant / Specialist",
        "Ireland": "Consultant", "Canada": "Staff Specialist", "Dubai/DHA": "Consultant",
        "India/Pakistan": "Consultant / Asst. Professor", "Nigeria": "Consultant",
        "China/S.Korea": "Chief Physician", "Europe": "Specialist / Consultant",
        "Poland": "Lekarz specjalista",
        "Responsibilities": "Final clinical accountability, service leadership, senior training."
    }
}

COUNTRY_KEY_MAP = {
    "United Kingdom": "UK", "United States": "US", "Australia": "Australia",
    "Ireland": "Ireland", "Canada": "Canada", "Dubai (DHA)": "Dubai/DHA",
    "India & Pakistan": "India/Pakistan", "Nigeria": "Nigeria",
    "China & S.Korea": "China/S.Korea", "Europe (General)": "Europe",
    "Poland": "Poland"
}

# --- 2. DATABASE UTILITIES ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

def fetch_user_data(table_name):
    try:
        res = client.table(table_name).select("*").eq("user_email", st.session_state.user_email).execute()
        return res.data
    except: return []

# --- 3. MAIN DASHBOARD ---
def main_dashboard():
    # Header logic
    h_col1, h_col2 = st.columns([0.8, 0.2])
    with h_col1:
        st.title("🩺 Global Medical Passport")
        st.caption(f"Active Session: Dr. {st.session_state.user_email}")
    with h_col2:
        st.write("##")
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    profile = fetch_user_data("profiles")
    rotations = fetch_user_data("rotations")
    procedures = fetch_user_data("procedures")
    projects = fetch_user_data("projects")

    saved_countries = []
    if profile and profile[0].get('selected_countries'):
        saved_countries = profile[0]['selected_countries']
        if isinstance(saved_countries, str): saved_countries = json.loads(saved_countries)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🌐 Standing & Equivalency", "📊 Analytics", "🏥 Experience", "💉 Procedures", "🔬 Academic", "🛡️ Compliance Vault"
    ])

    with tab1:
        st.subheader("Global Clinical Seniority Mapping")
        # RESTORED SIDE-BY-SIDE COMPARISON
        col_p1, col_p2 = st.columns([0.4, 0.6])
        with col_p1:
            current_tier = profile[0]['global_tier'] if profile else list(EQUIVALENCY_MAP.keys())[0]
            try: t_idx = list(EQUIVALENCY_MAP.keys()).index(current_tier)
            except: t_idx = 0
            selected_tier = st.selectbox("Current Clinical Standing", list(EQUIVALENCY_MAP.keys()), index=t_idx)
            active_countries = st.multiselect("Target Healthcare Systems", options=list(COUNTRY_KEY_MAP.keys()), default=saved_countries if saved_countries else ["United Kingdom", "Poland"])
            summary_text = st.text_area("Professional Pitch", value=profile[0].get('summary', '') if profile else "", height=150)
            
            if st.button("💾 Sync Profile"):
                client.table("profiles").upsert({"user_email": st.session_state.user_email, "global_tier": selected_tier, "selected_countries": active_countries, "summary": summary_text}, on_conflict="user_email").execute()
                st.success("Profile Updated."); st.rerun()

        with col_p2:
            st.info("How your seniority translates globally:")
            if active_countries:
                t_data = EQUIVALENCY_MAP[selected_tier]
                metric_cols = st.columns(min(len(active_countries), 3))
                for i, country in enumerate(active_countries):
                    key = COUNTRY_KEY_MAP[country]
                    metric_cols[i % 3].metric(country, t_data[key])
                st.divider()
                st.write(f"**Expected Scope of Practice:** {t_data['Responsibilities']}")
            

    with tab2:
        st.subheader("Procedural Competency Analytics")
        if procedures:
            df_proc = pd.DataFrame(procedures)
            chart_data = df_proc.groupby(['procedure', 'level'])['count'].sum().unstack().fillna(0)
            st.bar_chart(chart_data)
        else: st.info("Add procedures to generate charts.")

    with tab3:
        st.subheader("Clinical Experience")
        if rotations: st.table(pd.DataFrame(rotations).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_rot"):
            h, s, d, g = st.text_input("Hospital"), st.text_input("Specialty"), st.text_input("Dates"), st.text_input("Grade")
            if st.form_submit_button("Add Placement"):
                client.table("rotations").insert({"user_email": st.session_state.user_email, "hospital": h, "specialty": s, "dates": d, "grade": g}).execute()
                st.rerun()

    with tab4:
        st.subheader("Procedural Logbook")
        if procedures: st.table(pd.DataFrame(procedures).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_proc"):
            n = st.text_input("Procedure")
            l = st.selectbox("Level", ["Observed", "Supervised", "Independent", "Trainer"])
            c = st.number_input("Count", 1)
            if st.form_submit_button("Log Skill"):
                client.table("procedures").insert({"user_email": st.session_state.user_email, "procedure": n, "level": l, "count": c}).execute()
                st.rerun()

    with tab5:
        st.subheader("Academic Portfolio")
        if projects: st.table(pd.DataFrame(projects).drop(columns=['id', 'user_email'], errors='ignore'))
        with st.form("add_proj"):
            t = st.selectbox("Type", ["Audit", "Research", "QIP", "Teaching"])
            title, r, y = st.text_input("Title"), st.text_input("Role"), st.text_input("Year")
            if st.form_submit_button("Log Project"):
                client.table("projects").insert({"user_email": st.session_state.user_email, "type": t, "title": title, "role": r, "year": y}).execute()
                st.rerun()

    with tab6:
        st.subheader("🛡️ Compliance Tracker & Document Vault")
        # COMPLIANCE TRAFFIC LIGHTS
        st.write("### Readiness to Work")
        c_col1, c_col2, c_col3 = st.columns(3)
        c_col1.error("❌ Occupational Health: Expired")
        c_col2.success("✅ ACLS/ALS: Valid (Dec 2026)")
        c_col3.warning("⚠️ Indemnity: Renew in 30 Days")
        
        st.divider()
        up_file = st.file_uploader("Upload Evidence", type=['pdf', 'jpg'])
        if up_file and st.button("📤 Vault File"):
            path = f"{st.session_state.user_email}/{up_file.name}"
            client.storage.from_('medical-vault').upload(path, up_file.getvalue())
            st.success("Securely Uploaded.")
        
        # LIST VAULTED FILES
        files = client.storage.from_('medical-vault').list(st.session_state.user_email)
        for f in files:
            col_f1, col_f2 = st.columns([0.8, 0.2])
            col_f1.write(f"📄 {f['name']}")
            res = client.storage.from_('medical-vault').create_signed_url(f"{st.session_state.user_email}/{f['name']}", 60)
            col_f2.link_button("View", res['signedURL'])

# --- 4. AUTHENTICATION ---
def login_screen():
    st.title("🏥 Medical Passport Gateway")
    e, p = st.text_input("Email"), st.text_input("Password", type="password")
    if st.button("Sign In", use_container_width=True):
        try:
            res = client.auth.sign_in_with_password({"email": e, "password": p})
            if res.user:
                st.session_state.authenticated = True; st.session_state.user_email = e; st.rerun()
        except: st.error("Login failed.")

if st.session_state.authenticated: main_dashboard()
else: login_screen()
