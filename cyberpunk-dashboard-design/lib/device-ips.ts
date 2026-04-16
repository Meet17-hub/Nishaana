import deviceIpsConfig from "@/config/device-ips.json"

// Device IPs loaded from shared config
export const deviceIps: Record<string, string> = deviceIpsConfig.devices

// Special ID for custom/other IP selection
export const CUSTOM_IP_ID = "custom"

// Local storage key for remembering last custom IP
const CUSTOM_IP_STORAGE_KEY = "lakshya_custom_ip"

// Default octets for custom IP input
export const DEFAULT_CUSTOM_IP_OCTETS = [192, 168, 1, 1]

/**
 * Get device options for the select dropdown
 * Includes all predefined devices plus "Other IP" option
 */
export function getDeviceOptions(): Array<{ id: string; label: string; ip: string }> {
  const options = Object.entries(deviceIps).map(([id, ip]) => ({
    id,
    label: `Device ${id} (${ip})`,
    ip,
  }))

  // Add "Other IP" option at the end
  options.push({
    id: CUSTOM_IP_ID,
    label: "Other IP (Custom)",
    ip: "",
  })

  return options
}

/**
 * Get IP address for a device ID
 * If custom, retrieves from localStorage or returns default
 */
export function getIpForDevice(deviceId: string): string {
  if (deviceId === CUSTOM_IP_ID) {
    return getLastCustomIp()
  }
  return deviceIps[deviceId] || ""
}

/**
 * Check if device ID is the custom option
 */
export function isCustomDevice(deviceId: string): boolean {
  return deviceId === CUSTOM_IP_ID
}

/**
 * Parse IP string into octets array
 */
export function parseIpToOctets(ip: string): number[] {
  const parts = ip.split(".")
  if (parts.length !== 4) {
    return [...DEFAULT_CUSTOM_IP_OCTETS]
  }
  return parts.map((p) => {
    const num = parseInt(p, 10)
    return isNaN(num) ? 0 : Math.min(255, Math.max(0, num))
  })
}

/**
 * Convert octets array back to IP string
 */
export function octetsToIp(octets: number[]): string {
  if (octets.length !== 4) return ""
  return octets
    .map((o) => Math.min(255, Math.max(0, o)))
    .join(".")
}

/**
 * Validate a single octet value (0-255)
 */
export function validateOctet(value: string): number {
  const num = parseInt(value, 10)
  if (isNaN(num)) return 0
  return Math.min(255, Math.max(0, num))
}

/**
 * Save custom IP to localStorage
 */
export function saveCustomIp(ip: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(CUSTOM_IP_STORAGE_KEY, ip)
  }
}

/**
 * Get last used custom IP from localStorage
 */
export function getLastCustomIp(): string {
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem(CUSTOM_IP_STORAGE_KEY)
    if (stored && stored.split(".").length === 4) {
      return stored
    }
  }
  return octetsToIp(DEFAULT_CUSTOM_IP_OCTETS)
}

/**
 * Get last custom IP as octets
 */
export function getLastCustomIpOctets(): number[] {
  return parseIpToOctets(getLastCustomIp())
}
