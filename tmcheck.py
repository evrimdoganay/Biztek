#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------------
# Transformer Substation Check - Python Edition v2.7
# (Bash v58 based - DEVICE & REGION VALIDATION + KYLAND VERSION & VLAN CHECK)
#
# ÖZELLİKLER:
# - Bash scripti ile birebir aynı argüman yapısı.
# - Standart kütüphaneler (Harici pip install gerekmez).
# - Bölge ve Cihaz validasyonu.
# - Renkli konsol çıktısı ve CSV raporlama.
# - Tekil TM sorgusunda Kyland versiyon kontrolü.
# - -v parametresi ile toplu Kyland detay taraması (Satır içi).
# - İsim aramalarında 'Tam Eşleşme' mantığı.
# - GÜNCELLEME v2.0: Parametresiz çalıştırma Help menüsünü açar.
# - GÜNCELLEME v2.1: .txt dosya modu eklendi (Toplu özel liste taraması).
# - GÜNCELLEME v2.2: Çoklu isim eşleşmelerinde interaktif seçim menüsü eklendi.
# - GÜNCELLEME v2.3: Yardım menüsü tüm özellikleri kapsayacak şekilde detaylandırıldı.
# - GÜNCELLEME v2.4: VLAN kontrolü kaldırıldı (Feedback).
# - GÜNCELLEME v2.5: CLI çıktı temizliği iyileştirildi (Boşluklar ve Debug mesajları gizlendi).
# - GÜNCELLEME v2.6: Komut modu başlığı kaldırıldı. 'down' linkler kırmızı yapıldı. 'show clock' eklendi.
# - GÜNCELLEME v2.7: Yardım menüsü "Kullanıcı Rehberi" formatında yeniden tasarlandı. 'report' komutu eklendi.
# ----------------------------------------------------------------------------------

import sys
import os
import subprocess
import socket
import datetime
import re
import csv
import operator

# --- RENKLER (ANSI) ---
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    GRAY = '\033[0;90m'
    WHITE = '\033[1;37m'
    MAGENTA = '\033[0;35m'
    ORANGE = '\033[0;33m'
    NC = '\033[0m'

# --- AYARLAR ---
HOME = os.path.expanduser("~")
SOURCE_DIR = os.path.join(HOME, "source")
DATE_STR = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
CSV_FILENAME = os.path.join(SOURCE_DIR, f"TM_Rapor_{DATE_STR}.csv")
DEFAULT_DB = os.path.join(SOURCE_DIR, "veritabani.csv")

if not os.path.exists(SOURCE_DIR):
    os.makedirs(SOURCE_DIR)

# Varsayılanlar
PING_COUNT = 1
VALID_DEVICE_TYPES = ["Sdwan", "SEL3555", "SEL3530", "Ulak", "Kyland"]
VALID_DEVICE_REGEX = r"(?i)^(" + "|".join(VALID_DEVICE_TYPES) + ")$"
VALID_SHOW_COMMANDS = ["show interface brief", "show vlan brief", "show clock"]

# Global değişkenler
CURRENT_PING_LOSS = ""
LOG_TO_FILE = True
ONLY_LIST = False
FILTER_SCOPE = "ALL" # ALL, REGION, NAME, FILE
FILTER_VAL = ""
FILTER_DEVICE = ""
FILTER_EXACT = False 
VERBOSE_MODE = False
CUSTOM_COMMAND_MODE = False
CUSTOM_COMMAND_STR = ""
TARGET_IPS = set() # Dosya modunda taranacak IP listesi

# --- YARDIMCI FONKSİYONLAR ---

def clean_turkish(text):
    """Türkçe karakterleri İngilizce karşılıklarına çevirir (Görüntüleme için)"""
    tr_map = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    return text.translate(tr_map)

def normalize_text(text):
    """Arama ve karşılaştırma için metni normalize eder"""
    return clean_turkish(text).upper()

def clean_cli_output(text):
    """CLI çıktısındaki '--More--', debug mesajları ve gereksiz boşlukları temizler."""
    # 1. Backspace temizliği (Terminal emülasyonu)
    while '\x08' in text:
        text = re.sub(r'[^\x08]\x08', '', text)
    
    # 2. --More-- temizliği
    text = re.sub(r'\s*--More--\s*', '', text, flags=re.IGNORECASE)

    lines = text.splitlines()
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Boş satırları atla
        if not stripped:
            continue
            
        # [DEBUG] mesajlarını atla (Örn: ---[DEBUG] >> Sayfalama...)
        if "[DEBUG]" in line:
            continue

        # Komutun kendisinin ekrana yansımasını (echo) engelle
        if stripped in VALID_SHOW_COMMANDS or stripped == "exit":
            continue

        # Prompt satırlarını atla (Örn: KARSIYAKA#, KARSIYAKA>exit)
        # Genellikle alfanümerik karakterlerle başlayıp # veya > ile biter.
        if re.match(r'^[\w-]+[#>]\s*(exit)?$', stripped):
            continue

        # Kalan temiz satırı ekle
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines)

def print_help():
    print(f"{Colors.YELLOW}================================================================{Colors.NC}")
    print(f"{Colors.YELLOW}   TM CHECKER - PYTHON EDITION (v2.7)")
    print(f"{Colors.YELLOW}================================================================{Colors.NC}")
    print(f"{Colors.CYAN}VERİTABANI:{Colors.NC} {DEFAULT_DB}")
    print("")
    print(f"{Colors.WHITE}GENEL KULLANIM:{Colors.NC}  tmcheck.py [HEDEF] [EK_PARAMETRE] [-v]")
    print("")
    
    print(f"{Colors.GREEN}--- 1. CANLI SORGULAMA & İZLEME ---{Colors.NC}")
    print(f"  {Colors.WHITE}tmcheck.py Bagcilar{Colors.NC}")
    print("      -> 'Bağcılar' ismini arar. Tek sonuçsa detaylı tarar.")
    print("      -> Çoklu sonuç varsa (Bagcilar GIS, Bagcilar TM vb.) seçim menüsü sunar.")
    print(f"  {Colors.WHITE}tmcheck.py 5{Colors.NC}")
    print("      -> 5. Bölgedeki tüm merkezleri sırayla tarar.")
    print(f"  {Colors.WHITE}tmcheck.py 5 kyland{Colors.NC}")
    print("      -> 5. Bölgedeki sadece 'Kyland' cihazlarını tarar.")

    print(f"\n{Colors.GREEN}--- 2. CİHAZ KOMUT MODU (KYLAND) ---{Colors.NC}")
    print("  Belirtilen TM'nin Kyland cihazına bağlanır ve komut çıktısını gösterir.")
    print(f"  {Colors.WHITE}tmcheck.py Bagcilar \"show interface brief\"{Colors.NC}")
    print(f"  {Colors.WHITE}tmcheck.py Bagcilar \"show vlan brief\"{Colors.NC}")
    print(f"  {Colors.WHITE}tmcheck.py Bagcilar \"show clock\"{Colors.NC}")
    print(f"  {Colors.CYAN}* Down olan portlar kırmızı, Up olanlar yeşil görünür.{Colors.NC}")

    print(f"\n{Colors.GREEN}--- 3. TOPLU TARAMA & DOSYA MODU ---{Colors.NC}")
    print(f"  {Colors.WHITE}tmcheck.py liste.txt{Colors.NC}")
    print("      -> 'liste.txt' dosyasındaki her satırı (IP veya İsim) okur ve tarar.")
    print("      -> Özel çalışma listeleri oluşturmak için idealdir.")
    print(f"  {Colors.WHITE}tmcheck.py liste.txt -v{Colors.NC}")
    print("      -> Dosyadaki cihazları tararken versiyon detaylarını da gösterir.")

    print(f"\n{Colors.GREEN}--- 4. RAPORLAMA & ENVANTER ---{Colors.NC}")
    print(f"  {Colors.WHITE}tmcheck.py report{Colors.NC}  (veya {Colors.WHITE}rapor{Colors.NC})")
    print("      -> Tüm veritabanını tarar (Hızlı Mod).")
    print(f"      -> Sonuçları {Colors.CYAN}~/source/TM_Rapor_TARIH.csv{Colors.NC} dosyasına kaydeder.")
    print(f"  {Colors.WHITE}tmcheck.py list{Colors.NC}")
    print("      -> Ping atmaz. Veritabanındaki tüm kayıtları tablo olarak listeler.")
    print(f"  {Colors.WHITE}tmcheck.py 5 list{Colors.NC}")
    print("      -> Sadece 5. Bölge envanterini listeler.")

    print(f"\n{Colors.GREEN}--- PARAMETRELER ---{Colors.NC}")
    print(f"  {Colors.CYAN}-v{Colors.NC}      : (Verbose) Kyland taramalarında versiyon bilgisini satıra ekler.")
    print("")
    print(f"{Colors.YELLOW}================================================================{Colors.NC}")
    sys.exit(0)

def load_database(filepath):
    """CSV dosyasını okur ve sıralı bir liste döner"""
    data = []
    if not os.path.exists(filepath):
        print(f"{Colors.RED}HATA: Veritabanı bulunamadı: {filepath}{Colors.NC}")
        sys.exit(1)
        
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                if not row: continue
                if len(row) < 3: continue
                
                r_region = row[0].strip().replace('"', '')
                r_name = row[1].strip().replace('"', '')
                r_ip = row[2].strip().replace('"', '')
                r_3530 = row[3].strip().replace('"', '') if len(row) > 3 else "0"
                r_kyland = row[4].strip().replace('"', '') if len(row) > 4 else "1"
                r_vlan = row[5].strip().replace('"', '') if len(row) > 5 else "0"
                
                if not r_region.isdigit(): continue
                if not r_3530.isdigit(): r_3530 = "0"
                if not r_kyland.isdigit(): r_kyland = "1"
                if not r_vlan.isdigit(): r_vlan = "0"
                
                data.append({
                    "region": int(r_region),
                    "name": r_name,
                    "ip": r_ip,
                    "c3530": int(r_3530),
                    "cKyland": int(r_kyland),
                    "mgmt_vlan": int(r_vlan)
                })
        data.sort(key=operator.itemgetter("region", "name"))
        return data
    except Exception as e:
        print(f"{Colors.RED}HATA: Veritabanı okunurken hata oluştu: {e}{Colors.NC}")
        sys.exit(1)

def check_region_exists(db_data, region_val):
    try:
        reg_int = int(region_val)
        for item in db_data:
            if item["region"] == reg_int:
                return True
    except ValueError:
        return False
    return False

def check_ping(ip):
    global CURRENT_PING_LOSS
    CURRENT_PING_LOSS = ""
    param_c = '-c'
    param_w = '-W' 
    command = ['ping', param_c, str(PING_COUNT), param_w, '1', ip]
    try:
        result = subprocess.run(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        if result.returncode == 0:
            match = re.search(r'(\d+)% packet loss', result.stdout)
            if match:
                loss = int(match.group(1))
                if loss > 0:
                    CURRENT_PING_LOSS = f"{Colors.ORANGE}(Loss: %{loss}){Colors.NC}"
            return True
        else:
            return False
    except Exception:
        return False

def check_port(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except:
        return False

def check_kyland_extra(ip):
    """Sadece Kyland Versiyon kontrolü yapar."""
    cmd = ["python3", "/usr/local/bin/kyland_check.py", ip, "show ver"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        output = result.stdout
        found_version = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("SICOM"):
                found_version = line.split(',')[0].strip()
                break
        
        if found_version:
            expected = "SICOM3028GPT-L2GT-T1080"
            if found_version == expected:
                return True, found_version
            else:
                return False, found_version
        else:
            return False, "Versiyon Okunamadı"
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, "Script Hatası"

def run_kyland_command_mode(tm, command_str):
    """Özel Kyland komutlarını çalıştırır ve çıktıyı basar."""
    # Kyland-1 IP'sini hesapla (Prefix.94)
    parts = tm['ip'].split('.')
    prefix = ".".join(parts[:3])
    target_ip = f"{prefix}.94"
    
    print(f"\n{Colors.CYAN}>>> BAĞLANIYOR: {tm['name']} - KYLAND ({target_ip}){Colors.NC}")
    print(f"{Colors.GRAY}>>> KOMUT: {command_str}{Colors.NC}\n")
    
    if not check_ping(target_ip):
        print(f"{Colors.RED}HATA: Cihaza ping atılamadı!{Colors.NC}")
        return

    # Komutu çalıştır
    cmd = ["python3", "/usr/local/bin/kyland_check.py", target_ip, command_str]
    try:
        # Timeout süresini biraz uzun tutuyoruz çünkü show komutları uzun sürebilir
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        
        if result.returncode == 0 and result.stdout:
            raw_output = result.stdout
            cleaned_output = clean_cli_output(raw_output)
            
            # Çıktıyı renklendirme
            print("-" * 80)
            if not cleaned_output:
                print(f"{Colors.YELLOW}Uyarı: Komut çalıştı ancak gösterilecek veri bulunamadı.{Colors.NC}")
            else:
                for line in cleaned_output.splitlines():
                    # Header Renklendirme
                    if "Port" in line and "Type" in line: # Interface Header
                        print(f"{Colors.YELLOW}{line}{Colors.NC}")
                    elif "Existing Vlans" in line: # Vlan Header
                        print(f"{Colors.YELLOW}{line}{Colors.NC}")
                    # Durum Renklendirme
                    elif "down" in line.lower():
                         print(f"{Colors.RED}{line}{Colors.NC}")
                    elif "up" in line.lower():
                         print(f"{Colors.GREEN}{line}{Colors.NC}")
                    else:
                        print(line)
            print("-" * 80)
        else:
            print(f"{Colors.RED}HATA: Komut çıktısı alınamadı veya boş.{Colors.NC}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")

    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}HATA: Komut zaman aşımına uğradı (Timeout).{Colors.NC}")
    except Exception as e:
        print(f"{Colors.RED}HATA: Beklenmeyen hata: {e}{Colors.NC}")

def log_result(tm, dev_name, dev_ip, status_text, web_stat):
    if not LOG_TO_FILE: return
    try:
        with open(CSV_FILENAME, 'a') as f:
            tm_type = "BELIRSIZ"
            if tm['ip'].endswith(".93"): tm_type = "OTOMASYONLU"
            elif tm['ip'].endswith(".66"): tm_type = "KLASİK"
            parts = tm['ip'].split('.')
            prefix = ".".join(parts[:3]) if len(parts) == 4 else "0.0.0"
            f.write(f"{tm['region']},{tm['name']},{tm_type},{prefix},{dev_name},{dev_ip},{status_text},{web_stat}\n")
    except:
        pass

def print_result(tm, dev_name, dev_ip, status, web_msg="", extra_info=None, inline_extra=False):
    if LOG_TO_FILE or ONLY_LIST: return
    
    status_text = "SUCCESS" if status else "FAILED"
    status_color = Colors.GREEN if status else Colors.RED
    nm_clean = clean_turkish(tm['name'])
    dev_clean = clean_turkish(dev_name)
    meta_color = Colors.WHITE
    if tm['ip'].endswith(".93"): meta_color = Colors.YELLOW 
    
    line = (
        f"{meta_color}{str(tm['region']):<3}{Colors.NC} | "
        f"{meta_color}{nm_clean[:20]:<20}{Colors.NC} | "
        f"{meta_color}{dev_clean[:16]:<16} {dev_ip:<15}{Colors.NC} : "
        f"{status_color}{status_text:<10}{Colors.NC} "
        f"{CURRENT_PING_LOSS} {web_msg}"
    )

    if extra_info:
        if inline_extra:
            print(f"{line} {extra_info}")
        else:
            print(line)
            prefix_padding = " " * 29
            print(f"{prefix_padding}{Colors.GRAY}↳{Colors.NC} {extra_info}")
    else:
        print(line)

def run_check(tm, dev_name, dev_ip, check_type):
    global CURRENT_PING_LOSS
    
    # Komut modundaysak normal check yapma, doğrudan komutu çalıştır
    if CUSTOM_COMMAND_MODE and "Kyland" in dev_name:
         # Sadece Kyland-1 için çalıştır (genellikle .94)
         if dev_ip.endswith(".94"):
             run_kyland_command_mode(tm, CUSTOM_COMMAND_STR)
         return True # Diğer checkleri atla

    if FILTER_DEVICE:
        if FILTER_DEVICE.lower() not in dev_name.lower():
            return True

    p_stat = False
    w_stat = "N/A"
    
    if check_ping(dev_ip):
        p_stat = True
        if check_type == "HTTPS":
            if check_port(dev_ip, 443): w_stat = "HTTPS_OPEN"
            else: w_stat = "HTTPS_KAPALI (Ping Var)"
        elif check_type == "HTTP":
            if check_port(dev_ip, 80): w_stat = "HTTP_OPEN"
            else: w_stat = "HTTP_KAPALI (Ping Var)"
            
    status_text = "SUCCESS" if p_stat else "FAILED"
    
    log_result(tm, dev_name, dev_ip, status_text, w_stat)
    
    web_msg_colored = ""
    if w_stat != "N/A":
        if "KAPALI" in w_stat:
            web_msg_colored = f"{Colors.MAGENTA}[Web: {w_stat}]{Colors.NC}"
        else:
            web_msg_colored = f"[Web: {w_stat}]"

    should_check_deep = (PING_COUNT == 4) or (VERBOSE_MODE)

    extra_msg_list = []
    # GÜNCELLEME: VLAN kontrolü kaldırıldı, sadece Versiyon kontrolü kaldı.
    if should_check_deep and "Kyland" in dev_name and p_stat:
        if os.path.exists("/usr/local/bin/kyland_check.py"):
             v_ok, v_out = check_kyland_extra(dev_ip)
             v_color = Colors.GREEN if v_ok else Colors.RED
             extra_msg_list.append(f"{v_color}[{v_out}]{Colors.NC}")
    
    extra_info_str = " ".join(extra_msg_list) if extra_msg_list else None
    inline_mode = True if VERBOSE_MODE else False

    print_result(tm, dev_name, dev_ip, p_stat, web_msg_colored, extra_info=extra_info_str, inline_extra=inline_mode)
    
    return p_stat

def check_infrastructure(tm, dev_name, dev_ip):
    p_stat = check_ping(dev_ip)
    should_print = False
    
    if not p_stat:
        should_print = True
    else:
        if FILTER_DEVICE:
            if FILTER_DEVICE.lower() in dev_name.lower(): should_print = True
        else:
            should_print = True
            
    status_text = "SUCCESS" if p_stat else "FAILED"
    log_result(tm, dev_name, dev_ip, status_text, "N/A")
    
    if should_print and not LOG_TO_FILE and not ONLY_LIST:
        status_color = Colors.GREEN if p_stat else Colors.RED
        nm_clean = clean_turkish(tm['name'])
        meta_color = Colors.WHITE
        if tm['ip'].endswith(".93"): meta_color = Colors.YELLOW
        
        line = (
            f"{meta_color}{str(tm['region']):<3}{Colors.NC} | "
            f"{meta_color}{nm_clean[:20]:<20}{Colors.NC} | "
            f"{meta_color}{dev_name[:16]:<16} {dev_ip:<15}{Colors.NC} : "
            f"{status_color}{status_text:<10}{Colors.NC} "
            f"{CURRENT_PING_LOSS}"
        )
        print(line)
        
    return p_stat

# --- MAIN ---

def main():
    global INPUT_FILE, FILTER_SCOPE, FILTER_VAL, FILTER_DEVICE, LOG_TO_FILE, ONLY_LIST, PING_COUNT, VERBOSE_MODE, FILTER_EXACT, TARGET_IPS, CUSTOM_COMMAND_MODE, CUSTOM_COMMAND_STR
    
    args = sys.argv[1:]
    
    if len(args) == 0:
        print_help()
        sys.exit(0)
    
    if "-v" in args:
        VERBOSE_MODE = True
        args.remove("-v")
    
    if "-h" in args or "-help" in args or "--help" in args:
        print_help()
        
    input_file_path = DEFAULT_DB
    arg_filter = ""
    arg_device = ""
    
    if len(args) > 0:
        possible_file = args[0]
        if os.path.isfile(possible_file) or os.path.isfile(os.path.join(SOURCE_DIR, possible_file)):
            if possible_file.endswith(".txt"):
                arg_filter = possible_file 
            else:
                if os.path.isfile(possible_file): input_file_path = possible_file
                else: input_file_path = os.path.join(SOURCE_DIR, possible_file)
                if len(args) > 1: arg_filter = args[1]
                if len(args) > 2: arg_device = args[2]
        else:
            arg_filter = args[0]
            if len(args) > 1: arg_device = args[1]
    
    db_data = load_database(input_file_path)
    
    # Argüman Analizi
    if arg_filter:
        if arg_filter.lower().endswith(".txt"):
            FILTER_SCOPE = "FILE"
            target_file = arg_filter
            if not os.path.exists(target_file):
                 target_file = os.path.join(SOURCE_DIR, arg_filter)
            
            if not os.path.exists(target_file):
                print(f"{Colors.RED}HATA: Dosya bulunamadı: {arg_filter}{Colors.NC}")
                sys.exit(1)
            
            if arg_device and re.match(VALID_DEVICE_REGEX, arg_device):
                FILTER_DEVICE = arg_device
            
            LOG_TO_FILE = False
            
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    search_lines = [line.strip() for line in f if line.strip()]
            except Exception as e:
                print(f"{Colors.RED}HATA: Dosya okunamadı: {e}{Colors.NC}")
                sys.exit(1)
                
            print(f"{Colors.YELLOW}MOD:{Colors.NC} Dosya Listesi Taraması -> {target_file}")
            
            UNMATCHED_LINES = []
            
            for s_line in search_lines:
                s_norm = normalize_text(s_line)
                found_for_line = False
                
                is_ip = False
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", s_line):
                    is_ip = True
                
                for tm in db_data:
                    if is_ip and tm['ip'] == s_line:
                        TARGET_IPS.add(tm['ip'])
                        found_for_line = True
                    elif not is_ip:
                        tm_norm = normalize_text(tm['name'])
                        if s_norm in tm_norm:
                            TARGET_IPS.add(tm['ip'])
                            found_for_line = True
                
                if not found_for_line:
                    UNMATCHED_LINES.append(s_line)

            if UNMATCHED_LINES:
                print(f"{Colors.RED}UYARI: Aşağıdaki {len(UNMATCHED_LINES)} kayıt veritabanında eşleşmedi (Atlanıyor):{Colors.NC}")
                for m in UNMATCHED_LINES:
                    print(f"  - {m}")
                print("-" * 114)
                
            if not TARGET_IPS:
                print(f"{Colors.RED}HATA: Dosyadaki hiçbir kayıt ile eşleşme sağlanamadı!{Colors.NC}")
                sys.exit(1)
            else:
                print(f"{Colors.CYAN}EŞLEŞEN TM SAYISI:{Colors.NC} {len(TARGET_IPS)}")

        elif arg_device:
            # Burası önemli: İkinci parametre bir "show" komutu mu?
            if arg_device in VALID_SHOW_COMMANDS:
                 CUSTOM_COMMAND_MODE = True
                 CUSTOM_COMMAND_STR = arg_device
                 FILTER_SCOPE = "NAME" # Komut modu için isim aramayı varsayıyoruz
                 FILTER_VAL = arg_filter
                 LOG_TO_FILE = False
            else:
                # Normal filtreleme
                FILTER_VAL = arg_filter
                if FILTER_VAL.isdigit():
                    if not check_region_exists(db_data, FILTER_VAL):
                        print(f"{Colors.RED}HATA: {Colors.WHITE}{FILTER_VAL}{Colors.RED} numaralı bölge veritabanında bulunamadı!{Colors.NC}")
                        sys.exit(1)
                    FILTER_SCOPE = "REGION"
                else:
                    FILTER_SCOPE = "NAME"
                    
                if arg_device in ["ALL", "all", "*"]:
                    ONLY_LIST = True
                    LOG_TO_FILE = False
                else:
                    if re.match(VALID_DEVICE_REGEX, arg_device):
                        FILTER_DEVICE = arg_device
                        LOG_TO_FILE = False
                    else:
                        print(f"{Colors.RED}HATA: {Colors.WHITE}'{arg_device}'{Colors.RED} geçerli bir cihaz tipi değil!{Colors.NC}")
                        print(f"{Colors.YELLOW}Geçerli Cihazlar:{Colors.NC} {', '.join(VALID_DEVICE_TYPES)}")
                        print(f"{Colors.YELLOW}Geçerli Komutlar:{Colors.NC} {', '.join(VALID_SHOW_COMMANDS)}")
                        sys.exit(1)
        else:
            val = arg_filter
            if val.isdigit():
                if not check_region_exists(db_data, val):
                    print(f"{Colors.RED}HATA: {Colors.WHITE}{val}{Colors.RED} numaralı bölge veritabanında bulunamadı!{Colors.NC}")
                    sys.exit(1)
                FILTER_SCOPE = "REGION"
                FILTER_VAL = val
                LOG_TO_FILE = False 
            elif val in ["ALL", "all", "*", "list", "LIST"]:
                FILTER_SCOPE = "ALL"
                ONLY_LIST = True
                LOG_TO_FILE = False
            elif val in ["RAPOR", "rapor", "full", "FULL", "REPORT", "report"]:
                FILTER_SCOPE = "ALL"
                ONLY_LIST = False
                LOG_TO_FILE = True
            elif re.match(VALID_DEVICE_REGEX, val):
                FILTER_DEVICE = val
                LOG_TO_FILE = False
            else:
                FILTER_SCOPE = "NAME"
                FILTER_VAL = val
                LOG_TO_FILE = False
                PING_COUNT = 4
    
    if FILTER_SCOPE == "NAME" and not ONLY_LIST:
        search_term = normalize_text(FILTER_VAL)
        matches = []
        for item in db_data:
            nm_norm = normalize_text(item["name"])
            if search_term in nm_norm:
                matches.append(item["name"])
        
        count = len(matches)
        if count == 0:
            print(f"{Colors.RED}HATA: '{FILTER_VAL}' veritabanında TM ismi olarak bulunamadı.{Colors.NC}")
            print(f"{Colors.YELLOW}Eğer bir cihaz arıyorsanız geçerli liste:{Colors.NC} {', '.join(VALID_DEVICE_TYPES)}")
            sys.exit(1)
        elif count >= 1:
            exact_match = None
            for m in matches:
                if normalize_text(m) == search_term:
                    exact_match = m
                    break
            
            if exact_match:
                FILTER_VAL = exact_match
                FILTER_EXACT = True 
                PING_COUNT = 4
            else:
                if count > 1:
                    print(f"\n{Colors.YELLOW}UYARI: Birden fazla TM bulundu. Lütfen işlem yapmak istediğiniz TM'yi seçin:{Colors.NC}")
                    
                    for i, m in enumerate(matches, 1):
                        print(f"{Colors.CYAN}[{i}]{Colors.NC} {m}")
                    
                    print(f"{Colors.GRAY}[q] Çıkış{Colors.NC}")
                    
                    try:
                        selection = input(f"\n{Colors.WHITE}Seçiminiz (Numara): {Colors.NC}")
                        
                        if selection.lower() == 'q':
                            print(f"{Colors.RED}İşlem iptal edildi.{Colors.NC}")
                            sys.exit(0)
                            
                        sel_idx = int(selection) - 1
                        
                        if 0 <= sel_idx < count:
                            selected_tm_name = matches[sel_idx]
                            print(f"{Colors.GREEN}Seçilen TM: {selected_tm_name}{Colors.NC}\n")
                            
                            FILTER_VAL = selected_tm_name
                            FILTER_EXACT = True
                            PING_COUNT = 4
                        else:
                            print(f"{Colors.RED}HATA: Geçersiz seçim numarası!{Colors.NC}")
                            sys.exit(1)
                            
                    except ValueError:
                        print(f"{Colors.RED}HATA: Lütfen geçerli bir numara girin!{Colors.NC}")
                        sys.exit(1)
                else:
                    PING_COUNT = 4

    # Komut Modu Kontrolü
    if CUSTOM_COMMAND_MODE:
        if count > 1 and not FILTER_EXACT:
             # Eğer çoklu eşleşme varsa yukarıdaki menüden seçilmiştir.
             # Seçilen TM için komutu çalıştıracağız.
             # Loop zaten tekil TM için çalışacak
             pass
    
    if LOG_TO_FILE:
        try:
            with open(CSV_FILENAME, 'w') as f:
                f.write("Bolge_No,TM_Adi,TM_Tipi,TM_Prefix,Cihaz_Adi,Cihaz_IP,Ping_Durumu,Web_Port_Durumu\n")
            print(f"{Colors.YELLOW}MOD:{Colors.NC} Rapor Modu (+ Canlı Ekran) -> {CSV_FILENAME}")
        except:
            print(f"{Colors.RED}HATA: Dosya oluşturulamadı: {CSV_FILENAME}{Colors.NC}")
            sys.exit(1)
    elif ONLY_LIST:
        print(f"{Colors.YELLOW}MOD:{Colors.NC} Envanter Listeleme Modu (SIRALI - Tarama Yok)")
    elif CUSTOM_COMMAND_MODE:
        print(f"{Colors.YELLOW}MOD:{Colors.NC} Kyland Komut Modu: '{CUSTOM_COMMAND_STR}'")
    else:
        print(f"{Colors.YELLOW}MOD:{Colors.NC} Canlı İzleme Modu (Ping Count: {PING_COUNT})")
        if VERBOSE_MODE:
            print(f"{Colors.CYAN}BİLGİ:{Colors.NC} Detaylı tarama (-v) aktif. Kyland versiyonu kontrol edilecek.")
        
    print(f"{Colors.YELLOW}KAYNAK:{Colors.NC} {input_file_path}")
    if FILTER_DEVICE and not CUSTOM_COMMAND_MODE:
        print(f"{Colors.CYAN}FİLTRE:{Colors.NC} '{FILTER_DEVICE}'")
        
    print("-" * 114)
    if ONLY_LIST:
        print(f"{Colors.GRAY}{'BLG':<3}{Colors.NC} | {Colors.GRAY}{'TM ADI':<25}{Colors.NC} | {'ANA IP':<15} | {'3530':<5} | {'KYLAND':<6} | {'MGMT VLAN'}")
    elif not CUSTOM_COMMAND_MODE:
        print(f"{Colors.GRAY}{'BLG':<3}{Colors.NC} | {Colors.GRAY}{'TM ADI':<20}{Colors.NC} | {'CIHAZ':<16} {'IP ADRESI':<15} : {'DURUM':<10} {'WEB'}")
    else:
         # Komut modunda başlık basılmıyor.
         pass

    if not CUSTOM_COMMAND_MODE:
        print("-" * 114)

    total_processed = 0
    for tm in db_data:
        if ONLY_LIST:
            if FILTER_SCOPE == "REGION" and tm["region"] != int(FILTER_VAL): continue
        else:
            if FILTER_SCOPE == "REGION" and tm["region"] != int(FILTER_VAL): continue
            elif FILTER_SCOPE == "NAME":
                nm_norm = normalize_text(tm["name"])
                input_norm = normalize_text(FILTER_VAL)
                
                if FILTER_EXACT:
                    if nm_norm != input_norm:
                        continue
                else:
                    if input_norm not in nm_norm: 
                        continue
            elif FILTER_SCOPE == "FILE":
                if tm['ip'] not in TARGET_IPS:
                    continue

        total_processed += 1
        
        if ONLY_LIST:
            nm_clean = clean_turkish(tm["name"])
            line_color = Colors.WHITE
            if tm["ip"].endswith(".93"): line_color = Colors.YELLOW
            
            print(f"{line_color}{str(tm['region']):<3}{Colors.NC} | "
                  f"{line_color}{nm_clean[:25]:<25}{Colors.NC} | "
                  f"{line_color}{tm['ip']:<15}{Colors.NC} | "
                  f"{line_color}{str(tm['c3530']):<5}{Colors.NC} | "
                  f"{line_color}{str(tm['cKyland']):<6}{Colors.NC} | "
                  f"{line_color}{str(tm['mgmt_vlan'])}{Colors.NC}")
            continue
        
        # KOMUT MODU: Sadece Kyland kontrolü yap ve çık
        if CUSTOM_COMMAND_MODE:
             # Sadece Kyland-1 için çalışır, bu yüzden prefix hesabı yeterli
             run_check(tm, "Kyland-1", "0.0.0.94", "None") # IP run_check içinde hesaplanır
             continue

        # NORMAL MOD AKIŞI
        parts = tm['ip'].split('.')
        if len(parts) != 4: continue
        prefix = ".".join(parts[:3])
        last_octet = parts[3]
        
        tm_type = "BELIRSIZ"
        if last_octet == "93": tm_type = "OTOMASYONLU"
        elif last_octet == "66": tm_type = "KLASİK"
        
        if not check_infrastructure(tm, "Sdwan", f"{prefix}.97"): continue
        if not check_infrastructure(tm, "ULAK_Fiziksel", f"{prefix}.99"): continue
        if not check_infrastructure(tm, "ULAK_Sanal", f"{prefix}.98"): continue
            
        run_check(tm, "Kyland-1", f"{prefix}.94", "HTTP")
        
        if tm_type == "OTOMASYONLU":
            run_check(tm, "SEL3555(O)", tm['ip'], "HTTPS")
        else:
            run_check(tm, "SEL3555", tm['ip'], "HTTPS")
            
        if tm['cKyland'] >= 1:
            if tm['cKyland'] > 1:
                for k in range(2, tm['cKyland'] + 1):
                    if tm_type == "OTOMASYONLU": octet = 94 - k
                    else: octet = 94 - (k - 1)
                    if not run_check(tm, f"Kyland-{k}", f"{prefix}.{octet}", "HTTP"): break
                        
        if tm['c3530'] > 0:
            for i in range(1, tm['c3530'] + 1):
                last = 66 + i
                run_check(tm, f"SEL3530_{i}", f"{prefix}.{last}", "HTTPS")
                
    if not CUSTOM_COMMAND_MODE:
        print("-" * 114)
        print(f"{Colors.CYAN}TOPLAM İŞLENEN TM SAYISI: {total_processed}{Colors.NC}")
        print("-" * 114)
    
    if LOG_TO_FILE:
        print(f"{Colors.GREEN}TARAMA BİTTİ.{Colors.NC} Rapor: {CSV_FILENAME}")
    elif not ONLY_LIST and not CUSTOM_COMMAND_MODE:
        print(f"{Colors.GREEN}İŞLEM TAMAMLANDI.{Colors.NC}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}İşlem kullanıcı tarafından durduruldu.{Colors.NC}")
        sys.exit(0)
