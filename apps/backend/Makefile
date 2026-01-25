
.PHONY: generate-schemas

generate-schemas:
	.venv/bin/python -m datamodel_code_generator --input app/api/specs/users.json --output app/schemas/generated/users.py --output-model-type pydantic_v2.BaseModel
	.venv/bin/python -m datamodel_code_generator --input app/api/specs/documents.json --output app/schemas/generated/documents.py --output-model-type pydantic_v2.BaseModel
	.venv/bin/python -m datamodel_code_generator --input app/api/specs/workflows.json --output app/schemas/generated/workflows.py --output-model-type pydantic_v2.BaseModel
	.venv/bin/python -m datamodel_code_generator --input app/api/specs/health.json --output app/schemas/generated/health.py --output-model-type pydantic_v2.BaseModel
