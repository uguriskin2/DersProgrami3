from ortools.sat.python import cp_model

def create_timetable(teachers, courses, classes, class_lessons, assignments, rooms, room_capacities=None, room_branches=None, room_teachers=None, room_courses=None, room_excluded_courses=None, mode="class", lunch_break_hour=None, num_hours=8, simultaneous_lessons=None, duty_day_reduction=2):
    """
    mode: "class" (Sınıf bazlı dağıtım) veya "room" (Derslik bazlı dağıtım)
    """
    model = cp_model.CpModel()
    
    def safe_int(val, default):
        try:
            if val is None: return default
            if isinstance(val, float) and val != val: return default
            return int(val)
        except:
            return default

    # Veri Temizliği: Oda-Öğretmen eşleşmelerindeki isimleri temizle
    if room_teachers:
        room_teachers = {r: [str(t).strip() for t in ts] for r, ts in room_teachers.items()}

    # --- Değişkenler ---
    # lessons[(sınıf, ders, öğretmen, derslik, gün, saat)] = 1/0
    lessons = {}
    days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
    hours = range(1, num_hours + 1) # Günde num_hours kadar saat

    # Veri hazırlığı
    # assignments: {'9-A': {'Matematik': 'Ahmet Hoca', ...}}
    
    # Tüm olası kombinasyonlar için değişken oluştur
    
    # --- Yardımcı: Ders Özelliklerini Çözümle (Etiketli dersler için) ---
    course_def_map = {c['name']: c for c in courses}
    
    def get_base_name(crs_name):
        if crs_name in course_def_map:
            return crs_name
        if " (" in crs_name and crs_name.endswith(")"):
            base = crs_name.rsplit(" (", 1)[0]
            if base in course_def_map:
                return base
        return crs_name

    def get_course_prop(crs_name, prop, default=None):
        base = get_base_name(crs_name)
        if base in course_def_map:
            return course_def_map[base].get(prop, default)
        return default

    # --- Yardımcı Fonksiyon: Uygun Odaları Bul ---
    def get_allowed_rooms(crs_name, t_name):
        base_crs_name = get_base_name(crs_name)
        
        # 1. Zorunlu Oda Kontrolü
        forced_room = get_course_prop(crs_name, 'specific_room')
        if forced_room and forced_room in rooms:
            return [forced_room]
        
        # 2. Aday Odaları Filtrele
        candidates = rooms if rooms else ["Varsayilan_Derslik"]
        
        # Yasaklı Ders Kontrolü: Eğer ders bu oda için yasaklıysa adaylardan çıkar
        if room_excluded_courses:
            candidates = [r for r in candidates if crs_name not in room_excluded_courses.get(r, []) and base_crs_name not in room_excluded_courses.get(r, [])]
            
        allowed = []
        crs_branch = get_course_prop(crs_name, 'branch')
        
        # Pass 1: Strict Check (Branch + Teacher)
        for r in candidates:
            # 1. Ders Kısıtlaması (Varsa kesin uyulmalı)
            r_courses = room_courses.get(r, []) if room_courses else []
            is_course_explicit = False
            if r_courses:
                if crs_name not in r_courses and base_crs_name not in r_courses:
                    continue # Bu oda bu ders için yasak (Listede yok)
                is_course_explicit = True # Ders açıkça bu odaya tanımlanmış

            # Öğretmen Kısıtlaması
            r_teachers = room_teachers.get(r, []) if room_teachers else []
            if r_teachers and t_name not in r_teachers:
                continue
            
            # Branş Kısıtlaması
            r_branches = room_branches.get(r, []) if room_branches else []
            # Veri temizliği (Boşluk hatalarını önlemek için)
            r_branches = [str(b).strip() for b in r_branches]
            clean_crs_branch = str(crs_branch).strip() if crs_branch else ""
            
            # Eğer oda öğretmene özelse VEYA ders açıkça izin verilmişse, branş kısıtlamasını es geç
            is_teacher_room = t_name in r_teachers
            
            if r_branches and clean_crs_branch not in r_branches:
                if not is_teacher_room and not is_course_explicit:
                    continue
            
            allowed.append(r)
            
        # Pass 2: Fallback (Branch Only) - Eğer hiç oda bulunamazsa öğretmen kısıtlamasını esnet
        if not allowed:
            for r in candidates:
                # Ders Kısıtlaması (Burada da geçerli olmalı)
                r_courses = room_courses.get(r, []) if room_courses else []
                is_course_explicit = False
                if r_courses:
                    if crs_name not in r_courses and base_crs_name not in r_courses:
                        continue
                    is_course_explicit = True

                r_branches = room_branches.get(r, []) if room_branches else []
                r_branches = [str(b).strip() for b in r_branches] # Temizlik
                
                if r_branches and clean_crs_branch not in r_branches:
                    if not is_course_explicit: # Ders izinliyse branşa takılma
                        continue
                allowed.append(r)
        
        # Pass 3: Ultimate Fallback (Any Room) - Branş da uymuyorsa herhangi bir odayı aç
        # Bu sayede dersin açıkta kalması engellenir.
        if not allowed and mode == "class":
            # Sadece kısıtlaması olmayan (Genel) veya dersin izinli olduğu odaları aç
            for r in candidates:
                r_courses = room_courses.get(r, []) if room_courses else []
                if r_courses and (crs_name not in r_courses and base_crs_name not in r_courses):
                    continue # Özel odaları koru
                allowed.append(r)
                
        return allowed

    for c_name in classes:
        if c_name not in class_lessons: continue
        
        for crs_name, count in class_lessons[c_name].items():
            if count <= 0: continue
            
            # Bu dersin öğretmeni kim?
            t_name = assignments.get(c_name, {}).get(crs_name)
            if not t_name: continue # Öğretmen atanmamışsa atla
            t_name = str(t_name).strip() # İsim temizliği (Boşlukları sil)
            
            available_rooms = get_allowed_rooms(crs_name, t_name)

            for r_name in available_rooms:
                for d in days:
                    for h in hours:
                        lessons[(c_name, crs_name, t_name, r_name, d, h)] = model.NewBoolVar(
                            f"lesson_{c_name}_{crs_name}_{t_name}_{r_name}_{d}_{h}"
                        )

    # --- Kısıtlamalar ---

    # 1. Her ders, haftada belirtilen saat kadar yapılmalı
    # Önce haftalık toplam kapasiteyi hesapla (Öğle arası varsa düş)
    weekly_slots = num_hours * 5
    if lunch_break_hour:
        weekly_slots -= 5

    for c_name in classes:
        if c_name not in class_lessons: continue
        
        # Sınıfın toplam yükünü hesapla
        total_class_load = sum(class_lessons[c_name].values())
        
        for crs_name, count in class_lessons[c_name].items():
            t_name = assignments.get(c_name, {}).get(crs_name)
            if not t_name: continue
            
            available_rooms = get_allowed_rooms(crs_name, t_name)
            # Eğer sınıfın yükü kapasiteyi aşıyorsa, tam eşitlik yerine <= kısıtlaması koy (Çözüm bulabilmek için)
            # Bu sayede "Çözüm Bulunamadı" yerine eksik dersli bir program çıkar.
            lesson_vars = [
                lessons[(c_name, crs_name, t_name, r_name, d, h)] 
                for r_name in available_rooms
                for d in days 
                for h in hours
                if (c_name, crs_name, t_name, r_name, d, h) in lessons
            ]
            
            # Eğer uygun oda yoksa veya değişken oluşturulamadıysa kısıtlamayı atla (Hata vermemesi için)
            if not lesson_vars: continue
            
            if total_class_load > weekly_slots:
                # Kapasite aşımı varsa zorlama, yapabildiğin kadar yap
                model.Add(sum(lesson_vars) <= count)
            else:
                # Kapasite yetiyorsa tam sayıya zorla
                model.Add(sum(lesson_vars) == count)

    # 2. Bir sınıf aynı anda sadece 1 derste olabilir
    for c_name in classes:
        # Eş zamanlı derslerde (Sınıf bölme), ikinci dersi çakışma kontrolünden hariç tut
        # Çünkü birinci dersle aynı anda yapılmasına izin veriyoruz.
        skip_courses = set()
        if simultaneous_lessons and c_name in simultaneous_lessons:
            for pair in simultaneous_lessons[c_name]:
                if len(pair) >= 2:
                    skip_courses.add(pair[1]) # Çiftin ikinci elemanını atla
        
        for d in days:
            for h in hours:
                current_vars = []
                if c_name in class_lessons:
                    for crs_name in class_lessons[c_name]:
                        if crs_name in skip_courses: continue
                        
                        t_name = assignments.get(c_name, {}).get(crs_name)
                        if t_name:
                            available_rooms = get_allowed_rooms(crs_name, t_name)
                                    
                            for r_name in available_rooms:
                                key = (c_name, crs_name, t_name, r_name, d, h)
                                if key in lessons:
                                    current_vars.append(lessons[key])
                if current_vars:
                    model.Add(sum(current_vars) <= 1)

    # 3. Bir öğretmen aynı anda sadece 1 derste olabilir
    all_teachers = set(k[2] for k in lessons.keys())
    
    for t_name in all_teachers:
        for d in days:
            for h in hours:
                teacher_vars = []
                for key, var in lessons.items():
                    # key = (c_name, crs_name, t_assigned, r_name, d_key, h_key)
                    if key[2] == t_name and key[4] == d and key[5] == h:
                        teacher_vars.append(var)
                
                if teacher_vars:
                    model.Add(sum(teacher_vars) <= 1)

    # 4. DERSLİK KISITLAMASI: Bir derslikte aynı anda sadece 1 ders olabilir
    if mode == "room" and rooms:
        if room_capacities is None: room_capacities = {}
        for r_name in rooms:
            capacity = safe_int(room_capacities.get(r_name), 1)
            for d in days:
                for h in hours:
                    room_vars = []
                    for key, var in lessons.items():
                        if key[3] == r_name and key[4] == d and key[5] == h:
                            room_vars.append(var)
                    if room_vars:
                        model.Add(sum(room_vars) <= capacity)

    # 5. ÖĞRETMEN MÜSAİTLİK (İZİN GÜNÜ) KISITLAMASI
    # teachers listesinden izin günlerini alıyoruz
    teacher_unavailable = {str(t['name']).strip(): t.get('unavailable_days') or [] for t in teachers if t.get('name')}
    
    for t_name, bad_days in teacher_unavailable.items():
        for d in bad_days:
            # Bu öğretmenin yasaklı günündeki tüm ders olasılıklarını bul
            variables = []
            for key, var in lessons.items():
                # key: (c_name, crs_name, t_assigned, r_name, d_key, h_key)
                if key[2] == t_name and key[4] == d:
                    variables.append(var)
            
            if variables:
                model.Add(sum(variables) == 0)

    # 11. ÖĞRETMEN SAAT KISITLAMASI (Belirli saatlerde müsait değil)
    # Format: "Gün:Saat" (Örn: "Pazartesi:1")
    teacher_unavailable_slots = {str(t['name']).strip(): t.get('unavailable_slots') or [] for t in teachers if t.get('name')}
    for t_name, bad_slots in teacher_unavailable_slots.items():
        for slot in bad_slots:
            try:
                if ":" not in slot: continue
                d_str, h_str = slot.split(":", 1)
                d_str = d_str.strip()
                h_val = int(h_str.strip())
                
                for key, var in lessons.items():
                    # key: (c_name, crs_name, t_name, r_name, d, h)
                    if key[2] == t_name and key[4] == d_str and key[5] == h_val:
                        model.Add(var == 0)
            except ValueError:
                continue

    # 6. ÖĞRETMEN GÜNLÜK MAKSİMUM DERS SAATİ KISITLAMASI
    teacher_max_hours = {str(t['name']).strip(): safe_int(t.get('max_hours_per_day'), 8) for t in teachers if t.get('name')}
    
    for t_name, limit in teacher_max_hours.items():
        for d in days:
            # Bu öğretmenin o günkü tüm dersleri
            daily_vars = []
            for key, var in lessons.items():
                # key: (c_name, crs_name, t_assigned, r_name, d_key, h_key)
                if key[2] == t_name and key[4] == d:
                    daily_vars.append(var)
            
            if daily_vars:
                model.Add(sum(daily_vars) <= limit)

    # 7. BLOK DERS KISITLAMASI (Aynı gün içindeki dersler birbirini takip etmeli)
    for c_name in classes:
        if c_name not in class_lessons: continue
        for crs_name in class_lessons[c_name]:
            t_name = assignments.get(c_name, {}).get(crs_name)
            if not t_name: continue
            
            available_rooms = get_allowed_rooms(crs_name, t_name)
            
            for d in days:
                # active_vars[h]: O saatte bu ders var mı? (Bool)
                active_vars = {}
                for h in hours:
                    # İlgili dersin tüm derslik alternatiflerini topla
                    current_vars = []
                    for r_name in available_rooms:
                        key = (c_name, crs_name, t_name, r_name, d, h)
                        if key in lessons:
                            current_vars.append(lessons[key])
                    
                    if current_vars:
                        active_vars[h] = model.NewBoolVar(f"active_{c_name}_{crs_name}_{d}_{h}")
                        model.Add(sum(current_vars) == active_vars[h])
                    else:
                        active_vars[h] = 0
                
                # Blok başlangıçlarını say (0'dan 1'e geçiş sayısı <= 1 olmalı)
                start_vars = []
                for h in hours:
                    is_start = model.NewBoolVar(f"start_{c_name}_{crs_name}_{d}_{h}")
                    start_vars.append(is_start)
                    prev = active_vars[h-1] if h > 1 else 0
                    model.Add(is_start >= active_vars[h] - prev)
                
                model.Add(sum(start_vars) <= 1)

    # 8. DERS GÜNLÜK MAKSİMUM SAAT KISITLAMASI
    for c_name in classes:
        if c_name not in class_lessons: continue
        for crs_name in class_lessons[c_name]:
            limit = safe_int(get_course_prop(crs_name, 'max_daily_hours', 2), 2)
            # Çakışma Önleyici: Eğer blok süresi günlük limitten büyükse, limiti blok süresine eşitle
            blk_size = safe_int(get_course_prop(crs_name, 'block_size', 1), 1)
            limit = max(limit, blk_size)
            
            t_name = assignments.get(c_name, {}).get(crs_name)
            if not t_name: continue

            available_rooms = get_allowed_rooms(crs_name, t_name)

            for d in days:
                daily_vars = []
                for h in hours:
                    for r_name in available_rooms:
                        key = (c_name, crs_name, t_name, r_name, d, h)
                        if key in lessons:
                            daily_vars.append(lessons[key])
                
                if daily_vars:
                    model.Add(sum(daily_vars) <= limit)

    # 9. ÖĞLE ARASI KISITLAMASI
    if lunch_break_hour:
        # Tüm dersler için belirtilen saatte ders yapılmasını engelle
        for key, var in lessons.items():
            # key: (c_name, crs_name, t_name, r_name, d, h)
            if key[5] == lunch_break_hour:
                model.Add(var == 0)

    # 12. DERS BLOK (SABİT SÜRE) KISITLAMASI
    for c_name in classes:
        if c_name not in class_lessons: continue
        for crs_name, count in class_lessons[c_name].items():
            blk = safe_int(get_course_prop(crs_name, 'block_size', 1), 1)
            if blk <= 1: continue
            
            t_name = assignments.get(c_name, {}).get(crs_name)
            if not t_name: continue
            
            available_rooms = get_allowed_rooms(crs_name, t_name)
            # İzin verilen günlük ders sürelerini hesapla
            # Örn: Haftalık 5 saat, Blok 2 ise -> Günlük 0, 2 veya 1 (kalan) olabilir.
            # DÜZELTME: Günlük limit izin veriyorsa blok katlarına (2, 4, 6...) izin ver.
            count = int(count)
            limit = safe_int(get_course_prop(crs_name, 'max_daily_hours', 2), 2)
            limit = max(limit, blk) # Limit en az blok kadar olmalı
            
            allowed = {0}
            current_blk = blk
            while current_blk <= limit and current_blk <= count:
                allowed.add(current_blk)
                current_blk += blk
            
            remainder = count % blk
            if remainder > 0:
                allowed.add(remainder)
            
            allowed_durations = sorted(list(allowed))

            for d in days:
                daily_vars = []
                for h in hours:
                    for r_name in available_rooms:
                        key = (c_name, crs_name, t_name, r_name, d, h)
                        if key in lessons:
                            daily_vars.append(lessons[key])
                
                if daily_vars:
                    # Günlük toplam ders saati değişkeni
                    daily_sum = model.NewIntVar(0, num_hours, f"daily_sum_{c_name}_{crs_name}_{d}")
                    model.Add(daily_sum == sum(daily_vars))
                    
                    # Günlük toplam sadece izin verilen değerlerden biri olabilir (0, Blok, Kalan)
                    domain = cp_model.Domain.FromValues(allowed_durations)
                    model.AddLinearExpressionInDomain(daily_sum, domain)

    # 13. ÖĞRETMEN NÖBET GÜNÜ YÜKÜNÜ HAFİFLETME
    # Nöbetçi olduğu gün, günlük maksimum ders saatinden 2 saat daha az ders verilsin.
    for t in teachers:
        if not t.get('name'): continue
        t_name = str(t['name']).strip()
        d_day = t.get('duty_day')
        
        if not d_day or d_day in [None, "Yok", ""]: continue
        
        duty_vars = []
        for key, var in lessons.items():
            if key[2] == t_name and key[4] == d_day:
                duty_vars.append(var)
        
        if duty_vars:
            limit = teacher_max_hours.get(t_name, 8)
            # Nöbet gününde belirtilen miktar kadar daha az ders ver (Min 0)
            reduced_limit = max(0, limit - duty_day_reduction)
            model.Add(sum(duty_vars) <= reduced_limit)

    # 14. ÖĞRETMEN SABAH/ÖĞLE TERCİHİ (SABAHÇI / ÖĞLENCİ)
    for t in teachers:
        pref = t.get('preference')
        if not pref or pref == "Farketmez": continue
        
        if not t.get('name'): continue
        t_name = str(t['name']).strip()
        
        # Sabah/Öğle ayrımı (Öğle arası saatine göre veya ortadan bölerek)
        if lunch_break_hour:
            morning_slots = range(1, lunch_break_hour)
            afternoon_slots = range(lunch_break_hour + 1, num_hours + 1)
        else:
            mid = num_hours // 2
            morning_slots = range(1, mid + 1)
            afternoon_slots = range(mid + 1, num_hours + 1)
            
        forbidden_slots = []
        if pref == "Sabahçı":
            forbidden_slots = afternoon_slots
        elif pref == "Öğlenci":
            forbidden_slots = morning_slots
            
        for d in days:
            for h in forbidden_slots:
                for key, var in lessons.items():
                    # key: (c_name, crs_name, t_name, r_name, d, h)
                    if key[2] == t_name and key[4] == d and key[5] == h:
                        model.Add(var == 0)

    # 15. EŞ ZAMANLI DERSLER (Sınıf Bölme)
    # Tanımlanan ders çiftlerinin aynı saatte yapılmasını zorunlu kıl
    if simultaneous_lessons:
        for c_name, pairs in simultaneous_lessons.items():
            if c_name not in class_lessons: continue
            
            for pair in pairs:
                if len(pair) < 2: continue
                c1, c2 = pair[0], pair[1]
                
                # Bu derslerin atanmış olması lazım
                if c1 not in class_lessons[c_name] or c2 not in class_lessons[c_name]: continue
                
                # Sync Constraint: Her saat dilimi için c1 varsa c2 de olmalı
                for d in days:
                    for h in hours:
                        # c1 değişkenleri
                        vars_c1 = []
                        t1 = assignments.get(c_name, {}).get(c1)
                        if t1:
                            rooms1 = get_allowed_rooms(c1, t1)
                            for r in rooms1:
                                key = (c_name, c1, t1, r, d, h)
                                if key in lessons: vars_c1.append(lessons[key])
                        
                        # c2 değişkenleri
                        vars_c2 = []
                        t2 = assignments.get(c_name, {}).get(c2)
                        if t2:
                            rooms2 = get_allowed_rooms(c2, t2)
                            for r in rooms2:
                                key = (c_name, c2, t2, r, d, h)
                                if key in lessons: vars_c2.append(lessons[key])
                        
                        if vars_c1 and vars_c2:
                            model.Add(sum(vars_c1) == sum(vars_c2))

    # --- Amaç Fonksiyonu ---
    # Gevşetilmiş kısıtlamalar (<=) kullanıldığında boş program dönmemesi için atamayı maksimize et
    model.Maximize(sum(lessons.values()))

    # --- Çözüm ---
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule = []
        for key, var in lessons.items():
            if solver.Value(var):
                schedule.append({
                    "Sınıf": key[0],
                    "Ders": key[1],
                    "Öğretmen": key[2],
                    "Derslik": key[3],
                    "Gün": key[4],
                    "Saat": key[5]
                })
        return schedule, "Çözüm Bulundu!"
    else:
        return [], "Çözüm Bulunamadı. Kısıtlamaları gevşetin."
