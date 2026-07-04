import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router";
import { toast } from "sonner";
import { z } from "zod";
import { useAuthState, useSetup } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";

const setupSchema = z
	.object({
		username: z.string().min(3, "At least 3 characters").max(64),
		password: z.string().min(10, "At least 10 characters"),
		confirm: z.string(),
		setup_token: z.string().optional(),
	})
	.refine((v) => v.password === v.confirm, { message: "Passwords do not match", path: ["confirm"] });

type SetupFormData = z.infer<typeof setupSchema>;

export default function SetupPage(): ReactElement {
	const { data: authState } = useAuthState();
	const setup = useSetup();
	const navigate = useNavigate();
	const inputClass = cn("w-full rounded-md border border-input bg-background px-3 py-2 text-sm", "focus:outline-none focus:ring-2 focus:ring-ring");

	const {
		register,
		handleSubmit,
		formState: { errors },
	} = useForm<SetupFormData>({ resolver: zodResolver(setupSchema) });

	if (authState?.state === "authenticated") return <Navigate to="/" replace />;
	if (authState?.state === "login_required") return <Navigate to="/login" replace />;

	const tokenRequired = authState?.setup_token_required === true;

	const onSubmit = (data: SetupFormData): void => {
		setup.mutate(
			{ username: data.username, password: data.password, setup_token: data.setup_token ?? undefined },
			{
				onSuccess: () => {
					void navigate("/");
				},
				onError: (e) => {
					toast.error(e.message);
				},
			}
		);
	};

	return (
		<div className="flex h-screen items-center justify-center bg-background">
			<form
				onSubmit={(e) => {
					void handleSubmit(onSubmit)(e);
				}}
				className="w-full max-w-sm space-y-4 rounded-lg border border-border p-6">
				<div>
					<h1 className="text-lg font-semibold">Create the admin account</h1>
					<p className="mt-1 text-xs text-muted-foreground">One-time setup - this account manages users and settings.</p>
				</div>
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
					<input id="password" type="password" autoComplete="new-password" {...register("password")} className={inputClass} />
					{errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
				</div>
				<div className="space-y-2">
					<label htmlFor="confirm" className="text-sm font-medium">
						Confirm password
					</label>
					<input id="confirm" type="password" autoComplete="new-password" {...register("confirm")} className={inputClass} />
					{errors.confirm && <p className="text-xs text-destructive">{errors.confirm.message}</p>}
				</div>
				{tokenRequired && (
					<div className="space-y-2">
						<label htmlFor="setup_token" className="text-sm font-medium">
							Setup token
						</label>
						<p className="text-xs text-muted-foreground">This server is network-exposed; paste the token from the backend logs.</p>
						<input id="setup_token" {...register("setup_token")} className={inputClass} />
					</div>
				)}
				<button
					type="submit"
					disabled={setup.isPending}
					className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50">
					{setup.isPending ? "Creating..." : "Create admin"}
				</button>
			</form>
		</div>
	);
}
