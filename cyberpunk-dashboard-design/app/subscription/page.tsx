"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Check, ShieldCheck, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAccent } from "@/components/accent-provider"
import { getCurrentUser } from "@/lib/api"
import { hasActiveSubscription, type PaidPlanCode } from "@/lib/subscription"

type PlanItem = {
  code: PaidPlanCode
  title: string
  price: string
  period: string
  highlight?: boolean
  features: string[]
}

const PLAN_ITEMS: PlanItem[] = [
  {
    code: "monthly",
    title: "Monthly",
    price: "INR 1",
    period: "for 1 day",
    features: ["Full access to all targets", "Live scoring and analytics", "Email reports"],
  },
  {
    code: "half_yearly",
    title: "Half Yearly",
    price: "INR 4,999",
    period: "for 6 months",
    highlight: true,
    features: ["Better value than monthly", "All monthly features", "Priority support"],
  },
  {
    code: "yearly",
    title: "Yearly",
    price: "INR 8,999",
    period: "per year",
    features: ["Best long-term value", "All features included", "Extended validity"],
  },
]

const RAZORPAY_CHECKOUT_URL = "https://checkout.razorpay.com/v1/checkout.js"

async function loadRazorpayCheckout() {
  if (typeof window === "undefined") {
    return false
  }

  if (window.Razorpay) {
    return true
  }

  return new Promise<boolean>((resolve) => {
    const existingScript = document.querySelector(`script[src="${RAZORPAY_CHECKOUT_URL}"]`) as HTMLScriptElement | null

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(true), { once: true })
      existingScript.addEventListener("error", () => resolve(false), { once: true })
      return
    }

    const script = document.createElement("script")
    script.src = RAZORPAY_CHECKOUT_URL
    script.async = true
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

export default function SubscriptionPage() {
  const router = useRouter()
  const { accent } = useAccent()
  const [username, setUsername] = useState("")
  const [processingPlan, setProcessingPlan] = useState<PaidPlanCode | null>(null)
  const [error, setError] = useState("")

  const accentGradient = useMemo(() => {
    if (accent === "green") return "from-green-500 to-green-600"
    if (accent === "blue") return "from-blue-500 to-blue-600"
    return "from-orange-500 to-orange-600"
  }, [accent])

  useEffect(() => {
    let cancelled = false

    const loadUser = async () => {
      const loggedIn = localStorage.getItem("lakshya_logged_in")
      if (!loggedIn) {
        router.replace("/login")
        return
      }

      const user = await getCurrentUser()
      if (!user) {
        if (!cancelled) {
          router.replace("/login")
        }
        return
      }

      if (cancelled) {
        return
      }

      localStorage.setItem("lakshya_username", user.username)
      setUsername(user.username)

      if (hasActiveSubscription(user)) {
        router.replace("/dashboard")
      }
    }

    void loadUser()

    return () => {
      cancelled = true
    }
  }, [router])

  const handleSelectPlan = async (planCode: PaidPlanCode) => {
    if (!username) {
      return
    }

    setError("")
    setProcessingPlan(planCode)

    try {
      const checkoutLoaded = await loadRazorpayCheckout()

      if (!checkoutLoaded || !window.Razorpay) {
        throw new Error("Razorpay Checkout could not be loaded.")
      }

      const response = await fetch("/api/payments/razorpay/create-order", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          planCode,
        }),
      })

      const data = (await response.json()) as {
        error?: string
        details?: string
        keyId?: string
        orderId?: string
        amount?: number
        currency?: string
        planLabel?: string
      }

      if (!response.ok || !data.keyId || !data.orderId || !data.amount || !data.currency) {
        throw new Error(data.details || data.error || "Unable to start Razorpay payment.")
      }

      localStorage.setItem("lakshya_pending_plan", planCode)
      localStorage.setItem("lakshya_pending_customer", username)
      localStorage.setItem("lakshya_pending_order_id", data.orderId)

      const razorpay = new window.Razorpay({
        key: data.keyId,
        amount: data.amount,
        currency: data.currency,
        name: "Lakshya",
        description: `${data.planLabel || "Plan"} access`,
        order_id: data.orderId,
        prefill: {
          name: username,
        },
        notes: {
          username,
          plan_code: planCode,
        },
        theme: {
          color: accent === "green" ? "#16a34a" : accent === "blue" ? "#2563eb" : "#f97316",
        },
        modal: {
          ondismiss: () => {
            setProcessingPlan(null)
          },
        },
        handler: async (paymentResponse) => {
          const params = new URLSearchParams({
            customer_id: username,
            plan_code: planCode,
            order_id: data.orderId ?? "",
            razorpay_order_id: paymentResponse.razorpay_order_id || data.orderId || "",
            razorpay_payment_id: paymentResponse.razorpay_payment_id || "",
            razorpay_signature: paymentResponse.razorpay_signature || "",
          } satisfies Record<string, string>)

          setProcessingPlan(null)
          router.push(`/payment-return?${params.toString()}`)
        },
      })

      razorpay.on("payment.failed", (paymentError) => {
        const message =
          paymentError.error.description ||
          paymentError.error.reason ||
          "Payment failed. Please try again."

        setError(message)
        setProcessingPlan(null)
      })

      razorpay.open()
    } catch (err) {
      console.error("Razorpay checkout error:", err)
      setError(err instanceof Error ? err.message : "Unable to start payment.")
      setProcessingPlan(null)
    }
  }

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 text-center">
          <div className={`mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br ${accentGradient}`}>
            <ShieldCheck className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-3xl font-bold tracking-wide text-foreground">Choose Your Lakshya Plan</h1>
          <p className="mt-2 text-muted-foreground">Subscription is required before entering the target dashboard.</p>
        </div>

        {error && (
          <div className="mx-auto mb-6 max-w-2xl rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-3">
          {PLAN_ITEMS.map((plan) => (
            <Card
              key={plan.code}
              className={`relative border-border bg-card/90 ${plan.highlight ? "ring-2 ring-amber-400/70" : ""}`}
            >
              {plan.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-amber-400 px-3 py-1 text-xs font-semibold text-black">
                  Most Popular
                </div>
              )}
              <CardHeader>
                <CardTitle className="text-2xl tracking-wide">{plan.title}</CardTitle>
                <CardDescription>
                  <span className="text-xl font-semibold text-foreground">{plan.price}</span> {plan.period}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {plan.features.map((feature) => (
                  <div key={feature} className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Check className="h-4 w-4 text-emerald-500" />
                    <span>{feature}</span>
                  </div>
                ))}
                <Button
                  className={`mt-4 w-full bg-gradient-to-r ${accentGradient} text-white`}
                  onClick={() => handleSelectPlan(plan.code)}
                  disabled={processingPlan !== null}
                >
                  {processingPlan === plan.code ? (
                    "Processing..."
                  ) : (
                    <>
                      <Zap className="mr-2 h-4 w-4" />
                      Subscribe {plan.title}
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
