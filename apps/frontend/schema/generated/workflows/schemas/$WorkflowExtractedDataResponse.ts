/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $WorkflowExtractedDataResponse = {
    properties: {
        workflow_id: {
            type: 'string',
            format: 'uuid',
        },
        document_id: {
            type: 'string',
            format: 'uuid',
        },
        extracted_data: {
            properties: {
                sections: {
                    type: 'array',
                    contains: {
                        properties: {
                            section_type: {
                                type: 'string',
                            },
                            fields: {
                                type: 'dictionary',
                                contains: {
                                    properties: {
                                    },
                                },
                            },
                            confidence: {
                                type: 'number',
                            },
                        },
                    },
                },
                entities: {
                    type: 'array',
                    contains: {
                        properties: {
                            entity_type: {
                                type: 'string',
                            },
                            fields: {
                                type: 'dictionary',
                                contains: {
                                    properties: {
                                    },
                                },
                            },
                            confidence: {
                                type: 'number',
                            },
                        },
                    },
                },
            },
        },
    },
} as const;
