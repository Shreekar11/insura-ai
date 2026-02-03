import axios from "axios";
import { OpenAPI as WorkflowsOpenAPI } from "@/schema/generated/workflows";
import { OpenAPI as UsersOpenAPI } from "@/schema/generated/users";
import { OpenAPI as DocumentsOpenAPI } from "@/schema/generated/documents";
import { OpenAPI as CitationsOpenAPI } from "@/schema/generated/citations";
import { createClient } from "@/utils/supabase/client";

// Default base URL
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_VERSION = "/api/v1";

const supabase = createClient();

const configureOpenAPI = (OpenAPI: any) => {
  OpenAPI.BASE = BASE_URL;
  OpenAPI.TOKEN = async () => {
    if (typeof window !== "undefined") {
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        localStorage.setItem("access_token", session.access_token);
        localStorage.setItem("refresh_token", session.refresh_token);
        return session.access_token;
      }
      return localStorage.getItem("access_token") || "";
    }
    return "";
  };
};

configureOpenAPI(WorkflowsOpenAPI);
configureOpenAPI(UsersOpenAPI);
configureOpenAPI(DocumentsOpenAPI);
configureOpenAPI(CitationsOpenAPI);

export const api = axios.create({
  baseURL: `${BASE_URL}${API_VERSION}`,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use(
  async (config) => {
    // Get token from storage
    const token =
      typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// Response interceptor for handling 401s
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If the error is 401 and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Attempt to refresh the session
        const { data: { session }, error: refreshError } = await supabase.auth.refreshSession();

        if (refreshError || !session) {
          // If refresh fails, clear tokens and redirect to sign-in
          if (typeof window !== "undefined") {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
            localStorage.removeItem("user_data");
            window.location.href = "/sign-in";
          }
          return Promise.reject(error);
        }

        // Update localStorage with new tokens
        localStorage.setItem("access_token", session.access_token);
        localStorage.setItem("refresh_token", session.refresh_token);

        // Update the header and retry the request
        originalRequest.headers.Authorization = `Bearer ${session.access_token}`;
        return api(originalRequest);
      } catch (refreshCatchError) {
        return Promise.reject(refreshCatchError);
      }
    }

    return Promise.reject(error);
  }
);
