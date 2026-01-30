#!/usr/bin/env python3
import os
import sys
import pty
import select
import time
import csv
import termios
import tty

# 'kyland' veya 'ulak' seçimine göre otomatik IP ayarlar ve bağlanır.

CSV_PATH = "source/veritabani.csv"

# --- CİHAZ YAPILANDIRMALARI ---
DEVICE_CONFIG = {
    "kyland": {
        "octet": "94",
        "user": "admin",
        "pass": "Kyl@Nd1234.!"
    },
    "ulak": {
        "octet": "98",
        "user": "cliadmin",
        "pass": "sobesobe"
    }
}

def normalize_text(text):
    """Türkçe karakterleri düzeltir ve büyük harfe çevirir."""
    if not text: return ""
    tr_map = {
        ord('ı'): 'i', ord('İ'): 'I', ord('ğ'): 'g', ord('Ğ'): 'G',
        ord('ü'): 'u', ord('Ü'): 'U', ord('ş'): 's', ord('Ş'): 'S',
        ord('ö'): 'o', ord('Ö'): 'O', ord('ç'): 'c', ord('Ç'): 'C'
    }
    return text.translate(tr_map).upper()

def print_help():
    """Yardım menüsünü ekrana basar."""
    help_text = """
    TM SSH Bağlantı Aracı (v2.0)
    ----------------------------
    Belirtilen cihaz tipine göre (Kyland veya ULAK) otomatik IP hesaplar,
    şifreyi girer ve interaktif bağlantı sağlar.

    Kullanım:
        tmssh.py <CİHAZ_TİPİ> <HEDEF>

    Parametreler:
        <CİHAZ_TİPİ>  : 'kyland' veya 'ulak'
        <HEDEF>       : Hedef IP adresi (örn: 10.37.4.94)
                        YA DA
                        Veritabanındaki TM Adı (örn: AKSARAY)

    Örnekler:
        tmssh.py kyland 10.37.4.94
        tmssh.py kyland AKSARAY      (IP sonunu .94 yapar)
        tmssh.py ulak ALIBEYKOY      (IP sonunu .98 yapar)
    """
    print(help_text)

def modify_ip(original_ip, target_octet):
    """IP son oktetini belirtilen değer (94 veya 98) yapar."""
    parts = original_ip.split('.')
    if len(parts) == 4:
        parts[3] = target_octet
        return ".".join(parts)
    return None

def get_ip_from_csv(search_term, target_octet):
    """CSV'den TM adını arar, IP'yi bulur ve cihaza göre modifiye eder."""
    if not os.path.exists(CSV_PATH):
        print(f"Hata: Veritabanı dosyası bulunamadı: {CSV_PATH}")
        return None

    normalized_search = normalize_text(search_term)
    matches = []

    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 3: continue
                
                tm_name_raw = row[1]
                tm_name_clean = normalize_text(tm_name_raw)
                original_ip = row[2]
                
                if normalized_search in tm_name_clean:
                    matches.append({'name': tm_name_raw, 'ip': original_ip})
        
        if len(matches) == 0:
            print(f"Hata: '{search_term}' isminde bir lokasyon bulunamadı.")
            return None
        elif len(matches) == 1:
            selected = matches[0]
            final_ip = modify_ip(selected['ip'], target_octet)
            print(f"Lokasyon: {selected['name']} (Orijinal IP: {selected['ip']} -> Hedef: {final_ip})")
            return final_ip
        else:
            print(f"\nBirden fazla sonuç bulundu ('{search_term}'):")
            print("-" * 40)
            for idx, m in enumerate(matches):
                print(f"{idx + 1}. {m['name']} \t[IP: {m['ip']}]")
            print("-" * 40)
            while True:
                try:
                    selection = input("Seçiminiz (Çıkış 'q'): ")
                    if selection.lower() == 'q': return None
                    idx = int(selection) - 1
                    if 0 <= idx < len(matches):
                        return modify_ip(matches[idx]['ip'], target_octet)
                except ValueError: pass

    except Exception as e:
        print(f"CSV hatası: {e}")
        return None

def is_valid_ip(text):
    parts = text.split('.')
    return len(parts) == 4 and all(p.isdigit() for p in parts)

def ssh_connect():
    # En az 2 argüman gerekli (script adı hariç): tipi ve hedef
    if len(sys.argv) < 3:
        if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
            print_help()
        else:
            print("Hata: Eksik parametre.")
            print_help()
        return

    device_type = sys.argv[1].lower()
    input_target = sys.argv[2]

    # Cihaz tipi kontrolü
    if device_type not in DEVICE_CONFIG:
        print(f"Hata: Geçersiz cihaz tipi '{device_type}'. Seçenekler: 'kyland', 'ulak'")
        return

    config = DEVICE_CONFIG[device_type]
    target_octet = config["octet"]
    target_user = config["user"]
    target_pass = config["pass"]

    target_ip = ""

    # Hedef IP mi yoksa İsim mi?
    if is_valid_ip(input_target):
        # IP girildiyse bile sonunu cihaza göre düzeltelim mi? 
        # Genelde kullanıcı IP girdiyse bildiği yere gidiyordur ama
        # isteğinize göre IP girilse bile sonunu değiştirebiliriz.
        # Şimdilik direkt kullanıyoruz, isterseniz modify_ip buraya da eklenir.
        target_ip = input_target 
    else:
        # İsim ise veritabanından bul ve sonunu ayarla
        found_ip = get_ip_from_csv(input_target, target_octet)
        if found_ip:
            target_ip = found_ip
        else:
            return

    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", f"{target_user}@{target_ip}"]

    print(f"[{device_type.upper()}] {target_ip} adresine bağlanılıyor... (Kullanıcı: {target_user})")
    
    pid, fd = pty.fork()

    if pid == 0:
        os.execvp("ssh", ssh_cmd)
    else:
        try:
            # --- OTOMATİK GİRİŞ KISMI ---
            password_sent = False
            buffer = b""
            
            while not password_sent:
                r, _, _ = select.select([fd], [], [], 10)
                if fd in r:
                    data = os.read(fd, 1024)
                    if not data: return # Bağlantı koptu
                    
                    os.write(sys.stdout.fileno(), data)
                    buffer += data
                    str_data = buffer.decode('utf-8', errors='ignore')

                    if "Are you sure" in str_data:
                        os.write(fd, b"yes\n")
                        buffer = b""
                    elif "password:" in str_data.lower():
                        os.write(fd, (target_pass + "\n").encode())
                        password_sent = True
                        buffer = b"" 
                else:
                    print("\nZaman aşımı: Sunucu cevap vermedi.")
                    return

            # --- İNTERAKTİF MOD ---
            print("\n>>> Giriş başarılı! Kontrol sizde.\n")
            
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin)
            
            while True:
                r, w, e = select.select([fd, sys.stdin], [], [])
                
                if fd in r:
                    data = os.read(fd, 1024)
                    if not data: break
                    os.write(sys.stdout.fileno(), data)
                
                if sys.stdin in r:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if not data: break
                    os.write(fd, data)
                    
        except OSError:
            pass
        except Exception as e:
            os.write(sys.stdout.fileno(), f"\r\nHata: {e}\r\n".encode())
        finally:
            if 'old_settings' in locals():
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            try:
                os.close(fd)
                os.waitpid(pid, 0)
            except:
                pass
            print("\nBağlantı sonlandırıldı.")

if __name__ == "__main__":
    ssh_connect()
