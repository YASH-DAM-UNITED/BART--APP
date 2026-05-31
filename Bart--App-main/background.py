# background.py
import streamlit as st
import base64

def set_background(image_path="barthomepage.jpg"):
    """Set a universal background image for all Streamlit pages."""
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode()
    
    css = f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpg;base64,{image_base64}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: scroll; /* allows scrolling */
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)