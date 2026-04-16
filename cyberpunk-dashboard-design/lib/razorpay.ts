import crypto from "crypto"
import { isPaidPlanCode, type PaidPlanCode } from "@/lib/subscription"

export const RAZORPAY_CURRENCY = "INR"

export const PLAN_PRICING: Record<PaidPlanCode, { amountPaise: number; label: string }> = {
  monthly: { amountPaise: 100, label: "1 Day Access" },
  half_yearly: { amountPaise: 499_900, label: "Half Yearly" },
  yearly: { amountPaise: 899_900, label: "Yearly" },
}

type RazorpayOrderResponse = {
  id: string
  entity: "order"
  amount: number
  amount_paid: number
  amount_due: number
  currency: string
  receipt: string | null
  offer_id: string | null
  status: "created" | "attempted" | "paid"
  attempts: number
  notes: Record<string, string>
  created_at: number
}

type RazorpayOrderPaymentsResponse = {
  entity: "collection"
  count: number
  items: Array<{
    id: string
    entity: "payment"
    amount: number
    currency: string
    status: "created" | "authorized" | "captured" | "refunded" | "failed"
    order_id: string
    method: string
    amount_refunded: number
    refund_status: string | null
    captured: boolean
    description: string | null
    email: string
    contact: string
    notes: Record<string, string>
    created_at: number
  }>
}

function getBasicAuthHeader() {
  const keyId = process.env.RAZORPAY_KEY_ID
  const keySecret = process.env.RAZORPAY_KEY_SECRET

  if (!keyId || !keySecret) {
    throw new Error("Razorpay keys are missing. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.")
  }

  return {
    keyId,
    keySecret,
    authorization: `Basic ${Buffer.from(`${keyId}:${keySecret}`).toString("base64")}`,
  }
}

async function parseError(response: Response) {
  const text = await response.text()

  try {
    const parsed = JSON.parse(text) as { error?: { description?: string; code?: string } }
    return parsed.error?.description || parsed.error?.code || text
  } catch {
    return text
  }
}

export function getRazorpayCheckoutConfig() {
  return {
    keyId: getBasicAuthHeader().keyId,
    currency: RAZORPAY_CURRENCY,
  }
}

export function getPlanPricing(planCode: PaidPlanCode) {
  return PLAN_PRICING[planCode]
}

export async function createRazorpayOrder(planCode: PaidPlanCode, username: string) {
  const pricing = getPlanPricing(planCode)
  const { authorization } = getBasicAuthHeader()
  const receipt = `lak_${planCode}_${Date.now()}`.slice(0, 40)

  const response = await fetch("https://api.razorpay.com/v1/orders", {
    method: "POST",
    headers: {
      Authorization: authorization,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      amount: pricing.amountPaise,
      currency: RAZORPAY_CURRENCY,
      receipt,
      notes: {
        username,
        plan_code: planCode,
      },
    }),
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Failed to create Razorpay order: ${await parseError(response)}`)
  }

  return response.json() as Promise<RazorpayOrderResponse>
}

export async function fetchRazorpayOrderPayment(orderId: string, paymentId: string) {
  const { authorization } = getBasicAuthHeader()

  const response = await fetch(`https://api.razorpay.com/v1/orders/${orderId}/payments`, {
    method: "GET",
    headers: {
      Authorization: authorization,
    },
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch Razorpay payment status: ${await parseError(response)}`)
  }

  const data = (await response.json()) as RazorpayOrderPaymentsResponse
  return data.items.find((item) => item.id === paymentId) || null
}

export function verifyRazorpaySignature({
  orderId,
  paymentId,
  signature,
}: {
  orderId: string
  paymentId: string
  signature: string
}) {
  const { keySecret } = getBasicAuthHeader()

  const expectedSignature = crypto
    .createHmac("sha256", keySecret)
    .update(`${orderId}|${paymentId}`)
    .digest("hex")

  const expectedBuffer = Buffer.from(expectedSignature)
  const actualBuffer = Buffer.from(signature)

  if (expectedBuffer.length !== actualBuffer.length) {
    return false
  }

  return crypto.timingSafeEqual(expectedBuffer, actualBuffer)
}

export function isValidPaidPlanCode(value: string | null | undefined): value is PaidPlanCode {
  return isPaidPlanCode(value)
}
