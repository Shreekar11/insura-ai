.PHONY: generate-frontend-schemas

SPEC_DIR = specs
OUTPUT_DIR = schema/generated

generate-frontend-schemas:
	pnpm dlx openapi-typescript-codegen \
		--input $(SPEC_DIR)/users.json \
		--output $(OUTPUT_DIR)/users \
		--exportSchemas true

	pnpm dlx openapi-typescript-codegen \
		--input $(SPEC_DIR)/documents.json \
		--output $(OUTPUT_DIR)/documents \
		--exportSchemas true

	pnpm dlx openapi-typescript-codegen \
		--input $(SPEC_DIR)/workflows.json \
		--output $(OUTPUT_DIR)/workflows \
		--exportSchemas true

	pnpm dlx openapi-typescript-codegen \
		--input $(SPEC_DIR)/citations.json \
		--output $(OUTPUT_DIR)/citations \
		--exportSchemas true

	pnpm dlx openapi-typescript-codegen \
		--input $(SPEC_DIR)/query.json \
		--output $(OUTPUT_DIR)/query \
		--exportSchemas true
