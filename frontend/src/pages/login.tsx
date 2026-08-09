import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { z } from "zod";
import { useAuthState, useLogin } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";

const loginSchema = z.object({
	username: z.string().min(1, "Username is required"),
	password: z.string().min(1, "Password is required"),
});

type LoginFormData = z.infer<typeof loginSchema>;

export default function LoginPage(): ReactElement {
	const { data: authState } = useAuthState();
	const login = useLogin();
	const navigate = useNavigate();
	const inputClass = cn("w-full rounded-md border border-input bg-background px-3 py-2 text-sm", "focus:outline-none focus:ring-2 focus:ring-ring");

	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<LoginFormData>({ resolver: zodResolver(loginSchema) });

	if (authState?.state === "authenticated") return <Navigate to="/" replace />;
	if (authState?.state === "setup_required") return <Navigate to="/setup" replace />;

	const onSubmit = (data: LoginFormData): void => {
		login.mutate(data, {
			onSuccess: () => {
				void navigate({ to: "/" });
			},
			onError: (e) => {
				toast.error(e.message);
			},
		});
	};

	return (
		<div className="flex h-screen items-center justify-center bg-background">
			<form
				onSubmit={(e) => {
					void handleSubmit(onSubmit)(e);
				}}
				className="w-full max-w-sm space-y-4 rounded-lg border border-border p-6">
				<h1 className="text-lg font-semibold">Sign in to MPMB Copilot</h1>
				<div className="space-y-2">
					<label htmlFor="username" className="text-sm font-medium">
						Username
					</label>
					<input id="username" autoComplete="username" {...register("username")} className={inputClass} />
					{errors.username && <p className="text-xs text-destructive">{errors.username.message}</p>}
				</div>
				<div className="space-y-2">
					<label htmlFor="password" className="text-sm font-medium">
						Password
					</label>
					<input id="password" type="password" autoComplete="current-password" {...register("password")} className={inputClass} />
					{errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
				</div>
				<button
					type="submit"
					disabled={login.isPending}
					className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50">
					{login.isPending ? "Signing in..." : "Sign in"}
				</button>
			</form>
		</div>
	);
}
