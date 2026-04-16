"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { X, ZoomIn, ZoomOut, Focus, Sun, Contrast, Move, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  focusIncrease,
  focusDecrease,
  zoomIncrease,
  zoomDecrease,
  setBrightness,
} from "@/lib/api"
import { useToast } from "@/hooks/use-toast"

interface SettingsModalProps {
  open: boolean
  onClose: () => void
}

// Global display zoom state (persists across modal open/close)
let globalDisplayZoom = 1
let globalPanX = 0
let globalPanY = 0

export default function SettingsModal({ open, onClose }: SettingsModalProps) {
  const { toast } = useToast()
  const [brightness, setBrightnessValue] = useState(128)
  const [displayBrightness, setDisplayBrightness] = useState(100)
  const [displayContrast, setDisplayContrast] = useState(100)
  
  // Display zoom & pan state
  const [displayZoom, setDisplayZoom] = useState(globalDisplayZoom)
  const [panX, setPanX] = useState(globalPanX)
  const [panY, setPanY] = useState(globalPanY)

  // Apply zoom & pan to camera feed
  const applyZoomPan = useCallback((zoom: number, x: number, y: number) => {
    globalDisplayZoom = zoom
    globalPanX = x
    globalPanY = y
    
    const images = document.querySelectorAll('img[alt="Camera Feed"]')
    images.forEach((img) => {
      const el = img as HTMLElement
      el.style.transform = `scale(${zoom}) translate(${x}px, ${y}px)`
      el.style.transformOrigin = 'center center'
    })
  }, [])

  // Apply on mount and when values change
  useEffect(() => {
    applyZoomPan(displayZoom, panX, panY)
  }, [displayZoom, panX, panY, applyZoomPan])

  const handleDisplayZoomIn = () => {
    const newZoom = Math.min(displayZoom + 0.25, 4)
    setDisplayZoom(newZoom)
    toast({ title: "Display Zoom", description: `${Math.round(newZoom * 100)}%` })
  }

  const handleDisplayZoomOut = () => {
    const newZoom = Math.max(displayZoom - 0.25, 1)
    setDisplayZoom(newZoom)
    // Reset pan if zooming out to 1x
    if (newZoom === 1) {
      setPanX(0)
      setPanY(0)
    }
    toast({ title: "Display Zoom", description: `${Math.round(newZoom * 100)}%` })
  }

  const handlePan = (direction: 'up' | 'down' | 'left' | 'right') => {
    const step = 20 / displayZoom // Smaller steps at higher zoom
    const maxPan = (displayZoom - 1) * 100 // Limit pan based on zoom level
    
    switch (direction) {
      case 'up':
        setPanY(Math.min(panY + step, maxPan))
        break
      case 'down':
        setPanY(Math.max(panY - step, -maxPan))
        break
      case 'left':
        setPanX(Math.min(panX + step, maxPan))
        break
      case 'right':
        setPanX(Math.max(panX - step, -maxPan))
        break
    }
  }

  const handleResetZoomPan = () => {
    setDisplayZoom(1)
    setPanX(0)
    setPanY(0)
    toast({ title: "Reset", description: "Zoom & pan reset to default" })
  }

  const handleZoomIn = async () => {
    try {
      await zoomIncrease()
      toast({ title: "Zoom", description: "Zoom increased" })
    } catch {
      toast({ title: "Error", description: "Zoom failed", variant: "destructive" })
    }
  }

  const handleZoomOut = async () => {
    try {
      await zoomDecrease()
      toast({ title: "Zoom", description: "Zoom decreased" })
    } catch {
      toast({ title: "Error", description: "Zoom failed", variant: "destructive" })
    }
  }

  const handleFocusIn = async () => {
    try {
      await focusIncrease()
      toast({ title: "Focus", description: "Focus increased" })
    } catch {
      toast({ title: "Error", description: "Focus failed", variant: "destructive" })
    }
  }

  const handleFocusOut = async () => {
    try {
      await focusDecrease()
      toast({ title: "Focus", description: "Focus decreased" })
    } catch {
      toast({ title: "Error", description: "Focus failed", variant: "destructive" })
    }
  }

  const handleBrightnessChange = async (value: number[]) => {
    const val = value[0]
    setBrightnessValue(val)
    try {
      await setBrightness(val)
    } catch {
      // Ignore - debounced updates
    }
  }

  const handleDisplayBrightnessChange = (value: number[]) => {
    setDisplayBrightness(value[0])
    applyDisplayFilters(value[0], displayContrast)
  }

  const handleDisplayContrastChange = (value: number[]) => {
    setDisplayContrast(value[0])
    applyDisplayFilters(displayBrightness, value[0])
  }

  const applyDisplayFilters = (brightness: number, contrast: number) => {
    const filterValue = `brightness(${brightness / 100}) contrast(${contrast / 100})`
    // Apply to any camera feed images
    const images = document.querySelectorAll('img[alt="Camera Feed"]')
    images.forEach((img) => {
      (img as HTMLElement).style.filter = filterValue
    })
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="bg-card border-border text-foreground max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold text-orange-500 tracking-wide flex items-center gap-2">
            <span className="w-2 h-2 bg-orange-500 rounded-full animate-pulse" />
            CAMERA SETTINGS
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-8 py-4">
          {/* Display Zoom & Pan Controls */}
          <div className="space-y-4">
            <h3 className="text-foreground text-sm font-medium tracking-wider flex items-center gap-2">
              <Move className="w-4 h-4 text-cyan-500" />
              DISPLAY ZOOM & PAN
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {/* Zoom Controls */}
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">Zoom Level</p>
                <div className="flex gap-2">
                  <Button
                    onClick={handleDisplayZoomOut}
                    disabled={displayZoom <= 1}
                    className="flex-1 bg-secondary hover:bg-accent border border-border text-foreground"
                  >
                    <ZoomOut className="w-4 h-4" />
                  </Button>
                  <div className="flex-1 flex items-center justify-center bg-secondary border border-border rounded-md">
                    <span className="text-cyan-500 font-mono font-bold">{Math.round(displayZoom * 100)}%</span>
                  </div>
                  <Button
                    onClick={handleDisplayZoomIn}
                    disabled={displayZoom >= 4}
                    className="flex-1 bg-secondary hover:bg-accent border border-border text-foreground"
                  >
                    <ZoomIn className="w-4 h-4" />
                  </Button>
                </div>
              </div>
              
              {/* Pan Controls (D-Pad style) */}
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">Pan Direction</p>
                <div className="grid grid-cols-3 gap-1">
                  <div />
                  <Button
                    onClick={() => handlePan('up')}
                    disabled={displayZoom <= 1}
                    size="sm"
                    className="bg-secondary hover:bg-accent border border-border text-foreground h-8"
                  >
                    ↑
                  </Button>
                  <div />
                  <Button
                    onClick={() => handlePan('left')}
                    disabled={displayZoom <= 1}
                    size="sm"
                    className="bg-secondary hover:bg-accent border border-border text-foreground h-8"
                  >
                    ←
                  </Button>
                  <Button
                    onClick={handleResetZoomPan}
                    size="sm"
                    className="bg-cyan-600 hover:bg-cyan-700 text-white h-8"
                    title="Reset"
                  >
                    <RotateCcw className="w-3 h-3" />
                  </Button>
                  <Button
                    onClick={() => handlePan('right')}
                    disabled={displayZoom <= 1}
                    size="sm"
                    className="bg-secondary hover:bg-accent border border-border text-foreground h-8"
                  >
                    →
                  </Button>
                  <div />
                  <Button
                    onClick={() => handlePan('down')}
                    disabled={displayZoom <= 1}
                    size="sm"
                    className="bg-secondary hover:bg-accent border border-border text-foreground h-8"
                  >
                    ↓
                  </Button>
                  <div />
                </div>
              </div>
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Zoom in and pan to inspect specific areas of the target
            </p>
          </div>

          {/* Divider */}
          <div className="border-t border-border" />

          {/* Camera Zoom & Focus Controls */}
          <div className="grid grid-cols-2 gap-8">
            {/* Camera Zoom */}
            <div className="space-y-4">
              <h3 className="text-foreground text-sm font-medium tracking-wider flex items-center gap-2">
                <ZoomIn className="w-4 h-4 text-orange-500" />
                CAMERA ZOOM
              </h3>
              <div className="flex gap-2">
                <Button
                  onClick={handleZoomIn}
                  className="flex-1 bg-secondary hover:bg-accent border border-border text-foreground"
                >
                  <ZoomIn className="w-5 h-5" />
                </Button>
                <Button
                  onClick={handleZoomOut}
                  className="flex-1 bg-secondary hover:bg-accent border border-border text-foreground"
                >
                  <ZoomOut className="w-5 h-5" />
                </Button>
              </div>
            </div>

            {/* Focus */}
            <div className="space-y-4">
              <h3 className="text-foreground text-sm font-medium tracking-wider flex items-center gap-2">
                <Focus className="w-4 h-4 text-orange-500" />
                FOCUS
              </h3>
              <div className="flex gap-2">
                <Button
                  onClick={handleFocusIn}
                  className="flex-1 bg-secondary hover:bg-accent border border-border text-foreground"
                >
                  +
                </Button>
                <Button
                  onClick={handleFocusOut}
                  className="flex-1 bg-secondary hover:bg-accent border border-border text-foreground"
                >
                  −
                </Button>
              </div>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-border" />

          {/* LED Brightness */}
          <div className="space-y-4">
            <h3 className="text-foreground text-sm font-medium tracking-wider flex items-center gap-2">
              <Sun className="w-4 h-4 text-orange-500" />
              LED BRIGHTNESS
            </h3>
            <div className="space-y-2">
              <Slider
                value={[brightness]}
                onValueChange={handleBrightnessChange}
                min={0}
                max={255}
                step={1}
                className="w-full"
              />
              <div className="text-center text-orange-500 font-mono font-bold">
                {brightness}
              </div>
            </div>
          </div>

          {/* Divider */}
          <div className="border-t border-border" />

          {/* Preview Brightness (Local) */}
          <div className="space-y-4">
            <h3 className="text-foreground text-sm font-medium tracking-wider flex items-center gap-2">
              <Sun className="w-4 h-4 text-yellow-500" />
              PREVIEW BRIGHTNESS (LOCAL)
            </h3>
            <div className="space-y-2">
              <Slider
                value={[displayBrightness]}
                onValueChange={handleDisplayBrightnessChange}
                min={40}
                max={140}
                step={1}
                className="w-full"
              />
              <div className="text-center text-yellow-500 font-mono font-bold">
                {displayBrightness}%
              </div>
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Adjusts only what you see here (does not change camera exposure)
            </p>
          </div>

          {/* Preview Contrast (Local) */}
          <div className="space-y-4">
            <h3 className="text-foreground text-sm font-medium tracking-wider flex items-center gap-2">
              <Contrast className="w-4 h-4 text-amber-500" />
              PREVIEW CONTRAST (LOCAL)
            </h3>
            <div className="space-y-2">
              <Slider
                value={[displayContrast]}
                onValueChange={handleDisplayContrastChange}
                min={50}
                max={150}
                step={1}
                className="w-full"
              />
              <div className="text-center text-amber-500 font-mono font-bold">
                {displayContrast}%
              </div>
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Local-only contrast for the displayed preview
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-border">
          <p className="text-center text-xs text-muted-foreground">
            Adjust settings for optimal target clarity and precision
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
