import streamlit as st
import pandas as pd
from datetime import datetime
import io

# ============================================
# GOOGLE SHEETS
# ============================================
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSHEETS = True
except ImportError:
    HAS_GSHEETS = False

st.set_page_config(page_title="PO Extractor", layout="wide")
st.title("📄 Ekstrak Data Purchase Order")

# ============================================
# SESSION STATE
# ============================================
if 'data_po' not in st.session_state:
    st.session_state.data_po = []

# ============================================
# FUNGSI FORMAT RUPIAH
# ============================================
def format_rupiah(angka):
    try:
        return f"Rp {angka:,.0f}".replace(',', '.')
    except:
        return "Rp 0"

# ============================================
# FUNGSI GOOGLE SHEETS
# ============================================
def get_gsheet_client():
    if not HAS_GSHEETS:
        return None, "Library gspread tidak tersedia"
    
    try:
        creds_dict = {
            "type": st.secrets["gsheets"]["type"],
            "project_id": st.secrets["gsheets"]["project_id"],
            "private_key_id": st.secrets["gsheets"]["private_key_id"],
            "private_key": st.secrets["gsheets"]["private_key"],
            "client_email": st.secrets["gsheets"]["client_email"],
            "client_id": st.secrets["gsheets"]["client_id"],
            "auth_uri": st.secrets["gsheets"]["auth_uri"],
            "token_uri": st.secrets["gsheets"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"]
        }
        
        scope = ['https://spreadsheets.google.com/feeds', 
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client, None
    except Exception as e:
        return None, str(e)

def save_to_gsheet():
    if not HAS_GSHEETS:
        st.error("❌ Library gspread belum terinstall")
        return
    
    if not st.session_state.data_po:
        st.warning("⚠️ Tidak ada data untuk disimpan")
        return
    
    client, error = get_gsheet_client()
    if error:
        st.error(f"❌ Gagal koneksi: {error}")
        return
    
    try:
        sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.get_worksheet(0)
        
        df_to_save = pd.DataFrame(st.session_state.data_po)
        data_to_save = [df_to_save.columns.values.tolist()] + df_to_save.values.tolist()
        
        worksheet.clear()
        worksheet.update(data_to_save, value_input_option='USER_ENTERED')
        
        st.success(f"✅ {len(df_to_save)} data berhasil disimpan ke Google Sheets!")
        
    except Exception as e:
        st.error(f"❌ Gagal menyimpan: {e}")

def load_from_gsheet():
    if not HAS_GSHEETS:
        st.error("❌ Library gspread belum terinstall")
        return
    
    client, error = get_gsheet_client()
    if error:
        st.error(f"❌ Gagal koneksi: {error}")
        return
    
    try:
        sheet_url = st.secrets["gsheets"]["spreadsheet_url"]
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.get_worksheet(0)
        
        data = worksheet.get_all_values()
        
        if data and len(data) > 1:
            headers = data[0]
            rows = data[1:]
            
            df_loaded = pd.DataFrame(rows, columns=headers)
            
            if 'total_nilai' in df_loaded.columns:
                df_loaded['total_nilai'] = pd.to_numeric(df_loaded['total_nilai'], errors='coerce').fillna(0)
            
            if 'nomor_urut' in df_loaded.columns:
                df_loaded['nomor_urut'] = pd.to_numeric(df_loaded['nomor_urut'], errors='coerce').fillna(0).astype(int)
            
            st.session_state.data_po = df_loaded.to_dict('records')
            st.success(f"📂 Berhasil memuat {len(st.session_state.data_po)} data dari Google Sheets")
            st.rerun()
        else:
            st.info("📂 Google Sheets kosong")
            
    except Exception as e:
        st.error(f"❌ Gagal memuat: {e}")

# ============================================
# SIDEBAR
# ============================================
with st.sidebar:
    st.header("📝 Input Data Manual")
    
    tanggal_m = st.date_input(
        "📅 Tanggal PO",
        value=datetime.now().date(),
        format="DD/MM/YYYY"
    )
    
    no_po_m = st.text_input("📋 No. PO Customer")
    perusahaan_m = st.text_input("🏢 Nama Perusahaan")
    pic_m = st.text_input("👤 Nama PIC")
    
    total_m = st.number_input(
        "💰 Total Nilai PO",
        min_value=0.0,
        step=1000.0,
        format="%.0f"
    )
    
    if total_m > 0:
        st.success(f"**Format Rupiah:** {format_rupiah(total_m)}")
    
    items_m = st.text_input("📦 Item Produk (pisahkan dengan koma)")
    bayar_m = st.text_input("⏱️ Waktu Pembayaran (contoh: 30 hari)")
    
    if st.button("➕ Tambahkan Data"):
        tanggal_str = tanggal_m.strftime("%d/%m/%Y")
        
        data = {
            'nomor_urut': len(st.session_state.data_po) + 1,
            'tanggal_po': tanggal_str,
            'nomor_po_customer': no_po_m if no_po_m else "-",
            'nama_perusahaan': perusahaan_m if perusahaan_m else "-",
            'nama_pic': pic_m if pic_m else "-",
            'total_nilai': total_m,
            'item_produk': items_m if items_m else "-",
            'waktu_pembayaran': bayar_m if bayar_m else "-",
            'sumber': 'Manual Input'
        }
        
        if no_po_m or perusahaan_m or total_m > 0:
            st.session_state.data_po.append(data)
            st.success(f"✅ Data berhasil ditambahkan!")
            st.rerun()
        else:
            st.warning("⚠️ Minimal isi No. PO, Perusahaan, atau Total Nilai")
    
    # ===== GOOGLE SHEETS =====
    st.markdown("---")
    st.subheader("💾 Google Sheets")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Simpan ke GSheet"):
            save_to_gsheet()
    with col2:
        if st.button("📂 Muat dari GSheet"):
            load_from_gsheet()

# ============================================
# DATA
# ============================================
if st.session_state.data_po:
    df = pd.DataFrame(st.session_state.data_po)
    
    st.dataframe(
        df,
        column_config={
            "nomor_urut": "No",
            "tanggal_po": "Tanggal PO",
            "nomor_po_customer": "No. PO Customer",
            "nama_perusahaan": "Perusahaan",
            "nama_pic": "PIC",
            "total_nilai": st.column_config.NumberColumn(
                "Total Nilai",
                format="Rp %,.0f"
            ),
            "item_produk": "Item Produk",
            "waktu_pembayaran": "Waktu Bayar",
            "sumber": "Sumber"
        },
        hide_index=True,
        use_container_width=True
    )
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total PO", len(df))
    with col2:
        total_nilai = df['total_nilai'].sum() if 'total_nilai' in df.columns else 0
        st.metric("💰 Total Nilai", format_rupiah(total_nilai))
    with col3:
        avg_nilai = df['total_nilai'].mean() if 'total_nilai' in df.columns else 0
        st.metric("📈 Rata-rata", format_rupiah(avg_nilai))
    with col4:
        max_nilai = df['total_nilai'].max() if 'total_nilai' in df.columns else 0
        st.metric("🏆 Tertinggi", format_rupiah(max_nilai))
    
    if st.button("📥 Download Excel"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Data PO', index=False)
        output.seek(0)
        st.download_button(
            label="Klik untuk download",
            data=output,
            file_name=f"Data_PO_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("💡 Input data manual untuk memulai")