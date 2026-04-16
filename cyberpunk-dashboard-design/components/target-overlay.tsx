"use client"

import { useMemo } from "react"
import type { Shot } from "@/lib/api"

interface TargetOverlayProps {
  shots: Shot[]
  hoveredShotId: number | null
  onShotHover: (shotId: number | null) => void
  containerSize: number // 640
  imageWidth?: number
  imageHeight?: number
  zoom?: number
  panX?: number
  panY?: number
}

export default function TargetOverlay({
  shots,
  hoveredShotId,
  onShotHover,
  containerSize = 640,
  imageWidth = 320,
  imageHeight = 320,
  zoom = 1,
  panX = 0,
  panY = 0,
}: TargetOverlayProps) {
  // Scale factor from image coordinates to display coordinates
  const scaleX = containerSize / (imageWidth || 320)
  const scaleY = containerSize / (imageHeight || 320)

  const shotMarkers = useMemo(() => {
    return shots.map((shot, index) => {
      const displayX = shot.x * scaleX
      const displayY = shot.y * scaleY
      const isHovered = hoveredShotId === (shot.id || index)

      return {
        id: shot.id || index,
        x: displayX,
        y: displayY,
        score: shot.score,
        isHovered,
        index,
      }
    })
  }, [shots, hoveredShotId, scaleX, scaleY])

  if (shots.length === 0) return null

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-auto transition-transform duration-200"
      viewBox={`0 0 ${containerSize} ${containerSize}`}
      preserveAspectRatio="xMidYMid slice"
      style={{
        transform: `scale(${zoom}) translate(${panX}px, ${panY}px)`,
        transformOrigin: 'center center',
      }}
    >
      {/* Background for interaction */}
      <rect
        width={containerSize}
        height={containerSize}
        fill="transparent"
        onClick={() => onShotHover(null)}
      />

      {/* Draw all shots */}
      {shotMarkers.map((marker) => {
        const isLatestShot = marker.id === shotMarkers[shotMarkers.length - 1]?.id
        
        return (
          <g key={marker.id}>
            {/* GREEN CIRCLE for LATEST shot (always visible) */}
            {isLatestShot && (
              <circle
                cx={marker.x}
                cy={marker.y}
                r={8}
                fill="#22c55e"
                opacity={1}
              />
            )}

            {/* ORANGE hover visualization for ALL shots */}
            {marker.isHovered && (
              <>
                {/* Large highlight circle */}
                <circle
                  cx={marker.x}
                  cy={marker.y}
                  r={30}
                  fill="none"
                  stroke="#FFA500"
                  strokeWidth="1.5"
                  opacity="0.3"
                  className="animate-pulse"
                />

                {/* Medium glow circle */}
                <circle
                  cx={marker.x}
                  cy={marker.y}
                  r={20}
                  fill="none"
                  stroke="#FFA500"
                  strokeWidth="2"
                  opacity="0.5"
                />

                {/* Crosshair reticle */}
                {/* Horizontal lines */}
                <line
                  x1={marker.x - 35}
                  y1={marker.y}
                  x2={marker.x - 12}
                  y2={marker.y}
                  stroke="#FFA500"
                  strokeWidth="2"
                  opacity="0.8"
                />
                <line
                  x1={marker.x + 12}
                  y1={marker.y}
                  x2={marker.x + 35}
                  y2={marker.y}
                  stroke="#FFA500"
                  strokeWidth="2"
                  opacity="0.8"
                />

                {/* Vertical lines */}
                <line
                  x1={marker.x}
                  y1={marker.y - 35}
                  x2={marker.x}
                  y2={marker.y - 12}
                  stroke="#FFA500"
                  strokeWidth="2"
                  opacity="0.8"
                />
                <line
                  x1={marker.x}
                  y1={marker.y + 12}
                  x2={marker.x}
                  y2={marker.y + 35}
                  stroke="#FFA500"
                  strokeWidth="2"
                  opacity="0.8"
                />

                {/* Orange circle on hover */}
                <circle
                  cx={marker.x}
                  cy={marker.y}
                  r={12}
                  fill="#FFA500"
                  opacity={1}
                />

                {/* Center dot for precision */}
                <circle
                  cx={marker.x}
                  cy={marker.y}
                  r={3}
                  fill="#ffffff"
                  opacity="0.9"
                />

              </>
            )}

            {/* Invisible hitbox for all shots - for interaction */}
            <circle
              cx={marker.x}
              cy={marker.y}
              r={12}
              fill="transparent"
              opacity={0}
              className="cursor-pointer"
              onClick={(e) => {
                e.stopPropagation()
                onShotHover(marker.id)
              }}
              onMouseEnter={() => onShotHover(marker.id)}
              onMouseLeave={() => onShotHover(null)}
            />
          </g>
        )
      })}
    </svg>
  )
}
