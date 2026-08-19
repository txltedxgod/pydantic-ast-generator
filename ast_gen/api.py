from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict
from ast_gen.compiler import PydanticASTCompiler

app = FastAPI(title="Pydantic AST Generator", version="0.1.0")
comp = PydanticASTCompiler()

class CompileReq(BaseModel):
    table_name: str
    fields: Dict[str, str]

@app.post("/api/v1/compile")
def compile_model(req: CompileReq):
    code = comp.compile_ddl_to_pydantic(req.table_name, req.fields)
    return {"generated_python_code": code}
