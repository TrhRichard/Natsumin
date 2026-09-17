from __future__ import annotations

from typing import overload, Literal

MISSING = object()

__all__ = ["select", "insert", "update", "sanitize"]


class QueryBuilder:
	@overload
	def build(self, include_params: Literal[True] = ...) -> tuple[str, list]: ...
	@overload
	def build(self, include_params: Literal[False]) -> str: ...
	def build(self, include_params: bool = True) -> tuple[str, list] | str:
		raise NotImplementedError()

	def __str__(self):
		return self.build(False)


class SelectQuery(QueryBuilder):
	def __init__(self, table: str, alias: str | None = None):
		self.table = table
		self.alias = alias
		self._columns: list[str | tuple[str, list]] = []
		self._joins: list[tuple[str, list]] = []
		self._where: list[tuple[str, list]] = []
		self._order_by: list[str] = []
		self._group_by: list[str] = []
		self._having: list[tuple[str, list]] = []
		self._limit: int | None = None
		self._offset: int | None = None

	def columns(self, *exprs: str) -> SelectQuery:
		self._columns.extend(exprs)
		return self

	def column(self, expr: str, *params) -> SelectQuery:
		self._columns.append((expr, list(params)))
		return self

	def join(self, expr: str, *params, kind: str = "LEFT JOIN") -> SelectQuery:
		self._joins.append((f"{kind} {expr}", list(params)))
		return self

	def where(self, expr: str, *params, cond: bool = MISSING) -> SelectQuery:
		if cond is not MISSING and not cond:
			return self
		self._where.append((expr, list(params)))
		return self

	def group_by(self, *exprs: str) -> SelectQuery:
		self._group_by.extend(exprs)
		return self

	def having(self, expr: str, *params) -> SelectQuery:
		self._having.append((expr, list(params)))
		return self

	def order_by(self, *exprs: str) -> SelectQuery:
		self._order_by.extend([str(expr) for expr in exprs])
		return self

	def limit(self, limit: int, offset: int = MISSING) -> SelectQuery:
		if offset is not MISSING:
			self._offset = offset
		self._limit = limit
		return self

	def offset(self, offset: int) -> SelectQuery:
		self._offset = offset
		return self

	def build(self, include_params: bool = True) -> tuple[str, list] | str:
		col_exprs = [c if isinstance(c, str) else c[0] for c in self._columns]
		select_clause = ", ".join(col_exprs) if col_exprs else "*"
		from_clause = f"{self.table} {self.alias}" if self.alias else self.table

		parts = [f"SELECT {select_clause}", f"FROM {from_clause}"]
		params: list = []

		for c in self._columns:
			if not isinstance(c, str):
				_, col_params = c
				params.extend(col_params)

		for join_sql, join_params in self._joins:
			parts.append(join_sql)
			params.extend(join_params)

		if self._where:
			where_exprs = [f"({w})" for w, _ in self._where]
			parts.append(f"WHERE {' AND '.join(where_exprs)}")
			for _, where_params in self._where:
				params.extend(where_params)

		if self._group_by:
			parts.append(f"GROUP BY {', '.join(self._group_by)}")

		if self._having:
			having_exprs = [h for h, _ in self._having]
			parts.append(f"HAVING {' AND '.join(having_exprs)}")
			for _, having_params in self._having:
				params.extend(having_params)

		if self._order_by:
			parts.append(f"ORDER BY {', '.join(self._order_by)}")
		if self._limit is not None:
			if self._offset is not None:
				parts.append(f"LIMIT {self._limit} OFFSET {self._offset}")
			else:
				parts.append(f"LIMIT {self._limit}")

		sql = "\n".join(parts)
		return (sql, params) if include_params else sql


class InsertQuery(QueryBuilder):
	def __init__(self, table: str):
		self.table = table
		self._columns: list[str] = []
		self._params: list = []
		self._returning: list[str] = []
		self._or: str | None = None

	def values(self, **columns: dict[str]) -> InsertQuery:
		for col, val in columns.items():
			self._columns.append(col)
			self._params.append(val)
		return self

	def or_(self, clause: str) -> InsertQuery:
		self._or = clause
		return self

	def returning(self, *exprs: str) -> InsertQuery:
		self._returning.extend(exprs)
		return self

	def build(self, include_params: bool = True) -> tuple[str, list] | str:
		or_clause = f" OR {self._or}" if self._or else ""
		col_list = ", ".join(self._columns)
		placeholders = ", ".join("?" for _ in self._columns)

		parts = [f"INSERT{or_clause} INTO {self.table} ({col_list})", f"VALUES ({placeholders})"]
		if self._returning:
			parts.append(f"RETURNING {', '.join(self._returning)}")

		sql = "\n".join(parts)
		return (sql, self._params) if include_params else sql


class UpdateQuery(QueryBuilder):
	def __init__(self, table: str):
		self.table = table
		self._set: list[tuple[str, list]] = []
		self._where: list[tuple[str, list]] = []
		self._returning: list[str] = []

	def set(self, column: str, value, *, cond: bool = MISSING) -> UpdateQuery:
		if cond is not MISSING and not cond:
			return self
		self._set.append((f"{column} = ?", [value]))
		return self

	def sets(self, **columns: dict[str]) -> UpdateQuery:
		for column, value in columns.items():
			self._set.append((f"{column} = ?", [value]))
		return self

	def where(self, expr: str, *params, cond: bool = MISSING) -> UpdateQuery:
		if cond is not MISSING and not cond:
			return self
		self._where.append((expr, list(params)))
		return self

	def returning(self, *exprs: str) -> UpdateQuery:
		self._returning.extend(exprs)
		return self

	def build(self, include_params: bool = True) -> tuple[str, list] | str:
		set_exprs = [s for s, _ in self._set]
		parts: list[str] = [f"UPDATE {self.table}", f"SET {', '.join(set_exprs)}"]
		params: list = []
		for _, set_params in self._set:
			params.extend(set_params)

		if self._where:
			where_exprs = [w for w, _ in self._where]
			parts.append(f"WHERE {' AND '.join(where_exprs)}")
			for _, where_params in self._where:
				params.extend(where_params)

		if self._returning:
			parts.append(f"RETURNING {', '.join(self._returning)}")

		sql = "\n".join(parts)
		return (sql, params) if include_params else sql


def select(table: str, alias: str | None = None) -> SelectQuery:
	return SelectQuery(table, alias)


def insert(table: str) -> InsertQuery:
	return InsertQuery(table)


def update(table: str) -> UpdateQuery:
	return UpdateQuery(table)


def sanitize(query: str) -> str:
	return query.replace("%", "\\%").replace("_", "\\_")
