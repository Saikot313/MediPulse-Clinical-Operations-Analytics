"""Thin PostgreSQL helpers: connection, SQL files, bulk COPY, query -> DataFrame."""
import io
import os
from pathlib import Path

import pandas as pd
import psycopg2

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def db_url() -> str:
    return os.getenv("MEDIPULSE_DB_URL", "postgresql://warehouse:warehouse@localhost:5432/medipulse")


def connect(url: str | None = None):
    return psycopg2.connect(url or db_url())


def run_sql_file(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute((SQL_DIR / name).read_text())
    conn.commit()


def query(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def copy_df(conn, table: str, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} ({','.join(df.columns)}) FROM STDIN WITH (FORMAT csv, NULL '')", buf
        )
