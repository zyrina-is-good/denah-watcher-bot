import os
import json
import time
import socket
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Furina Denah Watcher Bot is active!")

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        server.serve_forever()
    except Exception:
        pass

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "bot_token": "9059475981:AAFYkATEvgIUl33nksX5vjM1zXfYmV52UWk",
    "chat_id": 7580316080,
    "watchlist": ["4", "7"],
    "last_layout_ts": 0,
    "poll_interval_sec": 15
}

SUPABASE_URL = "https://qwcglomkdzjseophlbzy.supabase.co"
SUPABASE_KEY = "sb_publishable_dl1LB9CECK4c53mm68ZhZQ_pwXgcCeg"

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in cfg:
                        cfg[k] = v
                return cfg
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

config = load_config()
config_lock = threading.Lock()

def fetch_supabase(endpoint):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def get_students_map():
    try:
        data = fetch_supabase("history_entries?type=eq.STUDENTS_LIST&class_id=eq.VIII-C&order=timestamp_ms.desc&limit=1")
        if data and "snapshot_before" in data[0]:
            st_list = data[0]["snapshot_before"]
            return {str(s.get("number")): s.get("name", str(s.get("number"))) for s in st_list if s.get("number")}
    except Exception:
        pass
    return {str(i): f"Siswa {i}" for i in range(1, 33)}

def get_latest_layout():
    try:
        data = fetch_supabase("history_entries?type=eq.CURRENT_LAYOUT&class_id=eq.VIII-C&order=timestamp_ms.desc&limit=1")
        if data:
            entry = data[0]
            desks = entry.get("snapshot_before", [])
            ts = entry.get("timestamp_ms", 0)
            desc = entry.get("edit_description", "Denah Kelas Aktif")
            return desks, ts, desc
    except Exception:
        pass
    return [], 0, ""

def send_telegram(method, payload):
    token = config.get("bot_token")
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"ok": False, "error": err_msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def answer_callback(cb_id, text=None):
    payload = {"callback_query_id": cb_id}
    if text:
        payload["text"] = text
    send_telegram("answerCallbackQuery", payload)

def format_timestamp(ts):
    if not ts:
        return "-"
    try:
        dt = datetime.fromtimestamp(ts / 1000.0)
        return dt.strftime("%d/%m/%Y • %H:%M:%S WIB")
    except Exception:
        return str(ts)

def get_seating_pairs(desks, students_map):
    pairs = {}
    for desk in desks:
        label = desk.get("deskLabel", f"Meja {desk.get('deskNumber', '?')}")
        seats = desk.get("seats", [])
        if len(seats) >= 2:
            s1 = str(seats[0].get("studentNumber", "")).strip()
            s2 = str(seats[1].get("studentNumber", "")).strip()
            n1 = seats[0].get("studentName") or students_map.get(s1, s1)
            n2 = seats[1].get("studentName") or students_map.get(s2, s2)

            if s1:
                pairs[s1] = {
                    "desk": label,
                    "self_num": s1,
                    "self_name": n1,
                    "partner_num": s2 if s2 else None,
                    "partner_name": n2 if s2 else "(Kursi Kosong)"
                }
            if s2:
                pairs[s2] = {
                    "desk": label,
                    "self_num": s2,
                    "self_name": n2,
                    "partner_num": s1 if s1 else None,
                    "partner_name": n1 if s1 else "(Kursi Kosong)"
                }
    return pairs

def build_main_menu_text(students_map, last_ts):
    with config_lock:
        watchlist = sorted(config.get("watchlist", []), key=lambda x: int(x) if x.isdigit() else 999)

    preview_items = []
    for w in watchlist:
        name = students_map.get(w, f"Siswa {w}")
        preview_items.append(f"<b>{w}</b> ({name})")
    
    if preview_items:
        wl_str = ", ".join(preview_items)
    else:
        wl_str = "<i>(Belum ada - klik tombol di bawah)</i>"

    t_str = format_timestamp(last_ts)

    text = (
        "🏫 <b>PANTAU DENAH KELAS VIII-C</b>\n"
        "────────────────────────\n"
        "🟢 <b>Status:</b> Aktif Memantau Server 24/7\n"
        f"⏱️ <b>Denah Terakhir:</b> {t_str}\n"
        f"👥 <b>Absen Dipantau:</b> {wl_str}\n"
        "────────────────────────\n"
        "<i>Silakan pilih menu di bawah ini:</i>"
    )
    return text

def build_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🔍 Cek Pasangan Duduk", "callback_data": "menu_check"}],
            [{"text": "⚙️ Atur Absen Pantauan", "callback_data": "menu_watchlist"}],
            [{"text": "🗺️ Lihat Seluruh Denah", "callback_data": "menu_all_desks"}],
            [{"text": "🔄 Refresh Data", "callback_data": "menu_refresh"}]
        ]
    }

def build_watchlist_keyboard():
    with config_lock:
        current_wl = set(config.get("watchlist", []))

    rows = []
    for r in range(8):
        row = []
        for c in range(1, 5):
            num = str(r * 4 + c)
            is_active = num in current_wl
            icon = "✅ " if is_active else ""
            row.append({
                "text": f"{icon}{num}",
                "callback_data": f"toggle_{num}"
            })
        rows.append(row)

    rows.append([
        {"text": "✅ Pilih Semua", "callback_data": "wl_select_all"},
        {"text": "❌ Kosongkan", "callback_data": "wl_clear_all"}
    ])
    rows.append([
        {"text": "💾 Selesai & Kembali", "callback_data": "menu_main"}
    ])
    return {"inline_keyboard": rows}

def build_check_result_text(desks, ts, students_map):
    with config_lock:
        watchlist = sorted(config.get("watchlist", []), key=lambda x: int(x) if x.isdigit() else 999)

    if not watchlist:
        return (
            "⚠️ <b>Belum ada absen yang dipantau!</b>\n\n"
            "Silakan klik tombol <b>⚙️ Atur Absen Pantauan</b> di bawah untuk memilih absen siapa saja yang ingin kamu ketahui pasangan duduknya."
        )

    pairs = get_seating_pairs(desks, students_map)
    t_str = format_timestamp(ts)

    lines = [
        "🔔 <b>HASIL PANTAUAN PASANGAN DUDUK</b>",
        f"🏫 <i>Kelas VIII-C • Update: {t_str}</i>",
        "────────────────────────"
    ]

    grouped_by_desk = {}
    reported_pairs = set()

    for w in watchlist:
        if w in pairs:
            info = pairs[w]
            desk = info["desk"]
            p_num = info["partner_num"]
            pair_key = tuple(sorted([w, p_num if p_num else ""]))
            if pair_key in reported_pairs:
                continue
            reported_pairs.add(pair_key)

            if desk not in grouped_by_desk:
                grouped_by_desk[desk] = []
            grouped_by_desk[desk].append(info)
        else:
            if "Belum Duduk" not in grouped_by_desk:
                grouped_by_desk["Belum Duduk"] = []
            name = students_map.get(w, f"Siswa {w}")
            grouped_by_desk["Belum Duduk"].append({
                "self_num": w,
                "self_name": name,
                "partner_num": None,
                "partner_name": "Belum menempati kursi"
            })

    for desk, items in grouped_by_desk.items():
        if desk == "Belum Duduk":
            lines.append("🚪 <b>Belum Menempati Kursi:</b>")
            for it in items:
                lines.append(f"└ 👤 Absen <b>{it['self_num']}</b> ({it['self_name']})")
            lines.append("")
        else:
            lines.append(f"🪑 <b>{desk}</b>")
            for it in items:
                s_num = it["self_num"]
                s_name = it["self_name"]
                p_num = it["partner_num"]
                p_name = it["partner_name"]

                if p_num:
                    lines.append(f"└ 👤 Absen <b>{s_num}</b> ({s_name})  🤝  👤 Absen <b>{p_num}</b> ({p_name})")
                else:
                    lines.append(f"└ 👤 Absen <b>{s_num}</b> ({s_name})  🤝  <i>{p_name}</i>")
            lines.append("")

    lines.append("────────────────────────")
    lines.append("💡 <i>Data dibaca langsung dari server Supabase.</i>")
    return "\n".join(lines)

def build_all_desks_text(desks, ts, students_map):
    t_str = format_timestamp(ts)
    lines = [
        "🗺️ <b>DENAH KELAS VIII-C LENGKAP</b>",
        f"📅 <i>Update: {t_str}</i>",
        "────────────────────────"
    ]

    for d in desks:
        label = d.get("deskLabel", f"Meja {d.get('deskNumber', '?')}")
        seats = d.get("seats", [])
        seat_strs = []
        for s in seats:
            num = str(s.get("studentNumber", "")).strip()
            name = s.get("studentName") or students_map.get(num, num)
            if num:
                seat_strs.append(f"[<b>{num}</b>] {name}")
            else:
                seat_strs.append("<i>[Kosong]</i>")
        pair_display = "  •  ".join(seat_strs)
        lines.append(f"🪑 <b>{label}</b>: {pair_display}")

    lines.append("────────────────────────")
    return "\n".join(lines)

def notify_layout_update(desks, ts, desc, students_map):
    chat_id = config.get("chat_id")
    if not chat_id:
        return

    check_text = build_check_result_text(desks, ts, students_map)
    header = (
        "🚨 <b>DENAH KELAS BARU TERDETEKSI!</b>\n"
        "Pengurus baru saja mengacak / memperbarui susunan kursi di server.\n\n"
    )
    full_text = header + check_text

    keyboard = {
        "inline_keyboard": [
            [{"text": "🔍 Cek Rinci", "callback_data": "menu_check"}],
            [{"text": "🗺️ Lihat Denah Lengkap", "callback_data": "menu_all_desks"}],
            [{"text": "🏠 Menu Utama", "callback_data": "menu_main"}]
        ]
    }

    send_telegram("sendMessage", {
        "chat_id": chat_id,
        "text": full_text,
        "parse_mode": "HTML",
        "reply_markup": keyboard
    })

def background_watcher():
    students_map = get_students_map()
    _, initial_ts, _ = get_latest_layout()

    with config_lock:
        if config.get("last_layout_ts", 0) == 0 and initial_ts > 0:
            config["last_layout_ts"] = initial_ts
            save_config(config)

    while True:
        try:
            poll_sec = config.get("poll_interval_sec", 15)
            time.sleep(poll_sec)

            desks, ts, desc = get_latest_layout()
            if not ts:
                continue

            with config_lock:
                last_ts = config.get("last_layout_ts", 0)

            if ts > last_ts:
                with config_lock:
                    config["last_layout_ts"] = ts
                    save_config(config)

                students_map = get_students_map()
                notify_layout_update(desks, ts, desc, students_map)
        except Exception:
            pass

def handle_update(upd, students_map):
    if "callback_query" in upd:
        cq = upd["callback_query"]
        cq_id = cq["id"]
        data = cq.get("data", "")
        message = cq.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")

        if data == "menu_main":
            desks, ts, _ = get_latest_layout()
            text = build_main_menu_text(students_map, ts)
            kb = build_main_menu_keyboard()
            send_telegram("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            })
            answer_callback(cq_id, "Menu Utama")

        elif data == "menu_check":
            desks, ts, _ = get_latest_layout()
            text = build_check_result_text(desks, ts, students_map)
            kb = {
                "inline_keyboard": [
                    [{"text": "🔄 Cek Ulang", "callback_data": "menu_check"}],
                    [{"text": "⚙️ Atur Absen Pantauan", "callback_data": "menu_watchlist"}],
                    [{"text": "🏠 Menu Utama", "callback_data": "menu_main"}]
                ]
            }
            send_telegram("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            })
            answer_callback(cq_id, "Hasil pasangan diperbarui!")

        elif data == "menu_watchlist":
            text = (
                "⚙️ <b>PAPAN TOMBOL ABSEN PANTAUAN</b>\n"
                "────────────────────────\n"
                "Sentuh nomor absen di bawah untuk <b>mengaktifkan (✅)</b> atau <b>menonaktifkan</b> pantauan pasangan duduk.\n\n"
                "<i>Tiap tombol yang disentuh langsung berubah secara instan:</i>"
            )
            kb = build_watchlist_keyboard()
            send_telegram("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            })
            answer_callback(cq_id, "Papan tombol absen dibuka")

        elif data.startswith("toggle_"):
            num = data.replace("toggle_", "")
            with config_lock:
                wl = config.get("watchlist", [])
                if num in wl:
                    wl.remove(num)
                    status_txt = f"Absen {num} dinonaktifkan"
                else:
                    wl.append(num)
                    status_txt = f"Absen {num} diaktifkan"
                config["watchlist"] = sorted(wl, key=lambda x: int(x) if x.isdigit() else 999)
                save_config(config)

            kb = build_watchlist_keyboard()
            send_telegram("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "reply_markup": kb
            })
            answer_callback(cq_id, status_txt)

        elif data == "wl_select_all":
            with config_lock:
                config["watchlist"] = [str(i) for i in range(1, 33)]
                save_config(config)
            kb = build_watchlist_keyboard()
            send_telegram("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "reply_markup": kb
            })
            answer_callback(cq_id, "Semua 32 absen dipilih!")

        elif data == "wl_clear_all":
            with config_lock:
                config["watchlist"] = []
                save_config(config)
            kb = build_watchlist_keyboard()
            send_telegram("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "reply_markup": kb
            })
            answer_callback(cq_id, "Daftar pantauan dikosongkan!")

        elif data == "menu_all_desks":
            desks, ts, _ = get_latest_layout()
            text = build_all_desks_text(desks, ts, students_map)
            kb = {
                "inline_keyboard": [
                    [{"text": "🔍 Cek Pasangan Pilihan", "callback_data": "menu_check"}],
                    [{"text": "🏠 Menu Utama", "callback_data": "menu_main"}]
                ]
            }
            send_telegram("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            })
            answer_callback(cq_id, "Denah lengkap dimuat")

        elif data == "menu_refresh":
            desks, ts, _ = get_latest_layout()
            text = build_main_menu_text(students_map, ts)
            kb = build_main_menu_keyboard()
            send_telegram("editMessageText", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": kb
            })
            answer_callback(cq_id, "Data berhasil diperbarui dari server!")

    elif "message" in upd:
        msg = upd["message"]
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()

        with config_lock:
            if config.get("chat_id") != chat_id:
                config["chat_id"] = chat_id
                save_config(config)

        desks, ts, _ = get_latest_layout()
        menu_text = build_main_menu_text(students_map, ts)
        kb = build_main_menu_keyboard()
        send_telegram("sendMessage", {
            "chat_id": chat_id,
            "text": menu_text,
            "parse_mode": "HTML",
            "reply_markup": kb
        })

def main():
    print("Memulai Furina Denah Watcher Bot...")
    token = config.get("bot_token")

    students_map = get_students_map()

    watcher_thread = threading.Thread(target=background_watcher, daemon=True)
    watcher_thread.start()
    print("Background server watcher aktif.")

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    print("HTTP Health check server aktif.")

    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=25"
            if offset is not None:
                url += f"&offset={offset}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=35) as r:
                res = json.loads(r.read().decode("utf-8"))

            if res.get("ok"):
                for upd in res.get("result", []):
                    upd_id = upd.get("update_id")
                    offset = upd_id + 1
                    try:
                        handle_update(upd, students_map)
                    except Exception as e:
                        print("Error handling update:", e)
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    main()
