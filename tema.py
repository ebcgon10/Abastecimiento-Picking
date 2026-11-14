"""Tema visual CCU (verde / blanco), igual en todas las apps del CD.
Uso: import tema; tema.aplicar()  — justo después de st.set_page_config(...)."""
import streamlit as st

VERDE = "#5BB030"
VERDE_OSC = "#205C40"
FONDO = "#DCEBD9"


def aplicar():
    st.markdown(f"""<style>
    .stApp {{ background-color: {FONDO}; }}
    header[data-testid="stHeader"] {{ background: {FONDO}; }}
    header[data-testid="stHeader"] * {{ color: {VERDE_OSC} !important; }}
    h1, h2, h3 {{ color: {VERDE_OSC} !important; }}
    section[data-testid="stSidebar"] {{ background: #F2F8F0; }}
    div.stButton > button {{ background-color: {VERDE}; color: #fff; font-weight: 700; border: none;
        border-radius: 8px; }}
    div.stButton > button:hover {{ background-color: #4E9A28; color: #fff; }}
    div[data-testid="stFileUploader"] {{ background: #fff; border-radius: 14px; padding: 10px 16px; }}
    div[data-testid="stFileUploader"] label p {{ color: {VERDE_OSC} !important; font-weight: 600; }}
    section[data-testid="stFileUploaderDropzone"] {{ background: #F2F8F0 !important;
        border: 2px dashed {VERDE} !important; }}
    section[data-testid="stFileUploaderDropzone"] *, div[data-testid="stFileUploaderFile"],
    div[data-testid="stFileUploaderFile"] * {{ color: {VERDE_OSC} !important; }}
    div[data-testid="stFileUploader"] button {{ background: #fff !important; color: {VERDE_OSC} !important;
        border: 1px solid {VERDE} !important; }}
    div[data-testid="stAlert"] {{ background: #FFFFFF !important; border-left: 6px solid {VERDE} !important;
        border-radius: 10px; }}
    div[data-testid="stAlert"] * {{ color: {VERDE_OSC} !important; }}
    div[data-testid="stDownloadButton"] button {{ background: #fff !important; color: {VERDE_OSC} !important;
        border: 2px solid {VERDE} !important; font-weight: 700; }}
    div[data-testid="stMetric"] {{ background: #fff; border-radius: 10px; padding: 10px 14px;
        border-left: 5px solid {VERDE}; }}
    div[data-testid="stTabs"] button[aria-selected="true"] p {{ color: {VERDE_OSC} !important; font-weight: 700; }}
    hr {{ border-color: #B9D3B2 !important; }}
    </style>""", unsafe_allow_html=True)
