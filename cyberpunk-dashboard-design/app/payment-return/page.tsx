"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { activateCurrentUserSubscription, getErrorMessage } from "@/lib/api"
import { isPaidPlanCode, type PaidPlanCode } from "@/lib/subscription"

function PaymentReturnContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<"processing" | "success" | "pending" | "error">("processing")
  const [message, setMessage] = useState("Processing payment and activating subscription...")

  useEffect(() => {
    const loggedIn = localStorage.getItem("lakshya_logged_in")
    if (!loggedIn) {
      router.replace("/login")
      return
    }

    const userFromQuery = searchParams.get("customer_id")
    const username = userFromQuery || localStorage.getItem("lakshya_pending_customer") || localStorage.getItem("lakshya_username")

    if (!username) {
      setStatus("error")
      setMessage("Could not identify account for subscription activation.")
      return
    }

    const fromUrl = searchParams.get("plan_code")
    const fromPending = localStorage.getItem("lakshya_pending_plan")
    const requestedPlan: PaidPlanCode = isPaidPlanCode(fromUrl)
      ? fromUrl
      : isPaidPlanCode(fromPending)
        ? fromPending
        : "monthly"
    const orderId = searchParams.get("order_id") || localStorage.getItem("lakshya_pending_order_id")
    const razorpayOrderId = searchParams.get("razorpay_order_id")
    const paymentId = searchParams.get("razorpay_payment_id")
    const signature = searchParams.get("razorpay_signature")

    if (!orderId || !paymentId || !signature) {
      setStatus("error")
      setMessage("Missing payment confirmation details. Please retry the payment.")
      return
    }

    let cancelled = false

    const verifyPayment = async () => {
      try {
        const response = await fetch("/api/payments/razorpay/verify", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            username,
            planCode: requestedPlan,
            orderId,
            razorpay_order_id: razorpayOrderId,
            razorpay_payment_id: paymentId,
            razorpay_signature: signature,
          }),
        })

        const data = (await response.json()) as {
          verified?: boolean
          captured?: boolean
          message?: string
          error?: string
          details?: string
          status?: string
        }

        if (cancelled) {
          return
        }

        if (!response.ok) {
          setStatus("error")
          setMessage(data.details || data.error || "Payment verification failed.")
          return
        }

        if (!data.verified || !data.captured) {
          setStatus("pending")
          setMessage(
            data.message ||
              `Payment is not captured yet${data.status ? ` (${data.status})` : ""}. Please confirm auto-capture is enabled in Razorpay, or try again in a moment.`
          )
          return
        }

        const activationResponse = await activateCurrentUserSubscription(requestedPlan)
        if (!activationResponse.ok) {
          setStatus("error")
          setMessage(await getErrorMessage(activationResponse, "Payment is verified, but subscription activation failed for this account."))
          return
        }

        localStorage.removeItem("lakshya_pending_plan")
        localStorage.removeItem("lakshya_pending_customer")
        localStorage.removeItem("lakshya_pending_order_id")
        setStatus("success")
        setMessage("Payment received. Subscription is active. Redirecting to dashboard...")

        setTimeout(() => {
          router.replace("/dashboard")
        }, 1200)
      } catch (error) {
        if (cancelled) {
          return
        }

        console.error("Payment verification error:", error)
        setStatus("error")
        setMessage(error instanceof Error ? error.message : "Payment verification failed.")
      }
    }

    void verifyPayment()

      return () => {
      cancelled = true
    }
  }, [router, searchParams])

  return (
    <div className="min-h-screen bg-background p-4">
      <div className="mx-auto flex min-h-screen max-w-xl items-center justify-center">
        <Card className="w-full border-border bg-card/90">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15">
              {status === "processing" ? (
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              ) : status === "success" ? (
                <CheckCircle2 className="h-8 w-8 text-emerald-500" />
              ) : (
                <AlertCircle className="h-8 w-8 text-amber-500" />
              )}
            </div>
            <CardTitle className="text-2xl">Payment Status</CardTitle>
            <CardDescription>{message}</CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center gap-3">
            <Button variant="outline" onClick={() => router.push("/subscription")}>
              Back to Plans
            </Button>
            <Button onClick={() => router.push("/dashboard")} disabled={status !== "success"}>
              Go to Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default function PaymentReturnPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background p-4">
        <div className="mx-auto flex min-h-screen max-w-xl items-center justify-center">
          <Card className="w-full border-border bg-card/90">
            <CardHeader className="text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              </div>
              <CardTitle className="text-2xl">Payment Status</CardTitle>
              <CardDescription>Processing payment and activating subscription...</CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    }>
      <PaymentReturnContent />
    </Suspense>
  )
}
