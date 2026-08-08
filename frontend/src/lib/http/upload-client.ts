import { BASE_URL, toApiError } from "./core";

export async function uploadFile<T>(path: string, file: File, fields: Readonly<Record<string, string>>, onProgress?: (fraction: number) => void): Promise<T> {
	return new Promise<T>((resolve, reject) => {
		const xhr = new XMLHttpRequest();
		xhr.open("POST", `${BASE_URL}${path}`);
		xhr.withCredentials = true;
		xhr.responseType = "json";
		xhr.upload.onprogress = (e) => {
			if (e.lengthComputable) onProgress?.(e.loaded / e.total);
		};
		xhr.onload = () => {
			if (xhr.status >= 200 && xhr.status < 300) {
				resolve(xhr.response as T);
				return;
			}
			reject(toApiError(xhr.status, xhr.response));
		};
		xhr.onerror = () => {
			reject(toApiError(0, null));
		};
		const form = new FormData();
		for (const [key, value] of Object.entries(fields)) form.append(key, value);
		form.append("file", file);
		xhr.send(form);
	});
}
