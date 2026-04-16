// Utility functions for calculating shot directions and angles

export interface ShotDirection {
  arrow: string;
  direction: string;
  angle: number; // 0–360 degrees
}

const DIRECTIONS = [
  { arrow: "↑", direction: "N",  minAngle: 337.5, maxAngle: 22.5 },   // North (wrap)
  { arrow: "↗", direction: "NE", minAngle: 22.5,  maxAngle: 67.5 },   // Northeast
  { arrow: "→", direction: "E",  minAngle: 67.5,  maxAngle: 112.5 },  // East
  { arrow: "↘", direction: "SE", minAngle: 112.5, maxAngle: 157.5 },  // Southeast
  { arrow: "↓", direction: "S",  minAngle: 157.5, maxAngle: 202.5 },  // South
  { arrow: "↙", direction: "SW", minAngle: 202.5, maxAngle: 247.5 },  // Southwest
  { arrow: "←", direction: "W",  minAngle: 247.5, maxAngle: 292.5 },  // West
  { arrow: "↖", direction: "NW", minAngle: 292.5, maxAngle: 337.5 },  // Northwest
];

/**
 * Calculate the direction of a shot relative to target center
 *
 * @param shotX   Shot x-coordinate
 * @param shotY   Shot y-coordinate
 * @param centerX Target center x-coordinate (default 320)
 * @param centerY Target center y-coordinate (default 320)
 */
export function calculateShotDirection(
  shotX: number,
  shotY: number,
  centerX: number = 320,
  centerY: number = 320
): ShotDirection {
  // Relative position from center
  const dx = shotX - centerX;
  const dy = shotY - centerY;

  // Angle from East (0°), counter-clockwise
  // +90° converts it to compass style:
  // 0° = North, 90° = East, 180° = South, 270° = West
  let angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;

  // Normalize to 0–360
  if (angle < 0) {
    angle += 360;
  }
  angle = angle % 360;

  // Find matching compass direction
  let matchedDirection = DIRECTIONS[0]; // Default: North

  for (const dir of DIRECTIONS) {
    if (dir.minAngle <= dir.maxAngle) {
      // Normal range
      if (angle >= dir.minAngle && angle < dir.maxAngle) {
        matchedDirection = dir;
        break;
      }
    } else {
      // Wrap-around range (North)
      if (angle >= dir.minAngle || angle < dir.maxAngle) {
        matchedDirection = dir;
        break;
      }
    }
  }

  return {
    arrow: matchedDirection.arrow,
    direction: matchedDirection.direction,
    angle: Math.round(angle * 10) / 10, // 1 decimal place
  };
}

/**
 * Get Tailwind color class based on direction
 */
export function getDirectionColor(direction: string): string {
  const colorMap: Record<string, string> = {
    N: "text-blue-400",
    NE: "text-cyan-400",
    E: "text-green-400",
    SE: "text-emerald-400",
    S: "text-orange-400",
    SW: "text-rose-400",
    W: "text-pink-400",
    NW: "text-violet-400",
  };

  return colorMap[direction] || "text-foreground";
}
