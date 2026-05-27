from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


class DuckDBResearchReader:
    def __init__(self, duckdb_path: Path) -> None:
        self.duckdb_path = duckdb_path

    def query(self, sql: str) -> pd.DataFrame:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as conn:
            return conn.execute(sql).fetchdf()

    def list_tables(self) -> list[str]:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as conn:
            rows = conn.execute("show tables").fetchall()
        return [row[0] for row in rows]

    def sample_table(self, table_name: str, limit: int = 10, order_by: str | None = None) -> pd.DataFrame:
        clause = order_by or "1"
        sql = f"""
        select *
        from {table_name}
        order by {clause}
        limit {int(limit)}
        """
        return self.query(sql)

    def sample_daily_base(self, limit: int = 10) -> pd.DataFrame:
        sql = f"""
        select *
        from daily_base
        order by trade_date desc, ts_code asc
        limit {int(limit)}
        """
        return self.query(sql)

    def get_stock_history(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        filters: list[str] = [f"ts_code = '{ts_code}'"]
        if start_date:
            filters.append(f"trade_date >= '{start_date}'")
        if end_date:
            filters.append(f"trade_date <= '{end_date}'")

        where_clause = " and ".join(filters)
        sql = f"""
        select *
        from daily_base
        where {where_clause}
        order by trade_date asc
        """
        return self.query(sql)

    def get_cross_section(self, trade_date: str, columns: list[str] | None = None, limit: int | None = None) -> pd.DataFrame:
        select_columns = "*" if not columns else ", ".join(columns)
        limit_clause = "" if limit is None else f"limit {int(limit)}"
        sql = f"""
        select {select_columns}
        from daily_base
        where trade_date = '{trade_date}'
        order by ts_code asc
        {limit_clause}
        """
        return self.query(sql)

    def get_tradable_cross_section(self, trade_date: str, tradable_only: bool = True, limit: int | None = None) -> pd.DataFrame:
        filters = [f"trade_date = '{trade_date}'"]
        if tradable_only:
            filters.append("is_tradable = true")
        where_clause = " and ".join(filters)
        limit_clause = "" if limit is None else f"limit {int(limit)}"
        sql = f"""
        select *
        from tradable_daily_base
        where {where_clause}
        order by ts_code asc
        {limit_clause}
        """
        return self.query(sql)

    def get_fundamental_history(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        filters: list[str] = [f"ts_code = '{ts_code}'"]
        if start_date:
            filters.append(f"trade_date >= '{start_date}'")
        if end_date:
            filters.append(f"trade_date <= '{end_date}'")
        where_clause = " and ".join(filters)
        sql = f"""
        select *
        from daily_fundamental_base
        where {where_clause}
        order by trade_date asc
        """
        return self.query(sql)

    def get_benchmark_history(self, ts_code: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
        filters: list[str] = [f"ts_code = '{ts_code}'"]
        if start_date:
            filters.append(f"trade_date >= '{start_date}'")
        if end_date:
            filters.append(f"trade_date <= '{end_date}'")
        where_clause = " and ".join(filters)
        sql = f"""
        select *
        from index_daily
        where {where_clause}
        order by trade_date asc
        """
        return self.query(sql)
