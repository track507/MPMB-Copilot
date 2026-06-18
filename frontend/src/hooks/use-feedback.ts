import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { MessageFeedback } from "@/types/session";

interface SetFeedbackVars {
	readonly messageId: string;
	readonly rating: "up" | "down";
	readonly note?: string | undefined;
}

export function useSetFeedback(sessionId: string): ReturnType<typeof useMutation<MessageFeedback, Error, SetFeedbackVars>> {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async ({ messageId, rating, note }: SetFeedbackVars) =>
			apiClient.put<MessageFeedback>(`/api/sessions/${sessionId}/messages/${messageId}/feedback`, { rating, note }),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: ["sessions", sessionId] });
		},
	});
}

export function useClearFeedback(sessionId: string): ReturnType<typeof useMutation<undefined, Error, string>> {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async (messageId: string) => apiClient.delete<undefined>(`/api/sessions/${sessionId}/messages/${messageId}/feedback`),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: ["sessions", sessionId] });
		},
	});
}
