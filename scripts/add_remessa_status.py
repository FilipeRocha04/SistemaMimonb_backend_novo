import shutil
import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / 'mimonb.db'
if not db_path.exists():
    print(f"DB not found: {db_path}")
    raise SystemExit(1)
backup = db_path.with_suffix('.db.bak')
shutil.copyfile(db_path, backup)
print(f"Backup created: {backup}")
conn = sqlite3.connect(str(db_path))
try:
    conn.execute("ALTER TABLE pedido_remessas ADD COLUMN status TEXT NOT NULL DEFAULT 'pendente'")
    conn.commit()
    print('ALTER_OK')
except Exception as e:
    print('ALTER_FAILED', e)
finally:
    conn.close()
