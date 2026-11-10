"""Real Python AST-based compiler generating Pydantic v2 models from SQL DDL and JSON Schema."""

from __future__ import annotations

import ast
import keyword
import re
from typing import Any

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\.)?\"?([A-Za-z_][A-Za-z0-9_]*)\"?\s*\((.*)\)\s*;?",
    re.IGNORECASE | re.DOTALL,
)
_SQL_CONSTRAINTS = frozenset(
    {"PRIMARY", "CONSTRAINT", "UNIQUE", "FOREIGN", "CHECK", "INDEX", "KEY"}
)


def _to_pascal_case(name: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name.strip()) if p]
    if not parts:
        raise ValueError(f"Invalid model name: {name!r}")
    class_name = "".join(p[:1].upper() + p[1:] for p in parts)
    if class_name[0].isdigit() or keyword.iskeyword(class_name):
        class_name = f"Model{class_name}"
    return class_name


def _validate_field_name(name: str) -> str:
    cleaned = name.strip().strip('"').strip("`")
    if not _IDENT_RE.match(cleaned) or keyword.iskeyword(cleaned):
        raise ValueError(f"Invalid Python field identifier: {name!r}")
    return cleaned


def _split_sql_columns(body: str) -> list[str]:
    """Split comma-separated SQL column definitions while respecting nested parentheses."""
    items: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        elif ch == "," and depth == 0:
            chunk = "".join(buf).strip()
            if chunk:
                items.append(chunk)
            buf.clear()
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    return items


def _sql_type_to_python(sql_spec: str) -> tuple[str, set[tuple[str, str]], bool]:
    """Map SQL type declaration to (python_type_expr, required_imports, is_optional)."""
    upper = sql_spec.upper()
    is_not_null = "NOT NULL" in upper or "PRIMARY KEY" in upper
    is_optional = ("NULLABLE" in upper or "NULL" in upper) and not is_not_null

    # Strip type parameters like VARCHAR(255) or NUMERIC(10, 2) for clean matching
    base = re.sub(r"\(.*?\)", "", upper).strip()
    imports: set[tuple[str, str]] = set()

    if any(tok in base for tok in ("BOOL", "BOOLEAN")):
        py_type = "bool"
    elif any(tok in base for tok in ("BIGINT", "SMALLINT", "INT", "SERIAL")):
        py_type = "int"
    elif any(tok in base for tok in ("REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL")):
        py_type = "float"
    elif "TIMESTAMP" in base or "DATETIME" in base:
        py_type = "datetime"
        imports.add(("datetime", "datetime"))
    elif re.search(r"\bDATE\b", base):
        py_type = "date"
        imports.add(("datetime", "date"))
    elif any(tok in base for tok in ("JSON", "JSONB")):
        py_type = "dict[str, Any]"
        imports.add(("typing", "Any"))
    elif any(tok in base for tok in ("TEXT", "VARCHAR", "CHAR", "UUID")):
        py_type = "str"
    else:
        py_type = "str"

    return py_type, imports, is_optional


def _build_field_ast(
    field_name: str,
    type_expr: str,
    optional: bool = False,
    field_kwargs: dict[str, Any] | None = None,
) -> ast.AnnAssign:
    annotation_src = f"{type_expr} | None" if optional else type_expr
    annotation = ast.parse(annotation_src, mode="eval").body

    value: ast.expr | None = None
    if field_kwargs:
        keywords = [
            ast.keyword(arg=k, value=ast.Constant(value=v)) for k, v in field_kwargs.items()
        ]
        if optional and "default" not in field_kwargs:
            keywords.insert(0, ast.keyword(arg="default", value=ast.Constant(value=None)))
        value = ast.Call(func=ast.Name(id="Field", ctx=ast.Load()), args=[], keywords=keywords)
    elif optional:
        value = ast.Constant(value=None)

    return ast.AnnAssign(
        target=ast.Name(id=field_name, ctx=ast.Store()),
        annotation=annotation,
        value=value,
        simple=1,
    )


def _render_module(
    class_name: str,
    field_nodes: list[ast.AnnAssign],
    extra_imports: set[tuple[str, str]],
    use_field: bool = False,
) -> str:
    imports: list[ast.stmt] = []
    for mod in sorted({m for m, _ in extra_imports}):
        names = sorted(sym for m, sym in extra_imports if m == mod)
        imports.append(ast.ImportFrom(module=mod, names=[ast.alias(name=n) for n in names], level=0))

    pydantic_names = ["BaseModel", "Field"] if use_field else ["BaseModel"]
    imports.append(
        ast.ImportFrom(
            module="pydantic",
            names=[ast.alias(name=n) for n in pydantic_names],
            level=0,
        )
    )

    body: list[ast.stmt] = list(field_nodes) if field_nodes else [ast.Pass()]
    cls_def = ast.ClassDef(
        name=class_name,
        bases=[ast.Name(id="BaseModel", ctx=ast.Load())],
        keywords=[],
        body=body,
        decorator_list=[],
    )
    module = ast.Module(body=[*imports, cls_def], type_ignores=[])
    ast.fix_missing_locations(module)
    rendered = ast.unparse(module)
    # Validate syntactic soundness via ast.parse roundtrip
    ast.parse(rendered)
    return rendered


class PydanticASTCompiler:
    """Compiles SQL DDL mappings, raw CREATE TABLE statements, and JSON Schemas via Python AST."""

    def compile_ddl_to_pydantic(
        self,
        table_name: str,
        fields: dict[str, str],
    ) -> str:
        """Compile a table_name and column-type mapping into Pydantic v2 source code."""
        if not fields:
            raise ValueError("fields mapping must not be empty")

        class_name = _to_pascal_case(table_name)
        extra_imports: set[tuple[str, str]] = set()
        field_nodes: list[ast.AnnAssign] = []

        for raw_col, sql_spec in fields.items():
            col_name = _validate_field_name(raw_col)
            py_type, req_imports, is_optional = _sql_type_to_python(sql_spec)
            extra_imports.update(req_imports)
            field_nodes.append(_build_field_ast(col_name, py_type, optional=is_optional))

        return _render_module(class_name, field_nodes, extra_imports)

    def compile_sql(self, ddl: str) -> str:
        """Parse a raw SQL CREATE TABLE statement and emit a Pydantic v2 BaseModel."""
        cleaned = re.sub(r"--[^\n]*", "", ddl).strip()
        match = _CREATE_TABLE_RE.match(cleaned)
        if not match:
            raise ValueError("Expected a valid SQL CREATE TABLE statement")

        table_name = match.group(1)
        body = match.group(2)
        field_map: dict[str, str] = {}

        for clause in _split_sql_columns(body):
            tokens = clause.split()
            if not tokens:
                continue
            head = tokens[0].strip('"').strip("`").upper()
            if head in _SQL_CONSTRAINTS:
                continue
            col_name = _validate_field_name(tokens[0])
            col_spec = " ".join(tokens[1:]) if len(tokens) > 1 else "TEXT"
            # Columns without explicit NOT NULL or PRIMARY KEY default to optional
            upper_spec = col_spec.upper()
            if "NOT NULL" not in upper_spec and "PRIMARY KEY" not in upper_spec:
                col_spec = f"{col_spec} NULL"
            field_map[col_name] = col_spec

        if not field_map:
            raise ValueError("No column definitions found in CREATE TABLE statement")
        return self.compile_ddl_to_pydantic(table_name, field_map)

    def compile_json_schema(self, schema: dict[str, Any]) -> str:
        """Compile a JSON Schema object definition into a validated Pydantic v2 BaseModel."""
        props = schema.get("properties")
        if not isinstance(props, dict) or not props:
            raise ValueError("JSON Schema must define a non-empty 'properties' object")

        class_name = _to_pascal_case(str(schema.get("title") or "GeneratedModel"))
        required_fields = set(schema.get("required") or [])
        extra_imports: set[tuple[str, str]] = set()
        field_nodes: list[ast.AnnAssign] = []
        use_field = False

        json_to_py = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "object": "dict[str, Any]",
            "array": "list[Any]",
        }

        for raw_name, prop_spec in props.items():
            field_name = _validate_field_name(raw_name)
            j_type = prop_spec.get("type", "string")
            if j_type == "array" and isinstance(prop_spec.get("items"), dict):
                inner = json_to_py.get(prop_spec["items"].get("type", "any"), "Any")
                py_type = f"list[{inner}]"
                if inner == "Any":
                    extra_imports.add(("typing", "Any"))
            else:
                py_type = json_to_py.get(j_type, "Any")
                if "Any" in py_type:
                    extra_imports.add(("typing", "Any"))

            kwargs: dict[str, Any] = {}
            for j_key, p_key in (
                ("minLength", "min_length"),
                ("maxLength", "max_length"),
                ("minimum", "ge"),
                ("maximum", "le"),
                ("description", "description"),
            ):
                if j_key in prop_spec:
                    kwargs[p_key] = prop_spec[j_key]

            if kwargs:
                use_field = True
            is_optional = field_name not in required_fields
            field_nodes.append(
                _build_field_ast(
                    field_name,
                    py_type,
                    optional=is_optional,
                    field_kwargs=kwargs or None,
                )
            )

        return _render_module(class_name, field_nodes, extra_imports, use_field=use_field)
