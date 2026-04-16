// Session storage for history tracking
import type { Shot } from './api';

export interface SessionData {
  id: string;
  date: string;
  mode: 'rifle' | 'pistol';
  totalScore: number;
  shots: Shot[];
}

// Session mode type
export type SessionMode = 'tournament' | 'training' | 'free_training';

// New interface for series history
export interface SeriesHistoryItem {
  id: string;
  date: string;
  mode: 'rifle' | 'pistol';
  sessionMode: SessionMode;
  shots: Shot[];
  totalScore: number;
  inner10: number;
  imageUrl: string;
}

const SESSIONS_KEY = 'lakshya_sessions';
const CURRENT_SESSION_KEY = 'lakshya_current_session';
const HISTORY_KEY = 'lakshya_history';

function getActiveUsername(): string {
  if (typeof window === 'undefined') return 'guest';
  const username = localStorage.getItem('lakshya_username')?.trim();
  return username || 'guest';
}

function buildUserScopedKey(baseKey: string, username = getActiveUsername()): string {
  return `${baseKey}_${username}`;
}

function getSessionsKey(username?: string): string {
  return buildUserScopedKey(SESSIONS_KEY, username);
}

function getCurrentSessionKey(username?: string): string {
  return buildUserScopedKey(CURRENT_SESSION_KEY, username);
}

function getHistoryKey(username?: string): string {
  return buildUserScopedKey(HISTORY_KEY, username);
}

export function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

export function generateHistoryId(): string {
  return `history_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

export function getCurrentSession(): SessionData | null {
  if (typeof window === 'undefined') return null;
  const data = localStorage.getItem(getCurrentSessionKey());
  return data ? JSON.parse(data) : null;
}

export function startNewSession(mode: 'rifle' | 'pistol'): SessionData {
  const session: SessionData = {
    id: generateSessionId(),
    date: new Date().toISOString(),
    mode,
    totalScore: 0,
    shots: [],
  };
  localStorage.setItem(getCurrentSessionKey(), JSON.stringify(session));
  return session;
}

export function updateCurrentSession(shots: Shot[], totalScore: number): void {
  const current = getCurrentSession();
  if (current) {
    current.shots = shots;
    current.totalScore = totalScore;
    localStorage.setItem(getCurrentSessionKey(), JSON.stringify(current));
  }
}

export function clearCurrentSession(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(getCurrentSessionKey());
}

export function saveCurrentSession(): void {
  const current = getCurrentSession();
  if (current && current.shots.length > 0) {
    const sessions = getAllSessions();
    sessions.unshift(current); // Add to beginning
    localStorage.setItem(getSessionsKey(), JSON.stringify(sessions.slice(0, 50))); // Keep last 50 sessions
  }
  localStorage.removeItem(getCurrentSessionKey());
}

export function getAllSessions(): SessionData[] {
  if (typeof window === 'undefined') return [];
  const data = localStorage.getItem(getSessionsKey());
  return data ? JSON.parse(data) : [];
}

export function getSessionById(id: string): SessionData | null {
  const sessions = getAllSessions();
  return sessions.find(s => s.id === id) || null;
}

export function clearAllSessions(): void {
  localStorage.removeItem(getSessionsKey());
  localStorage.removeItem(getCurrentSessionKey());
}

export function deleteSession(id: string): void {
  const sessions = getAllSessions();
  const filtered = sessions.filter(s => s.id !== id);
  localStorage.setItem(getSessionsKey(), JSON.stringify(filtered));
}

// ==================== SERIES HISTORY FUNCTIONS ====================

/**
 * Save a completed series to history
 */
export function saveSeriesToHistory(
  shots: Shot[],
  mode: 'rifle' | 'pistol',
  imageUrl: string,
  sessionMode: SessionMode = 'training'
): SeriesHistoryItem {
  const totalScore = shots.reduce((sum, shot) => sum + (shot.score || 0), 0);
  const inner10 = shots.filter(shot => shot.score >= 10).length;
  
  const historyItem: SeriesHistoryItem = {
    id: generateHistoryId(),
    date: new Date().toISOString(),
    mode,
    sessionMode,
    shots: shots.map((shot, index) => ({
      ...shot,
      id: shot.id || index + 1,
    })),
    totalScore,
    inner10,
    imageUrl,
  };
  
  const history = getAllHistory();
  history.unshift(historyItem); // Add to beginning (newest first)
  
  // Keep last 100 history items
  localStorage.setItem(getHistoryKey(), JSON.stringify(history.slice(0, 100)));
  
  return historyItem;
}

/**
 * Get all series history (newest first)
 */
export function getAllHistory(): SeriesHistoryItem[] {
  if (typeof window === 'undefined') return [];
  const data = localStorage.getItem(getHistoryKey());
  return data ? JSON.parse(data) : [];
}

/**
 * Get a specific history item by ID
 */
export function getHistoryById(id: string): SeriesHistoryItem | null {
  const history = getAllHistory();
  return history.find(h => h.id === id) || null;
}

/**
 * Delete a specific history item
 */
export function deleteHistoryItem(id: string): void {
  const history = getAllHistory();
  const filtered = history.filter(h => h.id !== id);
  localStorage.setItem(getHistoryKey(), JSON.stringify(filtered));
}

/**
 * Clear all history
 */
export function clearAllHistory(): void {
  localStorage.removeItem(getHistoryKey());
}

export function migrateUserSessionStore(oldUsername: string, newUsername: string): void {
  if (typeof window === 'undefined') return;

  const fromUser = oldUsername.trim();
  const toUser = newUsername.trim();
  if (!fromUser || !toUser || fromUser === toUser) return;

  const keyPairs: Array<[string, string]> = [
    [getSessionsKey(fromUser), getSessionsKey(toUser)],
    [getCurrentSessionKey(fromUser), getCurrentSessionKey(toUser)],
    [getHistoryKey(fromUser), getHistoryKey(toUser)],
  ];

  keyPairs.forEach(([fromKey, toKey]) => {
    const existing = localStorage.getItem(fromKey);
    if (existing !== null) {
      localStorage.setItem(toKey, existing);
      localStorage.removeItem(fromKey);
    }
  });
}
