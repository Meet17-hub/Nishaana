/**
 * Detect the local IP address of the device using WebRTC
 * Returns a promise that resolves to the local IP string
 */
export function detectLocalIP(): Promise<string> {
  return new Promise((resolve) => {
    // Create a temporary RTCPeerConnection to trigger local IP discovery
    const pc = new (window.RTCPeerConnection ||
      (window as any).webkitRTCPeerConnection ||
      (window as any).mozRTCPeerConnection)({
      iceServers: [],
    })

    // Listen for ICE candidates which contain the local IP
    pc.onicecandidate = (ice) => {
      if (!ice || !ice.candidate) {
        pc.close()
        return
      }

      // Parse the candidate string to extract IP
      const ipRegex = /([0-9]{1,3}(\.[0-9]{1,3}){3})/
      const ipAddress = ipRegex.exec(ice.candidate.candidate)

      if (ipAddress) {
        const ip = ipAddress[1]
        // Filter out non-private IPs (exclude 127.0.0.1)
        if (
          ip.startsWith("192.168.") ||
          ip.startsWith("10.") ||
          ip.startsWith("172.")
        ) {
          resolve(ip)
          pc.close()
        }
      }
    }

    // Trigger ICE candidate gathering
    pc.createDataChannel("")
    pc.createOffer().then((offer) => pc.setLocalDescription(offer))

    // Timeout fallback
    setTimeout(() => {
      pc.close()
      resolve("Unable to detect")
    }, 3000)
  })
}
