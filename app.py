import os
import sys
import tempfile
import traceback
import re
import io
from datetime import datetime

# ============================================
# SETTING TESSERACT - HARUS PALING AWAL
# ============================================
os.environ['TESSDATA_PREFIX'] = r'C:\Program Files\Tesseract-OCR'

tesseract_dir = r'C:\Program Files\Tesseract-OCR'
if os.path.exists(tesseract_dir):
    os.environ['PATH'] = tesseract_dir + ';' + os.environ.get('PATH', '')

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

import streamlit as st
import pandas as pd
from PIL import Image, ImageEnhance, ImageOps
import pdf2image

# Coba import PDF extractor
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except:
    HAS_PDFPLUMBER = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except:
    HAS_PYPDF2 = False

# ============================================
# SETTING POPPLER
# ============================================
POPPLER_PATH = r'C:\poppler-26.02.0\Library\bin'

MAX_PAGES = 15

st.set_page_config(page_title="PO Extractor", layout="wide")
st.title("📄 Ekstrak Data Purchase Order")

# ============================================
# FUNGSI FORMAT RUPIAH
# ============================================
def format_rupiah(angka):
    """Format angka menjadi Rupiah dengan pemisah ribuan"""
    try:
        return f"Rp {angka:,.0f}".replace(',', '.')
    except:
        return "Rp 0"

def parse_rupiah(text):
    """Parse string Rupiah menjadi angka"""
    try:
        clean = text.replace('Rp', '').replace(' ', '').replace('.', '')
        return float(clean) if clean else 0
    except:
        return 0

# ============================================
# SESSION STATE
# ============================================
if 'data_po' not in st.session_state:
    st.session_state.data_po = []
if 'error_files' not in st.session_state:
    st.session_state.error_files = []
if 'debug_info' not in st.session_state:
    st.session_state.debug_info = []
if 'ocr_preview' not in st.session_state:
    st.session_state.ocr_preview = {}

# ============================================
# FUNGSI OCR DAN EKSTRAK
# ============================================

def preprocess_image(gambar):
    if gambar.mode != 'L':
        gambar = gambar.convert('L')
    
    max_size = 3000
    if max(gambar.size) > max_size:
        ratio = max_size / max(gambar.size)
        new_size = (int(gambar.size[0] * ratio), int(gambar.size[1] * ratio))
        gambar = gambar.resize(new_size, Image.LANCZOS)
    
    enhancer = ImageEnhance.Contrast(gambar)
    gambar = enhancer.enhance(2.0)
    
    enhancer = ImageEnhance.Sharpness(gambar)
    gambar = enhancer.enhance(2.0)
    
    gambar = ImageOps.autocontrast(gambar, cutoff=5)
    
    return gambar

def extract_text_from_image(gambar):
    try:
        gambar = preprocess_image(gambar)
        
        configs = [
            r'--oem 3 --psm 6 -l ind+eng',
            r'--oem 3 --psm 3 -l ind+eng',
            r'--oem 3 --psm 4 -l ind+eng',
            r'--oem 3 --psm 11 -l ind+eng',
            r'--oem 3 --psm 6 -l eng',
        ]
        
        for config in configs:
            try:
                text = pytesseract.image_to_string(gambar, config=config)
                if text and len(text.strip()) > 10:
                    return text
            except:
                continue
        
        try:
            text = pytesseract.image_to_string(gambar)
            if text and len(text.strip()) > 10:
                return text
        except:
            pass
        
        return "❌ Tidak ada teks terbaca"
            
    except Exception as e:
        return f"❌ OCR Error: {str(e)}"

def extract_text_from_pdf_direct(file_pdf):
    """Ekstrak teks langsung dari PDF (jika bukan scan)"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(file_pdf.getvalue())
            tmp_path = tmp.name
        
        text = ""
        
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(tmp_path) as pdf:
                    for page in pdf.pages[:MAX_PAGES]:
                        page_text = page.extract_text() or ""
                        text += page_text + "\n"
                os.unlink(tmp_path)
                if len(text.strip()) > 50:
                    return text
            except:
                pass
        
        if HAS_PYPDF2:
            try:
                reader = PyPDF2.PdfReader(tmp_path)
                for page in reader.pages[:MAX_PAGES]:
                    text += page.extract_text() or ""
                os.unlink(tmp_path)
                if len(text.strip()) > 50:
                    return text
            except:
                pass
        
        os.unlink(tmp_path)
        return None
        
    except Exception as e:
        return None

def extract_text_from_pdf(file_pdf):
    file_name = file_pdf.name
    debug_info = []
    
    # Pertama, coba ekstrak teks langsung
    direct_text = extract_text_from_pdf_direct(file_pdf)
    if direct_text and len(direct_text.strip()) > 50:
        debug_info.append(f"✅ Teks diekstrak langsung dari PDF ({len(direct_text)} karakter)")
        st.session_state.debug_info.append({
            'file': file_name,
            'status': 'success',
            'info': debug_info
        })
        st.session_state.ocr_preview[file_name] = {
            'text': direct_text[:2000],
            'length': len(direct_text)
        }
        return direct_text
    
    debug_info.append("🔄 PDF tidak readable, mencoba OCR...")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(file_pdf.getvalue())
            tmp_path = tmp_file.name
        
        images = None
        for dpi in [300, 200, 150]:
            try:
                images = pdf2image.convert_from_path(
                    tmp_path,
                    poppler_path=POPPLER_PATH,
                    dpi=dpi,
                    first_page=1,
                    last_page=MAX_PAGES,
                    thread_count=1
                )
                debug_info.append(f"✅ Converted {len(images)} pages with DPI={dpi}")
                break
            except Exception as e:
                debug_info.append(f"❌ DPI={dpi} failed: {str(e)}")
                continue
        
        os.unlink(tmp_path)
        
        if not images:
            raise Exception("No pages extracted from PDF")
        
        full_text = ""
        for i, img in enumerate(images):
            debug_info.append(f"📄 Processing page {i+1}/{len(images)}...")
            page_text = extract_text_from_image(img)
            full_text += page_text + "\n\n"
            debug_info.append(f"   Page {i+1} text length: {len(page_text)} characters")
        
        st.session_state.ocr_preview[file_name] = {
            'text': full_text[:2000],
            'length': len(full_text)
        }
        
        st.session_state.debug_info.append({
            'file': file_name,
            'status': 'success',
            'info': debug_info
        })
        
        return full_text
        
    except Exception as e:
        error_msg = str(e)
        debug_info.append(f"❌ ERROR: {error_msg}")
        
        st.session_state.debug_info.append({
            'file': file_name,
            'status': 'error',
            'info': debug_info
        })
        
        return f"❌ {error_msg[:150]}"

def extract_data_from_text(teks, nomor_urut):
    data = {
        'nomor_urut': nomor_urut,
        'tanggal_po': '',
        'nomor_po_customer': '',
        'nama_perusahaan': '',
        'nama_pic': '',
        'total_nilai': 0,
        'item_produk': '',
        'waktu_pembayaran': ''
    }
    
    if not teks or teks.startswith('❌'):
        return data
    
    st.session_state._last_text_sample = teks[:1000]
    
    # Cari tanggal
    date_patterns = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',
        r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Aug|Sep|Okt|Nov|Des)\s+(\d{4})',
        r'Tanggal\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'Date\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    ]
    for pattern in date_patterns:
        match = re.search(pattern, teks, re.IGNORECASE)
        if match:
            data['tanggal_po'] = match.group(0)
            break
    
    # Cari nomor PO
    po_patterns = [
        r'PO\s*[:#]?\s*([A-Z0-9-]+)',
        r'Purchase\s*Order\s*[:#]?\s*([A-Z0-9-]+)',
        r'No\.?\s*PO\s*[:#]?\s*([A-Z0-9-]+)',
        r'PO[-_]\s*([A-Z0-9-]+)',
        r'Nomor\s*PO\s*[:#]?\s*([A-Z0-9-]+)'
    ]
    for pattern in po_patterns:
        match = re.search(pattern, teks, re.IGNORECASE)
        if match:
            data['nomor_po_customer'] = match.group(1)
            break
    
    # Cari nama perusahaan
    lines = teks.split('\n')
    for line in lines[:50]:
        line = line.strip()
        if re.search(r'(PT|CV|UD|Perusahaan|Company|CORPORATION)', line, re.IGNORECASE):
            if len(line) > 5 and len(line) < 100:
                data['nama_perusahaan'] = line
                break
    
    # Cari PIC
    pic_patterns = [
        r'PIC\s*[:#]?\s*([A-Za-z\s.]+)',
        r'Contact\s*Person\s*[:#]?\s*([A-Za-z\s.]+)',
        r'Attn\.?\s*[:#]?\s*([A-Za-z\s.]+)',
        r'Kontak\s*[:#]?\s*([A-Za-z\s.]+)'
    ]
    for pattern in pic_patterns:
        match = re.search(pattern, teks, re.IGNORECASE)
        if match:
            pic = match.group(1).strip()
            if len(pic) > 3:
                data['nama_pic'] = pic
                break
    
    # Cari total nilai
    total_patterns = [
        r'Total\s*[:#]?\s*Rp\s*([\d,.]+)',
        r'Grand\s*Total\s*[:#]?\s*Rp\s*([\d,.]+)',
        r'Jumlah\s*[:#]?\s*Rp\s*([\d,.]+)',
        r'Rp\s*([\d,.]+)\s*(?:,-|\.-)',
        r'Total\s*[:#]?\s*([\d,.]+)'
    ]
    for pattern in total_patterns:
        match = re.search(pattern, teks, re.IGNORECASE)
        if match:
            try:
                nilai = match.group(1).replace('.', '').replace(',', '.')
                data['total_nilai'] = float(nilai)
                break
            except:
                pass
    
    # Cari item produk
    items = []
    for line in lines[:50]:
        line = line.strip()
        if re.search(r'^\s*\d+[\.\)]?\s+[A-Za-z]', line):
            items.append(line[:100])
        elif re.search(r'[A-Za-z]+\s+[A-Za-z]+\s+\d+', line):
            if len(line) > 10 and len(line) < 100:
                items.append(line[:100])
    data['item_produk'] = ', '.join(items[:5])
    
    # Cari waktu pembayaran
    payment_patterns = [
        r'(\d+)\s*(days?|hari?)',
        r'Term\s*[:#]?\s*(\d+)\s*(days?|hari?)',
        r'Pembayaran\s*[:#]?\s*(\d+)\s*(days?|hari?)',
        r'Jatuh\s*Tempo\s*[:#]?\s*(\d+)\s*(days?|hari?)'
    ]
    for pattern in payment_patterns:
        match = re.search(pattern, teks, re.IGNORECASE)
        if match:
            data['waktu_pembayaran'] = f"{match.group(1)} hari"
            break
    
    return data

# ============================================
# SIDEBAR
# ============================================
with st.sidebar:
    st.header("📤 Upload File")
    
    with st.expander("🔧 Status Library"):
        st.write(f"✅ Pdfplumber: {'Tersedia' if HAS_PDFPLUMBER else 'Tidak tersedia'}")
        st.write(f"✅ PyPDF2: {'Tersedia' if HAS_PYPDF2 else 'Tidak tersedia'}")
        st.write(f"✅ Tesseract: {'Tersedia' if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe') else 'Tidak tersedia'}")
    
    st.info("📌 **Tips:**\n"
            "- Untuk hasil terbaik, gunakan PDF yang teksnya bisa di-copy\n"
            "- Jika PDF scan, pastikan kualitas gambar bagus\n"
            f"- Maksimal {MAX_PAGES} halaman per PDF\n"
            "- Bisa juga upload gambar JPG/PNG")
    
    uploaded_files = st.file_uploader(
        "Pilih file (gambar/PDF)",
        type=['png', 'jpg', 'jpeg', 'pdf'],
        accept_multiple_files=True
    )
    
    if st.button("🚀 Proses Data", use_container_width=True):
        if uploaded_files:
            st.session_state.error_files = []
            st.session_state.debug_info = []
            st.session_state.ocr_preview = {}
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, file in enumerate(uploaded_files):
                status_text.write(f"Memproses {i+1}/{len(uploaded_files)}: {file.name}")
                
                try:
                    if file.type == 'application/pdf':
                        teks = extract_text_from_pdf(file)
                    else:
                        gambar = Image.open(file)
                        teks = extract_text_from_image(gambar)
                        st.session_state.ocr_preview[file.name] = {
                            'text': teks[:2000],
                            'length': len(teks)
                        }
                    
                    if teks and teks.startswith('❌'):
                        st.session_state.error_files.append({
                            'file': file.name,
                            'error': teks,
                            'debug': st.session_state.debug_info[-1]['info'] if st.session_state.debug_info else []
                        })
                    elif teks and len(teks.strip()) > 20:
                        data = extract_data_from_text(teks, len(st.session_state.data_po) + i + 1)
                        data['nama_file'] = file.name
                        
                        if data['nomor_po_customer'] or data['nama_perusahaan'] or data['total_nilai'] > 0:
                            st.session_state.data_po.append(data)
                        else:
                            st.session_state.error_files.append({
                                'file': file.name,
                                'error': '⚠️ Tidak ada data PO yang bisa diekstrak',
                                'debug': st.session_state.debug_info[-1]['info'] if st.session_state.debug_info else []
                            })
                    else:
                        st.session_state.error_files.append({
                            'file': file.name,
                            'error': '❌ Tidak ada teks yang terbaca',
                            'debug': st.session_state.debug_info[-1]['info'] if st.session_state.debug_info else []
                        })
                        
                except Exception as e:
                    st.session_state.error_files.append({
                        'file': file.name,
                        'error': f"❌ {str(e)[:150]}",
                        'debug': [traceback.format_exc()]
                    })
                
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            status_text.write("✅ Selesai!")
            
            if st.session_state.error_files:
                st.warning(f"⚠️ {len(st.session_state.error_files)} file gagal diproses")
            
            st.rerun()
        else:
            st.warning("⚠️ Upload file dulu")
    
    # ===== INPUT MANUAL =====
    with st.expander("📝 Input Data Manual (Alternatif)"):
        st.write("Jika OCR gagal, input data secara manual:")
        
        # Tanggal dengan date picker
        tanggal_m = st.date_input(
            "📅 Tanggal PO",
            value=datetime.now().date(),
            key="manual_date",
            format="DD/MM/YYYY"
        )
        
        no_po_m = st.text_input("📋 No. PO Customer", key="manual_po")
        perusahaan_m = st.text_input("🏢 Nama Perusahaan", key="manual_company")
        pic_m = st.text_input("👤 Nama PIC", key="manual_pic")
        
        # Total nilai dengan format Rupiah
        total_m = st.number_input(
            "💰 Total Nilai PO",
            min_value=0.0,
            step=1000.0,
            key="manual_total",
            format="%.0f"
        )
        
        # Tampilkan format Rupiah
        if total_m > 0:
            st.success(f"**Format Rupiah:** {format_rupiah(total_m)}")
        
        items_m = st.text_input("📦 Item Produk (pisahkan dengan koma)", key="manual_items")
        bayar_m = st.text_input("⏱️ Waktu Pembayaran (contoh: 30 hari)", key="manual_payment")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Tambahkan Data", use_container_width=True):
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
                    'nama_file': 'Manual Input'
                }
                
                if no_po_m or perusahaan_m or total_m > 0:
                    st.session_state.data_po.append(data)
                    st.success(f"✅ Data berhasil ditambahkan! (Total: {format_rupiah(total_m)})")
                    st.rerun()
                else:
                    st.warning("⚠️ Minimal isi No. PO, Perusahaan, atau Total Nilai")
        
        with col2:
            if st.button("🗑️ Kosongkan Form", use_container_width=True):
                st.rerun()

# ============================================
# TAMPILAN HASIL
# ============================================

# Preview OCR
if st.session_state.ocr_preview:
    with st.expander("📝 Preview Hasil OCR (Untuk Debug)"):
        for filename, data in st.session_state.ocr_preview.items():
            st.write(f"**{filename}** - {data['length']} karakter")
            if data['text'] and len(data['text']) > 10:
                st.text(data['text'][:1000])
                if data['length'] > 1000:
                    st.write(f"... dan {data['length'] - 1000} karakter lagi")
            else:
                st.write("⚠️ Tidak ada teks yang terbaca")

# Debug Info
if st.session_state.debug_info:
    with st.expander("🔍 Debug Info"):
        for debug in st.session_state.debug_info:
            st.write(f"**{debug['file']}** - Status: {debug['status']}")
            for info in debug['info']:
                st.write(f"  {info}")

# Error Files
if st.session_state.error_files:
    with st.expander(f"⚠️ {len(st.session_state.error_files)} File Gagal Diproses"):
        for err in st.session_state.error_files:
            st.write(f"❌ **{err['file']}**")
            st.write(f"   {err['error']}")
            if 'debug' in err and err['debug']:
                with st.expander("   📋 Detail"):
                    for line in err['debug']:
                        st.write(f"      {line}")

# ============================================
# DATA
# ============================================
if st.session_state.data_po:
    df = pd.DataFrame(st.session_state.data_po)
    
    # Tampilkan total nilai dengan format Rupiah di tabel
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
                format="Rp %,.0f"  # Format dengan pemisah ribuan
            ),
            "item_produk": "Item Produk",
            "waktu_pembayaran": "Waktu Bayar",
            "nama_file": "Sumber"
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Statistik
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
    
    # Download Excel
    if st.button("📥 Download Excel", use_container_width=True):
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
    st.info("💡 Upload file PO atau input manual untuk memulai")