const SERVER_URL_KEY = "ze_server_url";
const API_KEY_KEY = "ze_api_key";

export interface AppConfig {
  serverUrl: string;
  apiKey: string;
}

export function getConfig(): AppConfig | null {
  const serverUrl = localStorage.getItem(SERVER_URL_KEY);
  const apiKey = localStorage.getItem(API_KEY_KEY);
  if (!serverUrl || !apiKey) return null;
  return { serverUrl, apiKey };
}

export function saveConfig(config: AppConfig) {
  localStorage.setItem(SERVER_URL_KEY, config.serverUrl);
  localStorage.setItem(API_KEY_KEY, config.apiKey);
}

export function clearConfig() {
  localStorage.removeItem(SERVER_URL_KEY);
  localStorage.removeItem(API_KEY_KEY);
}

export function hasConfig(): boolean {
  return !!localStorage.getItem(SERVER_URL_KEY) && !!localStorage.getItem(API_KEY_KEY);
}
