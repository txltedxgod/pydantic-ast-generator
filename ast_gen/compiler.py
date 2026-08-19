from typing import Dict, Any

class PydanticASTCompiler:
    def compile_ddl_to_pydantic(self, table_name: str, fields: Dict[str, str]) -> str:
        lines = [f"class {table_name.capitalize()}(BaseModel):"]
        for k, v in fields.items():
            py_type = "str" if "TEXT" in v or "VARCHAR" in v else "int" if "INT" in v else "float"
            lines.append(f"    {k}: {py_type}")
        return "
".join(lines)
