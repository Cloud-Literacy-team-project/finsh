"""db/schema.sql 을 DB에 적용한다 (여러 번 해도 안전).  실행: python -m db.init"""
from pathlib import Path

from db.database import connect

sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

with connect() as conn, conn.cursor() as cur:
    for statement in statements:
        cur.execute(statement)
    cur.execute("SHOW TABLES")
    print("표:", [list(row.values())[0] for row in cur.fetchall()])