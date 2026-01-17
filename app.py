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
import hmac
import urllib.parse
import random
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import sqlite3
from solver import create_timetable

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

# --- Dosya İşlemleri ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DATA_FILE = os.path.join(DATA_DIR, "okul_verileri.json")
DB_FILE = os.path.join(DATA_DIR, "okul_verileri.db")

def init_db():
    """Veritabanı tablosunu oluşturur."""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # Anahtar-Değer saklama yapısı (Key-Value Store)
        c.execute('CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT)')
        # Okullar tablosu
        c.execute('CREATE TABLE IF NOT EXISTS schools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, username TEXT UNIQUE, password TEXT)')

def create_school(name, username, password):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO schools (name, username, password) VALUES (?, ?, ?)", (name, username, password))
        return True, "Okul başarıyla oluşturuldu."
    except sqlite3.IntegrityError:
        return False, "Bu kullanıcı adı zaten kullanılıyor."
    except Exception as e:
        return False, str(e)

def get_schools():
    if not os.path.exists(DB_FILE): return []
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, username FROM schools")
        rows = c.fetchall()
    return rows

def delete_school(school_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM schools WHERE id = ?", (school_id,))
        # Okula ait verileri de temizle
        prefix = f"school_{school_id}_%"
        c.execute("DELETE FROM kv_store WHERE key LIKE ?", (prefix,))

def update_school(school_id, name, username, password):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            if password:
                c.execute("UPDATE schools SET name = ?, username = ?, password = ? WHERE id = ?", (name, username, password, school_id))
            else:
                c.execute("UPDATE schools SET name = ?, username = ? WHERE id = ?", (name, username, school_id))
        return True, "Okul güncellendi."
    except sqlite3.IntegrityError:
        return False, "Bu kullanıcı adı zaten kullanılıyor."
    except Exception as e:
        return False, str(e)

def get_db_size():
    if os.path.exists(DB_FILE):
        return os.path.getsize(DB_FILE)
    return 0

def verify_school_user(username, password):
    if not os.path.exists(DB_FILE): return None
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, name FROM schools WHERE username = ? AND password = ?", (username, password))
        row = c.fetchone()
    return row # (id, name)

def load_data(school_id=None):
    # Dosya varlık ve zaman kontrolü
    db_exists = os.path.exists(DB_FILE)
    json_exists = os.path.exists(DATA_FILE)
    
    # Çoklu Okul Modu: Sadece Veritabanından Yükle
    if school_id:
        data = {}
        if db_exists:
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    c = conn.cursor()
                    prefix = f"school_{school_id}_"
                    c.execute("SELECT key, value FROM kv_store WHERE key LIKE ?", (f"{prefix}%",))
                    rows = c.fetchall()

                for key, val in rows:
                    # Prefix'i kaldırarak dict'e ekle
                    clean_key = key[len(prefix):]
                    try:
                        data[clean_key] = json.loads(val)
                    except:
                        data[clean_key] = val
            except Exception as e:
                st.error(f"Okul verisi yükleme hatası: {e}")
        return data

    # Eğer JSON dosyası DB'den daha yeniyse (manuel yükleme/düzenleme) JSON'ı tercih et
    prefer_json = False
    if json_exists and db_exists:
        if os.path.getmtime(DATA_FILE) > os.path.getmtime(DB_FILE):
            prefer_json = True
    elif json_exists and not db_exists:
        prefer_json = True

    # 1. JSON Tercih Ediliyorsa Oku
    if prefer_json:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass # Hata olursa DB'yi dene

    # 2. SQLite Veritabanını dene
    if db_exists:
        try:
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute('SELECT key, value FROM kv_store')
                rows = c.fetchall()
            
            data = {}
            for key, val in rows:
                try:
                    data[key] = json.loads(val)
                except:
                    data[key] = val
            if data:
                return data
        except Exception as e:
            st.error(f"Veritabanı okuma hatası: {e}")
    
    # 3. Veritabanı yoksa veya boşsa ve JSON henüz denenmediyse JSON dosyasını dene
    if json_exists and not prefer_json:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data():
    school_id = st.session_state.get('school_id')
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
        "email_config": st.session_state.get('email_config', {}),
        "last_schedule": st.session_state.get('last_schedule', []),
        "duty_places": st.session_state.get('duty_places', []),
        "duty_place_constraints": st.session_state.get('duty_place_constraints', {}),
        "duty_place_branch_constraints": st.session_state.get('duty_place_branch_constraints', {}),
        "duty_place_scores": st.session_state.get('duty_place_scores', {}),
        "vice_principals": st.session_state.get('vice_principals', {})
    }
    
    # 1. JSON Yedeği (Sadece tekil modda veya yedekleme amaçlı)
    if not school_id:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            st.warning(f"JSON yedek dosyası oluşturulamadı: {e}")
        
    # 2. SQLite Veritabanına Kayıt
    try:
        init_db() # Tablo yoksa oluştur
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            
            prefix = f"school_{school_id}_" if school_id else ""
            
            for k, v in data.items():
                # Okul ID varsa anahtarı prefixle
                db_key = f"{prefix}{k}"
                # Her bir veri parçasını (teachers, courses vb.) ayrı satır olarak kaydet
                c.execute('INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)', (db_key, json.dumps(v, ensure_ascii=False)))
        st.toast("Veriler Veritabanına (SQLite) Kaydedildi!", icon="💾")
    except Exception as e:
        st.error(f"Veritabanı kayıt hatası: {e}")

def search_teacher_by_name(name_query):
    """
    SQLite JSON özelliklerini kullanarak veritabanından isme göre öğretmen arar.
    """
    if not os.path.exists(DB_FILE): return []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            # json_each fonksiyonu JSON dizisini sanal bir tabloya dönüştürür
            # key='teachers' olan satırdaki JSON listesini parçalar
            query = """
                SELECT json_each.value 
                FROM kv_store, json_each(kv_store.value) 
                WHERE key = 'teachers' 
                AND json_extract(json_each.value, '$.name') LIKE ?
            """
            c.execute(query, (f'%{name_query}%',))
            return [json.loads(row[0]) for row in c.fetchall()]
    except Exception as e:
        st.error(f"Arama hatası: {e}")
        return []

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
        # Sadece programda dersi olanları değil, tüm tanımlı derslikleri göster
        if 'rooms' in st.session_state and st.session_state.rooms:
            items = sorted([str(r) for r in st.session_state.rooms])
        else:
            items = sorted([str(r) for r in df['Derslik'].unique() if r])
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
            duty_place = t_info.get('duty_place', '')
            
            if isinstance(duty_day, list):
                safe_duty = ", ".join(duty_day) if duty_day else "-"
            else:
                safe_duty = str(duty_day) if duty_day and duty_day not in [None, "Yok", ""] else "-"
                
            if duty_place:
                safe_duty += f" ({duty_place})"
            
            header_text = f"Öğretmen: {safe_name}   |   Toplam Ders Saati: {total_hours}   |   Nöbet: {safe_duty}"
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

def create_duty_pdf(start_date=None, num_weeks=1, vice_principals=None, include_weekend=False, rotate_weekly=False):
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
            self.set_font(font_family, 'B', 12)
            rep_conf = st.session_state.get('report_config', {})
            main_title = rep_conf.get('report_title', "")
            if main_title:
                self.cell(0, 7, clean_text(main_title), 0, 1, 'C')
            sub_title = getattr(self, 'week_title', 'Nöbet Çizelgesi')
            self.cell(0, 7, clean_text(sub_title), 0, 1, 'C')
            self.ln(5)

    pdf = PDF(orientation='L')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Türkçe Font Ekleme
    if os.path.exists(font_path):
        try:
            try:
                pdf.add_font('TrArial', '', font_path, uni=True)
            except TypeError:
                pdf.add_font('TrArial', '', font_path)
            
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
            
            font_family = 'TrArial'
        except:
            pass
            
    # Veriyi Hazırla
    days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
    if include_weekend:
        days.extend(["Cumartesi", "Pazar"])
    places = sorted(st.session_state.get("duty_places", []))
    used_places = set()
    for t in st.session_state.teachers:
        if t.get('duty_place'):
            used_places.add(t['duty_place'])
    all_places = sorted(list(set(places) | used_places))
    
    # Öğretmenlerin nöbet durumlarını geçici bir yapıda tut (Rotasyon için)
    # current_duties[t_name][day] = place
    current_duties = {}
    
    for t in st.session_state.teachers:
        t_name = t['name']
        d_raw = t.get('duty_day')
        place = t.get('duty_place')
        
        if isinstance(d_raw, str): d_list = [d_raw]
        elif isinstance(d_raw, list): d_list = d_raw
        else: d_list = []
        
        # Sadece geçerli günleri al
        valid_days = [d for d in d_list if d in days]
        
        if valid_days and place:
            current_duties[t_name] = {}
            for d in valid_days:
                current_duties[t_name][d] = place

    # Hafta Döngüsü
    for w in range(num_weeks):
        # VP Rotasyonu
        current_week_vps = vice_principals
        if rotate_weekly and vice_principals:
            vp_list_ordered = [vice_principals.get(d, "") for d in days]
            shift = w % len(days)
            rotated_vp_list = vp_list_ordered[-shift:] + vp_list_ordered[:-shift]
            current_week_vps = {d: rotated_vp_list[i] for i, d in enumerate(days)}

        # Rotasyon (İlk hafta hariç)
        if w > 0 and rotate_weekly:
            for d in days:
                # O gün nöbetçi olanları ve yerlerini bul
                day_assignments = [] # (t_name, place)
                
                # İsim sırasına göre al ki her seferinde aynı sırada olsun
                sorted_teachers = sorted(current_duties.keys())
                
                for t_name in sorted_teachers:
                    if d in current_duties[t_name]:
                        day_assignments.append((t_name, current_duties[t_name][d]))
                
                if day_assignments:
                    # Yerleri ayır
                    places_on_day = [x[1] for x in day_assignments]
                    # Kaydır (Sağa doğru 1 birim: Sonuncusu başa gelir)
                    rotated_places = [places_on_day[-1]] + places_on_day[:-1]
                    
                    # Yeni yerleri ata
                    for idx, (t_name, _) in enumerate(day_assignments):
                        current_duties[t_name][d] = rotated_places[idx]

        # Tarih Başlığı Hesapla
        title_suffix = ""
        current_monday = None
        if start_date:
            current_monday = start_date + timedelta(weeks=w)
            days_to_add = 6 if include_weekend else 4
            end_date = current_monday + timedelta(days=days_to_add)
            title_suffix = f" ({current_monday.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')})"

        pdf.week_title = f"Nöbet Çizelgesi{title_suffix}"
        pdf.add_page()
        
        if not all_places:
            pdf.set_font(font_family, '', 10)
            pdf.cell(0, 10, clean_text("Tanımlı nöbet yeri bulunamadı."), 0, 1, 'C')
        else:
            pdf.set_font(font_family, 'B', 10)
            w_place = 50
            w_day = 45
            
            if include_weekend:
                w_place = 40
                w_day = 32
            
            def print_header_row():
                # Başlık yüksekliğini içeriğe göre ayarla (Tarih ve Müdür Yrd varsa artır)
                header_height = 10
                if start_date or (current_week_vps and any(current_week_vps.values())):
                    header_height = 20
                
                pdf.set_font(font_family, 'B', 10)
                pdf.cell(w_place, header_height, clean_text("Nöbet Yeri"), 1, 0, 'C')
                
                for i, d in enumerate(days):
                    x_curr = pdf.get_x()
                    y_curr = pdf.get_y()
                    
                    # Çerçeve
                    pdf.rect(x_curr, y_curr, w_day, header_height)
                    
                    # İçerik
                    vp_text = current_week_vps.get(d, "") if current_week_vps else ""
                    date_text = ""
                    if start_date and current_monday:
                        d_obj = current_monday + timedelta(days=i)
                        date_text = d_obj.strftime('%d.%m.%Y')
                    
                    # 1. Gün Adı
                    pdf.set_font(font_family, 'B', 10)
                    pdf.set_xy(x_curr, y_curr + 2)
                    pdf.cell(w_day, 5, clean_text(d), 0, 0, 'C')
                    
                    next_y = y_curr + 7
                    # 2. Tarih
                    if date_text:
                        pdf.set_font(font_family, '', 8)
                        pdf.set_xy(x_curr, next_y)
                        pdf.cell(w_day, 5, clean_text(date_text), 0, 0, 'C')
                        next_y += 5
                    
                    # 3. Müdür Yrd (Renkli ve Kalın)
                    if vp_text:
                        pdf.set_font(font_family, 'B', 8)
                        pdf.set_text_color(180, 0, 0) # Koyu Kırmızı
                        pdf.set_xy(x_curr, next_y)
                        pdf.cell(w_day, 5, clean_text(vp_text), 0, 0, 'C')
                        pdf.set_text_color(0, 0, 0)
                    
                    pdf.set_xy(x_curr + w_day, y_curr)
                
                pdf.ln(header_height)
                pdf.set_font(font_family, '', 9)

            print_header_row()
            
            for place in all_places:
                day_teachers = {d: [] for d in days}
                # current_duties'den veriyi çek
                for t_name, duties in current_duties.items():
                    for d, p in duties.items():
                        if p == place:
                            day_teachers[d].append(t_name)
                
                max_lines = 1
                for d in days:
                    max_lines = max(max_lines, len(day_teachers[d]))
                
                line_height = 5
                row_height = max(10, max_lines * line_height + 2) # Biraz padding
                
                # Sayfa sonu kontrolü (Basit)
                if pdf.get_y() + row_height > 180: # Sayfa boyutu A4 Landscape ~210mm yükseklik
                    pdf.add_page()
                    print_header_row()

                x_start = pdf.get_x()
                y_start = pdf.get_y()
                
                # Renk Ayarı (Pastel)
                h_val = hashlib.md5(place.encode('utf-8')).hexdigest()
                r = int(h_val[:2], 16) % 50 + 205
                g = int(h_val[2:4], 16) % 50 + 205
                b = int(h_val[4:6], 16) % 50 + 205
                pdf.set_fill_color(r, g, b)
                
                # Nöbet Yeri
                pdf.multi_cell(w_place, row_height, clean_text(place), 1, 'C', fill=True)
                
                # Günler
                for i, d in enumerate(days):
                    curr_x = x_start + w_place + (i * w_day)
                    pdf.set_xy(curr_x, y_start)
                    content = "\n".join(day_teachers[d])
                    # Multi cell border çizimi bazen sorunlu olabilir, rect çizelim
                    pdf.multi_cell(w_day, line_height, clean_text(content), 0, 'C')
                    pdf.rect(curr_x, y_start, w_day, row_height)
                    
                pdf.set_xy(x_start, y_start + row_height)

    # İmza
    pdf.ln(10)
    rep_conf = st.session_state.get('report_config', {})
    principal_name = rep_conf.get('principal_name', "")
    
    pdf.set_x(200)
    pdf.set_font(font_family, 'B', 10)
    pdf.cell(60, 5, clean_text("Okul Müdürü"), 0, 1, 'C')
    pdf.set_x(200)
    pdf.set_font(font_family, '', 10)
    pdf.cell(60, 5, clean_text(principal_name), 0, 1, 'C')
    
    try:
        return bytes(pdf.output())
    except TypeError:
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
if 'role' not in st.session_state:
    st.session_state.role = 'viewer' # Varsayılan rol

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
            init_db() # DB tablolarını garantiye al
            
            # 1. Süper Admin Kontrolü (Sabit veya Secrets)
            is_super = False
            if username == "superadmin" and password == "superpass": # Varsayılan
                is_super = True
            elif "super_auth" in st.secrets:
                if username == st.secrets["super_auth"]["username"] and password == st.secrets["super_auth"]["password"]:
                    is_super = True
            
            if is_super:
                st.session_state.logged_in = True
                st.session_state.role = "super_admin"
                st.rerun()

            # 2. Okul Yöneticisi Kontrolü (DB'den)
            school_user = verify_school_user(username, password)
            if school_user:
                st.session_state.logged_in = True
                st.session_state.role = "admin" # Okul yöneticisi kendi okulunun adminidir
                st.session_state.school_id = school_user[0]
                st.session_state.school_name = school_user[1]
                st.rerun()

            # Örnek Kullanıcılar (Rol Tabanlı Erişim İçin)
            # Gerçek senaryoda bu veriler veritabanından veya secrets.toml'dan gelmelidir.
            DEMO_USERS = {
                "admin": {"pass": "admin", "role": "admin"},
                "ogretmen": {"pass": "123", "role": "teacher"},
                "misafir": {"pass": "123", "role": "viewer"}
            }

            # Secrets üzerinden şifre kontrolü
            if username in DEMO_USERS and DEMO_USERS[username]["pass"] == password:
                st.session_state.logged_in = True
                st.session_state.role = DEMO_USERS[username]["role"]
                st.rerun()
            elif "auth" in st.secrets:
                valid_user = st.secrets["auth"]["username"]
                stored_hash = st.secrets["auth"]["password_hash"]
                
                # Girilen şifreyi hashle
                input_hash = hashlib.sha256(password.encode()).hexdigest()
                
                # Güvenli karşılaştırma (hmac ile)
                if username == valid_user and hmac.compare_digest(input_hash, stored_hash):
                    st.session_state.logged_in = True
                    st.session_state.role = "admin"
                    st.rerun()
                else:
                    st.error("Hatalı kullanıcı adı veya şifre")
            else:
                # Secrets yapılandırılmamışsa varsayılan giriş (admin/admin)
                if username == "admin" and password == "admin":
                    st.session_state.logged_in = True
                    st.session_state.role = "admin"
                    st.rerun()
                else:
                    st.error("Giriş bilgileri (secrets.toml) bulunamadı! Varsayılan: admin / admin")
    st.stop()

# --- Süper Admin Paneli ---
if st.session_state.get("role") == "super_admin":
    st.sidebar.title("Süper Admin")
    if st.sidebar.button("🚪 Çıkış Yap"):
        st.session_state.logged_in = False
        st.session_state.role = 'viewer'
        st.rerun()
    
    st.title("🏫 Okul Yönetim Paneli")
    
    # İstatistikler
    schools = get_schools()
    total_schools = len(schools)
    db_size = get_db_size()
    db_size_mb = db_size / (1024 * 1024)
    
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Toplam Okul", total_schools)
    col_m2.metric("Veritabanı Boyutu", f"{db_size_mb:.2f} MB")
    col_m3.metric("Sistem Durumu", "Aktif", delta="Çalışıyor")
    
    st.divider()
    
    tab_main, tab_sys = st.tabs(["🏫 Okul Yönetimi", "⚙️ Sistem"])
    
    with tab_main:
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            st.subheader("Kayıtlı Okullar")
            if schools:
                df_schools = pd.DataFrame(schools, columns=["ID", "Okul Adı", "Kullanıcı Adı"])
                st.dataframe(df_schools, use_container_width=True, hide_index=True)
            else:
                st.info("Henüz kayıtlı okul bulunmamaktadır.")
        
        with col_right:
            st.subheader("İşlemler")
            action_type = st.radio("İşlem Seçiniz", ["Yeni Okul Ekle", "Okul Düzenle", "Okul Sil"])
            
            if action_type == "Yeni Okul Ekle":
                with st.form("add_school_form"):
                    new_s_name = st.text_input("Okul Adı")
                    new_s_user = st.text_input("Yönetici Kullanıcı Adı")
                    new_s_pass = st.text_input("Şifre", type="password")
                    if st.form_submit_button("Okul Ekle", type="primary"):
                        if new_s_name and new_s_user and new_s_pass:
                            success, msg = create_school(new_s_name, new_s_user, new_s_pass)
                            if success: 
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else: st.error(msg)
                        else:
                            st.warning("Lütfen tüm alanları doldurun.")
            
            elif action_type == "Okul Düzenle":
                if schools:
                    school_opts = {f"{s[1]} ({s[2]})": s for s in schools}
                    selected_s_name = st.selectbox("Okul Seç", list(school_opts.keys()))
                    selected_s = school_opts[selected_s_name]
                    
                    with st.form("edit_school_form"):
                        edit_name = st.text_input("Okul Adı", value=selected_s[1])
                        edit_user = st.text_input("Kullanıcı Adı", value=selected_s[2])
                        edit_pass = st.text_input("Yeni Şifre (Değişmeyecekse boş bırakın)", type="password")
                        
                        if st.form_submit_button("Güncelle"):
                            suc, msg = update_school(selected_s[0], edit_name, edit_user, edit_pass)
                            if suc:
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)
                else:
                    st.warning("Düzenlenecek okul yok.")
            
            elif action_type == "Okul Sil":
                if schools:
                    school_opts = {f"{s[1]} ({s[2]})": s for s in schools}
                    selected_s_name = st.selectbox("Silinecek Okul", list(school_opts.keys()))
                    selected_s = school_opts[selected_s_name]
                    
                    st.warning(f"**{selected_s[1]}** okulunu ve tüm verilerini silmek üzeresiniz!")
                    if st.button("Evet, Okulu Sil", type="primary"):
                        delete_school(selected_s[0])
                        st.success("Okul başarıyla silindi.")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Silinecek okul yok.")

    with tab_sys:
        st.subheader("Sistem Bakımı")
        c_sys1, c_sys2 = st.columns(2)
        with c_sys1:
            if st.button("Veritabanını Optimize Et (VACUUM)"):
                try:
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.execute("VACUUM")
                    st.success("Veritabanı optimize edildi ve boyutu küçültüldü.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Hata: {e}")
        
        with c_sys2:
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    st.download_button("Veritabanı Yedeğini İndir", f, file_name="okul_verileri.db", mime="application/x-sqlite3")

    st.stop()

# --- Session State Başlatma ---
saved_data = load_data(st.session_state.get('school_id'))

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
        "lunch_break_hour": "Yok",
        "min_daily_hours": 2
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
if 'last_schedule' not in st.session_state:
    st.session_state.last_schedule = saved_data.get('last_schedule', [])
if 'duty_places' not in st.session_state:
    st.session_state.duty_places = saved_data.get('duty_places', ["Bahçe", "Zemin Kat", "1. Kat", "2. Kat", "Kantin"])
if 'duty_place_constraints' not in st.session_state:
    st.session_state.duty_place_constraints = saved_data.get('duty_place_constraints', {})
if 'duty_place_branch_constraints' not in st.session_state:
    st.session_state.duty_place_branch_constraints = saved_data.get('duty_place_branch_constraints', {})
if 'duty_place_scores' not in st.session_state:
    st.session_state.duty_place_scores = saved_data.get('duty_place_scores', {})
if 'vice_principals' not in st.session_state:
    st.session_state.vice_principals = saved_data.get('vice_principals', {})

# --- Yan Menü ---
panel_title = f"Panel ({st.session_state.get('role', 'user')})"
if st.session_state.get('school_name'):
    panel_title += f"\n🏫 {st.session_state.school_name}"

st.sidebar.title(panel_title)
if st.sidebar.button("🚪 Çıkış Yap"):
    st.session_state.logged_in = False
    st.session_state.role = 'viewer'
    st.rerun()

if st.session_state.get("role") == "admin":
    if st.sidebar.button("💾 Tüm Verileri Kaydet"):
        save_data()
    menu_options = ["Tanımlamalar", "Ders Atama & Kopyalama", "Program Oluştur", "Nöbet İşlemleri", "Hızlı Düzenle", "Veri İşlemleri"]
else:
    menu_options = ["Program Oluştur", "Nöbet İşlemleri"]

menu = st.sidebar.radio("Menü", menu_options)

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
            curr_branches = st.session_state.room_branches.get(selected_room) or []
            curr_teachers = st.session_state.room_teachers.get(selected_room) or []
            curr_courses = st.session_state.room_courses.get(selected_room) or []
            curr_excluded = st.session_state.room_excluded_courses.get(selected_room) or []
            
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
            if "duty_place" not in t: t["duty_place"] = ""
            if "preference" not in t: t["preference"] = "Farketmez"
            if "email" not in t: t["email"] = ""
            if "phone" not in t: t["phone"] = ""
            if "gender" not in t: t["gender"] = "Erkek"
            if "unwanted_duty_places" not in t: t["unwanted_duty_places"] = []
            if "title" not in t: t["title"] = "Öğretmen"
            
        if not st.session_state.teachers:
            df_teachers = pd.DataFrame(columns=["name", "branch", "title", "gender", "email", "phone", "unavailable_days", "unavailable_slots", "max_hours_per_day", "duty_day", "duty_place", "unwanted_duty_places", "preference"])
        else:
            df_teachers = pd.DataFrame(st.session_state.teachers)
            if "duty_place" not in df_teachers.columns: df_teachers["duty_place"] = ""
            if "gender" not in df_teachers.columns: df_teachers["gender"] = "Erkek"
            if "unwanted_duty_places" not in df_teachers.columns: 
                df_teachers["unwanted_duty_places"] = [[] for _ in range(len(df_teachers))]
            if "title" not in df_teachers.columns: df_teachers["title"] = "Öğretmen"
            
            # PyArrow uyumluluğu için veri tiplerini garantiye al
            # 1. Liste olması gereken sütunlar
            for col in ["unavailable_days", "unavailable_slots", "unwanted_duty_places"]:
                if col in df_teachers.columns:
                    df_teachers[col] = df_teachers[col].apply(lambda x: x if isinstance(x, list) else [])
            
            # 2. duty_day (TextColumn olduğu için stringe çeviriyoruz, kaydederken geri çevireceğiz)
            if "duty_day" in df_teachers.columns:
                def fmt_duty(x):
                    if isinstance(x, list): return ", ".join(x)
                    if pd.isna(x) or x == "Yok": return ""
                    return str(x)
                df_teachers["duty_day"] = df_teachers["duty_day"].apply(fmt_duty)
            
        edited_teachers = st.data_editor(
            df_teachers,
            column_config={
                "name": "Adı Soyadı",
                "branch": st.column_config.SelectboxColumn("Branş", options=st.session_state.branches, required=True),
                "gender": st.column_config.SelectboxColumn("Cinsiyet", options=["Erkek", "Kadın"], required=False),
                "title": st.column_config.SelectboxColumn("Unvan", options=["Öğretmen", "Müdür Yardımcısı", "Müdür"], required=True, default="Öğretmen"),
                "email": st.column_config.TextColumn("E-Posta", help="Ders programının gönderileceği e-posta adresi"),
                "phone": st.column_config.TextColumn("Telefon", help="WhatsApp için 905xxxxxxxxx formatında"),
                "unavailable_days": st.column_config.ListColumn("İzin Günleri", help="Müsait olunmayan günleri ekleyin"),
                "unavailable_slots": st.column_config.ListColumn("Kısıtlı Saatler", help="Format: Gün:Saat (Örn: Pazartesi:1, Salı:5)"),
                "max_hours_per_day": st.column_config.NumberColumn("Günlük Max", min_value=1, max_value=8),
                "duty_day": st.column_config.TextColumn("Nöbet Günleri", disabled=True, help="Nöbet günlerini 'Manuel Nöbet Düzenleme' bölümünden çoklu olarak seçebilirsiniz."),
                "duty_place": st.column_config.SelectboxColumn("Nöbet Yeri", options=st.session_state.duty_places, required=False),
                "unwanted_duty_places": st.column_config.ListColumn("İstemediği Yerler", help="Öğretmenin nöbet tutmak istemediği yerleri ekleyin."),
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
            if "gender" in cleaned_df.columns:
                cleaned_df["gender"] = cleaned_df["gender"].astype(str).str.strip()
            if "title" in cleaned_df.columns:
                cleaned_df["title"] = cleaned_df["title"].astype(str).str.strip()
            
            # duty_day string'den listeye geri çevir
            if "duty_day" in cleaned_df.columns:
                def parse_duty(x):
                    if not x: return []
                    if isinstance(x, str):
                        return [d.strip() for d in x.split(",") if d.strip()]
                    return []
                cleaned_df["duty_day"] = cleaned_df["duty_day"].apply(parse_duty)
            
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
    st.header("Ders Programı")
    
    if st.session_state.role == "admin":
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
            
            col_dr1, col_dr2 = st.columns(2)
            duty_reduction = col_dr1.slider("Nöbet Günü Ders Yükü Azaltma (Saat)", min_value=0, max_value=8, value=int(lc.get("duty_day_reduction", 2)), help="Öğretmenin nöbetçi olduğu gün, günlük maksimum ders saatinden kaç saat daha az ders verileceğini belirler.")
            min_daily = col_dr2.slider("Öğretmen Günlük Min. Ders (Geldiği Gün)", min_value=1, max_value=5, value=int(lc.get("min_daily_hours", 2)), help="Öğretmen okula geldiği gün en az kaç saat dersi olsun?")

            st.session_state.lesson_config = {
                "start_time": new_start,
                "lesson_duration": new_ldur,
                "break_duration": new_bdur,
                "lunch_duration": new_lunch_dur,
                "num_hours": new_num_hours,
                "lunch_break_hour": new_lunch_hour,
                "duty_day_reduction": duty_reduction,
                "min_daily_hours": min_daily
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
    else:
        mode = "Sınıf Bazlı"

    solver_mode = "room" if "Derslik" in mode else "class"
    
    # Değerleri config'den al
    num_hours = st.session_state.lesson_config.get("num_hours", 8)
    lunch_val = st.session_state.lesson_config.get("lunch_break_hour", "Yok")
    lunch_break_hour = int(lunch_val) if lunch_val != "Yok" else None

    if st.session_state.role == "admin" and st.button("Programı Dağıt"):
        st.session_state.last_schedule = [] # Yeni işlem öncesi eski sonucu temizle
        
        # İlerleme Çubuğu Oluştur
        prog_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(pct, msg):
            prog_bar.progress(pct)
            status_text.text(msg)

        # Veri temizliği: None olan listeleri boş listeye çevir (TypeError önlemek için)
        clean_room_branches = {k: (v if v is not None else []) for k, v in st.session_state.room_branches.items()}
        clean_room_teachers = {k: (v if v is not None else []) for k, v in st.session_state.room_teachers.items()}
        clean_room_courses = {k: (v if v is not None else []) for k, v in st.session_state.room_courses.items()}
        clean_room_excluded = {k: (v if v is not None else []) for k, v in st.session_state.get('room_excluded_courses', {}).items()}

        try:
            schedule, msg = create_timetable(
                st.session_state.teachers, st.session_state.courses, st.session_state.classes,
                st.session_state.class_lessons, st.session_state.assignments, st.session_state.rooms, 
                room_capacities=st.session_state.room_capacities,
                room_branches=clean_room_branches,
                room_teachers=clean_room_teachers,
                room_courses=clean_room_courses,
                room_excluded_courses=clean_room_excluded,
                mode=solver_mode, lunch_break_hour=lunch_break_hour, num_hours=num_hours,
                simultaneous_lessons=st.session_state.simultaneous_lessons,
                duty_day_reduction=st.session_state.lesson_config.get("duty_day_reduction", 2),
                min_daily_hours=st.session_state.lesson_config.get("min_daily_hours", 2),
                progress_callback=update_progress
            )
        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                try:
                    schedule, msg = create_timetable(
                        st.session_state.teachers, st.session_state.courses, st.session_state.classes,
                        st.session_state.class_lessons, st.session_state.assignments, st.session_state.rooms, 
                        room_capacities=st.session_state.room_capacities,
                        room_branches=clean_room_branches,
                        room_teachers=clean_room_teachers,
                        room_courses=clean_room_courses,
                        room_excluded_courses=clean_room_excluded,
                        mode=solver_mode, lunch_break_hour=lunch_break_hour, num_hours=num_hours,
                        simultaneous_lessons=st.session_state.simultaneous_lessons,
                        duty_day_reduction=st.session_state.lesson_config.get("duty_day_reduction", 2),
                        min_daily_hours=st.session_state.lesson_config.get("min_daily_hours", 2)
                    )
                except TypeError as e2:
                    if "unexpected keyword argument" in str(e2):
                        schedule, msg = create_timetable(
                            st.session_state.teachers, st.session_state.courses, st.session_state.classes,
                            st.session_state.class_lessons, st.session_state.assignments, st.session_state.rooms, 
                            room_capacities=st.session_state.room_capacities,
                            room_branches=clean_room_branches,
                            room_teachers=clean_room_teachers,
                            room_courses=clean_room_courses,
                            room_excluded_courses=clean_room_excluded,
                            mode=solver_mode, lunch_break_hour=lunch_break_hour, num_hours=num_hours,
                            simultaneous_lessons=st.session_state.simultaneous_lessons,
                            duty_day_reduction=st.session_state.lesson_config.get("duty_day_reduction", 2)
                        )
                    else:
                        raise e2
            else:
                raise e
        
        prog_bar.empty()
        status_text.empty()
        
        if schedule:
            st.session_state.last_schedule = schedule
            save_data()
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
                
                if room_df.empty:
                    st.warning(f"⚠️ **{r}** dersliği için programda ders bulunamadı.")
                    st.caption("Eğer bu dersliği yeni eklediyseniz veya değişiklik yaptıysanız, **'Programı Dağıt'** butonuna basarak programı güncelleyiniz.")
                else:
                    st.info(f"📍 **{r}** dersliğinde toplam **{len(room_df)}** saat ders var.")
                    
                    # Hücre içeriği: Sınıf - Ders (Öğretmen)
                    room_df["Derslik_Hucre"] = room_df["Sınıf"] + " - " + room_df["Ders"] + " (" + room_df["Öğretmen"] + ")"
                    
                    # Pivot tablo oluştururken duplicate kontrolü (Kapasite > 1 ise hata verebilir)
                    try:
                        pivot = room_df.pivot(index="Saat", columns="Gün", values="Derslik_Hucre")
                    except ValueError:
                        # Çakışma varsa (aynı saatte birden fazla ders), birleştirerek göster
                        pivot = room_df.pivot_table(index="Saat", columns="Gün", values="Derslik_Hucre", aggfunc=lambda x: " / ".join(x))

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
        
        # --- Öğretmen Programı Görüntüleyici (Yeni Özellik) ---
        if st.session_state.role != "teacher":
            st.divider()
            st.subheader("🔍 Öğretmen Programı Görüntüle")
            
            view_t_list = [t['name'] for t in st.session_state.teachers]
            selected_view_t = st.selectbox("Programını Görmek İstediğiniz Öğretmeni Seçin", view_t_list, key="sel_teacher_view_specific")
            
            if selected_view_t:
                t_view_df = df[df["Öğretmen"] == selected_view_t].copy()
                if not t_view_df.empty:
                    t_view_df["Hucre"] = t_view_df["Sınıf"] + " - " + t_view_df["Ders"]
                    t_view_pivot = t_view_df.pivot(index="Saat", columns="Gün", values="Hucre")
                    
                    days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                    t_view_pivot = t_view_pivot.reindex(columns=days_order, index=range(1, num_hours + 1)).fillna("")
                    
                    st.dataframe(t_view_pivot, use_container_width=True)
                else:
                    st.info(f"{selected_view_t} isimli öğretmenin programda dersi bulunmamaktadır.")

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
        if st.session_state.role != "teacher":
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
        if st.session_state.role == "admin" and st.button("Öğretmenlere Programlarını Gönder"):
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
        elif st.session_state.role != "admin":
            st.info("E-Posta gönderimi sadece yönetici yetkisiyle yapılabilir.")

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
                
                # --- Isı Haritası (Heatmap) ---
                st.write("###### Derslik - Gün Bazlı Yoğunluk Haritası")
                heatmap_data = valid_rooms.groupby(["Derslik", "Gün"]).size().reset_index(name="Ders Saati")
                days_order = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                
                heatmap_chart = alt.Chart(heatmap_data).mark_rect().encode(
                    x=alt.X('Gün', sort=days_order, title='Gün'),
                    y=alt.Y('Derslik', title='Derslik'),
                    color=alt.Color('Ders Saati', title='Ders Saati', scale=alt.Scale(scheme='orangered')),
                    tooltip=['Derslik', 'Gün', 'Ders Saati']
                ).properties(title="Derslik Kullanım Yoğunluğu").configure_axis(
                    labelFontSize=12,
                    titleFontSize=14,
                    titleFontWeight='bold'
                ).configure_title(fontSize=20, color='blue')
                st.altair_chart(heatmap_chart, use_container_width=True)
            else:
                st.info("Programda tanımlı derslik kullanımı bulunamadı.")

# --- 4. NÖBET İŞLEMLERİ ---
elif menu == "Nöbet İşlemleri":
    st.header("Nöbet Yönetimi")
    
    # Yetki Kontrolü (Sadece Admin düzenleyebilir, diğerleri rapor görebilir)
    is_admin = st.session_state.role == "admin"
    
    if is_admin:
        tab_def, tab_day, tab_place, tab_rep = st.tabs(["Nöbet Yerleri Tanımlama", "Nöbet Günü Atama", "Nöbet Yeri Atama", "Çizelge ve Raporlar"])
    else:
        tab_rep = st.tabs(["Çizelge ve Raporlar"])[0]
        tab_def, tab_day, tab_place = None, None, None

    if is_admin:
        with tab_def:
            st.info("Okuldaki nöbet yerlerini (Bahçe, Koridor vb.) buradan tanımlayabilirsiniz.")
            
            place_data = []
            for p in st.session_state.duty_places:
                place_data.append({
                    "Nöbet Yeri": p,
                    "Kısıtlama": st.session_state.duty_place_constraints.get(p, "Herkes"),
                    "Branş Kısıtlaması": st.session_state.duty_place_branch_constraints.get(p, []),
                    "Zorluk Puanı": st.session_state.duty_place_scores.get(p, 1)
                })
            df_places = pd.DataFrame(place_data)
            
            edited_places = st.data_editor(
                df_places, 
                column_config={
                    "Kısıtlama": st.column_config.SelectboxColumn("Cinsiyet Kısıtlaması", options=["Herkes", "Erkek", "Kadın"], required=True, default="Herkes"),
                    "Branş Kısıtlaması": st.column_config.ListColumn("Branş Kısıtlaması", help="Sadece belirli branşlar nöbet tutsun (Boş bırakılırsa herkes tutabilir)."),
                    "Zorluk Puanı": st.column_config.NumberColumn("Zorluk Puanı", min_value=1, max_value=10, help="1: Çok Kolay, 10: Çok Zor")
                },
                num_rows="dynamic", width="stretch", key="editor_duty_places_def")
            if st.button("Nöbet Yerlerini Kaydet", key="save_duty_places"):
                st.session_state.duty_places = edited_places["Nöbet Yeri"].dropna().astype(str).tolist()
                st.session_state.duty_place_constraints = {row["Nöbet Yeri"]: row["Kısıtlama"] for _, row in edited_places.iterrows()}
                st.session_state.duty_place_branch_constraints = {row["Nöbet Yeri"]: row["Branş Kısıtlaması"] for _, row in edited_places.iterrows()}
                st.session_state.duty_place_scores = {row["Nöbet Yeri"]: int(row["Zorluk Puanı"]) for _, row in edited_places.iterrows()}
                save_data()
                st.success("Nöbet yerleri listesi güncellendi.")

        with tab_day:
            st.subheader("Otomatik Nöbet Atama")
            st.info("Öğretmenlerin izinli olduğu günleri dikkate alarak, nöbet günlerini haftaya dengeli bir şekilde dağıtır.")
            
            col_duty1, col_duty2, col_duty3 = st.columns([2, 1, 1])
            keep_existing = col_duty1.checkbox("Mevcut nöbet atamalarını koru (Sadece boş olanlara ata)", value=False)
            include_weekend_auto = col_duty1.checkbox("Hafta Sonu Dahil Et", value=False, key="inc_weekend_auto")
            
            total_teachers_count = len(st.session_state.teachers)
            default_max = (total_teachers_count // 5) + 1 if total_teachers_count > 0 else 5
            target_per_day = col_duty2.number_input("Günlük Maks. Nöbetçi", min_value=1, max_value=50, value=default_max, help="Her gün için atanacak maksimum nöbetçi öğretmen sayısı.")
            
            if col_duty3.button("Nöbetleri Dağıt", key="btn_auto_duty"):
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                if include_weekend_auto:
                    days.extend(["Cumartesi", "Pazar"])
                day_counts = {d: 0 for d in days}
                
                # Mevcut dolulukları hesapla (Eğer koruma açıksa)
                if keep_existing:
                    for t in st.session_state.teachers:
                        d = t.get('duty_day')
                        if d in days:
                            day_counts[d] += 1
                
                # İşlenecek öğretmenleri belirle
                teachers_to_process = []
                for t in st.session_state.teachers:
                    if keep_existing and t.get('duty_day') in days:
                        continue
                    teachers_to_process.append(t)
                
                # Karıştır (Adil dağılım için)
                random.shuffle(teachers_to_process)
                
                assigned_count = 0
                unassigned_count = 0
                
                for t in teachers_to_process:
                    unavailable = t.get('unavailable_days', []) or []
                    valid_days = [d for d in days if d not in unavailable]
                    
                    # Kapasite kontrolü: Sadece limiti aşmamış günleri aday yap
                    available_candidates = [d for d in valid_days if day_counts[d] < target_per_day]
                    
                    if available_candidates:
                        # En az yoğun olan günlerden rastgele birini seç
                        min_count = min(day_counts[d] for d in available_candidates)
                        candidates = [d for d in available_candidates if day_counts[d] == min_count]
                        selected_day = random.choice(candidates)
                        
                        t['duty_day'] = selected_day
                        day_counts[selected_day] += 1
                        assigned_count += 1
                    else:
                        # Uygun gün yok veya kontenjan dolu
                        if not keep_existing:
                            t['duty_day'] = "Yok"
                        unassigned_count += 1
                
                save_data()
                msg = f"{assigned_count} öğretmene nöbet günü atandı!"
                if unassigned_count > 0:
                    st.warning(f"{msg} (Kontenjan veya kısıtlamalar nedeniyle {unassigned_count} öğretmen boşta kaldı.)")
                else:
                    st.success(msg)
                time.sleep(1)
                st.rerun()

            # --- Manuel Nöbet Düzenleme (Kova Sistemi) ---
            st.divider()
            st.subheader("Manuel Nöbet Düzenleme")
            st.info("Öğretmenleri ilgili günlerin kutucuklarına ekleyip çıkararak nöbet günlerini belirleyebilirsiniz.")
            
            with st.form("manual_duty_form"):
                include_weekend_manual = st.checkbox("Hafta Sonu Göster", value=False)
                days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                if include_weekend_manual:
                    days.extend(["Cumartesi", "Pazar"])
                
                # Mevcut durumu al
                current_assignments = {d: [] for d in days}
                all_teacher_names = sorted([t['name'] for t in st.session_state.teachers if t.get('name')])
                
                # Ders Yüklerini Hesapla (Program oluşturulmuşsa)
                teacher_daily_loads = {d: {} for d in days}
                if 'last_schedule' in st.session_state and st.session_state.last_schedule:
                    for item in st.session_state.last_schedule:
                        t_name = item.get('Öğretmen')
                        day = item.get('Gün')
                        if t_name and day in teacher_daily_loads:
                            teacher_daily_loads[day][t_name] = teacher_daily_loads[day].get(t_name, 0) + 1

                for t in st.session_state.teachers:
                    d_raw = t.get('duty_day')
                    # Listeye çevir
                    if isinstance(d_raw, str) and d_raw not in [None, "Yok", ""]: d_list = [d_raw]
                    elif isinstance(d_raw, list): d_list = d_raw
                    else: d_list = []
                    
                    for d in d_list:
                        if d in days and t.get('name'):
                            current_assignments[d].append(t['name'])
                
                # Multiselectler
                cols = st.columns(len(days))
                new_assignments = {}
                
                for i, d in enumerate(days):
                    with cols[i]:
                        st.markdown(f"**{d}**")
                        # Varsayılan değerler, listede mevcut olmalı
                        valid_defaults = [t for t in current_assignments[d] if t in all_teacher_names]
                        
                        # Format fonksiyonu (O günkü ders sayısını göster)
                        def fmt_func(x, day=d):
                            return f"{x} ({teacher_daily_loads[day].get(x, 0)} Ders)"

                        new_assignments[d] = st.multiselect(
                            "Seç", 
                            all_teacher_names, 
                            default=valid_defaults, 
                            key=f"ms_duty_{d}",
                            label_visibility="collapsed",
                            format_func=fmt_func
                        )
                
                if st.form_submit_button("Nöbetleri Kaydet"):
                    # Çakışma ve Veri Kontrolü
                    teacher_days_map = {} # name -> set of days
                    
                    for d in days:
                        for t_name in new_assignments[d]:
                            if t_name not in teacher_days_map: teacher_days_map[t_name] = set()
                            teacher_days_map[t_name].add(d)
                    
                    # Güncelleme
                    cnt = 0
                    for t in st.session_state.teachers:
                        t_name = t.get('name')
                        new_days = []
                        if t_name in teacher_days_map:
                            # Günleri sıralı kaydet
                            new_days = sorted(list(teacher_days_map[t_name]), key=lambda x: days.index(x))
                        
                        # Değişiklik var mı?
                        old_days = t.get('duty_day')
                        if isinstance(old_days, str): old_days = [old_days] if old_days not in [None, "Yok", ""] else []
                        if not isinstance(old_days, list): old_days = []
                        
                        if new_days != old_days:
                            t['duty_day'] = new_days
                            cnt += 1
                    
                    save_data()
                    st.success(f"Nöbet günleri güncellendi. ({cnt} değişiklik)")
                    time.sleep(1)
                    st.rerun()

        with tab_place:
            st.subheader("Nöbet Yeri Düzenleme")
            
            # Yükleri Hesapla (Tekrar, bu blok için)
            teacher_daily_loads_table = {d: {} for d in ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]}
            if 'last_schedule' in st.session_state and st.session_state.last_schedule:
                 for item in st.session_state.last_schedule:
                    t_name = item.get('Öğretmen')
                    day = item.get('Gün')
                    if t_name and day in teacher_daily_loads_table:
                        teacher_daily_loads_table[day][t_name] = teacher_daily_loads_table[day].get(t_name, 0) + 1

            # Nöbet günü olan öğretmenleri filtrele
            duty_teachers = []
            for t in st.session_state.teachers:
                d_raw = t.get('duty_day')
                if isinstance(d_raw, list) and len(d_raw) > 0: duty_teachers.append(t)
                elif isinstance(d_raw, str) and d_raw not in [None, "Yok", ""]: duty_teachers.append(t)
            
            with st.expander("Otomatik Yer Dağıtımı"):
                st.info("Seçilen öğretmenlere, nöbet günlerinde dengeli olacak şekilde nöbet yeri atar.")
                
                # 1. Öğretmen Seçimi
                teacher_opts = [t['name'] for t in duty_teachers]
                selected_teachers_dist = st.multiselect("Öğretmenleri Seç", teacher_opts, default=teacher_opts)
                
                # 2. Yer Seçimi
                place_opts = st.session_state.duty_places
                selected_places_dist = st.multiselect("Dağıtılacak Yerler", place_opts, default=place_opts)
                
                use_rotation = st.checkbox("Rotasyon Uygula (Mevcut yerlerden farklı ata)", value=False, help="Seçili ise, öğretmenin şu anki nöbet yerinden farklı bir yer atanmaya çalışılır.")
                include_weekend_place = st.checkbox("Hafta Sonu Dahil Et", value=False, key="inc_weekend_place")
                
                if st.button("Yerleri Dağıt", key="btn_distribute_places"):
                    if not selected_places_dist:
                        st.error("Lütfen en az bir nöbet yeri seçin.")
                    elif not selected_teachers_dist:
                        st.error("Lütfen en az bir öğretmen seçin.")
                    else:
                        days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                        if include_weekend_place:
                            days.extend(["Cumartesi", "Pazar"])
                        usage = {d: {p: 0 for p in selected_places_dist} for d in days}
                        
                        # Öğretmen Ders Yüklerini Hesapla (Sıralama için)
                        t_loads = {}
                        for c_name, courses in st.session_state.class_lessons.items():
                            for crs_name, hours in courses.items():
                                t_name = st.session_state.assignments.get(c_name, {}).get(crs_name)
                                if t_name:
                                    t_loads[t_name] = t_loads.get(t_name, 0) + int(hours)

                        # Rotasyon için mevcut yerleri sakla
                        previous_places = {}
                        if use_rotation:
                            for t in st.session_state.teachers:
                                if t['name'] in selected_teachers_dist:
                                    previous_places[t['name']] = t.get('duty_place')
                        
                        # Dağıtıma dahil OLMAYAN öğretmenlerin mevcut yerlerini say (Dengeyi korumak için)
                        for t in st.session_state.teachers:
                            if t['name'] not in selected_teachers_dist:
                                d_raw = t.get('duty_day')
                                d_list = d_raw if isinstance(d_raw, list) else ([d_raw] if d_raw in days else [])
                                p = t.get('duty_place')
                                if p in selected_places_dist:
                                    for d in d_list:
                                        if d in days: usage[d][p] += 1
                        
                        # Seçilen öğretmenleri karıştır ve dağıt
                        # Adil dağıtım için: Ders yükü FAZLA olan öğretmenlere öncelik ver (Böylece boş olan KOLAY yerleri onlar kapsın)
                        teachers_to_process = [t for t in st.session_state.teachers if t['name'] in selected_teachers_dist]
                        teachers_to_process.sort(key=lambda x: t_loads.get(x['name'], 0), reverse=True)
                        
                        for t in teachers_to_process:
                            d_raw = t.get('duty_day')
                            d_list = d_raw if isinstance(d_raw, list) else ([d_raw] if d_raw in days else [])
                            if not d_list: continue
                            
                            # En az yoğun olan yeri bul (Greedy)
                            best_place = None
                            min_score = float('inf')
                            candidates = list(selected_places_dist)
                            random.shuffle(candidates) # Eşitlik durumunda rastgelelik
                            
                            for p in candidates:
                                # Cinsiyet Kontrolü
                                constraint = st.session_state.duty_place_constraints.get(p, "Herkes")
                                t_gender = t.get('gender', 'Erkek')
                                if constraint != "Herkes" and t_gender != constraint:
                                    continue
                                
                                # Branş Kontrolü
                                allowed_branches = st.session_state.duty_place_branch_constraints.get(p, [])
                                t_branch = t.get('branch')
                                if allowed_branches and len(allowed_branches) > 0:
                                    if t_branch not in allowed_branches:
                                        continue

                                current_usage = sum(usage[d][p] for d in d_list if d in days)
                                difficulty = st.session_state.duty_place_scores.get(p, 1)
                                
                                # Puanlama: Öncelik doluluk dengesi (usage * 1000), ikincil öncelik zorluk (difficulty)
                                score = (current_usage * 1000) + difficulty
                                
                                # Rotasyon cezası (Eğer eski yer ise puanı artır ki seçilmesin)
                                if use_rotation and previous_places.get(t['name']) == p:
                                    score += 1000
                                
                                # İstemediği Yer Cezası
                                unwanted = t.get('unwanted_duty_places', [])
                                if unwanted and p in unwanted:
                                    score += 2000
                                    
                                if score < min_score:
                                    min_score = score
                                    best_place = p
                            
                            if best_place:
                                t['duty_place'] = best_place
                                for d in d_list:
                                    if d in days: usage[d][best_place] += 1
                        
                        save_data()
                        st.success("Nöbet yerleri başarıyla dağıtıldı.")
                        time.sleep(1)
                        st.rerun()

            if duty_teachers:
                # Tablo verisini hazırla (Ders yükü ile birlikte)
                table_data = []
                for t in duty_teachers:
                    d_raw = t.get('duty_day')
                    if isinstance(d_raw, str): d_list = [d_raw]
                    else: d_list = d_raw if d_raw else []
                    
                    t_name = t.get('name')
                    
                    for d in d_list:
                        load = teacher_daily_loads_table.get(d, {}).get(t_name, 0)
                        table_data.append({
                            "name": t_name,
                            "duty_day": d,
                            "daily_load": load,
                            "duty_place": t.get('duty_place')
                        })
                
                df_duty_places = pd.DataFrame(table_data)
                
                edited_places = st.data_editor(
                    df_duty_places,
                    column_config={
                        "name": st.column_config.TextColumn("Öğretmen", disabled=True),
                        "duty_day": st.column_config.TextColumn("Gün", disabled=True),
                        "daily_load": st.column_config.NumberColumn("Ders Yükü", disabled=True, help="Öğretmenin nöbet günündeki toplam ders saati"),
                        "duty_place": st.column_config.SelectboxColumn("Nöbet Yeri", options=st.session_state.duty_places, required=False)
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="editor_duty_places"
                )
                
                if st.button("Nöbet Yerlerini Kaydet"):
                    place_map = {row['name']: row['duty_place'] for _, row in edited_places.iterrows()}
                    for t in st.session_state.teachers:
                        if t['name'] in place_map:
                            t['duty_place'] = place_map[t['name']]
                    save_data()
                    st.success("Nöbet yerleri kaydedildi.")

    with tab_rep:
        st.subheader("Nöbet Yeri Dağılımı")
        
        # Öğretmen verilerini al
        duty_data = []
        for t in st.session_state.teachers:
            if t.get('duty_place'):
                d_raw = t.get('duty_day')
                if isinstance(d_raw, str): d_list = [d_raw]
                else: d_list = d_raw if d_raw else []
                
                for d in d_list:
                    duty_data.append({
                        "Öğretmen": t.get('name'),
                        "Nöbet Yeri": t.get('duty_place'),
                        "Nöbet Günü": d
                    })
        
        if duty_data:
            df_duty = pd.DataFrame(duty_data)
            
            # 1. Grafik: Nöbet Yerine Göre Öğretmen Sayısı
            place_counts = df_duty["Nöbet Yeri"].value_counts().reset_index()
            place_counts.columns = ["Nöbet Yeri", "Öğretmen Sayısı"]
            
            duty_chart = alt.Chart(place_counts).mark_bar(color="#9C27B0").encode(
                x=alt.X('Öğretmen Sayısı', title='Öğretmen Sayısı', axis=alt.Axis(tickMinStep=1)),
                y=alt.Y('Nöbet Yeri', sort='-x', title='Nöbet Yeri'),
                tooltip=['Nöbet Yeri', 'Öğretmen Sayısı']
            ).properties(
                title="Nöbet Yerlerine Göre Dağılım"
            ).configure_axis(
                labelFontSize=12,
                titleFontSize=14,
                titleFontWeight='bold'
            ).configure_title(
                fontSize=20,
                color='blue'
            )
            st.altair_chart(duty_chart, use_container_width=True)
            
            # 2. Tablo: Detaylı Liste
            st.write("###### Nöbet Yeri Listesi")
            
            def color_duty_place(val):
                h = hashlib.md5(str(val).encode()).hexdigest()
                r, g, b = int(h[:2], 16) % 50 + 200, int(h[2:4], 16) % 50 + 200, int(h[4:6], 16) % 50 + 200
                return f'background-color: rgb({r},{g},{b}); color: black'

            st.dataframe(df_duty.sort_values(by=["Nöbet Yeri", "Nöbet Günü"]).style.map(color_duty_place, subset=["Nöbet Yeri"]), use_container_width=True, hide_index=True)
            
            # PDF İndirme Butonu
            if FPDF:
                st.write("###### Rapor Seçenekleri")
                include_weekend_rep = st.checkbox("Hafta Sonu Dahil Et", value=False, key="inc_weekend_rep")
                
                # Müdür Yardımcıları Girişi
                st.write("###### Nöbetçi Müdür Yardımcıları")
                days_list = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
                if include_weekend_rep:
                    days_list.extend(["Cumartesi", "Pazar"])
                
                cols_vp = st.columns(len(days_list))
                
                # Müdür Yardımcılarını Filtrele
                vp_list = [t['name'] for t in st.session_state.teachers if t.get('title') == "Müdür Yardımcısı"]
                vp_options = [""] + sorted(vp_list)
                
                # Session state'den al ve güncelle
                for i, d in enumerate(days_list):
                    current_val = st.session_state.vice_principals.get(d, "")
                    # Eğer kayıtlı değer listede yoksa (örn: silinmişse veya unvanı değişmişse) boş seç
                    if current_val not in vp_options:
                        current_val = ""
                    st.session_state.vice_principals[d] = cols_vp[i].selectbox(d, options=vp_options, index=vp_options.index(current_val), key=f"vp_input_{d}")

                if st.button("Müdür Yardımcılarını Kaydet", key="save_vps"):
                    save_data()
                    st.success("Müdür yardımcıları kaydedildi.")

                col_rep1, col_rep2, col_rep3 = st.columns(3)
                use_dates = col_rep1.checkbox("Tarihli Çizelge Oluştur", value=False)
                rotate_opt = col_rep1.checkbox("Her Hafta Yer Değiştir (Rotasyon)", value=False)
                start_date = None
                num_weeks = 1
                if use_dates:
                    # Varsayılan olarak bugünün haftasının Pazartesi'sini bul
                    today = datetime.today()
                    monday = today - timedelta(days=today.weekday())
                    start_date = col_rep2.date_input("Başlangıç Tarihi (Pazartesi)", monday)
                    
                    # Pazartesi kontrolü ve düzeltme
                    if start_date.weekday() != 0:
                        st.warning(f"Seçilen {start_date.strftime('%d.%m.%Y')} tarihi Pazartesi değil. Çizelge o haftanın Pazartesi gününden başlatılacak.")
                        start_date = start_date - timedelta(days=start_date.weekday())
                        
                    num_weeks = col_rep3.number_input("Hafta Sayısı (Örn: 4 hafta = 1 Ay)", min_value=1, max_value=10, value=4)
                
                pdf_duty = create_duty_pdf(start_date=start_date if use_dates else None, num_weeks=num_weeks, vice_principals=st.session_state.vice_principals, include_weekend=include_weekend_rep, rotate_weekly=rotate_opt)
                st.download_button("📄 Nöbet Çizelgesini PDF İndir", data=pdf_duty, file_name="nobet_cizelgesi.pdf", mime="application/pdf")
        else:
            st.info("Henüz nöbet yeri tanımlanmış öğretmen bulunmamaktadır.")

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
                        "Unvan": t.get('title', 'Öğretmen'),
                        "Nöbet Günü": ", ".join(t.get('duty_day')) if isinstance(t.get('duty_day'), list) else t.get('duty_day'),
                        "Nöbet Yeri": t.get('duty_place'),
                        "Tercih": t.get('preference'),
                        "Cinsiyet": t.get('gender'),
                        "İstemediği Yerler": ", ".join(t.get('unwanted_duty_places', [])) if isinstance(t.get('unwanted_duty_places'), list) else "",
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
        
        st.divider()
        st.write("Veritabanı Yedeği")
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                st.download_button(
                    label="📥 Veritabanını İndir (.db)",
                    data=f,
                    file_name="okul_verileri.db",
                    mime="application/x-sqlite3"
                )
        else:
            st.warning("Henüz oluşturulmuş bir veritabanı dosyası yok.")

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
                                "title": str(row["Unvan"]).strip() if pd.notna(row.get("Unvan")) else "Öğretmen",
                                "unavailable_days": [],
                                "unavailable_slots": [],
                                "max_hours_per_day": int(row["Günlük Max Ders"]) if pd.notna(row.get("Günlük Max Ders")) else 8,
                                "duty_day": str(row["Nöbet Günü"]).split(", ") if pd.notna(row.get("Nöbet Günü")) and "," in str(row["Nöbet Günü"]) else (str(row["Nöbet Günü"]) if pd.notna(row.get("Nöbet Günü")) else []),
                                "duty_place": str(row["Nöbet Yeri"]).strip() if pd.notna(row.get("Nöbet Yeri")) else "",
                                "preference": str(row["Tercih"]) if pd.notna(row.get("Tercih")) else "Farketmez",
                                "gender": str(row["Cinsiyet"]).strip() if pd.notna(row.get("Cinsiyet")) else "Erkek",
                                "unwanted_duty_places": str(row["İstemediği Yerler"]).split(", ") if pd.notna(row.get("İstemediği Yerler")) and "," in str(row["İstemediği Yerler"]) else ([str(row["İstemediği Yerler"]).strip()] if pd.notna(row.get("İstemediği Yerler")) and str(row["İstemediği Yerler"]).strip() else []),
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

        st.divider()
        st.subheader("Veritabanı Yedeği Yükle (.db)")
        st.info("Daha önce indirdiğiniz .db uzantılı veritabanı dosyasını buradan yükleyerek sistemi geri alabilirsiniz.")
        uploaded_db = st.file_uploader("Veritabanı Dosyası Seç", type=["db", "sqlite"], key="db_uploader")
        
        if uploaded_db:
            if st.button("Veritabanını Geri Yükle", type="primary"):
                try:
                    # Dosyayı kaydet
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    
                    # Session state'i temizle ki yeni veriler yüklensin (Login hariç)
                    for key in list(st.session_state.keys()):
                        if key != 'logged_in':
                            del st.session_state[key]
                            
                    st.success("Veritabanı başarıyla geri yüklendi! Uygulama yeniden başlatılıyor...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Veritabanı yüklenirken hata oluştu: {e}")

        st.divider()
        st.subheader("🔄 JSON Yedeği ile Kurtarma")
        st.info("Bilgisayarınızdaki bir JSON yedeğini yükleyebilir veya sunucuda varsa mevcut yedeği kullanabilirsiniz.")
        
        # 1. Bilgisayardan Yükleme Seçeneği
        uploaded_json = st.file_uploader("Bilgisayardan JSON Dosyası Yükle", type=["json"], key="json_restore_upload")
        if uploaded_json:
            if st.button("Yüklenen JSON'ı İçeri Aktar", type="primary", key="btn_apply_json_upload"):
                try:
                    data = json.load(uploaded_json)
                    # Veritabanına yaz
                    init_db()
                    with sqlite3.connect(DB_FILE) as conn:
                        c = conn.cursor()
                        
                        # Okul ID varsa prefix ekle
                        school_id = st.session_state.get('school_id')
                        prefix = f"school_{school_id}_" if school_id else ""

                        for k, v in data.items():
                            db_key = f"{prefix}{k}"
                            c.execute('INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)', (db_key, json.dumps(v, ensure_ascii=False)))
                    
                    # Session state'i temizle ki yeni veriler yüklensin
                    for key in list(st.session_state.keys()):
                        if key not in ['logged_in', 'role', 'school_id', 'school_name']:
                            del st.session_state[key]

                    st.success("Veriler başarıyla yüklendi! Uygulama yeniden başlatılıyor...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Dosya okuma hatası: {e}")

        st.markdown("---")
        st.write("Sunucudaki Dosyayı Kullan:")
        if st.button("Sunucudaki Dosyadan (okul_verileri.json) Geri Yükle", key="btn_restore_json"):
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Veritabanına yaz
                    init_db()
                    with sqlite3.connect(DB_FILE) as conn:
                        c = conn.cursor()
                        
                        # Okul ID varsa prefix ekle
                        school_id = st.session_state.get('school_id')
                        prefix = f"school_{school_id}_" if school_id else ""

                        for k, v in data.items():
                            db_key = f"{prefix}{k}"
                            c.execute('INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)', (db_key, json.dumps(v, ensure_ascii=False)))
                    
                    # Session state'i temizle ki yeni veriler yüklensin
                    for key in list(st.session_state.keys()):
                        if key not in ['logged_in', 'role', 'school_id', 'school_name']:
                            del st.session_state[key]

                    st.success("Veriler JSON dosyasından veritabanına başarıyla aktarıldı! Uygulama yeniden başlatılıyor...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Kurtarma hatası: {e}")
            else:
                st.error("Sunucuda JSON yedek dosyası (okul_verileri.json) bulunamadı.")

        st.divider()
        st.subheader("⚠️ Veritabanını Sıfırla")
        st.warning("Bu işlem veritabanındaki TÜM verileri (Öğretmenler, Dersler, Program vb.) kalıcı olarak silecektir!")
        
        if st.button("Tüm Verileri Sil ve Sıfırla", type="primary", key="btn_reset_db"):
            try:
                # Veritabanı ve JSON dosyalarını sil
                if os.path.exists(DB_FILE): os.remove(DB_FILE)
                if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
                
                # Session state'i temizle
                for key in list(st.session_state.keys()):
                    if key != 'logged_in':
                        del st.session_state[key]
                
                st.success("Veritabanı sıfırlandı. Uygulama yeniden başlatılıyor...")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Sıfırlama hatası: {e}")

    st.divider()
    st.subheader("🔍 Veritabanında Öğretmen Ara (SQLite)")
    st.info("SQLite veritabanı üzerinden isme göre hızlı arama yapabilirsiniz.")
    
    t_search = st.text_input("Aranacak Öğretmen Adı", placeholder="Örn: Ahmet")
    if t_search:
        results = search_teacher_by_name(t_search)
        if results:
            st.success(f"{len(results)} kayıt bulundu.")
            res_df = pd.DataFrame(results)
            
            # Sütunları düzenle ve Türkçeleştir
            cols = ["name", "branch", "email", "phone", "duty_day"]
            valid_cols = [c for c in cols if c in res_df.columns]
            display_df = res_df[valid_cols].rename(columns={"name": "Adı Soyadı", "branch": "Branş", "email": "E-Posta", "phone": "Telefon", "duty_day": "Nöbet Günü"})
            
            st.dataframe(display_df, hide_index=True, use_container_width=True)
        else:
            st.warning("Eşleşen kayıt bulunamadı.")
