import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, BASE_URL } from "@/lib/http";
import type { FileListOut, UploadScope } from "@/types/uploads";

// Files attached to a chat session, keyed so message chips can group by message_id
export function useSessionFiles(sessionId: string | null): ReturnType<typeof useQuery<FileListOut>> {
	return useQuery({
		queryKey: ["uploads", "session", sessionId],
		queryFn: async () => apiClient.get<FileListOut>(`/api/uploads?scope=session&session_id=${sessionId ?? ""}`),
		enabled: sessionId !== null,
	});
}

// A user's personal library (global) or the admin-managed shared library
export function useLibraryFiles(scope: Exclude<UploadScope, "session">): ReturnType<typeof useQuery<FileListOut>> {
	return useQuery({
		queryKey: ["uploads", scope],
		queryFn: async () => apiClient.get<FileListOut>(`/api/uploads?scope=${scope}`),
	});
}

export function useDeleteUpload(): ReturnType<typeof useMutation<undefined, Error, string>> {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async (fileId: string) => apiClient.delete<undefined>(`/api/uploads/${fileId}`),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: ["uploads"] });
		},
	});
}

// Absolute URL for a stored file's bytes; used as an <a download> href
export function uploadContentUrl(fileId: string): string {
	return `${BASE_URL}/api/uploads/${fileId}/content`;
}
