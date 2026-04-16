import type { PlanCode } from "./subscription";

// API service layer for Flask backend communication
const API_BASE = typeof window !== 'undefined'
  ? '/backend'
  : 'http://127.0.0.1:5000';

const MANAGER_BASE = typeof window !== 'undefined'
  ? '/manager'
  : 'http://127.0.0.1:5005';

const SOCKET_BASE = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://127.0.0.1:5000';

export interface Shot {
  id: number;
  x: number;
  y: number;
  score: number;
  ts?: number;
  series?: string;
  center_x?: number;
  center_y?: number;
  dx?: number;
  dy?: number;
  angle?: number;
}

export interface ScoreData {
  status?: string;
  message?: string;
  scored_shots?: Shot[];
  stored_shots?: Shot[];
  stored_total_score?: number;
  total_score?: number;
  image_url?: string;
  target_seq?: number;
  overlapping_shots?: Shot[];
  overlap_count?: number;
  // 🔥 NEW SERIES FIELDS (ADD THESE)
  series?: Record<string, Shot[]>;
  series_totals?: Record<string, number>;
  grand_total?: number;
  current_series?: number;
}

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  subscription_start?: string | null;
  subscription_end?: string | null;
  subscription_id?: string | null;
  plan_type?: PlanCode | null;
  created_at?: string | null;
  updated_at?: string | null;
}

type ApiMessage = {
  success?: boolean;
  message?: string;
  error?: string;
  details?: string;
}

type CurrentUserResponse = ApiMessage & {
  user?: UserProfile;
}

// Fetch with credentials for session support
async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE}${endpoint}`;
  console.log(`[API] ${options.method || 'GET'} ${url}`);
  
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  return response;
}

async function readJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function getErrorMessage(response: Response, fallback: string): Promise<string> {
  const data = await readJson<ApiMessage>(response);
  return data?.error || data?.details || data?.message || fallback;
}

// Authentication
export async function registerUser(username: string, email: string, password: string) {
  return fetchApi('/register', {
    method: 'POST',
    body: JSON.stringify({
      username,
      email,
      password,
    }),
  });
}

export async function login(username: string, password: string, deviceId: string, customIp?: string) {
  return fetchApi('/login', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password,
      device_id: deviceId,
      ...(customIp ? { custom_ip: customIp } : {}),
    }),
  });
}

export async function logout() {
  const response = await fetchApi('/logout', { method: 'GET' });
  return response;
}

export async function getCurrentUser(): Promise<UserProfile | null> {
  try {
    const response = await fetchApi('/api/me');
    if (!response.ok) {
      return null;
    }

    const data = await readJson<CurrentUserResponse>(response);
    return data?.user ?? null;
  } catch {
    return null;
  }
}

export async function updateCurrentUser(data: { username: string; email: string }) {
  return fetchApi('/api/me', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function changeCurrentUserPassword(data: { current_password: string; new_password: string }) {
  return fetchApi('/api/me/password', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function activateCurrentUserSubscription(planCode: PlanCode) {
  return fetchApi('/api/me/subscription', {
    method: 'POST',
    body: JSON.stringify({
      plan_code: planCode,
    }),
  });
}

export async function deleteCurrentUser() {
  return fetchApi('/api/me', {
    method: 'DELETE',
  });
}

// Device & Connection
export async function getSelectedIP(): Promise<{ selected_ip: string } | null> {
  try {
    const response = await fetchApi('/api/selected_ip');
    if (response.ok) {
      return response.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function selectDevice(deviceId: string) {
  const response = await fetchApi('/api/select_ip', {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId }),
  });
  return response;
}

export async function selectDeviceByIp(ip: string) {
  const response = await fetchApi('/api/select_ip_direct', {
    method: 'POST',
    body: JSON.stringify({ ip }),
  });
  return response;
}

// Scoring
export async function getLiveScore(confidence: number = 1.0): Promise<ScoreData> {
  try {
    const response = await fetchApi(`/api/live_score?confidence=${confidence}`);
    if (response.ok) {
      return response.json();
    }
    return { status: 'error', message: 'Failed to fetch score' };
  } catch (error) {
    return { status: 'error', message: String(error) };
  }
}

export async function getStoredShots(): Promise<ScoreData> {
  try {
    const response = await fetchApi('/api/shots');
    if (response.ok) {
      return response.json();
    }
    return { stored_shots: [] };
  } catch {
    return { stored_shots: [] };
  }
}

export async function resetScore() {
  const response = await fetchApi('/api/reset');
  return response;
}

export async function clearShotSession() {
  return fetchApi('/api/clear_shots', { method: 'POST' });
}

export async function nextTarget() {
  const response = await fetchApi('/api/nexttarget');
  return response.json();
}

// Mode switching
export async function setRifleMode() {
  const response = await fetch(`${MANAGER_BASE}/api/rifle`);
  return response;
}

export async function setPistolMode() {
  const response = await fetch(`${MANAGER_BASE}/api/pistol`);
  return response;
}

// Camera controls
export async function focusIncrease() {
  return fetchApi('/api/focus_increase');
}

export async function focusDecrease() {
  return fetchApi('/api/focus_decrease');
}

export async function zoomIncrease() {
  return fetchApi('/api/zoom_increase');
}

export async function zoomDecrease() {
  return fetchApi('/api/zoom_decrease');
}

export async function setBrightness(value: number) {
  return fetchApi(`/api/set_brightness?value=${value}`);
}

// System controls
export async function rebootDevice() {
  return fetchApi('/api/reboot', { method: 'POST' });
}

export async function shutdownApp() {
  return fetchApi('/api/shutdown', { method: 'POST' });
}

export async function sendScoresheet() {
  return fetchApi('/api/send_email', { method: 'POST' });
}

// Data endpoints
export async function getLatestImage(): Promise<string> {
  return `${API_BASE}/api/data?ts=${Date.now()}`;
}

export async function getImageWithTimestamp(ts: number): Promise<string> {
  return `${API_BASE}/latest_image?ts=${ts}`;
}

// Connection check
export async function checkConnection(): Promise<boolean> {
  try {
    const response = await fetchApi('/api/data');
    return response.ok;
  } catch {
    return false;
  }
}

// Email functions for SMTP integration
export async function sendEmailWithScore(data: {
  username: string;
  email: string;
  totalScore: number;
  shots: Shot[];
  mode: 'rifle' | 'pistol';
  date?: string;
  averageScore?: number;
  imageBase64?: string;
  accent?: 'orange' | 'green' | 'blue';
}) {
  try {
    const response = await fetch('/api/send-email', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'score',
        ...data,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to send email');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending score email:', error);
    throw error;
  }
}

export async function sendEmailWithWrap(data: {
  username: string;
  email: string;
  summary: string;
  stats: {
    totalSessions: number;
    totalShots: number;
    averageScore: number;
    bestScore: number;
  };
  date?: string;
  imageData?: string;
}) {
  try {
    const response = await fetch('/api/send-email', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        type: 'wrap',
        ...data,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to send email');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending wrap email:', error);
    throw error;
  }
}

export { API_BASE, SOCKET_BASE };
