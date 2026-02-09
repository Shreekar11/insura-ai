import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DefaultService } from "@/schema/generated/users";

/**
 * Custom hook for user-related operations
 */
export const useUsers = () => {
  return useQuery({
    queryKey: ["whoami"],
    queryFn: async () => {
      const response = await DefaultService.getWhoami();
      if (!response?.status) {
        throw new Error("Failed to fetch user profile");
      }
      return response.data;
    },
    staleTime: 1000 * 60 * 60, // 1 hour
    retry: false,
  });
};

/**
 * Hook to sync user with the database after login
 */
export const useSyncUser = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async () => {
      const response = await DefaultService.syncUser();
      if (!response?.status) {
        throw new Error("Failed to sync user with database");
      }
      return response.data;
    },
    onSuccess: (data) => {
      // Invalidate whoami query to refresh user profile
      queryClient.setQueryData(["whoami"], data);
      queryClient.invalidateQueries({ queryKey: ["whoami"] });
    },
  });
};
