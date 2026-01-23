/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $UserProfile = {
    properties: {
        id: {
            type: 'string',
            description: `Supabase User ID`,
            isRequired: true,
        },
        email: {
            type: 'string',
            isRequired: true,
            format: 'email',
        },
        full_name: {
            type: 'string',
            isRequired: true,
            isNullable: true,
        },
        created_at: {
            type: 'string',
            isRequired: true,
            format: 'date-time',
        },
    },
} as const;
