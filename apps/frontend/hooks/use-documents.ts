import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface DocumentResponse {
  id: string;
  status: string;
  file_path: string;
  document_name: string | null;
  page_count: number | null;
  created_at: string;
}

interface FailedUpload {
  filename: string;
  error: string;
}

interface MultipleDocumentResponse {
  total_uploaded: number;
  documents: DocumentResponse[];
  failed_uploads: FailedUpload[];
}

interface UploadResponse {
  status: boolean;
  message: string;
  data: MultipleDocumentResponse;
}

interface DocumentsListResponse {
  total: number;
  documents: DocumentResponse[];
}

interface ListResponse {
  status: boolean;
  message: string;
  data: DocumentsListResponse;
}

/**
 * Hook for fetching documents
 */
export const useDocuments = (workflowId?: string) => {
  return useQuery({
    queryKey: ["documents", workflowId],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (workflowId) {
        params.append("workflow_id", workflowId);
      }
      
      const response = await api.get<ListResponse>(`/documents/?${params.toString()}`);
      
      if (!response.data?.status) {
        throw new Error(response.data?.message || "Failed to fetch documents");
      }
      
      return response.data.data;
    },
  });
};

/**
 * Hook for uploading documents to the backend
 */
export const useUploadDocuments = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ files, workflowId }: { files: File[]; workflowId?: string }): Promise<MultipleDocumentResponse> => {
      const formData = new FormData();
      files.forEach((file) => {
        formData.append("files", file);
      });

      if (workflowId) {
        formData.append("workflow_id", workflowId);
      }

      const response = await api.post<UploadResponse>("/documents/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      if (!response.data?.status) {
        throw new Error(response.data?.message || "Failed to upload documents");
      }

      return response.data.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (variables.workflowId) {
        queryClient.invalidateQueries({ queryKey: ["documents", variables.workflowId] });
      }
    },
  });
};

export const useUploadDocument = useUploadDocuments;
