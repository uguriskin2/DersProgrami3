import streamlit as st
import pandas as pd
import json
import os
import hashlib
import altair as alt
import base64
import io
import smtplib
import ssl
import time
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from solver import create_timetable

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

# --- Dosya İşlemleri ---
DATA_FILE = "okul_verileri.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data():
    data = {
        "branches": st.session_state.branches,
        "teachers": st.session_state.teachers,
        "courses": st.session_state.courses,
        "classes": st.session_state.classes,
        "rooms": st.session_state.rooms,
        "room_capacities": st.session_state.room_capacities,
        "room_branches": st.session_state.room_branches,
        "room_teachers": st.session_state.room_teachers,
        "room_courses": st.session_state.room_courses,
        "room_excluded_courses": st.session_state.get('room_excluded_courses', {}),
        "class_teachers": st.session_state.class_teachers,
        "class_lessons": st.session_state.class_lessons,
        "assignments": st.session_state.assignments,
        "lesson_config": st.session_state.get('lesson_config', {}),
        "simultaneous_lessons": st.session_state.get('simultaneous_lessons', {}),
        "report_config": st.session_state.get('report_config', {}),
        "email_config": st.session_state.get('email_config', {})
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    st.toast("Veriler Kaydedildi!", icon="💾")

def create_pdf_report(schedule_data, report_type="teacher", num_hours=8):
    if not FPDF: return None
    
    # Font Ayarları
    font_family = 'Arial'
    font_path = "arial.ttf"
    font_path_bold = "arialbd.ttf"
    font_path_italic = "ariali.ttf"
    
    if not os.path.exists(font_path) and os.path.exists("C:\\Windows\\Fonts\\arial.ttf"):
        font_path = "C:\\Windows\\Fonts\\arial.ttf"
    if not os.path.exists(font_path_bold) and os.path.exists("C:\\Windows\\Fonts\\arialbd.ttf"):
        font_path_bold = "C:\\Windows\\Fonts\\arialbd.ttf"
    if not os.path.exists(font_path_italic) and os.path.exists("C:\\Windows\\Fonts\\ariali.ttf"):
        font_path_italic = "C:\\Windows\\Fonts\\ariali.ttf"
    
    def clean_text(text):
        if font_family == 'TrArial':
            return str(text)
        replacements = {
            'ğ': 'g', 'Ğ': 'G', 'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I',
            'ç': 'c', 'Ç': 'C', 'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'
        }
        t = str(text)
        for k, v in replacements.items():
            t = t.replace(k, v)
        return t

    class PDF(FPDF):
        def header(self):
            self.set_font(font_family, 'B', 10)
            
            rep_conf = st.session_state.get('report_config', {})
            main_title = rep_conf.get('report_title', "")
            if main_title:
                self.cell(0, 5, clean_text(main_title), 0, 1, 'C')
            
            if report_type == "teacher": sub_title = 'Öğretmen Ders Programı'
            elif report_type == "class": sub_title = 'Sınıf Ders Programı'
            else: sub_title = 'Derslik Programı'
            self.cell(0, 5, clean_text(sub_title), 0, 1, 'C')
            self.ln(2)
    
    pdf = PDF(orientation='P')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Türkçe Font Ekleme
    if os.path.exists(font_path):
        try:
            # FPDF versiyonuna göre uni=True gerekebilir veya hata verebilir
            try:
                pdf.add_font('TrArial', '', font_path, uni=True)
            except TypeError:
                pdf.add_font('TrArial', '', font_path)
            
            # Bold font ekleme (Hata almamak için)
            if os.path.exists(font_path_bold):
                try:
                    pdf.add_font('TrArial', 'B', font_path_bold, uni=True)
                except TypeError:
                    pdf.add_font('TrArial', 'B', font_path_bold)
            else:
                try:
                    pdf.add_font('TrArial', 'B', font_path, uni=True)
                except TypeError:
                    pdf.add_font('TrArial', 'B', font_path)
            
            # Italic font ekleme (Hata almamak için)
            if os.path.exists(font_path_italic):
                try:
                    pdf.add_font('TrArial', 'I', font_path_italic, uni=True)
                except TypeError:
                    pdf.add_font('TrArial', 'I', font_path_italic)
            else:
                try:
                    pdf.add_font('TrArial', 'I', font_path, uni=True)
                except TypeError:
                    pdf.add_font('TrArial', 'I', font_path)
            
            font_family = 'TrArial'
        except:
            pass
    
    df = pd.DataFrame(schedule_data)
    days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
    hours = range(1, num_hours + 1)
    
    if report_type == "teacher":
        items = sorted(df['Öğretmen'].unique())
        group_col = 'Öğretmen'
        label_prefix = "Ogretmen: "
    elif report_type == "class":
        items = sorted(df['Sınıf'].unique())
        group_col = 'Sınıf'
        label_prefix = "Sinif: "
    else:
        items = sorted(df['Derslik'].unique())
        group_col = 'Derslik'
        label_prefix = "Derslik: "

    for item in items:
        pdf.add_page()
        pdf.set_font(font_family, 'B', 8)
        safe_name = str(item)
        
        # Toplam Ders Saati (Tablonun Üstünde)
        total_hours = len(df[df[group_col] == item])
        
        if report_type == "teacher":
            t_info = next((t for t in st.session_state.teachers if t['name'] == item), {})
            duty_day = t_info.get('duty_day', '-')
            safe_duty = str(duty_day) if duty_day and duty_day not in [None, "Yok", ""] else "-"
            
            header_text = f"Öğretmen: {safe_name}   |   Toplam Ders Saati: {total_hours}   |   Nöbet Günü: {safe_duty}"
            pdf.cell(0, 6, clean_text(header_text), ln=True)
        else:
            header_text = f"{label_prefix}{safe_name}"
            if report_type == "class" and 'class_teachers' in st.session_state:
                ct = st.session_state.class_teachers.get(item)
                if ct:
                    safe_ct = str(ct)
                    header_text += f" - Sınıf Öğretmeni: {safe_ct}"
            
            pdf.cell(0, 6, clean_text(header_text), ln=True)
            
            pdf.set_font(font_family, 'B', 7)
            pdf.cell(0, 6, f"Toplam Ders Saati: {total_hours}", ln=True)
        
        pdf.ln(2)
        
        pdf.set_font(font_family, 'B', 6)
        w_hour = 26
        w_day = 32
        pdf.cell(w_hour, 6, clean_text("Saat"), 1)
        for d in days:
            pdf.cell(w_day, 6, clean_text(d), 1)
        pdf.ln()
        
        pdf.set_font(font_family, '', 6)
        
        # Saat yapılandırmasını al
        lc = st.session_state.get('lesson_config', {"start_time": "08:30", "lesson_duration": 40, "break_duration": 10})
        try:
            sh, sm = map(int, lc.get("start_time", "08:30").split(":"))
            base_min = sh * 60 + sm
        except:
            base_min = 510 # 08:30
        l_dur = int(lc.get("lesson_duration", 40))
        b_dur = int(lc.get("break_duration", 10))
        lunch_dur = int(lc.get("lunch_duration", 40))
        
        # Öğle arası saati (int veya "Yok")
        lunch_h_val = lc.get("lunch_break_hour", "Yok")
        try:
            lunch_h = int(lunch_h_val)
        except:
            lunch_h = -1
            
        current_min = base_min
        
        for h in hours:
            is_lunch = (h == lunch_h)
            duration = lunch_dur if is_lunch else l_dur
            
            start_min = current_min
            end_min = start_min + duration
            
            time_str = f"{start_min//60:02d}:{start_min%60:02d}-{end_min//60:02d}:{end_min%60:02d}"
            pdf.cell(w_hour, 6, clean_text(time_str), 1)
            for d in days:
                if is_lunch:
                    content = clean_text("ÖĞLE ARASI")
                else:
                    lesson = df[(df[group_col] == item) & (df['Gün'] == d) & (df['Saat'] == h)]
                    if not lesson.empty:
                        row = lesson.iloc[0]
                        if report_type == "teacher":
                            content = f"{row['Sınıf']} - {row['Ders']}"
                        elif report_type == "class":
                            content = f"{row['Ders']} ({row['Öğretmen']})"
                        else:
                            content = f"{row['Sınıf']} - {row['Ders']} ({row['Öğretmen']})"
                    else:
                        content = "-"
                pdf.cell(w_day, 6, clean_text(content[:35]), 1)
            pdf.ln()
            
            # Bir sonraki dersin başlangıç saatini hesapla
            # Öğle arası bloğundan sonra ekstra teneffüs eklenmez (genellikle öğle arasına dahildir), 
            # normal derslerden sonra teneffüs eklenir.
            current_min += duration + (0 if is_lunch else b_dur)
            
        # Sınıf raporu için alt kısma ders özeti ekle
        if report_type == "class":
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 7)
            pdf.cell(0, 6, clean_text("Ders Listesi ve Saatleri:"), ln=True)
            
            class_df = df[df['Sınıf'] == item]
            if not class_df.empty:
                pdf.cell(70, 5, clean_text("Ders"), 1)
                pdf.cell(70, 5, clean_text("Öğretmen"), 1)
                pdf.cell(20, 5, clean_text("Saat"), 1, 1)
                
                pdf.set_font(font_family, '', 6)
                summary = class_df.groupby(['Ders', 'Öğretmen']).size().reset_index(name='Saat')
                for _, row in summary.iterrows():
                    c_name = str(row['Ders'])
                    t_name = str(row['Öğretmen'])
                    pdf.cell(70, 5, clean_text(c_name[:40]), 1)
                    pdf.cell(70, 5, clean_text(t_name[:40]), 1)
                    pdf.cell(20, 5, clean_text(str(row['Saat'])), 1, 1)
        
        # Derslik raporu için alt kısma ders özeti ekle
        if report_type == "room":
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 7)
            pdf.cell(0, 6, clean_text("Ders Listesi ve Saatleri:"), ln=True)
            
            room_df = df[df['Derslik'] == item]
            if not room_df.empty:
                pdf.cell(40, 5, clean_text("Sınıf"), 1)
                pdf.cell(50, 5, clean_text("Ders"), 1)
                pdf.cell(50, 5, clean_text("Öğretmen"), 1)
                pdf.cell(20, 5, clean_text("Saat"), 1, 1)
                
                pdf.set_font(font_family, '', 6)
                summary = room_df.groupby(['Sınıf', 'Ders', 'Öğretmen']).size().reset_index(name='Saat')
                for _, row in summary.iterrows():
                    c_name = str(row['Sınıf'])
                    d_name = str(row['Ders'])
                    t_name = str(row['Öğretmen'])
                    pdf.cell(40, 5, clean_text(c_name[:25]), 1)
                    pdf.cell(50, 5, clean_text(d_name[:30]), 1)
                    pdf.cell(50, 5, clean_text(t_name[:30]), 1)
                    pdf.cell(20, 5, clean_text(str(row['Saat'])), 1, 1)
        
        # Alt Bilgi Metni
        pdf.ln(3)
        pdf.set_font(font_family, 'I', 6)
        rep_conf = st.session_state.get('report_config', {})
        note_text = rep_conf.get('notification_text', "Bu Haftalık Ders Programı belirtilen tarihte tebliğ edildi.")
        pdf.multi_cell(0, 4, clean_text(note_text))
        
        # Öğretmen raporu için alt kısma toplam saat ve imza bölümü ekle
        if report_type == "teacher":
            pdf.ln(5)
            
            pdf.set_font(font_family, 'B', 7)
            pdf.ln(5)
            
            # İmza Bölümü
            w_half = 90
            pdf.cell(w_half, 6, clean_text("Ders Öğretmeni"), 0, 0, 'C')
            pdf.cell(w_half, 6, clean_text("Okul Müdürü"), 0, 1, 'C')
            
            pdf.set_font(font_family, '', 7)
            safe_teacher_name = str(item)
            principal_name = rep_conf.get('principal_name', "")
            
            pdf.cell(w_half, 6, clean_text(safe_teacher_name), 0, 0, 'C')
            pdf.cell(w_half, 6, clean_text(principal_name), 0, 1, 'C')
            
            pdf.ln(10)
            pdf.cell(w_half, 5, ".......................", 0, 0, 'C')
            pdf.cell(w_half, 5, ".......................", 0, 1, 'C')
            
    try:
        # FPDF 2.x için (bytes döner)
        return bytes(pdf.output())
    except TypeError:
        # FPDF 1.7.x için (string döner, encode gerekir)
        return pdf.output(dest='S').encode('latin-1', 'replace')

def check_conflicts(schedule, check_rooms=True):
    conflicts = []
    df = pd.DataFrame(schedule)
    
    # 1. Öğretmen Çakışması
    if "Öğretmen" in df.columns:
        t_groups = df.groupby(["Öğretmen", "Gün", "Saat"]).size()
        t_conflicts = t_groups[t_groups > 1]
        for idx, count in t_conflicts.items():
            conflicts.append(f"⚠️ Öğretmen Çakışması: {idx[0]} -> {idx[1]} {idx[2]}. Saat ({count} ders)")

    # 2. Sınıf Çakışması
    if "Sınıf" in df.columns:
        c_groups = df.groupby(["Sınıf", "Gün", "Saat"]).size()
        c_conflicts = c_groups[c_groups > 1]
        for idx, count in c_conflicts.items():
            conflicts.append(f"⚠️ Sınıf Çakışması: {idx[0]} -> {idx[1]} {idx[2]}. Saat ({count} ders)")

    # 3. Derslik Çakışması
    if check_rooms and "Derslik" in df.columns:
        # Boş olmayan derslikleri kontrol et
        r_df = df[df["Derslik"].notna() & (df["Derslik"] != "")]
        r_groups = r_df.groupby(["Derslik", "Gün", "Saat"]).size()
        
        for idx, count in r_groups.items():
            r_name = idx[0]
            cap = int(st.session_state.room_capacities.get(r_name, 1))
            if count > cap:
                conflicts.append(f"⚠️ Derslik Kapasite Aşımı: {r_name} -> {idx[1]} {idx[2]}. Saat ({count}/{cap} ders)")
            
    return conflicts

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Okul Ders Programı", layout="wide")

# --- Giriş Ekranı ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    # Arka plan resmi (background.jpg) varsa yükle
    if os.path.exists("background.jpg"):
        with open("background.jpg", "rb") as f:
            data = base64.b64encode(f.read()).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: url("data:image/jpg;base64,{data}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=200)
        st.title("Giriş Yap")
        username = st.text_input("Kullanıcı Adı")
        password = st.text_input("Şifre", type="password")
        if st.button("Giriş"):
            # Secrets üzerinden şifre kontrolü
            try:
                auth_secrets = st.secrets.get("auth", {})
            except Exception:
                auth_secrets = {}
            valid_user = auth_secrets.get("username", "admin")
            valid_pass = auth_secrets.get("password", "1234")

            if username == valid_user and password == valid_pass:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Hatalı kullanıcı adı veya şifre")
    st.stop()

# --- Session State Başlatma ---
saved_data = load_data()

if 'branches' not in st.session_state:
    st.session_state.branches = saved_data.get('branches', ["Matematik", "Fizik", "Kimya", "Biyoloji", "Edebiyat", "Tarih"])
if 'teachers' not in st.session_state:
    st.session_state.teachers = saved_data.get('teachers', [])
if 'courses' not in st.session_state:
    st.session_state.courses = saved_data.get('courses', [])
if 'classes' not in st.session_state:
    st.session_state.classes = saved_data.get('classes', ["9-A", "9-B", "10-A"])
if 'rooms' not in st.session_state:
    st.session_state.rooms = saved_data.get('rooms', [])
if 'room_capacities' not in st.session_state:
    st.session_state.room_capacities = saved_data.get('room_capacities', {})
if 'room_branches' not in st.session_state:
    st.session_state.room_branches = saved_data.get('room_branches', {})
if 'room_teachers' not in st.session_state:
    st.session_state.room_teachers = saved_data.get('room_teachers', {})
if 'room_courses' not in st.session_state:
    st.session_state.room_courses = saved_data.get('room_courses', {})
if 'room_excluded_courses' not in st.session_state:
    st.session_state.room_excluded_courses = saved_data.get('room_excluded_courses', {})
if 'class_teachers' not in st.session_state:
    st.session_state.class_teachers = saved_data.get('class_teachers', {})
if 'class_lessons' not in st.session_state:
    st.session_state.class_lessons = saved_data.get('class_lessons', {})
if 'assignments' not in st.session_state:
    st.session_state.assignments = saved_data.get('assignments', {})
if 'lesson_config' not in st.session_state:
    st.session_state.lesson_config = saved_data.get('lesson_config', {
        "start_time": "08:30", 
        "lesson_duration": 40, 
        "break_duration": 10,
        "lunch_duration": 50,
        "num_hours": 8,
        "lunch_break_hour": "Yok"
    })
if 'simultaneous_lessons' not in st.session_state:
    st.session_state.simultaneous_lessons = saved_data.get('simultaneous_lessons', {})
if 'report_config' not in st.session_state:
    st.session_state.report_config = saved_data.get('report_config', {
        "principal_name": "",
        "notification_text": "Bu Haftalık Ders Programı belirtilen tarihte tebliğ edildi.",
        "report_title": ""
    })
if 'email_config' not in st.session_state:
    st.session_state.email_config = saved_data.get('email_config', {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 465,
        "sender_email": "",
        "sender_password": "",
        "email_subject": "Haftalık Ders Programı",
        "email_body": "Sayın {name},\n\nYeni haftalık ders programınız ektedir.\n\nİyi çalışmalar dileriz."
    })

# --- Yan Menü ---
st.sidebar.title("Yönetim Paneli")
if st.sidebar.button("🚪 Çıkış Yap"):
    st.session_state.logged_in = False
    st.rerun()

if st.sidebar.button("💾 Tüm Verileri Kaydet"):
    save_data()

menu = st.sidebar.radio("Menü", ["Tanımlamalar", "Ders Atama & Kopyalama", "Program Oluştur", "Hızlı Düzenle", "Veri İşlemleri"])

# --- 1. TANIMLAMALAR ---
if menu == "Tanımlamalar":
    st.header("Veri Tanımlama Ekranı")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Branşlar", "Derslikler", "Öğretmenler", "Dersler", "Sınıflar"])

    with tab1: # Branşlar
        st.info("Branşları aşağıdaki tablodan ekleyebilir, düzenleyebilir veya silebilirsiniz.")
        df_branches = pd.DataFrame(st.session_state.branches, columns=["Branş"])
        edited_branches = st.data_editor(df_branches, num_rows="dynamic", width="stretch", key="editor_branches")
        if st.button("Branşları Kaydet", key="save_branches"):
            st.session_state.branches = edited_branches["Branş"].dropna().astype(str).tolist()
            save_data()
            st.success("Branş listesi güncellendi.")

    with tab2: # Derslikler
        st.info("Derslikleri, kapasitelerini, izin verilen branşları ve öğretmenleri yönetebilirsiniz.")
        
        # Mevcut veriyi tablo formatına getir
        room_data = []
        for r in st.session_state.rooms:
            room_data.append({
                "Derslik": r, 
                "Kapasite": st.session_state.room_capacities.get(r, 1),
                "İzin Verilen Branşlar": st.session_state.room_branches.get(r, []),
                "İzin Verilen Öğretmenler": st.session_state.room_teachers.get(r, []),
                "İzin Verilen Dersler": st.session_state.room_courses.get(r, [])
            })
            
        df_rooms = pd.DataFrame(room_data) if room_data else pd.DataFrame(columns=["Derslik", "Kapasite", "İzin Verilen Branşlar", "İzin Verilen Öğretmenler", "İzin Verilen Dersler"])

        edited_rooms = st.data_editor(
            df_rooms, 
            column_config={
                "Kapasite": st.column_config.NumberColumn("Kapasite", min_value=1, max_value=10, default=1, help="Bu derslikte aynı anda kaç sınıfın ders yapabileceğini belirtir. (Genellikle 1)"),
                "İzin Verilen Branşlar": st.column_config.ListColumn("İzin Verilen Branşlar", help="Bu dersliği kullanabilecek branşları seçin."),
                "İzin Verilen Öğretmenler": st.column_config.ListColumn("İzin Verilen Öğretmenler", help="Bu dersliği kullanabilecek öğretmenleri ekleyin."),
                "İzin Verilen Dersler": st.column_config.ListColumn("İzin Verilen Dersler", help="Bu derslikte işlenebilecek dersleri ekleyin.")
            },
            num_rows="dynamic", 
            width="stretch", 
            key="editor_rooms"
        )
        if st.button("Derslikleri Kaydet", key="save_rooms"):
            # Verileri session state'e aktar
            valid_rows = edited_rooms.dropna(subset=["Derslik"])
            st.session_state.rooms = valid_rows["Derslik"].astype(str).tolist()
            st.session_state.room_capacities = {str(row["Derslik"]): int(row.get("Kapasite", 1)) for _, row in valid_rows.iterrows()}
            st.session_state.room_branches = {str(row["Derslik"]): row.get("İzin Verilen Branşlar", []) for _, row in valid_rows.iterrows()}
            st.session_state.room_teachers = {str(row["Derslik"]): row.get("İzin Verilen Öğretmenler", []) for _, row in valid_rows.iterrows()}
            st.session_state.room_courses = {str(row["Derslik"]): row.get("İzin Verilen Dersler", []) for _, row in valid_rows.iterrows()}
            save_data()
            st.success("Derslik listesi güncellendi.")
            
        # --- Derslik Kısıtlamaları (Detaylı Seçim) ---
        st.divider()
        st.subheader("Derslik Kısıtlamaları (Detaylı Seçim)")
        st.info("Dersliklere ait branş, öğretmen ve ders kısıtlamalarını buradan menüden seçerek ayarlayabilirsiniz.")
        
        if st.session_state.rooms:
            selected_room = st.selectbox("Derslik Seçiniz", st.session_state.rooms, key="room_select_detail")
            
            # Mevcut değerleri al
            curr_branches = st.session_state.room_branches.get(selected_room, [])
            curr_teachers = st.session_state.room_teachers.get(selected_room, [])
            curr_courses = st.session_state.room_courses.get(selected_room, [])
            curr_excluded = st.session_state.room_excluded_courses.get(selected_room, [])
            
            # Seçenekler
            opt_branches = st.session_state.branches
            opt_teachers = [t['name'] for t in st.session_state.teachers]
            opt_courses = [c['name'] for c in st.session_state.courses]
            
            # Çoklu Seçim Kutuları
            new_branches = st.multiselect("İzin Verilen Branşlar", opt_branches, default=[b for b in curr_branches if b in opt_branches], key="ms_branches")
            new_teachers = st.multiselect("İzin Verilen Öğretmenler", opt_teachers, default=[t for t in curr_teachers if t in opt_teachers], key="ms_teachers")
            new_courses = st.multiselect("İzin Verilen Dersler", opt_courses, default=[c for c in curr_courses if c in opt_courses], key="ms_courses")
            new_excluded = st.multiselect("Yasaklı Dersler (Bu derslikte ASLA yapılmasın)", opt_courses, default=[c for c in curr_excluded if c in opt_courses], key="ms_excluded")
            
            if st.button("Kısıtlamaları Güncelle", key="btn_update_room_constraints"):
                st.session_state.room_branches[selected_room] = new_branches
                st.session_state.room_teachers[selected_room] = new_teachers
                st.session_state.room_courses[selected_room] = new_courses
                st.session_state.room_excluded_courses[selected_room] = new_excluded
                save_data()
                st.success(f"{selected_room} için kısıtlamalar güncellendi!")
                st.rerun()

    with tab3: # Öğretmenler
        st.info("Öğretmen bilgilerini tablodan düzenleyebilirsiniz.")
        # Veri yapısını garantiye al
        for t in st.session_state.teachers:
            if "unavailable_slots" not in t: t["unavailable_slots"] = []
            if "duty_day" not in t: t["duty_day"] = None
            if "preference" not in t: t["preference"] = "Farketmez"
            if "email" not in t: t["email"] = ""
            if "phone" not in t: t["phone"] = ""
            
        if not st.session_state.teachers:
            df_teachers = pd.DataFrame(columns=["name", "branch", "email", "phone", "unavailable_days", "unavailable_slots", "max_hours_per_day", "duty_day", "preference"])
        else:
            df_teachers = pd.DataFrame(st.session_state.teachers)
            
        edited_teachers = st.data_editor(
            df_teachers,
            column_config={
                "name": "Adı Soyadı",
                "branch": st.column_config.SelectboxColumn("Branş", options=st.session_state.branches, required=True),
                "email": st.column_config.TextColumn("E-Posta", help="Ders programının gönderileceği e-posta adresi"),
                "phone": st.column_config.TextColumn("Telefon", help="WhatsApp için 905xxxxxxxxx formatında"),
                "unavailable_days": st.column_config.ListColumn("İzin Günleri", help="Müsait olunmayan günleri ekleyin"),
                "unavailable_slots": st.column_config.ListColumn("Kısıtlı Saatler", help="Format: Gün:Saat (Örn: Pazartesi:1, Salı:5)"),
                "max_hours_per_day": st.column_config.NumberColumn("Günlük Max", min_value=1, max_value=8),
                "duty_day": st.column_config.SelectboxColumn("Nöbet Günü", options=["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Yok"], required=False),
                "preference": st.column_config.SelectboxColumn("Tercih", options=["Farketmez", "Sabahçı", "Öğlenci"], required=False, help="Derslerin günün hangi bölümüne yığılacağını belirler.")
            },
            num_rows="dynamic",
            width="stretch",
            key="editor_teachers"
        )
        if st.button("Öğretmenleri Kaydet", key="save_teachers"):
            # NaN değerleri temizle ve kaydet
            cleaned_df = edited_teachers.copy()
            if "name" in cleaned_df.columns:
                cleaned_df["name"] = cleaned_df["name"].astype(str).str.strip()
            if "email" in cleaned_df.columns:
                cleaned_df["email"] = cleaned_df["email"].astype(str).str.strip()
            if "phone" in cleaned_df.columns:
                cleaned_df["phone"] = cleaned_df["phone"].astype(str).str.strip()
            
            st.session_state.teachers = cleaned_df.where(pd.notnull(cleaned_df), None).to_dict("records")
            save_data()
            st.success("Öğretmen listesi güncellendi.")
            
        # --- Kısıtlama Yönetimi (Gün ve Saat) ---
        st.divider()
        st.subheader("Kısıtlama Yönetimi (Gün ve Saat)")
        st.info("Öğretmenlerin izinli olduğu günleri ve ders veremeyeceği saatleri buradan ayarlayabilirsiniz.")
        
        valid_teachers = [t for t in st.session_state.teachers if t and t.get('name')]
        if valid_teachers:
            t_names = [t['name'] for t in valid_teachers]
            sel_t_name = st.selectbox("Öğretmen Seçiniz", t_names, key="vis_t_select")
            
            # Seçilen öğretmeni bul
            sel_t = next((t for t in valid_teachers if t['name'] == sel_t_name), None)
            
            if sel_t:
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                current_slots = sel_t.get("unavailable_slots", []) or []
                current_days = sel_t.get("unavailable_days", []) or []
                
                # İzinli Günler Seçimi
                safe_current_days = [d for d in current_days if d in days]
                st.write(f"**{sel_t_name}** için izinli günleri seçiniz:")
                new_days = st.multiselect("İzinli Günler", days, default=safe_current_days, key="ms_days_vis")
                
                # Grid verisini hazırla (8 saatlik varsayılan)
                grid_data = []
                for h in range(1, 9):
                    row = {"Saat": f"{h}. Ders"}
                    for d in days:
                        key = f"{d}:{h}"
                        row[d] = key in current_slots
                    grid_data.append(row)
                
                df_grid = pd.DataFrame(grid_data)
                
                st.write(f"**{sel_t_name}** için ders veremeyeceği saatleri işaretleyin:")
                edited_grid = st.data_editor(
                    df_grid,
                    column_config={
                        "Saat": st.column_config.TextColumn("Saat", disabled=True),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="vis_grid_editor"
                )
                
                if st.button("Kısıtlamaları Güncelle", key="btn_update_vis"):
                    new_slots = []
                    for idx, row in edited_grid.iterrows():
                        h = idx + 1
                        for d in days:
                            if row[d]:
                                new_slots.append(f"{d}:{h}")
                    
                    # Session state güncelle
                    for t in st.session_state.teachers:
                        if t.get('name') == sel_t_name:
                            t['unavailable_slots'] = new_slots
                            t['unavailable_days'] = new_days
                            break
                    save_data()
                    st.success("Kısıtlamalar kaydedildi!")
                    st.rerun()

    with tab4: # Dersler
        st.info("Dersleri tablodan düzenleyebilirsiniz.")
        if not st.session_state.courses:
            df_courses = pd.DataFrame(columns=["name", "branch", "max_daily_hours", "specific_room", "block_size"])
        else:
            df_courses = pd.DataFrame(st.session_state.courses)
            if "block_size" not in df_courses.columns:
                df_courses["block_size"] = 1
            
        edited_courses = st.data_editor(
            df_courses,
            column_config={
                "name": "Ders Adı",
                "branch": st.column_config.SelectboxColumn("Branş", options=st.session_state.branches, required=True),
                "specific_room": st.column_config.SelectboxColumn("Zorunlu Derslik", options=st.session_state.rooms + [None]),
                "max_daily_hours": st.column_config.NumberColumn("Günlük Max", min_value=1, max_value=8),
                "block_size": st.column_config.NumberColumn("Blok Süresi", min_value=1, max_value=4, help="1: Serbest, 2: 2'li Blok...")
            },
            num_rows="dynamic",
            width="stretch",
            key="editor_courses"
        )
        if st.button("Dersleri Kaydet", key="save_courses"):
            st.session_state.courses = edited_courses.where(pd.notnull(edited_courses), None).to_dict("records")
            save_data()
            st.success("Ders listesi güncellendi.")

    with tab5: # Sınıflar
        st.info("Sınıfları ve sınıf öğretmenlerini aşağıdaki tablodan yönetebilirsiniz.")
        
        class_data = []
        for c in st.session_state.classes:
            class_data.append({
                "Sınıf": c,
                "Sınıf Öğretmeni": st.session_state.class_teachers.get(c)
            })
        
        df_classes = pd.DataFrame(class_data) if class_data else pd.DataFrame(columns=["Sınıf", "Sınıf Öğretmeni"])
        teacher_names = [t['name'] for t in st.session_state.teachers]

        edited_classes = st.data_editor(
            df_classes,
            column_config={
                "Sınıf": st.column_config.TextColumn("Sınıf Adı", required=True),
                "Sınıf Öğretmeni": st.column_config.SelectboxColumn("Sınıf Öğretmeni", options=teacher_names, required=False)
            },
            num_rows="dynamic",
            width="stretch",
            key="editor_classes"
        )
        if st.button("Sınıfları Kaydet", key="save_classes"):
            valid_rows = edited_classes.dropna(subset=["Sınıf"])
            st.session_state.classes = valid_rows["Sınıf"].astype(str).tolist()
            st.session_state.class_teachers = {
                row["Sınıf"]: row["Sınıf Öğretmeni"] 
                for _, row in valid_rows.iterrows() 
                if pd.notna(row["Sınıf Öğretmeni"]) and row["Sınıf Öğretmeni"]
            }
            save_data()
            st.success("Sınıf listesi ve öğretmenleri güncellendi.")

# --- 2. DERS ATAMA & KOPYALAMA ---
elif menu == "Ders Atama & Kopyalama":
    st.header("Sınıf Ders ve Öğretmen Atamaları")
    
    # Öğretmen ders yüklerini hesapla (Seçim ekranında göstermek için)
    teacher_loads = {t['name']: 0 for t in st.session_state.teachers}
    for c_name, courses in st.session_state.class_lessons.items():
        for crs_name, hours in courses.items():
            t_name = st.session_state.assignments.get(c_name, {}).get(crs_name)
            if t_name in teacher_loads:
                teacher_loads[t_name] += hours

    col1, col2 = st.columns([2, 1])

    with col1:
        selected_class = st.selectbox("İşlem Yapılacak Sınıf", st.session_state.classes)
        if selected_class not in st.session_state.class_lessons: st.session_state.class_lessons[selected_class] = {}
        if selected_class not in st.session_state.assignments: st.session_state.assignments[selected_class] = {}

        # Toplam ders saatini hesapla (Eş zamanlı dersleri dikkate alarak)
        current_lessons = st.session_state.class_lessons[selected_class]
        sim_groups = st.session_state.simultaneous_lessons.get(selected_class, [])
        
        processed_courses = set()
        calc_total_hours = 0
        
        # 1. Eş zamanlı grupları işle
        for group in sim_groups:
            valid_group = [c for c in group if c in current_lessons]
            if not valid_group: continue
            group_max = max([current_lessons.get(c, 0) for c in valid_group])
            calc_total_hours += group_max
            processed_courses.update(valid_group)
            
        # 2. Kalan dersleri işle
        calc_total_hours += sum([h for c, h in current_lessons.items() if c not in processed_courses])
        total_hours = calc_total_hours

        if total_hours > 40:
            st.markdown(f"### Toplam Ders Saati: :red[{total_hours} Saat] ⚠️")
        else:
            st.metric("Toplam Ders Saati", f"{total_hours} Saat")

        # Ders seçimini form dışına alıyoruz ki seçim değişince sayfa yenilensin ve öğretmen listesi güncellensin
        f_course = st.selectbox("Ders Seç", [c['name'] for c in st.session_state.courses])
        
        # Seçilen derse göre branşı ve öğretmenleri bul
        course_branch = next((c['branch'] for c in st.session_state.courses if c['name'] == f_course), None)
        filtered_teachers = [t['name'] for t in st.session_state.teachers if t['branch'] == course_branch]

        with st.form("add_lesson"):
            st.write(f"Seçilen Ders: **{f_course}** ({course_branch})")
            
            col_f1, col_f2 = st.columns(2)
            f_hours = col_f1.number_input("Haftalık Saat", 1, 10, 2)
            
            # Ders Bölme / Etiketleme Seçeneği
            is_split = col_f2.checkbox("Dersi Böl / Etiket Ekle", help="Aynı dersi farklı bir öğretmene daha atamak için işaretleyin.")
            split_label = ""
            if is_split:
                split_label = col_f2.text_input("Etiket (Örn: Grup A, Etüt)", placeholder="Grup A")
                st.caption("ℹ️ Aynı derse 2. öğretmeni atamak için buraya farklı bir etiket yazın (Örn: 'Grup B').")
            
            f_teacher = st.selectbox(
                "Öğretmen Seç", 
                filtered_teachers if filtered_teachers else ["Öğretmen Bulunamadı"],
                format_func=lambda x: f"{x} ({teacher_loads.get(x, 0)} Saat)" if x in teacher_loads else x
            )
            
            if st.form_submit_button("Ata"):
                final_course_name = f"{f_course} ({split_label})" if is_split and split_label else f_course
                st.session_state.class_lessons[selected_class][final_course_name] = f_hours
                if f_teacher != "Öğretmen Bulunamadı":
                    st.session_state.assignments[selected_class][final_course_name] = f_teacher
                
                # Otomatik Eşleştirme (Aynı dersin parçasıysa)
                if is_split and split_label:
                    potential_siblings = []
                    for existing_c in st.session_state.class_lessons[selected_class]:
                        if existing_c == final_course_name: continue
                        if existing_c == f_course or existing_c.startswith(f"{f_course} ("):
                            potential_siblings.append(existing_c)
                    
                    if potential_siblings:
                        if selected_class not in st.session_state.simultaneous_lessons:
                            st.session_state.simultaneous_lessons[selected_class] = []
                        
                        found_group = False
                        for group in st.session_state.simultaneous_lessons[selected_class]:
                            if any(s in group for s in potential_siblings):
                                if final_course_name not in group: group.append(final_course_name)
                                found_group = True; break
                        if not found_group:
                            st.session_state.simultaneous_lessons[selected_class].append([potential_siblings[0], final_course_name])
                            st.toast(f"Otomatik eşleştirildi: {potential_siblings[0]} ile", icon="🔗")

                save_data()
                st.rerun()

        # Mevcut Atamalar Tablosu (Düzenlenebilir)
        st.subheader("Mevcut Atamalar")
        current_lessons = st.session_state.class_lessons.get(selected_class, {})
        current_assignments = st.session_state.assignments.get(selected_class, {})
        
        data = []
        for c, h in current_lessons.items():
            t = current_assignments.get(c, None)
            data.append({"Ders": c, "Saat": h, "Öğretmen": t})
        
        df_assign = pd.DataFrame(data) if data else pd.DataFrame(columns=["Ders", "Saat", "Öğretmen"])
        
        # Tablo düzenleyicide "Ders" sütunu için seçenekleri hazırla
        # Hem ana dersleri hem de şu an atanmış (bölünmüş/etiketli) dersleri içermeli
        base_course_names = [c['name'] for c in st.session_state.courses]
        assigned_course_names = list(current_lessons.keys())
        all_course_options = sorted(list(set(base_course_names + assigned_course_names)))
        
        edited_assign = st.data_editor(
            df_assign,
            column_config={
                "Ders": st.column_config.SelectboxColumn("Ders", options=all_course_options, required=True),
                "Saat": st.column_config.NumberColumn("Saat", min_value=1, max_value=10, required=True),
                "Öğretmen": st.column_config.SelectboxColumn("Öğretmen", options=[t['name'] for t in st.session_state.teachers])
            },
            num_rows="dynamic",
            width="stretch",
            key=f"editor_assign_{selected_class}"
        )
        
        if st.button("Değişiklikleri Kaydet", key=f"save_assign_{selected_class}"):
            new_lessons = {}
            new_assignments = {}
            
            for _, row in edited_assign.iterrows():
                c_name = row["Ders"]
                h_val = row["Saat"]
                t_name = row["Öğretmen"]
                
                if pd.notna(c_name) and pd.notna(h_val):
                    new_lessons[c_name] = int(h_val)
                    if pd.notna(t_name) and t_name:
                        new_assignments[c_name] = t_name
            
            st.session_state.class_lessons[selected_class] = new_lessons
            st.session_state.assignments[selected_class] = new_assignments
            save_data()
            st.success("Atamalar güncellendi.")
            st.rerun()

        # --- Eş Zamanlı Dersler (Sınıf Bölme) ---
        st.divider()
        st.subheader("Eş Zamanlı Dersler (Sınıf Bölme)")
        st.info("Sınıfın ikiye bölündüğü (Örn: Resim - Müzik) dersleri buradan eşleştirebilirsiniz. Bu dersler programda aynı saate yerleştirilecektir.")
        
        # Init
        if selected_class not in st.session_state.simultaneous_lessons:
            st.session_state.simultaneous_lessons[selected_class] = []
            
        # O sınıfa atanmış dersleri listele (Bölünmüş dersleri de görebilmek için)
        class_assigned_courses = list(st.session_state.class_lessons.get(selected_class, {}).keys())
        
        # Form
        with st.form("add_simultaneous"):
            c1 = st.selectbox("Ders 1", class_assigned_courses, key="sim_c1")
            c2 = st.selectbox("Ders 2", class_assigned_courses, key="sim_c2")
            if st.form_submit_button("Eşleştir"):
                if c1 != c2:
                    # Check if already exists
                    exists = False
                    for pair in st.session_state.simultaneous_lessons[selected_class]:
                        if (c1 in pair and c2 in pair):
                            exists = True
                    if not exists:
                        st.session_state.simultaneous_lessons[selected_class].append([c1, c2])
                        save_data()
                        st.success(f"{c1} ve {c2} eşleştirildi.")
                        st.rerun()
                    else:
                        st.warning("Bu eşleştirme zaten var.")
                else:
                    st.warning("Aynı dersi eşleştiremezsiniz.")

        # List
        if st.session_state.simultaneous_lessons[selected_class]:
            st.write("Tanımlı Eşleştirmeler:")
            for i, pair in enumerate(st.session_state.simultaneous_lessons[selected_class]):
                col_s1, col_s2 = st.columns([4, 1])
                col_s1.write(f"🔗 {pair[0]} - {pair[1]}")
                if col_s2.button("Sil", key=f"del_sim_{i}"):
                    st.session_state.simultaneous_lessons[selected_class].pop(i)
                    save_data()
                    st.rerun()

        # Ders Programı Önizleme
        st.divider()
        st.subheader("Ders Programı Önizleme (Son Dağıtım)")
        if 'last_schedule' in st.session_state and st.session_state.last_schedule:
            df_preview = pd.DataFrame(st.session_state.last_schedule)
            class_preview = df_preview[df_preview["Sınıf"] == selected_class].copy()
            
            if not class_preview.empty:
                class_preview["Ders_Hoca"] = class_preview["Ders"] + " (" + class_preview["Öğretmen"] + ")"
                pivot = class_preview.pivot(index="Saat", columns="Gün", values="Ders_Hoca")
                days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                
                # Maksimum saati bul (Veriye göre veya varsayılan 8)
                max_h = int(df_preview["Saat"].max()) if "Saat" in df_preview.columns and not df_preview.empty else 8
                max_h = max(8, max_h)
                
                pivot = pivot.reindex(columns=days_order, index=range(1, max_h + 1))
                pivot = pivot.fillna("Boş")
                
                def color_cell(val):
                    if pd.isna(val) or val == "Boş": return ""
                    h = hashlib.md5(str(val).encode()).hexdigest()
                    r, g, b = int(h[:2], 16) % 50 + 200, int(h[2:4], 16) % 50 + 200, int(h[4:6], 16) % 50 + 200
                    return f'background-color: rgb({r},{g},{b}); color: black'

                st.dataframe(pivot.style.map(color_cell), width="stretch")
            else:
                st.info("Bu sınıf için oluşturulmuş programda ders bulunamadı.")
        else:
            st.info("Henüz program oluşturulmadı. 'Program Oluştur' menüsünden dağıtım yapınız.")

    with col2:
        st.subheader("Kopyala")
        src = st.selectbox("Kaynak", st.session_state.classes, key="src")
        tgt = st.selectbox("Hedef", st.session_state.classes, key="tgt")
        if st.button("Kopyala"):
            if src in st.session_state.class_lessons:
                st.session_state.class_lessons[tgt] = st.session_state.class_lessons[src].copy()
                st.session_state.assignments[tgt] = st.session_state.assignments[src].copy()
                save_data()
                st.success("Kopyalandı!")
                st.rerun()

    st.divider()
    st.subheader("Öğretmen Ders Yükü ve Atama Yönetimi")
    
    # 1. ÖZET TABLO (Geliştirilmiş)
    st.write("##### 📊 Ders Yükü Özeti")
    st.info("Bu tablodan öğretmen bilgilerini güncelleyebilir, öğretmeni silebilir veya 'Şubeler' sütunundan sınıf çıkararak atamaları kaldırabilirsiniz. Tabloyu filtrelemek için aşağıdaki alanları kullanın.")
    
    # --- Filtreler (Özet Tablo) ---
    all_branches = sorted(list(set([t.get('branch', '-') for t in st.session_state.teachers])))
    col_filter_sum1, col_filter_sum2 = st.columns(2)
    filter_branch = col_filter_sum1.multiselect("Branş Filtrele", all_branches, key="filter_branch_summary")
    filter_teacher_name = col_filter_sum2.text_input("Öğretmen Adı Ara", key="filter_teacher_name_summary")
    
    if teacher_loads:
        summary_data = []
        for t in st.session_state.teachers:
            t_name = t['name']
            total_hours = teacher_loads.get(t_name, 0)
            
            # Hangi sınıflara giriyor?
            assigned_classes = set()
            for c_key, courses in st.session_state.class_lessons.items():
                for crs_key, _ in courses.items():
                    if st.session_state.assignments.get(c_key, {}).get(crs_key) == t_name:
                        assigned_classes.add(c_key)
            
            max_daily = int(t.get('max_hours_per_day', 8))
            unavailable = t.get('unavailable_days') or []
            weekly_cap = (5 - len(unavailable)) * max_daily
            occupancy = total_hours / weekly_cap if weekly_cap > 0 else 0
            
            status = "✅"
            if total_hours > weekly_cap:
                status = "⚠️ Aşım"
            
            summary_data.append({
                "Öğretmen": t_name,
                "Branş": t.get('branch', '-'),
                "Günlük Max": max_daily,
                "Toplam Saat": total_hours,
                "Haftalık Kapasite": weekly_cap,
                "Doluluk": occupancy,
                "Durum": status,
                "Şubeler": sorted(list(assigned_classes))
            })
        
        df_summary = pd.DataFrame(summary_data).sort_values(by="Toplam Saat", ascending=False)
        
        # Filtreleri Uygula
        if filter_branch:
            df_summary = df_summary[df_summary["Branş"].isin(filter_branch)]
        if filter_teacher_name:
            df_summary = df_summary[df_summary["Öğretmen"].str.contains(filter_teacher_name, case=False, na=False)]

        edited_summary = st.data_editor(
            df_summary,
            column_config={
                "Öğretmen": st.column_config.TextColumn("Öğretmen", disabled=True),
                "Branş": st.column_config.SelectboxColumn("Branş", options=st.session_state.branches, required=True),
                "Günlük Max": st.column_config.NumberColumn("Günlük Max", min_value=1, max_value=12),
                "Toplam Saat": st.column_config.NumberColumn("Toplam Saat", disabled=True),
                "Haftalık Kapasite": st.column_config.NumberColumn("Kapasite", disabled=True),
                "Doluluk": st.column_config.ProgressColumn("Doluluk", format="%.0f%%", min_value=0, max_value=1),
                "Durum": st.column_config.TextColumn("Durum", disabled=True),
                "Şubeler": st.column_config.ListColumn("Şubeler")
            },
            num_rows="dynamic",
            width="stretch",
            key="editor_summary"
        )
        
        if st.button("Özet Tablo Değişikliklerini Kaydet", key="save_summary"):
            # Filtrelenmiş görünümdeki orijinal öğretmenler (Silinenleri tespit etmek için)
            original_teachers_in_view = set(df_summary["Öğretmen"])
            # Editördeki mevcut öğretmenler
            current_teachers_in_editor = set(edited_summary["Öğretmen"].dropna())
            
            new_teachers_list = []
            for t in st.session_state.teachers:
                # Eğer öğretmen bu görünümde hiç yoktuysa (filtrelenmişse), dokunma, listeye ekle
                if t['name'] not in original_teachers_in_view:
                    new_teachers_list.append(t)
                    continue
                
                # Eğer öğretmen görünümde vardı ve hala varsa (Güncelleme)
                if t['name'] in current_teachers_in_editor:
                    # Güncellenen verileri al
                    row = edited_summary[edited_summary["Öğretmen"] == t['name']].iloc[0]
                    t['branch'] = row["Branş"]
                    t['max_hours_per_day'] = int(row["Günlük Max"])
                    new_teachers_list.append(t)
                    
                    # Şube (Sınıf) Atamalarını Güncelle (Sadece silme işlemi)
                    kept_classes = set(row["Şubeler"]) if isinstance(row["Şubeler"], list) else set()
                    for c_key in list(st.session_state.assignments.keys()):
                        if c_key not in kept_classes:
                            # Bu sınıfta bu öğretmene ait dersleri bul ve sil
                            to_remove = []
                            if c_key in st.session_state.assignments:
                                for crs_key, assigned_t in st.session_state.assignments[c_key].items():
                                    if assigned_t == t['name']:
                                        to_remove.append(crs_key)
                            for crs_key in to_remove:
                                del st.session_state.assignments[c_key][crs_key]
                else:
                    # Öğretmen görünümde vardı ama artık yok (Silinmiş)
                    for c_key in st.session_state.assignments:
                        to_remove = []
                        for crs_key, assigned_t in st.session_state.assignments[c_key].items():
                            if assigned_t == t['name']:
                                to_remove.append(crs_key)
                        for crs_key in to_remove:
                            del st.session_state.assignments[c_key][crs_key]
            
            st.session_state.teachers = new_teachers_list
            save_data()
            st.success("Öğretmen listesi ve atamalar güncellendi.")
            st.rerun()

    # 2. DETAYLI DÜZENLEME TABLOSU
    st.write("##### 📝 Tüm Atamalar (Düzenle / Sil)")
    st.info("Aşağıdaki tablodan tüm atamaları inceleyebilir, düzenleyebilir veya silebilirsiniz. Filtreleri kullanarak listeyi daraltabilirsiniz.")
    
    # --- Filtreler (Tüm Atamalar) ---
    col_f1, col_f2, col_f3 = st.columns(3)
    f_class = col_f1.multiselect("Sınıf Filtrele", st.session_state.classes, key="filter_all_class")
    f_course = col_f2.multiselect("Ders Filtrele", sorted([c['name'] for c in st.session_state.courses]), key="filter_all_course")
    f_teacher = col_f3.multiselect("Öğretmen Filtrele", sorted([t['name'] for t in st.session_state.teachers]), key="filter_all_teacher")
    
    # Veriyi hazırla
    all_assignments = []
    for c_name, courses in st.session_state.class_lessons.items():
        for crs_name, hours in courses.items():
            t_name = st.session_state.assignments.get(c_name, {}).get(crs_name)
            all_assignments.append({
                "Sınıf": c_name,
                "Ders": crs_name,
                "Saat": hours,
                "Öğretmen": t_name
            })
    
    df_all = pd.DataFrame(all_assignments)
    
    # Filtreleri Uygula
    if f_class:
        df_all = df_all[df_all["Sınıf"].isin(f_class)]
    if f_course:
        df_all = df_all[df_all["Ders"].isin(f_course)]
    if f_teacher:
        df_all = df_all[df_all["Öğretmen"].isin(f_teacher)]
    
    edited_all = st.data_editor(
        df_all,
        column_config={
            "Sınıf": st.column_config.SelectboxColumn("Sınıf", options=st.session_state.classes, required=True),
            "Ders": st.column_config.SelectboxColumn("Ders", options=[c['name'] for c in st.session_state.courses], required=True),
            "Saat": st.column_config.NumberColumn("Saat", min_value=1, max_value=10, required=True),
            "Öğretmen": st.column_config.SelectboxColumn("Öğretmen", options=[t['name'] for t in st.session_state.teachers])
        },
        num_rows="dynamic",
        width="stretch",
        key="editor_all_assignments"
    )
    
    if st.button("Tüm Değişiklikleri Kaydet", key="save_all_assignments"):
        # 1. Filtrelenmiş görünümdeki orijinal kayıtları bul (Silinenleri tespit etmek için)
        # df_all, veritabanından gelen ve filtrelenmiş orijinal halidir.
        original_keys = set(zip(df_all["Sınıf"], df_all["Ders"]))
        
        # 2. Editördeki mevcut kayıtlar
        new_keys = set(zip(edited_all["Sınıf"], edited_all["Ders"]))
        
        # 3. Silinecekler (Orijinalde olup editörde olmayanlar)
        keys_to_delete = original_keys - new_keys
        
        # Silme İşlemi
        for c, crs in keys_to_delete:
            if c in st.session_state.class_lessons and crs in st.session_state.class_lessons[c]:
                del st.session_state.class_lessons[c][crs]
            if c in st.session_state.assignments and crs in st.session_state.assignments[c]:
                del st.session_state.assignments[c][crs]
        
        # 4. Güncelleme / Ekleme İşlemi
        for _, row in edited_all.iterrows():
            c = row["Sınıf"]
            crs = row["Ders"]
            h = row["Saat"]
            t = row["Öğretmen"]
            
            if pd.notna(c) and pd.notna(crs) and pd.notna(h):
                if c not in st.session_state.class_lessons: st.session_state.class_lessons[c] = {}
                if c not in st.session_state.assignments: st.session_state.assignments[c] = {}
                
                st.session_state.class_lessons[c][crs] = int(h)
                if pd.notna(t) and t:
                    st.session_state.assignments[c][crs] = t
                elif crs in st.session_state.assignments[c]:
                    # Öğretmen silinmişse atamayı kaldır
                    del st.session_state.assignments[c][crs]
        
        save_data()
        st.success("Tüm atamalar güncellendi!")
        st.rerun()

# --- 3. PROGRAM OLUŞTUR ---
elif menu == "Program Oluştur":
    st.header("Otomatik Dağıtım")
    
    with st.expander("Ders Saatleri Yapılandırması", expanded=False):
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        lc = st.session_state.lesson_config
        new_start = col_t1.text_input("Başlangıç Saati", value=lc.get("start_time", "08:30"), help="Örn: 08:30")
        new_ldur = col_t2.number_input("Ders Süresi (dk)", value=lc.get("lesson_duration", 40), min_value=10, max_value=120)
        new_bdur = col_t3.number_input("Teneffüs (dk)", value=lc.get("break_duration", 10), min_value=0, max_value=60)
        new_lunch_dur = col_t4.number_input("Öğle Arası (dk)", value=lc.get("lunch_duration", 50), min_value=0, max_value=120)
        
        col_t5, col_t6 = st.columns(2)
        new_num_hours = col_t5.number_input("Günlük Ders Saati Sayısı", min_value=5, max_value=12, value=lc.get("num_hours", 8))
        
        lunch_opts = ["Yok"] + [str(i) for i in range(1, new_num_hours + 1)]
        curr_lunch = str(lc.get("lunch_break_hour", "Yok"))
        if curr_lunch not in lunch_opts: curr_lunch = "Yok"
        new_lunch_hour = col_t6.selectbox("Öğle Arası (Hangi Ders Boş?)", lunch_opts, index=lunch_opts.index(curr_lunch))
        
        st.session_state.lesson_config = {
            "start_time": new_start,
            "lesson_duration": new_ldur,
            "break_duration": new_bdur,
            "lunch_duration": new_lunch_dur,
            "num_hours": new_num_hours,
            "lunch_break_hour": new_lunch_hour
        }
    
    with st.expander("Rapor Ayarları (İmza ve Metinler)", expanded=False):
        rc = st.session_state.report_config
        new_title = st.text_input("Rapor Başlığı (Okul Adı)", value=rc.get("report_title", ""), help="Raporun en üstünde görünecek başlık (Örn: X Lisesi).")
        new_principal = st.text_input("Okul Müdürü Adı", value=rc.get("principal_name", ""), help="İmza bölümünde görünecek isim.")
        new_notification = st.text_area("Alt Bilgi Metni", value=rc.get("notification_text", "Bu Haftalık Ders Programı belirtilen tarihte tebliğ edildi."), help="Tablonun altında görünecek bilgilendirme yazısı.")
        
        st.session_state.report_config = {
            "principal_name": new_principal,
            "notification_text": new_notification,
            "report_title": new_title
        }
    
    with st.expander("E-Posta Ayarları (SMTP)", expanded=False):
        st.info("Öğretmenlere ders programlarını e-posta ile göndermek için SMTP ayarlarını yapılandırın. (Gmail için 'Uygulama Şifresi' kullanmanız gerekebilir.)")
        ec = st.session_state.email_config
        smtp_server = st.text_input("SMTP Sunucusu", value=ec.get("smtp_server", "smtp.gmail.com"))
        smtp_port = st.number_input("SMTP Portu", value=ec.get("smtp_port", 465))
        sender_email = st.text_input("Gönderen E-Posta", value=ec.get("sender_email", ""))
        sender_password = st.text_input("Şifre / Uygulama Şifresi", value=ec.get("sender_password", ""), type="password", help="Gmail kullanıyorsanız normal şifreniz çalışmayabilir. 'Uygulama Şifresi' oluşturup onu girmelisiniz.")
        
        st.divider()
        email_subject = st.text_input("E-Posta Konusu", value=ec.get("email_subject", "Haftalık Ders Programı"), help="Konu başlığında {name} kullanarak öğretmen adını ekleyebilirsiniz.")
        email_body = st.text_area("E-Posta İçeriği", value=ec.get("email_body", "Sayın {name},\n\nYeni haftalık ders programınız ektedir.\n\nİyi çalışmalar dileriz."), help="{name} yazan yere öğretmen adı otomatik gelecektir.")
        
        st.session_state.email_config = {
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "sender_email": sender_email,
            "sender_password": sender_password,
            "email_subject": email_subject,
            "email_body": email_body
        }
    
    mode = st.radio("Mod:", ["Sınıf Bazlı", "Derslik Bazlı"])
    solver_mode = "room" if "Derslik" in mode else "class"
    
    # Değerleri config'den al
    num_hours = st.session_state.lesson_config.get("num_hours", 8)
    lunch_val = st.session_state.lesson_config.get("lunch_break_hour", "Yok")
    lunch_break_hour = int(lunch_val) if lunch_val != "Yok" else None

    if st.button("Programı Dağıt"):
        with st.spinner("Hesaplanıyor..."):
            schedule, msg = create_timetable(
                st.session_state.teachers, st.session_state.courses, st.session_state.classes,
                st.session_state.class_lessons, st.session_state.assignments, st.session_state.rooms, 
                room_capacities=st.session_state.room_capacities,
                room_branches=st.session_state.room_branches,
                room_teachers=st.session_state.room_teachers,
                room_courses=st.session_state.room_courses,
                room_excluded_courses=st.session_state.room_excluded_courses,
                mode=solver_mode, lunch_break_hour=lunch_break_hour, num_hours=num_hours,
                simultaneous_lessons=st.session_state.simultaneous_lessons
            )
        if schedule:
            st.session_state.last_schedule = schedule
            st.success(msg)
            
            # Eksik Ders Kontrolü (Yerleştirilemeyenler)
            scheduled_lessons = set()
            for item in schedule:
                scheduled_lessons.add((item['Sınıf'], item['Ders']))
            
            missing_lessons = []
            for c_name, courses in st.session_state.class_lessons.items():
                for crs_name, hours in courses.items():
                    if hours > 0 and st.session_state.assignments.get(c_name, {}).get(crs_name):
                        if (c_name, crs_name) not in scheduled_lessons:
                            missing_lessons.append(f"{c_name} - {crs_name}")
            
            if missing_lessons:
                st.warning(f"⚠️ Dikkat: Şu dersler programa yerleştirilemedi (Oda veya saat kısıtlaması nedeniyle): {', '.join(missing_lessons)}")
        else:
            st.error(msg)

    # Programı göster (Buton bloğunun dışında, session_state'den)
    if 'last_schedule' in st.session_state and st.session_state.last_schedule:
        schedule = st.session_state.last_schedule
        df = pd.DataFrame(schedule)
        
        # Çakışma Kontrolü
        conflicts = check_conflicts(schedule, check_rooms=(solver_mode == "room"))
        if conflicts:
            st.error("Dikkat! Programda çakışmalar tespit edildi:")
            for c in conflicts:
                st.write(c)
        else:
            st.info("✅ Programda herhangi bir çakışma (Öğretmen, Sınıf veya Derslik) tespit edilmedi.")
        
        # Tabloda göstermek için: Ders Adı (Öğretmen)
        df["Ders_Hoca"] = df["Ders"] + " (" + df["Öğretmen"] + ")"
        df["Sinif_Ders"] = df["Sınıf"] + " (" + df["Ders"] + ")"
        
        view = st.selectbox("Görünüm", ["Tüm Liste", "Sınıfa Göre", "Öğretmene Göre", "Dersliğe Göre"])
        if view == "Sınıfa Göre":
            c = st.selectbox("Sınıf", st.session_state.classes)
            
            # Pivot tablo oluştur
            pivot = df[df["Sınıf"] == c].pivot(index="Saat", columns="Gün", values="Ders_Hoca")
            # Günleri ve saatleri sıralı hale getir (Eksik dersleri boş göster)
            days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
            pivot = pivot.reindex(columns=days_order, index=range(1, num_hours + 1))
            pivot = pivot.fillna("Boş")

            def color_cell(val):
                if pd.isna(val) or val == "Boş": return ""
                # Ders adına göre benzersiz pastel renk üret
                h = hashlib.md5(str(val).encode()).hexdigest()
                r, g, b = int(h[:2], 16) % 50 + 200, int(h[2:4], 16) % 50 + 200, int(h[4:6], 16) % 50 + 200
                return f'background-color: rgb({r},{g},{b}); color: black'

            st.dataframe(pivot.style.map(color_cell), width="stretch")
            
            # Ekran altına özet tablo ekle
            st.write("###### Ders Dağılımı Özeti")
            class_df = df[df["Sınıf"] == c]
            if not class_df.empty:
                summary = class_df.groupby(['Ders', 'Öğretmen']).size().reset_index(name='Saat')
                st.dataframe(summary, hide_index=True, use_container_width=True)
                st.info(f"Toplam Ders Saati: **{summary['Saat'].sum()}**")
                
        elif view == "Öğretmene Göre":
            t = st.selectbox("Öğretmen", [x['name'] for x in st.session_state.teachers])
            pivot = df[df["Öğretmen"] == t].pivot(index="Saat", columns="Gün", values="Sinif_Ders")
            days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
            pivot = pivot.reindex(columns=days_order, index=range(1, num_hours + 1))
            pivot = pivot.fillna("Boş")
            
            def color_cell(val):
                if pd.isna(val) or val == "Boş": return ""
                h = hashlib.md5(str(val).encode()).hexdigest()
                r, g, b = int(h[:2], 16) % 50 + 200, int(h[2:4], 16) % 50 + 200, int(h[4:6], 16) % 50 + 200
                return f'background-color: rgb({r},{g},{b}); color: black'

            st.dataframe(pivot.style.map(color_cell), width="stretch")
        elif view == "Dersliğe Göre":
            if not st.session_state.rooms:
                st.warning("Derslik tanımlanmamış.")
            else:
                r = st.selectbox("Derslik", st.session_state.rooms)
                
                # Seçilen derslik verisi
                room_df = df[df["Derslik"] == r].copy()
                st.info(f"📍 **{r}** dersliğinde toplam **{len(room_df)}** saat ders var.")
                
                # Hücre içeriği: Sınıf - Ders (Öğretmen)
                room_df["Derslik_Hucre"] = room_df["Sınıf"] + " - " + room_df["Ders"] + " (" + room_df["Öğretmen"] + ")"
                
                pivot = room_df.pivot(index="Saat", columns="Gün", values="Derslik_Hucre")
                days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                pivot = pivot.reindex(columns=days_order, index=range(1, num_hours + 1))
                pivot = pivot.fillna("Boş")
                
                def color_cell(val):
                    if pd.isna(val) or val == "Boş": return ""
                    h = hashlib.md5(str(val).encode()).hexdigest()
                    r, g, b = int(h[:2], 16) % 50 + 200, int(h[2:4], 16) % 50 + 200, int(h[4:6], 16) % 50 + 200
                    return f'background-color: rgb({r},{g},{b}); color: black'

                st.dataframe(pivot.style.map(color_cell), width="stretch")
                
                # Ekran altına özet tablo ekle
                st.write("###### Ders Dağılımı Özeti")
                if not room_df.empty:
                    summary = room_df.groupby(['Sınıf', 'Ders', 'Öğretmen']).size().reset_index(name='Saat')
                    st.dataframe(summary, hide_index=True, use_container_width=True)
        else:
            st.dataframe(df)
        
        # PDF İndirme Butonu
        if FPDF:
            st.divider()
            col_pdf1, col_pdf2, col_pdf3 = st.columns(3)
            with col_pdf1:
                pdf_data_teacher = create_pdf_report(schedule, "teacher", num_hours)
                st.download_button("📄 Öğretmen Programlarını PDF İndir", data=pdf_data_teacher, file_name="ogretmen_programi.pdf", mime="application/pdf")
            with col_pdf2:
                pdf_data_class = create_pdf_report(schedule, "class", num_hours)
                st.download_button("📄 Sınıf Programlarını PDF İndir", data=pdf_data_class, file_name="sinif_programi.pdf", mime="application/pdf")
            with col_pdf3:
                pdf_data_room = create_pdf_report(schedule, "room", num_hours)
                st.download_button("📄 Derslik Programlarını PDF İndir", data=pdf_data_room, file_name="derslik_programi.pdf", mime="application/pdf")
        else:
            st.warning("PDF çıktısı alabilmek için 'fpdf' kütüphanesini yükleyin: pip install fpdf")
            
        # Çarşaf Liste (Excel)
        st.divider()
        st.subheader("📊 Çarşaf Liste (Excel)")
        st.info("Öğretmenlerin veya Sınıfların tüm programını tek bir tabloda (Çarşaf Liste) görmek için aşağıdaki butonları kullanın.")
        
        col_cl1, col_cl2 = st.columns(2)
        
        with col_cl1:
            if st.button("Öğretmen Çarşaf Listesini İndir (.xlsx)"):
                # Veriyi hazırla
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                
                # Başlıklar
                headers = ["Öğretmen"]
                for d in days:
                    for h in range(1, num_hours + 1):
                        headers.append(f"{d} {h}.Ders")
                
                rows = []
                # Tüm öğretmenleri al (sıralı)
                all_teachers = sorted([t['name'] for t in st.session_state.teachers])
                
                # Hızlı erişim için sözlük oluştur
                schedule_map = {} 
                for item in schedule:
                    key = (item['Öğretmen'], item['Gün'], item['Saat'])
                    val = f"{item['Sınıf']} - {item['Ders']}"
                    schedule_map[key] = val
                    
                for t_name in all_teachers:
                    row = [t_name]
                    for d in days:
                        for h in range(1, num_hours + 1):
                            val = schedule_map.get((t_name, d, h), "-")
                            row.append(val)
                    rows.append(row)
                    
                df_master = pd.DataFrame(rows, columns=headers)
                
                # Excel'e aktar
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_master.to_excel(writer, index=False, sheet_name='CarsafListe')
                    
                st.download_button(
                    label="📥 Öğretmen Çarşaf Listeyi İndir",
                    data=output.getvalue(),
                    file_name="ogretmen_carsaf_liste.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with col_cl2:
            if st.button("Sınıf Çarşaf Listesini İndir (.xlsx)"):
                # Veriyi hazırla
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                
                # Başlıklar
                headers = ["Sınıf"]
                for d in days:
                    for h in range(1, num_hours + 1):
                        headers.append(f"{d} {h}.Ders")
                
                rows = []
                # Tüm sınıfları al (sıralı)
                all_classes = sorted(st.session_state.classes)
                
                # Hızlı erişim için sözlük oluştur
                schedule_map = {} 
                for item in schedule:
                    key = (item['Sınıf'], item['Gün'], item['Saat'])
                    val = f"{item['Ders']} ({item['Öğretmen']})"
                    schedule_map[key] = val
                    
                for c_name in all_classes:
                    row = [c_name]
                    for d in days:
                        for h in range(1, num_hours + 1):
                            val = schedule_map.get((c_name, d, h), "-")
                            row.append(val)
                    rows.append(row)
                    
                df_master_class = pd.DataFrame(rows, columns=headers)
                
                # Excel'e aktar
                output_class = io.BytesIO()
                with pd.ExcelWriter(output_class, engine='openpyxl') as writer:
                    df_master_class.to_excel(writer, index=False, sheet_name='SinifCarsafListe')
                    
                st.download_button(
                    label="📥 Sınıf Çarşaf Listeyi İndir",
                    data=output_class.getvalue(),
                    file_name="sinif_carsaf_liste.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
        # E-Posta Gönderim Butonu
        st.divider()
        st.subheader("📧 Programları E-Posta ile Gönder")
        if st.button("Öğretmenlere Programlarını Gönder"):
            ec = st.session_state.email_config
            if not ec.get("sender_email") or not ec.get("sender_password"):
                st.error("Lütfen önce 'E-Posta Ayarları' bölümünden gönderici bilgilerini giriniz.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # E-postası olan öğretmenleri bul
                teachers_with_email = [t for t in st.session_state.teachers if t.get("email") and "@" in t.get("email")]
                total_emails = len(teachers_with_email)
                
                if total_emails == 0:
                    st.warning("E-posta adresi tanımlı öğretmen bulunamadı.")
                else:
                    sent_count = 0
                    try:
                        context = ssl.create_default_context()
                        
                        # Port 465 ise SSL, diğerleri (587 vb) için STARTTLS kullan
                        if int(ec["smtp_port"]) == 465:
                            server = smtplib.SMTP_SSL(ec["smtp_server"], ec["smtp_port"], context=context)
                        else:
                            server = smtplib.SMTP(ec["smtp_server"], ec["smtp_port"])
                            server.starttls(context=context)
                        
                        try:
                            server.login(ec["sender_email"], ec["sender_password"])
                            failed_emails = []
                            
                            for i, t in enumerate(teachers_with_email):
                                t_name = t["name"]
                                t_email = t["email"]
                                status_text.text(f"Gönderiliyor: {t_name} ({t_email})...")
                                
                                try:
                                    # Öğretmene özel PDF oluştur
                                    t_schedule = [row for row in schedule if row["Öğretmen"] == t_name]
                                    if not t_schedule: 
                                        progress_bar.progress((i + 1) / total_emails)
                                        continue # Dersi yoksa gönderme
                                    
                                    pdf_bytes = create_pdf_report(t_schedule, "teacher", num_hours)
                                    
                                    # E-posta hazırla
                                    msg = MIMEMultipart()
                                    msg['From'] = ec["sender_email"]
                                    msg['To'] = t_email
                                    
                                    subject_tmpl = ec.get("email_subject", "Haftalık Ders Programı")
                                    body_tmpl = ec.get("email_body", "Sayın {name},\n\nYeni haftalık ders programınız ektedir.\n\nİyi çalışmalar dileriz.")
                                    
                                    msg['Subject'] = subject_tmpl.replace("{name}", t_name)
                                    msg.attach(MIMEText(body_tmpl.replace("{name}", t_name), 'plain'))
                                    
                                    part = MIMEApplication(pdf_bytes, Name=f"Ders_Programi_{t_name}.pdf")
                                    part['Content-Disposition'] = f'attachment; filename="Ders_Programi_{t_name}.pdf"'
                                    msg.attach(part)
                                    
                                    server.send_message(msg)
                                    sent_count += 1
                                except Exception as e:
                                    failed_emails.append(f"{t_name} ({t_email}): {str(e)}")
                                    
                                progress_bar.progress((i + 1) / total_emails)
                                time.sleep(1.5) # Spam koruması için bekleme
                        finally:
                            server.quit()
                                
                        if sent_count > 0:
                            st.success(f"İşlem tamamlandı! Toplam {sent_count} öğretmene e-posta gönderildi.")
                        
                        if failed_emails:
                            st.error(f"Toplam {len(failed_emails)} gönderim başarısız oldu:")
                            for fail_msg in failed_emails:
                                st.write(f"❌ {fail_msg}")
                                
                    except smtplib.SMTPAuthenticationError as e:
                        st.error("❌ Kimlik Doğrulama Hatası!")
                        if "Application-specific password required" in str(e) or "534" in str(e):
                            st.warning("Google hesabınızda 2 Adımlı Doğrulama açık olduğu için normal şifrenizle giriş yapılamadı.")
                            st.info("👉 Çözüm: Google Hesabınızdan **Uygulama Şifresi (App Password)** oluşturup, şifre alanına onu girmelisiniz.")
                        else:
                            st.error(f"Hata Detayı: {e}")
                    except Exception as e:
                        st.error(f"Genel bağlantı hatası: {e}")

        st.divider()
        st.subheader("📱 WhatsApp ile Program Paylaşımı")
        st.info("Öğretmenlerin telefon numaralarına WhatsApp üzerinden ders programını metin olarak göndermek için aşağıdaki listeyi kullanabilirsiniz. 'WhatsApp'ı Aç' butonuna tıkladığınızda program metni otomatik olarak oluşturulur.")
        
        if 'last_schedule' in st.session_state and st.session_state.last_schedule:
            wa_schedule = st.session_state.last_schedule
            wa_data = []
            
            # Gün sıralaması için
            days_order_map = {"Pazartesi": 1, "Salı": 2, "Çarşamba": 3, "Perşembe": 4, "Cuma": 5}
            
            for t in st.session_state.teachers:
                t_name = t['name']
                phone = t.get('phone', '')
                
                # Telefon temizleme (Sadece rakamlar)
                clean_phone = ''.join(filter(str.isdigit, str(phone)))
                if not clean_phone: continue
                
                # Programı metne dök
                t_sched = [row for row in wa_schedule if row["Öğretmen"] == t_name]
                if not t_sched: continue
                
                # Sıralama
                t_sched.sort(key=lambda x: (days_order_map.get(x["Gün"], 6), x["Saat"]))
                
                msg_lines = [f"Sayın {t_name}, Haftalık Ders Programınız:"]
                curr_day = ""
                for row in t_sched:
                    if row["Gün"] != curr_day:
                        curr_day = row["Gün"]
                        msg_lines.append(f"\n*{curr_day}*")
                    msg_lines.append(f"{row['Saat']}. Ders: {row['Sınıf']} - {row['Ders']}")
                
                full_msg = "\n".join(msg_lines)
                encoded_msg = urllib.parse.quote(full_msg)
                link = f"https://wa.me/{clean_phone}?text={encoded_msg}"
                
                wa_data.append({"Öğretmen": t_name, "Telefon": phone, "Link": link})
            
            if wa_data:
                st.dataframe(pd.DataFrame(wa_data), column_config={"Link": st.column_config.LinkColumn("Gönder", display_text="WhatsApp'ı Aç")}, hide_index=True)
            else:
                st.warning("Telefon numarası kayıtlı veya dersi olan öğretmen bulunamadı.")

        st.divider()
        st.subheader("Öğretmen Boş Gün Çizelgesi")
        all_days_set = {"Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"}
        day_order = {"Pazartesi": 1, "Salı": 2, "Çarşamba": 3, "Perşembe": 4, "Cuma": 5}
        
        free_days_list = []
        for t in st.session_state.teachers:
            t_name = t['name']
            worked_days = set(df[df["Öğretmen"] == t_name]["Gün"].unique())
            free_days = sorted(list(all_days_set - worked_days), key=lambda x: day_order[x])
            free_days_list.append({
                "Öğretmen": t_name,
                "Boş Günler": ", ".join(free_days) if free_days else "-"
            })
        
        st.dataframe(pd.DataFrame(free_days_list), width="stretch")

        st.divider()
        st.subheader("Sınıf Günlük Ders Yoğunluğu")
        # Sınıf ve Gün bazında ders sayısını hesapla
        density_df = df.groupby(["Sınıf", "Gün"]).size().reset_index(name="Ders Sayısı")
        density_pivot = density_df.pivot(index="Sınıf", columns="Gün", values="Ders Sayısı")
        days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
        density_pivot = density_pivot.reindex(columns=days_order).fillna(0).astype(int)
        st.dataframe(density_pivot, width="stretch")

        st.divider()
        st.subheader("Öğretmen Toplam Ders Saati Grafiği")
        
        # Veriyi hazırla
        chart_data = df["Öğretmen"].value_counts().reset_index()
        chart_data.columns = ["Öğretmen", "Ders Saati"]
        
        # Altair ile detaylı grafik oluştur
        chart = alt.Chart(chart_data).mark_bar(color="#4CAF50").encode(
            x=alt.X('Ders Saati', title='Toplam Ders Saati'),
            y=alt.Y('Öğretmen', sort='-x', title='Öğretmen'),
            tooltip=['Öğretmen', 'Ders Saati']
        ).properties(
            title="Öğretmen Ders Yükü Dağılımı"
        ).configure_axis(
            labelFontSize=12,
            titleFontSize=14,
            titleFontWeight='bold'
        ).configure_title(
            fontSize=20,
            color='blue'
        )
        st.altair_chart(chart, use_container_width=True)

        st.divider()
        st.subheader("Derslik Doluluk Oranları")
        
        if "Derslik" in df.columns:
            # Sadece tanımlı derslikleri dikkate al
            valid_rooms = df[df["Derslik"].isin(st.session_state.rooms)]
            
            if not valid_rooms.empty:
                room_counts = valid_rooms["Derslik"].value_counts().reset_index()
                room_counts.columns = ["Derslik", "Ders Sayısı"]
                
                # Kapasite ve oran hesabı (Haftalık 40 saat üzerinden)
                TOTAL_SLOTS = 40 
                
                def get_occupancy(row):
                    r_name = row["Derslik"]
                    cap = int(st.session_state.room_capacities.get(r_name, 1))
                    max_lessons = cap * TOTAL_SLOTS
                    return (row["Ders Sayısı"] / max_lessons) * 100
                
                room_counts["Doluluk (%)"] = room_counts.apply(get_occupancy, axis=1)
                
                room_chart = alt.Chart(room_counts).mark_bar(color="#FF9800").encode(
                    x=alt.X('Doluluk (%)', title='Doluluk Oranı (%)', scale=alt.Scale(domain=[0, 100])),
                    y=alt.Y('Derslik', sort='-x', title='Derslik'),
                    tooltip=['Derslik', 'Ders Sayısı', alt.Tooltip('Doluluk (%)', format='.1f')]
                ).properties(
                    title="Derslik Kapasite Kullanım Oranları"
                ).configure_axis(
                    labelFontSize=12,
                    titleFontSize=14,
                    titleFontWeight='bold'
                ).configure_title(
                    fontSize=20,
                    color='blue'
                )
                st.altair_chart(room_chart, use_container_width=True)
            else:
                st.info("Programda tanımlı derslik kullanımı bulunamadı.")

# --- 4. HIZLI DÜZENLE ---
elif menu == "Hızlı Düzenle":
    st.header("Hızlı Düzenleme")
    if st.session_state.teachers:
        st.write("Öğretmenler")
        new_df = st.data_editor(
            pd.DataFrame(st.session_state.teachers),
            column_config={
                "unavailable_days": st.column_config.ListColumn(
                    "İzin Günleri",
                    help="Öğretmenin ders veremeyeceği günler",
                    width="medium",
                ),
                "unavailable_slots": st.column_config.ListColumn(
                    "Kısıtlı Saatler",
                    help="Format: Gün:Saat (Örn: Pazartesi:1)",
                    width="medium",
                ),
                "max_hours_per_day": st.column_config.NumberColumn(
                    "Günlük Max",
                    min_value=1,
                    max_value=8,
                    width="small"
                ),
                "duty_day": st.column_config.SelectboxColumn(
                    "Nöbet Günü",
                    options=["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Yok"],
                    width="medium"
                ),
                "preference": st.column_config.SelectboxColumn(
                    "Tercih",
                    options=["Farketmez", "Sabahçı", "Öğlenci"],
                    width="medium"
                ),
            },
            num_rows="dynamic"
        )
        if st.button("Öğretmenleri Kaydet"):
            st.session_state.teachers = new_df.where(pd.notnull(new_df), None).to_dict('records')
            save_data()

    if st.session_state.courses:
        st.divider()
        st.write("Dersler")
        
        df_courses_edit = pd.DataFrame(st.session_state.courses)
        if "block_size" not in df_courses_edit.columns:
            df_courses_edit["block_size"] = 1
            
        new_courses_df = st.data_editor(
            df_courses_edit,
            column_config={
                "max_daily_hours": st.column_config.NumberColumn(
                    "Günlük Max",
                    min_value=1,
                    max_value=8
                ),
                "block_size": st.column_config.NumberColumn("Blok Süresi", min_value=1, max_value=4, help="1: Serbest, 2: 2'li Blok..."),
                "specific_room": st.column_config.SelectboxColumn(
                    "Zorunlu Derslik",
                    options=st.session_state.rooms + [None],
                    width="medium"
                ),
            },
            num_rows="dynamic"
        )
        if st.button("Dersleri Kaydet"):
            st.session_state.courses = new_courses_df.where(pd.notnull(new_courses_df), None).to_dict('records')
            save_data()

# --- 5. VERİ İŞLEMLERİ ---
elif menu == "Veri İşlemleri":
    st.header("Veri İçe/Dışa Aktarma")
    
    st.info("Verilerinizi Excel formatında indirip düzenleyebilir veya toplu veri yükleyebilirsiniz.")
    
    col_ex1, col_ex2 = st.columns(2)
    
    with col_ex1:
        st.subheader("Mevcut Verileri İndir")
        if st.button("Excel Olarak İndir (.xlsx)"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Teachers
                t_data = []
                for t in st.session_state.teachers:
                    t_data.append({
                        "Adı Soyadı": t.get('name'),
                        "Branş": t.get('branch'),
                        "Nöbet Günü": t.get('duty_day'),
                        "Tercih": t.get('preference'),
                        "Günlük Max Ders": t.get('max_hours_per_day'),
                        "E-Posta": t.get('email'),
                        "Telefon": t.get('phone')
                    })
                pd.DataFrame(t_data).to_excel(writer, sheet_name='Ogretmenler', index=False)
                
                # Courses
                c_data = []
                for c in st.session_state.courses:
                    c_data.append({
                        "Ders Adı": c.get('name'),
                        "Branş": c.get('branch'),
                        "Günlük Max Saat": c.get('max_daily_hours'),
                        "Blok Süresi": c.get('block_size'),
                        "Zorunlu Derslik": c.get('specific_room')
                    })
                pd.DataFrame(c_data).to_excel(writer, sheet_name='Dersler', index=False)
                
                # Classes
                cl_data = []
                for c in st.session_state.classes:
                    cl_data.append({
                        "Sınıf Adı": c,
                        "Sınıf Öğretmeni": st.session_state.class_teachers.get(c)
                    })
                pd.DataFrame(cl_data).to_excel(writer, sheet_name='Siniflar', index=False)
                
                # Rooms
                r_data = []
                for r in st.session_state.rooms:
                    r_data.append({
                        "Derslik Adı": r,
                        "Kapasite": st.session_state.room_capacities.get(r, 1)
                    })
                pd.DataFrame(r_data).to_excel(writer, sheet_name='Derslikler', index=False)
                
                # Program
                p_data = []
                for c_name, courses in st.session_state.class_lessons.items():
                    for crs_name, hours in courses.items():
                        t_name = st.session_state.assignments.get(c_name, {}).get(crs_name)
                        p_data.append({
                            "Sınıf": c_name,
                            "Ders": crs_name,
                            "Haftalık Saat": hours,
                            "Öğretmen": t_name
                        })
                pd.DataFrame(p_data).to_excel(writer, sheet_name='DersProgrami', index=False)
                
            st.download_button(label="📥 İndir", data=output.getvalue(), file_name="okul_verileri.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with col_ex2:
        st.subheader("Excel'den Veri Yükle")
        uploaded_file = st.file_uploader("Excel Dosyası Seç", type=["xlsx"])
        if uploaded_file:
            if st.button("Verileri İçeri Aktar (Üzerine Yazar)"):
                try:
                    xls = pd.ExcelFile(uploaded_file)
                    
                    # 1. Öğretmenler
                    if 'Ogretmenler' in xls.sheet_names:
                        df_t = pd.read_excel(xls, 'Ogretmenler')
                        new_teachers = []
                        for _, row in df_t.iterrows():
                            if pd.isna(row.get("Adı Soyadı")): continue
                            t_obj = {
                                "name": str(row["Adı Soyadı"]).strip(),
                                "branch": str(row["Branş"]).strip() if pd.notna(row["Branş"]) else "Genel",
                                "unavailable_days": [],
                                "unavailable_slots": [],
                                "max_hours_per_day": int(row["Günlük Max Ders"]) if pd.notna(row.get("Günlük Max Ders")) else 8,
                                "duty_day": str(row["Nöbet Günü"]) if pd.notna(row.get("Nöbet Günü")) else None,
                                "preference": str(row["Tercih"]) if pd.notna(row.get("Tercih")) else "Farketmez",
                                "email": str(row["E-Posta"]).strip() if pd.notna(row.get("E-Posta")) else "",
                                "phone": str(row["Telefon"]).strip() if pd.notna(row.get("Telefon")) else ""
                            }
                            new_teachers.append(t_obj)
                        st.session_state.teachers = new_teachers
                        
                        # Branşları güncelle
                        branches = set(st.session_state.branches)
                        for t in new_teachers:
                            branches.add(t['branch'])
                        st.session_state.branches = sorted(list(branches))

                    # 2. Dersler
                    if 'Dersler' in xls.sheet_names:
                        df_c = pd.read_excel(xls, 'Dersler')
                        new_courses = []
                        for _, row in df_c.iterrows():
                            if pd.isna(row.get("Ders Adı")): continue
                            c_obj = {
                                "name": str(row["Ders Adı"]).strip(),
                                "branch": str(row["Branş"]).strip() if pd.notna(row["Branş"]) else "Genel",
                                "max_daily_hours": int(row["Günlük Max Saat"]) if pd.notna(row.get("Günlük Max Saat")) else 2,
                                "block_size": int(row["Blok Süresi"]) if pd.notna(row.get("Blok Süresi")) else 1,
                                "specific_room": str(row["Zorunlu Derslik"]) if pd.notna(row.get("Zorunlu Derslik")) else None
                            }
                            new_courses.append(c_obj)
                        st.session_state.courses = new_courses
                        
                        # Branşları güncelle
                        branches = set(st.session_state.branches)
                        for c in new_courses:
                            branches.add(c['branch'])
                        st.session_state.branches = sorted(list(branches))

                    # 3. Sınıflar
                    if 'Siniflar' in xls.sheet_names:
                        df_cl = pd.read_excel(xls, 'Siniflar')
                        new_classes = []
                        new_class_teachers = {}
                        for _, row in df_cl.iterrows():
                            if pd.isna(row.get("Sınıf Adı")): continue
                            c_name = str(row["Sınıf Adı"]).strip()
                            new_classes.append(c_name)
                            if pd.notna(row.get("Sınıf Öğretmeni")):
                                new_class_teachers[c_name] = str(row["Sınıf Öğretmeni"]).strip()
                        st.session_state.classes = new_classes
                        st.session_state.class_teachers = new_class_teachers

                    # 4. Derslikler
                    if 'Derslikler' in xls.sheet_names:
                        df_r = pd.read_excel(xls, 'Derslikler')
                        new_rooms = []
                        new_capacities = {}
                        for _, row in df_r.iterrows():
                            if pd.isna(row.get("Derslik Adı")): continue
                            r_name = str(row["Derslik Adı"]).strip()
                            new_rooms.append(r_name)
                            if pd.notna(row.get("Kapasite")):
                                new_capacities[r_name] = int(row["Kapasite"])
                        st.session_state.rooms = new_rooms
                        st.session_state.room_capacities = new_capacities

                    # 5. Ders Programı (Atamalar)
                    if 'DersProgrami' in xls.sheet_names:
                        df_p = pd.read_excel(xls, 'DersProgrami')
                        st.session_state.class_lessons = {}
                        st.session_state.assignments = {}
                        
                        for _, row in df_p.iterrows():
                            if pd.isna(row.get("Sınıf")) or pd.isna(row.get("Ders")): continue
                            c_name = str(row["Sınıf"]).strip()
                            crs_name = str(row["Ders"]).strip()
                            hours = int(row["Haftalık Saat"]) if pd.notna(row.get("Haftalık Saat")) else 0
                            t_name = str(row["Öğretmen"]).strip() if pd.notna(row.get("Öğretmen")) else None
                            
                            if c_name not in st.session_state.class_lessons:
                                st.session_state.class_lessons[c_name] = {}
                            if c_name not in st.session_state.assignments:
                                st.session_state.assignments[c_name] = {}
                                
                            st.session_state.class_lessons[c_name][crs_name] = hours
                            if t_name:
                                st.session_state.assignments[c_name][crs_name] = t_name

                    save_data()
                    st.success("Veriler başarıyla içe aktarıldı!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Hata oluştu: {e}")
