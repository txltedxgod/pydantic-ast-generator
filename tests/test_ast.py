from ast_gen.compiler import PydanticASTCompiler

def test_compiler():
    c = PydanticASTCompiler()
    code = c.compile_ddl_to_pydantic("order", {"id": "INT", "amount": "REAL"})
    assert "class Order(BaseModel):" in code
