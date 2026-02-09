/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $EventLogItem = {
    properties: {
        event_type: {
            type: 'string',
        },
        event_payload: {
            type: 'dictionary',
            contains: {
                properties: {
                },
            },
            isNullable: true,
        },
        created_at: {
            type: 'string',
            format: 'date-time',
        },
    },
} as const;
