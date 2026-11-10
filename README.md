# Pydantic AST Generator

[![CI](https://github.com/txltedxgod/pydantic-ast-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/txltedxgod/pydantic-ast-generator/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)

Python 3.11+ AST-driven schema compiler (`ast.Module` / `ast.ClassDef` / `ast.unparse`) generating validated Pydantic v2 models from SQL `CREATE TABLE` DDL and JSON Schema definitions.

## Testing
```bash
ruff check .
pytest -v tests/
```
