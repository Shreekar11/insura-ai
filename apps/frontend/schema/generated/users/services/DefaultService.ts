/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse } from '../models/ApiResponse';
import type { UserProfile } from '../models/UserProfile';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Get current user profile
     * @returns any User profile retrieved successfully
     * @throws ApiError
     */
    public static getWhoami(): CancelablePromise<(ApiResponse & {
        data?: UserProfile;
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/users/whoami',
            errors: {
                401: `Unauthorized`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Sync user with database
     * @returns any User synced successfully
     * @throws ApiError
     */
    public static syncUser(): CancelablePromise<(ApiResponse & {
        data?: UserProfile;
    })> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/users/sync',
            errors: {
                401: `Unauthorized`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Logout user
     * @returns any Logged out successfully
     * @throws ApiError
     */
    public static logoutUser(): CancelablePromise<(ApiResponse & {
        data?: {
            message?: string;
        };
    })> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/users/logout',
            errors: {
                500: `Internal server error`,
            },
        });
    }
}
