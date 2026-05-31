import json
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore


@st.cache_resource
def init_firestore():

    raw = st.secrets["FIREBASE_KEY"]

    # convert string → dict safely
    key_dict = json.loads(raw)

    if not firebase_admin._apps:
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred)

    return firestore.client()


db = init_firestore()
