import { NextRequest, NextResponse } from "next/server"
import { fetchRazorpayOrderPayment, isValidPaidPlanCode, verifyRazorpaySignature } from "@/lib/razorpay"

export const runtime = "nodejs"

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      username?: string
      planCode?: string
      orderId?: string
      razorpay_order_id?: string
      razorpay_payment_id?: string
      razorpay_signature?: string
    }

    const username = body.username?.trim()
    const planCode = body.planCode
    const orderId = body.orderId?.trim()
    const checkoutOrderId = body.razorpay_order_id?.trim()
    const paymentId = body.razorpay_payment_id?.trim()
    const signature = body.razorpay_signature?.trim()

    if (!username || !planCode || !orderId || !paymentId || !signature) {
      return NextResponse.json(
        { error: "Missing required payment verification fields" },
        { status: 400 }
      )
    }

    if (!isValidPaidPlanCode(planCode)) {
      return NextResponse.json({ error: "Invalid plan code" }, { status: 400 })
    }

    if (checkoutOrderId && checkoutOrderId !== orderId) {
      return NextResponse.json(
        { error: "Order mismatch detected during payment verification" },
        { status: 400 }
      )
    }

    const signatureIsValid = verifyRazorpaySignature({
      orderId,
      paymentId,
      signature,
    })

    if (!signatureIsValid) {
      return NextResponse.json(
        { error: "Invalid Razorpay signature", verified: false },
        { status: 400 }
      )
    }

    const payment = await fetchRazorpayOrderPayment(orderId, paymentId)

    if (!payment) {
      return NextResponse.json(
        { error: "Payment record not found for this order", verified: false },
        { status: 404 }
      )
    }

    if (payment.order_id !== orderId) {
      return NextResponse.json(
        { error: "Payment does not belong to the requested order", verified: false },
        { status: 400 }
      )
    }

    const captured = payment.captured || payment.status === "captured"

    return NextResponse.json({
      verified: captured,
      signatureVerified: true,
      captured,
      status: payment.status,
      paymentId: payment.id,
      orderId,
      username,
      planCode,
      message: captured
        ? "Payment verified and captured."
        : "Payment signature verified, but the payment is not captured yet.",
    })
  } catch (error) {
    console.error("Razorpay verify error:", error)
    return NextResponse.json(
      {
        error: "Failed to verify Razorpay payment",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    )
  }
}
