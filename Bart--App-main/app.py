import streamlit as st
import time
import streamlit as st
import streamlit.components.v1 as components




# Set up state
if "lang" not in st.session_state: st.session_state.lang = "en"

# Define your texts
texts = {
    "en": {
        "title": "B A R T",
        "sub": "Operations management <br>just got easier.",
        "desc": "Welcome to the central command unit for BART...",
        "btn_staff": "Staff Access →"
    },
    "ar": {
        "title": "بـارت",
        "sub": "إدارة العمليات <br>أصبحت أسهل.",
        "desc": "أهلاً بك في وحدة التحكم المركزية لـ BART...",
        "btn_staff": "وصول الموظفين ←"
    }
}

# Select the language
T = texts[st.session_state.lang]

# 2. Initialize Language State
if "lang" not in st.session_state:
    st.session_state.lang = "en"

# 3. Simple Toggle in the Sidebar (or top of page)
lang_col1, lang_col2 = st.columns([10, 1])
with lang_col2:
    if st.button("🌐"):
        st.session_state.lang = "ar" if st.session_state.lang == "en" else "en"
        st.rerun()

# 4. Helper function to get text
def _(key):
    return translations[st.session_state.lang].get(key, key)





# =========================================================
# SYSTEM CONFIG
# =========================================================
st.set_page_config(
    page_title="BART Portal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =========================================================
# CSS ARCHITECTURE (Dual Desktop & Mobile Engineering)
# =========================================================
st.markdown("""<style>
/* Global Hidden Elements */
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none !important; visibility: hidden !important; }
#MainMenu, footer, header { visibility: hidden; }

/* Transparencies */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"] { background: transparent !important; }
h1 { margin-bottom: 0px !important; }

/* =========================================================
   DESKTOP MASTER STYLES (Your Original Looks)
   ========================================================= */
.block-container { 
    max-width: 100% !important; 
    padding-top: 1rem !important; 
    padding-bottom: 1rem !important;
    padding-left: 5rem !important;  
    padding-right: 5rem !important; 
}

.bart-logo { 
    display: inline-block; 
    animation: breathe-bold 2s ease-in-out infinite; 
    background: linear-gradient(90deg, #F75D59 0%, #F75D59 100%); 
    -webkit-background-clip: text; 
    -webkit-text-fill-color: transparent; 
    cursor: default; 
    font-weight: 900 !important; 
    letter-spacing: -2px; 
}

.registered {
    font-size: 26px;              
    font-weight: 900;
    color: #8B5CF6 !important;    
    position: relative;
    top: -39px;                   
    left: 8px;
    display: inline-block;
    opacity: 1;
}

/* Background & Orbits */
.background-layer { 
    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: -9999; 
    overflow: hidden; background-color: #F8FAFC; 
    display: flex; justify-content: center; align-items: center;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 400'%3E%3Cpath fill='%23CBD5E1' d='M100 100c50 0 50 50 100 50s50-50 100-50 50 50 100 50 50-50 100-50 50 50 100 50 50-50 100-50 50 50 100 50'/%3E%3C/svg%3E");
    background-size: cover;
    background-position: center;
    opacity: 0.6; 
}
.orbit { position: absolute; border: 1px solid rgba(0, 0, 0, 0.2); border-radius: 50%; animation: spin linear infinite; left: 50%; top: 50%; transform: translate(-50%, -50%); }
.o1 { width: 200px; height: 200px; animation-duration: 20s; }
.o2 { width: 350px; height: 350px; animation-duration: 30s; }
.o3 { width: 500px; height: 500px; animation-duration: 40s; }
.o4 { width: 650px; height: 650px; animation-duration: 50s; }
.o5 { width: 800px; height: 800px; animation-duration: 65s; }
.o6 { width: 950px; height: 950px; animation-duration: 85s; }
.o7 { width: 1100px; height: 1100px; animation-duration: 110s; }

/* Cards & Buttons */
.card-glow { position: relative; padding: 2px; background: #FFFFFF; border-radius: 22px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05); }
.card-glow::before { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: conic-gradient(transparent, #F75D59, transparent 30%); animation: rotate 4s linear infinite; }
.card-content { position: relative; background: #FFFFFF; border-radius: 20px; padding: 30px; z-index: 1; }

div.stButton > button { 
    position: relative; 
    height: 54px !important; 
    border-radius: 50px !important; 
    border: none !important; 
    background: #F75D59 !important; 
    color: #FFFFFF !important; 
    font-weight: 900 !important; 
    text-transform: uppercase !important; 
    letter-spacing: 2px !important; 
    transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
}
div.stButton > button:hover {
    transform: scale(1.05) translateY(-2px);
    background: #e14c48 !important; 
    box-shadow: 0 10px 20px rgba(247, 93, 89, 0.35) !important;
    letter-spacing: 4px !important;
}
div.stButton > button:active { transform: scale(0.98) translateY(0); }

/* Keyframes Baseline */
@keyframes spin { from { transform: translate(-50%, -50%) rotate(0deg); } to { transform: translate(-50%, -50%) rotate(360deg); } }
@keyframes rotate { 100% { transform: rotate(360deg); } }
@keyframes breathe-bold { 0%, 100% { transform: scale(1); text-shadow: 0 0 10px rgba(247, 93, 89, 0.25); } 50% { transform: scale(1.05); text-shadow: 0 0 30px rgba(247, 93, 89, 0.65); } }
@keyframes fadeInUp { 0% { opacity: 0; transform: translateY(30px); } 100% { opacity: 1; transform: translateY(0); } }
.animate-text { animation: fadeInUp 0.8s ease-out forwards; opacity: 0; }
.delay-1 { animation-delay: 0.2s; } .delay-2 { animation-delay: 0.4s; } .delay-3 { animation-delay: 0.6s; } .delay-4 { animation-delay: 0.8s; }


/* =========================================================
   MOBILE RESPONSIVE OVERRIDES (Only triggers on screens < 768px)
   ========================================================= */
@media (max-width: 768px) {
    .block-container { 
        padding-left: 1.5rem !important; 
        padding-right: 1.5rem !important; 
        padding-top: 2rem !important;
    }
    
    /* Shrink huge main titles so they don't break lines awkwardly */
    h1.main-title-text { 
        font-size: 52px !important; 
    }
    h1.sub-title-text {
        font-size: 34px !important;
    }
    
    /* Fix the registered ® layout shift on mobile */
    .registered {
        font-size: 16px;
        top: -25px;
        left: 2px;
    }
    
    /* Prevent massive orbit canvas side-scrolling bugs */
    .background-layer {
        width: 100%;
        height: 100%;
    }
    .o5, .o6, .o7 { display: none !important; } /* Cut off extreme giant orbits on phones */
    
    /* Give cards spacing when stacked vertically */
    .card-glow {
        margin-bottom: 20px !important;
    }
    .card-content {
        padding: 22px 18px !important;
    }
    
    /* Make buttons easier to tap accurately on smartphones */
    div.stButton > button {
        height: 50px !important;
        letter-spacing: 1px !important;
        font-size: 13px !important;
    }
    div.stButton > button:hover {
        letter-spacing: 2px !important;
        transform: none !important; /* Eliminate desktop tilt hover on mobile */
    }
}
</style>""", unsafe_allow_html=True)

# =========================================================
# SESSION STATE
# =========================================================
st.session_state.authenticated = True
if "show_mgmt_password" not in st.session_state: st.session_state.show_mgmt_password = False
if "mgmt_lock_until" not in st.session_state: st.session_state.mgmt_lock_until = 0
if "show_hr_password" not in st.session_state: st.session_state.show_hr_password = False

def is_mgmt_locked():
    return time.time() < st.session_state.mgmt_lock_until

# =========================================================
# BACKGROUND LAYER
# =========================================================
st.markdown("""
<div class="background-layer">
    <div class="orbit-wrap">
        <div class="orbit o1"></div>
        <div class="orbit o2"></div>
        <div class="orbit o3"></div>
        <div class="orbit o4"></div>
        <div class="orbit o5"></div>
        <div class="orbit o6"></div>
        <div class="orbit o7"></div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================
# ANIMATED HEADER & UI
# =========================================================
st.markdown("<div class='animate-text delay-1' style='text-align: center;'><span style='background: rgba(59, 33, 230, 0.08); color: #3B21E6; padding: 6px 16px; border-radius: 100px; font-size: 12px; font-weight: 700; letter-spacing: 1px;'>INTERNAL STAFF NETWORK</span></div>", unsafe_allow_html=True)

# Wrapped classes here to target font alterations safely across viewports
st.markdown(f"""
<h1 class='animate-text delay-2 main-title-text' style='text-align: center; font-size: 88px; font-weight: 800; color: #111; margin-top: 5px; margin-bottom: -15px; letter-spacing: -2.5px;'>
    <span class='bart-logo'>{T['title']}</span><!--
 --><span style="position: relative; display: inline-block;">
        <span style="
            position: absolute;
            width: 26px;
            height: 16px;
            background-color: #8B5CF6;
            border-radius: 50%;
            transform: rotate(-30deg);
            top: 66px;
            left: -8px;
            z-index: 1;
        "></span>
        <span class="registered" style="position: relative; z-index: 2; margin-left: 0px;">®</span>
    </span>
</h1>
""", unsafe_allow_html=True)

st.markdown("<h1 class='animate-text delay-3 sub-title-text' style='text-align: center; font-size: 58px; font-weight: 800; color: #111111; margin-top: 15px; margin-bottom: 0;'>Operations management <br><span style='background: linear-gradient(90deg, #F75D59 0%, #F75D59 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>just got easier.</span></h1>", unsafe_allow_html=True)
st.markdown("<p class='animate-text delay-4' style='text-align: center; font-size: 16px; color: #64748B; max-width: 520px; margin: 20px auto 40px auto;'>Welcome to the central command unit for BART. Seamlessly organize branch metrics, manage shift requirements, and deploy localized branch parameters.</p>", unsafe_allow_html=True)

# =========================================================
# CARDS GRID
# =========================================================
grid_left, grid_right, grid_center = st.columns(3, gap="large")

with grid_left:
    st.markdown("""<div class="card-glow"><div class="card-content" style="text-align: center; font-family: 'Times New Roman', Times, serif; color: #1E293B; font-size: 20px; font-weight: 700;">Staff DashBoard """, unsafe_allow_html=True)
    st.markdown("<p style='font-family: sans-serif; font-size: 14px; color: #64748B; margin-bottom: 25px;'>Log daily updates, run item balance checkers, and communicate data parameters.</p>", unsafe_allow_html=True)
    if st.button("Staff Access →", use_container_width=True, key="staff_btn"): st.switch_page("pages/staff_dashboard.py")
    st.markdown('</div></div>', unsafe_allow_html=True)

with grid_center:
    st.markdown("""<div class="card-glow"><div class="card-content" style="text-align: center; font-family: 'Times New Roman', Times, serif; color: #1E293B; font-size: 20px; font-weight: 700;">HR DashBoard</div>""", unsafe_allow_html=True)
    st.markdown("<p style='font-family: sans-serif; font-size: 14px; color: #64748B; margin-bottom: 25px;'>Manage employee records, oversee Schedule systems, and coordinate</p>", unsafe_allow_html=True)
    if st.button("HR Access→", use_container_width=True, key="hr_btn"):
        st.session_state.show_hr_password = True
        st.session_state.show_mgmt_password = False 
        st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)

with grid_right:
    st.markdown("""<div class="card-glow"><div class="card-content" style="text-align: center; font-family: 'Times New Roman', Times, serif; color: #1E293B; font-size: 20px; font-weight: 700;">Admin DashBoard</div>""", unsafe_allow_html=True)
    st.markdown("<p style='font-family: sans-serif; font-size: 14px; color: #64748B; margin-bottom: 25px;'>Analyze operational logs, secure administrative configurations, and edit global secrets.</p>", unsafe_allow_html=True)
    if is_mgmt_locked():
        remaining = int(st.session_state.mgmt_lock_until - time.time())
        st.button(f"Console Locked ({remaining}s) 🔒", disabled=True, use_container_width=True, key="mgmt_btn")
    else:
        if st.button("Admin Access →", use_container_width=True, key="mgmt_btn"):
            st.session_state.show_mgmt_password = True
            st.session_state.show_hr_password = False
            st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)









# =========================================================
# PASSWORD VERIFICATION SHEETS
# =========================================================

# 1. HR SECURITY VERIFICATION
if st.session_state.show_hr_password:
    st.write("---")
    st.markdown('<div id="security_form_hr"></div>', unsafe_allow_html=True)
    st.components.v1.html("""<script>setTimeout(function() {var el = window.parent.document.getElementById('security_form_hr'); if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }}, 100);</script>""", height=0)
    
    sheet_left, sheet_center, sheet_right = st.columns([1, 5, 1])
    with sheet_center:
        with st.form("hr_pass_form", clear_on_submit=True):
            st.markdown("<h3 style='text-align: center; color: #1E293B; font-weight: 700; font-size: 20px; margin-bottom: 5px;'>HR Security Verification</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #64748B; font-size: 13px; margin-bottom: 20px;'>Input administrative access credentials to proceed into HR environments.</p>", unsafe_allow_html=True)
            
            hr_password_input = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Enter HR System Password", key="hr_pwd_field")
            
            st.write("##")
            action_col1, action_col2 = st.columns(2, gap="medium")
            with action_col2:
                if st.form_submit_button("Abort HR Login", use_container_width=True):
                    st.session_state.show_hr_password = False
                    st.rerun()
            with action_col1:
                if st.form_submit_button("Verify & Open HR", use_container_width=True):
                    if hr_password_input == st.secrets["HR_PASSWORD"]:
                        st.session_state.show_hr_password = False
                        st.switch_page("pages/staff_schedule.py")
                    else:
                        st.error("Access Refused: Invalid token signature.")

# 2. HQ ADMINISTRATION SECURITY VERIFICATION
if st.session_state.show_mgmt_password:
    st.write("---")
    st.markdown('<div id="security_form"></div>', unsafe_allow_html=True)
    st.components.v1.html("""<script>setTimeout(function() {var el = window.parent.document.getElementById('security_form'); if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }}, 100);</script>""", height=0)
    
    sheet_left, sheet_center, sheet_right = st.columns([1, 5, 1])
    with sheet_center:
        with st.form("pass_form", clear_on_submit=True):
            st.markdown("<h3 style='text-align: center; color: #1E293B; font-weight: 700; font-size: 20px; margin-bottom: 5px;'>Administration Security Verification</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #64748B; font-size: 13px; margin-bottom: 20px;'>Input administrative access credentials to proceed into critical system files.</p>", unsafe_allow_html=True)
            
            password_input = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Enter Administration Password", key="mgmt_pwd_field")
            
            st.write("##")
            action_col1, action_col2 = st.columns(2, gap="medium")
            with action_col2:
                if st.form_submit_button("Abort Login", use_container_width=True):
                    st.session_state.show_mgmt_password = False
                    st.rerun()
            with action_col1:
                if st.form_submit_button("Verify & Open", use_container_width=True):
                    if password_input == st.secrets["MANAGER_PASSWORD"]:
                        st.session_state.user_role = "admin"
                        st.session_state.show_mgmt_password = False
                        st.switch_page("pages/management_dashboard.py")
                    elif password_input == st.secrets["AREA_MANAGER_PASSWORD"]:
                        st.session_state.user_role = "area_manager"
                        st.session_state.show_mgmt_password = False
                        st.switch_page("pages/management_dashboard.py")

                    
                    else:
                        st.error("Access Refused: Invalid credentials or system configuration error.")
                        




