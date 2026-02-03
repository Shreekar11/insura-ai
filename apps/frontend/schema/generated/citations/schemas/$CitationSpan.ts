/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CitationSpan = {
    description: `Represents a continuous span of text on a single page with its location. A citation may span multiple pages.`,
    properties: {
        page_number: {
            type: 'number',
            description: `Page number (1-indexed)`,
            isRequired: true,
            minimum: 1,
        },
        bounding_boxes: {
            type: 'array',
            contains: {
                type: 'BoundingBox',
            },
            isRequired: true,
        },
        text_content: {
            type: 'string',
            description: `The text content for this span`,
            isRequired: true,
        },
    },
} as const;
