import os
from pathlib import Path
import time
import pandas as pd
import streamlit as st
from core.scan import largest_dirs, recent_files, human_size

st.set_page_config(page_title="Disk Avcısı (Streamlit)", layout="wide")

st.title("💽 Disk Avcısı — Streamlit GUI")

# --- SIDEBAR ---
st.sidebar.header("Ayarlar")
default_root = str(Path.home())
root_input = st.sidebar.text_input("Kök klasör yolu", value=default_root, key="root_path")
top_n = st.sidebar.number_input("En büyük kaç klasör?", min_value=3, max_value=50, value=10, step=1, key="topn")
days = st.sidebar.slider("Son kaç gün değişen dosyalar?", min_value=1, max_value=30, value=7, key="days")
limit_recent = st.sidebar.number_input("Recent dosya limiti", min_value=50, max_value=2000, value=300, step=50, key="limit_recent")
scan_btn = st.sidebar.button("Tara", type="primary", key="scan_button")

# --- VALIDATION ---
root_path = Path(root_input).expanduser()
if not root_path.exists() or not root_path.is_dir():
    st.warning("Geçerli bir klasör yolu giriniz. Örn: `/home/kullanici`")
    st.stop()

@st.cache_data(show_spinner=False)
def run_scan(root: str, top_n: int, days: int, limit_recent: int):
    root_p = Path(root)
    big = largest_dirs(root_p, top_n=top_n)
    rec = recent_files(root_p, days=days, limit=limit_recent)
    big_df = pd.DataFrame(big)[["path","size_h","size_bytes","type"]]
    rec_df = pd.DataFrame(rec)
    if not rec_df.empty:
        rec_df["mtime_readable"] = pd.to_datetime(rec_df["mtime"], unit="s")
        rec_df = rec_df[["path","mtime_readable","size_h","size_bytes","type"]]
    return big_df, rec_df

# --- ACTION ---
if scan_btn:
    with st.spinner("Taranıyor… sabit disk canavarına dürbün tutuyoruz 🔎"):
        big_df, rec_df = run_scan(str(root_path), top_n, days, limit_recent)

    st.subheader("📁 En Büyük Klasörler")
    if big_df.empty:
        st.info("Klasör bulunamadı ya da boyutlar hesaplanamadı.")
    else:
        st.dataframe(big_df, use_container_width=True, hide_index=True)
        csv_big = big_df.to_csv(index=False).encode("utf-8")
        st.download_button("CSV indir (largest)", csv_big, file_name="largest.csv", mime="text/csv", key="dl_big")

    st.subheader(f"🕒 Son {days} Günde Değişen Dosyalar")
    if rec_df.empty:
        st.info("Kayıt bulunamadı.")
    else:
        st.dataframe(rec_df, use_container_width=True, hide_index=True)
        csv_rec = rec_df.to_csv(index=False).encode("utf-8")
        st.download_button("CSV indir (recent)", csv_rec, file_name="recent.csv", mime="text/csv", key="dl_recent")

    st.caption(f"Kök: {root_path} • Zaman: {time.strftime('%Y-%m-%d %H:%M:%S')}")
else:
    st.info("Sol taraftan ayarları kontrol edip **Tara** butonuna bas.")
