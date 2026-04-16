"use client"

import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import {
  User,
  Mail,
  Shield,
  Target,
  Award,
  Edit2,
  Save,
  Bell,
  Lock,
  Trash2,
  X,
  Check,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { getAllSessions, clearAllSessions, clearAllHistory, migrateUserSessionStore } from "@/lib/session-store"
import {
  changeCurrentUserPassword,
  deleteCurrentUser,
  getCurrentUser,
  getErrorMessage,
  updateCurrentUser,
} from "@/lib/api"
import Sidebar from "@/components/sidebar"
import { useAccent } from "@/components/accent-provider"

export default function ProfilePage() {
  const router = useRouter()
  const { accent } = useAccent()
  const [editing, setEditing] = useState(false)
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [stats, setStats] = useState({
    totalSessions: 0,
    totalShots: 0,
    averageScore: 0,
  })
  
  // Modal states
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [showNotificationModal, setShowNotificationModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  
  // Password change state
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmNewPassword, setConfirmNewPassword] = useState("")
  const [passwordError, setPasswordError] = useState("")
  const [passwordSuccess, setPasswordSuccess] = useState(false)
  
  // Notification preferences
  const [notifications, setNotifications] = useState({
    emailScoreReports: true,
    sessionReminders: false,
    performanceAlerts: true,
    systemUpdates: true,
  })

  // Dynamic accent classes
  const accentText = accent === "orange" ? "text-orange-500" : accent === "green" ? "text-green-500" : "text-blue-500"
  const accentBorder = accent === "orange" ? "border-orange-500/50" : accent === "green" ? "border-green-500/50" : "border-blue-500/50"
  const accentHover = accent === "orange" ? "hover:bg-orange-500/10" : accent === "green" ? "hover:bg-green-500/10" : "hover:bg-blue-500/10"
  const accentGradient = accent === "orange" ? "from-orange-500 to-orange-600" : accent === "green" ? "from-green-500 to-green-600" : "from-blue-500 to-blue-600"
  const accentBg = accent === "orange" ? "bg-orange-500" : accent === "green" ? "bg-green-500" : "bg-blue-500"

  useEffect(() => {
    let cancelled = false

    const initialize = async () => {
      const loggedIn = localStorage.getItem("lakshya_logged_in")
      if (!loggedIn) {
        router.push("/login")
        return
      }

      const currentUser = await getCurrentUser()
      if (!currentUser) {
        if (!cancelled) {
          router.push("/login")
        }
        return
      }

      if (cancelled) {
        return
      }

      localStorage.setItem("lakshya_username", currentUser.username)
      setUsername(currentUser.username)
      setEmail(currentUser.email)
    
      // Calculate stats
      const sessions = getAllSessions()
      let totalShots = 0
      let totalScoreSum = 0

      sessions.forEach((session) => {
        totalShots += session.shots.length
        totalScoreSum += session.totalScore
      })

      setStats({
        totalSessions: sessions.length,
        totalShots,
        averageScore: sessions.length > 0 ? totalScoreSum / sessions.length : 0,
      })
    
      const savedNotifications = localStorage.getItem("lakshya_notifications")
      if (savedNotifications) {
        setNotifications(JSON.parse(savedNotifications))
      }
    }

    void initialize()

    return () => {
      cancelled = true
    }
  }, [router])

  const handleSave = async () => {
    const oldUsername = localStorage.getItem("lakshya_username") || ""
    const trimmedUsername = username.trim()
    if (!trimmedUsername) {
      return
    }

    const response = await updateCurrentUser({
      username: trimmedUsername,
      email: email.trim(),
    })
    if (!response.ok) {
      window.alert(await getErrorMessage(response, "Could not update profile"))
      return
    }

    const payload = await response.json().catch(() => null) as
      | { user?: { username: string; email: string } }
      | null

    const nextUsername = payload?.user?.username || trimmedUsername
    const nextEmail = payload?.user?.email || email.trim()
    localStorage.setItem("lakshya_username", nextUsername)
    migrateUserSessionStore(oldUsername, nextUsername)
    setUsername(nextUsername)
    setEmail(nextEmail)
    setEditing(false)
  }

  const handleChangePassword = async () => {
    setPasswordError("")
    setPasswordSuccess(false)
    
    if (!currentPassword || !newPassword || !confirmNewPassword) {
      setPasswordError("All fields are required")
      return
    }
    
    if (newPassword !== confirmNewPassword) {
      setPasswordError("New passwords do not match")
      return
    }
    
    if (newPassword.length < 6) {
      setPasswordError("Password must be at least 6 characters")
      return
    }

    const response = await changeCurrentUserPassword({
      current_password: currentPassword,
      new_password: newPassword,
    })
    if (!response.ok) {
      setPasswordError(await getErrorMessage(response, "Could not update password"))
      return
    }

    setPasswordSuccess(true)
    setCurrentPassword("")
    setNewPassword("")
    setConfirmNewPassword("")

    setTimeout(() => {
      setShowPasswordModal(false)
      setPasswordSuccess(false)
    }, 1500)
  }

  const handleSaveNotifications = () => {
    localStorage.setItem("lakshya_notifications", JSON.stringify(notifications))
    setShowNotificationModal(false)
  }

  const handleDeleteAccount = async () => {
    const response = await deleteCurrentUser()
    if (!response.ok) {
      window.alert(await getErrorMessage(response, "Could not delete account"))
      return
    }

    localStorage.removeItem("lakshya_logged_in")
    localStorage.removeItem("lakshya_username")
    localStorage.removeItem("lakshya_device_id")
    localStorage.removeItem("lakshya_device_ip")
    localStorage.removeItem("lakshya_notifications")
    clearAllSessions()
    clearAllHistory()
    
    router.push("/login")
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar activeSection="profile" />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="h-16 bg-card border-b border-border flex items-center px-6">
          <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <User className={`w-6 h-6 ${accentText}`} />
            PROFILE
          </h1>
        </div>

        <div className="flex-1 p-6 overflow-auto">
          <div className="max-w-2xl mx-auto space-y-6">
            {/* Profile Card */}
            <Card className="bg-card border-border">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-foreground">Personal Information</CardTitle>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => editing ? void handleSave() : setEditing(true)}
                    className={`${accentBorder} ${accentText} ${accentHover}`}
                  >
                    {editing ? (
                      <>
                        <Save className="w-4 h-4 mr-2" />
                        Save
                      </>
                    ) : (
                      <>
                        <Edit2 className="w-4 h-4 mr-2" />
                        Edit
                      </>
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Avatar */}
                <div className="flex items-center gap-4">
                  <div className={`w-20 h-20 rounded-full bg-gradient-to-br ${accentGradient} flex items-center justify-center`}>
                    <User className="w-10 h-10 text-white" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-foreground">{username}</h2>
                    <p className="text-muted-foreground text-sm">Target Shooter</p>
                  </div>
                </div>

                {/* Form Fields */}
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username" className="text-foreground">Username</Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input
                        id="username"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        disabled={!editing}
                        className="pl-10 bg-secondary border-border text-foreground disabled:opacity-70"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email" className="text-foreground">Email</Label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input
                        id="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        disabled={!editing}
                        className="pl-10 bg-secondary border-border text-foreground disabled:opacity-70"
                      />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Stats Card */}
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="text-foreground flex items-center gap-2">
                  <Award className={`w-5 h-5 ${accentText}`} />
                  Performance Summary
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-4 bg-accent/50 rounded-lg">
                    <Target className={`w-6 h-6 mx-auto mb-2 ${accentText}`} />
                    <div className="text-2xl font-bold text-foreground">{stats.totalSessions}</div>
                    <div className="text-muted-foreground text-sm">Sessions</div>
                  </div>
                  <div className="text-center p-4 bg-accent/50 rounded-lg">
                    <Shield className={`w-6 h-6 mx-auto mb-2 ${accentText}`} />
                    <div className="text-2xl font-bold text-foreground">{stats.totalShots}</div>
                    <div className="text-muted-foreground text-sm">Total Shots</div>
                  </div>
                  <div className="text-center p-4 bg-accent/50 rounded-lg">
                    <Award className={`w-6 h-6 mx-auto mb-2 ${accentText}`} />
                    <div className="text-2xl font-bold text-foreground">{stats.averageScore.toFixed(1)}</div>
                    <div className="text-muted-foreground text-sm">Avg Score</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Account Settings */}
            <Card className="bg-card border-border">
              <CardHeader>
                <CardTitle className="text-foreground">Account Settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Button
                  variant="outline"
                  className="w-full border-border text-foreground hover:bg-accent"
                  onClick={() => setShowPasswordModal(true)}
                >
                  <Lock className="w-4 h-4 mr-2" />
                  Change Password
                </Button>
                <Button
                  variant="outline"
                  className="w-full border-border text-foreground hover:bg-accent"
                  onClick={() => setShowNotificationModal(true)}
                >
                  <Bell className="w-4 h-4 mr-2" />
                  Notification Preferences
                </Button>
                <Button
                  variant="outline"
                  className="w-full border-red-500/50 text-red-400 hover:bg-red-500/10"
                  onClick={() => setShowDeleteModal(true)}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete Account
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Change Password Modal */}
      {showPasswordModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <Card className="w-full max-w-md bg-card border-border mx-4">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-foreground flex items-center gap-2">
                  <Lock className={`w-5 h-5 ${accentText}`} />
                  Change Password
                </CardTitle>
                <Button variant="ghost" size="icon" onClick={() => setShowPasswordModal(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {passwordSuccess ? (
                <div className="text-center py-8">
                  <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
                    <Check className="w-8 h-8 text-green-500" />
                  </div>
                  <p className="text-green-500 font-medium">Password changed successfully!</p>
                </div>
              ) : (
                <>
                  {passwordError && (
                    <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                      {passwordError}
                    </div>
                  )}
                  <div className="space-y-2">
                    <Label className="text-foreground">Current Password</Label>
                    <Input
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      className="bg-secondary border-border text-foreground"
                      placeholder="Enter current password"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-foreground">New Password</Label>
                    <Input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="bg-secondary border-border text-foreground"
                      placeholder="Enter new password"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-foreground">Confirm New Password</Label>
                    <Input
                      type="password"
                      value={confirmNewPassword}
                      onChange={(e) => setConfirmNewPassword(e.target.value)}
                      className="bg-secondary border-border text-foreground"
                      placeholder="Confirm new password"
                    />
                  </div>
                  <Button
                    className={`w-full bg-gradient-to-r ${accentGradient} text-white`}
                    onClick={() => void handleChangePassword()}
                  >
                    Update Password
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Notification Preferences Modal */}
      {showNotificationModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <Card className="w-full max-w-md bg-card border-border mx-4">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-foreground flex items-center gap-2">
                  <Bell className={`w-5 h-5 ${accentText}`} />
                  Notification Preferences
                </CardTitle>
                <Button variant="ghost" size="icon" onClick={() => setShowNotificationModal(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 bg-secondary rounded-lg">
                  <div>
                    <p className="text-foreground font-medium">Email Score Reports</p>
                    <p className="text-muted-foreground text-sm">Receive score summaries after each session</p>
                  </div>
                  <button
                    onClick={() => setNotifications(prev => ({ ...prev, emailScoreReports: !prev.emailScoreReports }))}
                    className={`w-12 h-6 rounded-full transition-colors ${notifications.emailScoreReports ? accentBg : 'bg-gray-600'}`}
                  >
                    <div className={`w-5 h-5 rounded-full bg-white transition-transform ${notifications.emailScoreReports ? 'translate-x-6' : 'translate-x-0.5'}`} />
                  </button>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-secondary rounded-lg">
                  <div>
                    <p className="text-foreground font-medium">Session Reminders</p>
                    <p className="text-muted-foreground text-sm">Get reminded to practice regularly</p>
                  </div>
                  <button
                    onClick={() => setNotifications(prev => ({ ...prev, sessionReminders: !prev.sessionReminders }))}
                    className={`w-12 h-6 rounded-full transition-colors ${notifications.sessionReminders ? accentBg : 'bg-gray-600'}`}
                  >
                    <div className={`w-5 h-5 rounded-full bg-white transition-transform ${notifications.sessionReminders ? 'translate-x-6' : 'translate-x-0.5'}`} />
                  </button>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-secondary rounded-lg">
                  <div>
                    <p className="text-foreground font-medium">Performance Alerts</p>
                    <p className="text-muted-foreground text-sm">Alerts when you hit new personal bests</p>
                  </div>
                  <button
                    onClick={() => setNotifications(prev => ({ ...prev, performanceAlerts: !prev.performanceAlerts }))}
                    className={`w-12 h-6 rounded-full transition-colors ${notifications.performanceAlerts ? accentBg : 'bg-gray-600'}`}
                  >
                    <div className={`w-5 h-5 rounded-full bg-white transition-transform ${notifications.performanceAlerts ? 'translate-x-6' : 'translate-x-0.5'}`} />
                  </button>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-secondary rounded-lg">
                  <div>
                    <p className="text-foreground font-medium">System Updates</p>
                    <p className="text-muted-foreground text-sm">Important updates and new features</p>
                  </div>
                  <button
                    onClick={() => setNotifications(prev => ({ ...prev, systemUpdates: !prev.systemUpdates }))}
                    className={`w-12 h-6 rounded-full transition-colors ${notifications.systemUpdates ? accentBg : 'bg-gray-600'}`}
                  >
                    <div className={`w-5 h-5 rounded-full bg-white transition-transform ${notifications.systemUpdates ? 'translate-x-6' : 'translate-x-0.5'}`} />
                  </button>
                </div>
              </div>
              
              <Button
                className={`w-full bg-gradient-to-r ${accentGradient} text-white`}
                onClick={handleSaveNotifications}
              >
                Save Preferences
              </Button>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Delete Account Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <Card className="w-full max-w-md bg-card border-border mx-4">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-red-400 flex items-center gap-2">
                  <Trash2 className="w-5 h-5" />
                  Delete Account
                </CardTitle>
                <Button variant="ghost" size="icon" onClick={() => setShowDeleteModal(false)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                <p className="text-red-400 font-medium mb-2">⚠️ Warning</p>
                <p className="text-muted-foreground text-sm">
                  This action cannot be undone. All your data, including:
                </p>
                <ul className="text-muted-foreground text-sm mt-2 space-y-1 list-disc list-inside">
                  <li>Your profile information</li>
                  <li>All session history ({stats.totalSessions} sessions)</li>
                  <li>Performance statistics</li>
                  <li>Notification preferences</li>
                </ul>
                <p className="text-muted-foreground text-sm mt-2">
                  will be permanently deleted.
                </p>
              </div>
              
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1 border-border text-foreground"
                  onClick={() => setShowDeleteModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1 bg-red-500 hover:bg-red-600 text-white"
                  onClick={() => void handleDeleteAccount()}
                >
                  Delete Account
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
