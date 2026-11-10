"""Pydantic AST Generator HTTP API."""

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ast_gen.compiler import PydanticASTCompiler

app = FastAPI(title="Pydantic AST Generator", version="1.0.0")
comp = PydanticASTCompiler()


class CompileReq(BaseModel):
    """Structured table-to-fields DDL request."""

    table_name: str = Field(..., min_length=1, max_length=128)
    fields: dict[str, str] = Field(..., min_length=1)


class SQLCompileReq(BaseModel):
    """Raw SQL CREATE TABLE statement compilation request."""

    sql: str = Field(..., min_length=10, max_length=20000)


class JSONSchemaCompileReq(BaseModel):
    """JSON Schema compilation request."""

    schema_def: dict[str, Any] = Field(..., alias="schema")

    model_config = {"populate_by_name": True}


@app.get("/health", tags=["Monitoring"])
def health_check() -> dict[str, str]:
    """Liveness check endpoint."""
    return {"status": "healthy"}


@app.post("/api/v1/compile", tags=["AST Compiler"])
def compile_model(req: CompileReq) -> dict[str, str]:
    """Compile table metadata into a Pydantic v2 BaseModel class."""
    try:
        code = comp.compile_ddl_to_pydantic(req.table_name, req.fields)
        return {"generated_python_code": code}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/compile/sql", tags=["AST Compiler"])
def compile_sql_model(req: SQLCompileReq) -> dict[str, str]:
    """Compile a raw SQL CREATE TABLE statement into Pydantic v2 code."""
    try:
        code = comp.compile_sql(req.sql)
        return {"generated_python_code": code}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/compile/json-schema", tags=["AST Compiler"])
def compile_json_schema_model(req: JSONSchemaCompileReq) -> dict[str, str]:
    """Compile a JSON Schema definition into a Pydantic v2 BaseModel class."""
    try:
        code = comp.compile_json_schema(req.schema_def)
        return {"generated_python_code": code}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
