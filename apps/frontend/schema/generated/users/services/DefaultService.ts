/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserProfile } from '../models/UserProfile';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Get current user profile
     * @returns UserProfile User profile retrieved successfully
     * @throws ApiError
     */
    public static getWhoami(): CancelablePromise<UserProfile> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/users/whoami',
            errors: {
                401: `Unauthorized`,
            },
        });
    }
    /**
     * Sync user with database
     * @returns UserProfile User synced successfully
     * @throws ApiError
     */
    public static syncUser(): CancelablePromise<UserProfile> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/users/sync',
            errors: {
                401: `Unauthorized`,
            },
        });
    }
    /**
     * Logout user
     * @returns any Logged out successfully
     * @throws ApiError
     */
    public static logoutUser(): CancelablePromise<{
        message?: string;
        status?: string;
    }> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/users/logout',
        });
    }
}
