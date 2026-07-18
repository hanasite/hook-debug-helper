#!/usr/bin/env python3
"""检查 cc-switch SQLite 数据库是否含有 9527 hook 残留，并可选修复。"""
import sqlite3, json, sys, os

DB_PATH = os.path.expanduser("~/.cc-switch/cc-switch.db")

def check():
    if not os.path.exists(DB_PATH):
        print("cc-switch 数据库不存在，跳过检查。")
        return True

    db = sqlite3.connect(DB_PATH)
    row = db.execute("SELECT value FROM settings WHERE key='common_config_claude'").fetchone()
    if not row:
        print("cc-switch 无 common_config_claude 条目，干净。")
        db.close()
        return True

    cfg = json.loads(row[0])
    hooks = cfg.get("hooks", {})
    issues = []

    for event, entries in hooks.items():
        for entry in entries:
            if isinstance(entry, dict):
                for h in entry.get("hooks", []):
                    url = h.get("url", "")
                    type_ = h.get("type", "")
                    cmd = h.get("command", "")
                    if "9527" in url:
                        issues.append(f"[{event}] HTTP hook url={url}")
                    if "Aemeath" in cmd:
                        issues.append(f"[{event}] command hook 含 Aemeath: {cmd[:60]}")

    db.close()

    if issues:
        print("发现以下 9527/Aemeath 残留:")
        for i in issues:
            print(f"  - {i}")
        return False
    else:
        print("cc-switch DB hooks 干净，无 9527 残留。")
        return True

def fix():
    """修复 cc-switch DB 中的 9527 hook"""
    if not os.path.exists(DB_PATH):
        print("cc-switch 数据库不存在，无需修复。")
        return

    db = sqlite3.connect(DB_PATH)
    row = db.execute("SELECT value FROM settings WHERE key='common_config_claude'").fetchone()
    if not row:
        db.close()
        return

    cfg = json.loads(row[0])
    hooks = cfg.get("hooks", {})

    # Remove any entry/hook containing 9527 or Aemeath
    cleaned = {}
    for event, entries in hooks.items():
        clean_entries = []
        for entry in entries:
            clean_subhooks = []
            for h in entry.get("hooks", []):
                if "9527" in h.get("url", "") or "Aemeath" in h.get("command", ""):
                    continue
                clean_subhooks.append(h)
            if clean_subhooks:
                entry["hooks"] = clean_subhooks
                clean_entries.append(entry)
        if clean_entries:
            cleaned[event] = clean_entries

    cfg["hooks"] = cleaned
    db.execute("UPDATE settings SET value=? WHERE key='common_config_claude'",
               (json.dumps(cfg, ensure_ascii=False, indent=2),))
    db.commit()
    db.close()
    print("cc-switch DB 已修复，9527 hook 已移除。")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fix":
        fix()
    else:
        ok = check()
        if not ok:
            print("\n运行 --fix 修复: python3 check-cc-switch.py --fix")
