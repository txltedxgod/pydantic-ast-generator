import ast
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ast_gen.api import app
from ast_gen.compiler import PydanticASTCompiler


def test_compiler() -> None:
    compiler = PydanticASTCompiler()
    code = compiler.compile_ddl_to_pydantic("order", {"id": "INT", "amount": "REAL"})
    assert "class Order(BaseModel):" in code
    ast.parse(code)


def test_compile_raw_sql_and_execute_generated_model() -> None:
    compiler = PydanticASTCompiler()
    ddl = """
    CREATE TABLE IF NOT EXISTS public.user_orders (
        id BIGSERIAL PRIMARY KEY,
        customer_email VARCHAR(255) NOT NULL,
        total_amount NUMERIC(10, 2) NOT NULL,
        is_paid BOOLEAN,
        metadata JSONB,
        created_at TIMESTAMP NOT NULL
    );
    """
    code = compiler.compile_sql(ddl)
    assert "class UserOrders(BaseModel):" in code

    namespace: dict[str, Any] = {}
    exec(compile(ast.parse(code), "<generated_sql>", "exec"), namespace)
    model_cls = namespace["UserOrders"]

    instance = model_cls(
        id=42,
        customer_email="dev@example.com",
        total_amount=99.95,
        created_at=datetime(2026, 11, 10, 12, 0),
    )
    assert instance.id == 42
    assert instance.is_paid is None
    assert instance.metadata is None


def test_compile_json_schema_with_constraints() -> None:
    compiler = PydanticASTCompiler()
    schema = {
        "title": "api_client_config",
        "type": "object",
        "required": ["client_id", "max_retries"],
        "properties": {
            "client_id": {"type": "string", "minLength": 4, "maxLength": 64},
            "max_retries": {"type": "integer", "minimum": 0, "maximum": 10},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }
    code = compiler.compile_json_schema(schema)
    assert "class ApiClientConfig(BaseModel):" in code

    namespace: dict[str, Any] = {}
    exec(compile(ast.parse(code), "<generated_json>", "exec"), namespace)
    cls = namespace["ApiClientConfig"]

    valid = cls(client_id="svc-alpha", max_retries=3, tags=["prod"])
    assert valid.max_retries == 3

    with pytest.raises(ValidationError):
        cls(client_id="ab", max_retries=99)


def test_http_api_ast_endpoints() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200

    ddl_resp = client.post(
        "/api/v1/compile",
        json={"table_name": "invoice_line", "fields": {"id": "INT NOT NULL", "price": "DECIMAL"}},
    )
    assert ddl_resp.status_code == 200
    assert "class InvoiceLine(BaseModel):" in ddl_resp.json()["generated_python_code"]

    sql_resp = client.post(
        "/api/v1/compile/sql",
        json={"sql": "CREATE TABLE audit_log (id INT PRIMARY KEY, event TEXT NOT NULL);"},
    )
    assert sql_resp.status_code == 200
    assert "class AuditLog(BaseModel):" in sql_resp.json()["generated_python_code"]

    js_resp = client.post(
        "/api/v1/compile/json-schema",
        json={"schema": {"title": "metric", "required": ["name"], "properties": {"name": {"type": "string"}}}},
    )
    assert js_resp.status_code == 200
    assert "class Metric(BaseModel):" in js_resp.json()["generated_python_code"]

    bad_resp = client.post("/api/v1/compile/sql", json={"sql": "SELECT * FROM invalid_statement;"})
    assert bad_resp.status_code == 422
