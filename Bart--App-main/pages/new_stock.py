import streamlit as st


import streamlit as st
from background import set_background

# Set the universal background
set_background("bart2.png")

# Rest of your page content stays the same
st.markdown("## Welcome to BART")
st.write("Your page content goes here...")

st.set_page_config(layout="wide")

hide_streamlit = """
<style>
/* Hide all Streamlit UI elements & prevent extra side columns */
#MainMenu {{visibility:hidden;}}
footer {{visibility:hidden;}}
header {{visibility:hidden;}}
[data-testid="stToolbar"] {{display:none;}}
[data-testid="stSidebar"] {{display:none;}}
.block-container {{
    padding:0 !important;
    margin:0 auto !important;
    max-width: 100% !important;
}}

#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
header {visibility:hidden;}
[data-testid="stToolbar"] {display:none;}
[data-testid="stSidebar"] {display:none;}
</style>
"""

st.markdown(hide_streamlit, unsafe_allow_html=True)

st.title("New Stock Entry")

product = st.text_input("Product Name")
quantity = st.number_input("Quantity Added",min_value=0)
#supplier = st.text_input("Supplier")

if st.button("Submit"):
    st.success("Stock Added")

if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")