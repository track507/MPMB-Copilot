/** Mirrors GET /api/auth/state and the login/setup responses */

export interface AuthUser {
	readonly username: string;
	readonly role: string;
}

export interface AuthState {
	readonly state: "setup_required" | "login_required" | "authenticated";
	readonly setup_token_required?: boolean | undefined;
	readonly user?: AuthUser | undefined;
}

export interface LoginRequest {
	readonly username: string;
	readonly password: string;
}

export interface SetupRequest extends LoginRequest {
	readonly setup_token?: string | undefined;
}
