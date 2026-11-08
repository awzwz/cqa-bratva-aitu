"""Copy every CQA table from one database to another (e.g. local SQLite -> cluster PostgreSQL).

    python scripts/migrate_sqlite_to_pg.py sqlite:///data/cqa.db postgresql+psycopg://cqa:...@127.0.0.1:15432/cqa

The target is wiped table by table first, so run it only to seed a fresh deployment.
"""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, func, select, text

from cqa.db import Base


def main(src_url: str, dst_url: str) -> None:
    src, dst = create_engine(src_url), create_engine(dst_url)
    Base.metadata.create_all(dst)
    tables = Base.metadata.sorted_tables
    with src.connect() as s, dst.begin() as d:
        for t in reversed(tables):
            d.execute(t.delete())
        for t in tables:
            rows = [dict(r._mapping) for r in s.execute(select(t))]
            for i in range(0, len(rows), 500):
                d.execute(t.insert(), rows[i:i + 500])
            print(f"{t.name}: {len(rows)}")
        if dst.dialect.name == "postgresql":
            for t in tables:
                if "id" in t.c and t.c.id.autoincrement is not False:
                    mx = d.execute(select(func.max(t.c.id))).scalar() or 0
                    d.execute(text(f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), :v, :called)"), {"v": max(mx, 1), "called": mx > 0})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
