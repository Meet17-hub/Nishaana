import { NextRequest, NextResponse } from "next/server"
import { createRazorpayOrder, getPlanPricing, getRazorpayCheckoutConfig, isValidPaidPlanCode } from "@/lib/razorpay"

export const runtime = "nodejs"

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      username?: string
      planCode?: string
    }

    const username = body.username?.trim()
    const planCode = body.planCode

    if (!username || !planCode) {
      return NextResponse.json(
        { error: "Missing required fields: username and planCode" },
        { status: 400 }
      )
    }

    if (!isValidPaidPlanCode(planCode)) {
      return NextResponse.json({ error: "Invalid plan code" }, { status: 400 })
    }

    const order = await createRazorpayOrder(planCode, username)
    const checkoutConfig = getRazorpayCheckoutConfig()
    const pricing = getPlanPricing(planCode)

    return NextResponse.json({
      keyId: checkoutConfig.keyId,
      orderId: order.id,
      amount: order.amount,
      currency: order.currency,
      planCode,
      username,
      planLabel: pricing.label,
    })
  } catch (error) {
    console.error("Razorpay create-order error:", error)
    return NextResponse.json(
      {
        error: "Failed to create Razorpay order",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    )
  }
}
