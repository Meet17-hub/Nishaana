"use client"

import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { Crosshair, Target } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import Sidebar from "@/components/sidebar"
import { useAccent } from "@/components/accent-provider"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useToast } from "@/hooks/use-toast"

export default function TrainingPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const { toast } = useToast()
  const [sessionMode, setSessionMode] = useState<"tournament" | "training" | "free_training">("training")
  const [trainingShotLimit, setTrainingShotLimit] = useState<number>(10)

  const accentText = accent === "orange" ? "text-orange-500" : accent === "green" ? "text-green-500" : "text-blue-500"
  const accentBg = accent === "orange" ? "bg-orange-500" : accent === "green" ? "bg-green-500" : "bg-blue-500"
  const accentBorder = accent === "orange" ? "border-orange-500/50" : accent === "green" ? "border-green-500/50" : "border-blue-500/50"

  useEffect(() => {
    const loggedIn = localStorage.getItem("lakshya_logged_in")
    if (!loggedIn) {
      router.push("/login")
    }

    const savedMode = localStorage.getItem("lakshya_training_session_mode")
    if (savedMode === "training" || savedMode === "tournament" || savedMode === "free_training") {
      setSessionMode(savedMode)
    }

    const savedLimit = Number.parseInt(localStorage.getItem("lakshya_training_shot_limit") || "", 10)
    if (Number.isInteger(savedLimit) && savedLimit >= 1 && savedLimit <= 10) {
      setTrainingShotLimit(savedLimit)
    }
  }, [router])

  const handleModeChange = (mode: "tournament" | "training" | "free_training") => {
    setSessionMode(mode)
    localStorage.setItem("lakshya_training_session_mode", mode)
    toast({
      title: "Session Mode Updated",
      description:
        mode === "tournament"
          ? "Tournament: single shot per target"
          : mode === "training"
            ? `Training: up to ${trainingShotLimit} shots per target`
            : "Free Training: unlimited shots per target",
    })
  }

  const handleShotLimitChange = (limit: number) => {
    setTrainingShotLimit(limit)
    localStorage.setItem("lakshya_training_shot_limit", String(limit))
    toast({
      title: "Shot Limit Updated",
      description: `Training target limit set to ${limit} shot${limit > 1 ? "s" : ""}`,
    })
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar activeSection="training" />

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-16 bg-card border-b border-border flex items-center px-6">
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Crosshair className={`w-6 h-6 ${accentText}`} />
            TRAINING
          </h1>
        </div>

        <div className="flex-1 p-6 overflow-auto">
          <Card className={`max-w-3xl bg-card border ${accentBorder}`}>
            <CardHeader>
              <CardTitle className="text-foreground text-base flex items-center gap-2">
                <Target className={`w-5 h-5 ${accentText}`} />
                Target Control
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col sm:flex-row gap-2">
                <Button
                  variant={sessionMode === "tournament" ? "default" : "outline"}
                  className={sessionMode === "tournament" ? `${accentBg} text-white` : ""}
                  onClick={() => handleModeChange("tournament")}
                >
                  Tournament
                </Button>
                <Button
                  variant={sessionMode === "training" ? "default" : "outline"}
                  className={sessionMode === "training" ? `${accentBg} text-white` : ""}
                  onClick={() => handleModeChange("training")}
                >
                  Training
                </Button>
                <Button
                  variant={sessionMode === "free_training" ? "default" : "outline"}
                  className={sessionMode === "free_training" ? `${accentBg} text-white` : ""}
                  onClick={() => handleModeChange("free_training")}
                >
                  Free Training
                </Button>
              </div>

              {sessionMode === "training" && (
                <div className="max-w-[220px]">
                  <p className="text-xs text-muted-foreground mb-2">Shots per target (1-10)</p>
                  <Select value={String(trainingShotLimit)} onValueChange={(value) => handleShotLimitChange(Number.parseInt(value, 10))}>
                    <SelectTrigger className="bg-secondary border-border text-foreground">
                      <SelectValue placeholder="Select shot limit" />
                    </SelectTrigger>
                    <SelectContent className="bg-card border-border">
                      {Array.from({ length: 10 }, (_, i) => i + 1).map((count) => (
                        <SelectItem key={count} value={String(count)}>
                          {count} shot{count > 1 ? "s" : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <p className="text-xs text-muted-foreground">
                {sessionMode === "tournament"
                  ? "Tournament mode enforces one shot per target. Scoring and target changes are done from Dashboard."
                  : sessionMode === "training"
                    ? `Training mode uses ${trainingShotLimit} shot${trainingShotLimit > 1 ? "s" : ""} per target. Use Dashboard to update score and move to next target.`
                    : "Free Training mode allows unlimited shots per target. Use Dashboard to update score and move to next target when you want."}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
