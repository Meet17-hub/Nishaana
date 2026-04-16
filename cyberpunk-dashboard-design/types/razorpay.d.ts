type RazorpayPaymentSuccessResponse = {
  razorpay_payment_id: string
  razorpay_order_id?: string
  razorpay_subscription_id?: string
  razorpay_signature: string
}

type RazorpayPaymentFailureResponse = {
  error: {
    code?: string
    description?: string
    source?: string
    step?: string
    reason?: string
    metadata?: {
      order_id?: string
      subscription_id?: string
      payment_id?: string
    }
  }
}

type RazorpayCheckoutOptions = {
  key: string
  amount?: number
  currency?: string
  name: string
  description?: string
  order_id?: string
  subscription_id?: string
  handler?: (response: RazorpayPaymentSuccessResponse) => void
  prefill?: {
    name?: string
    email?: string
    contact?: string
  }
  notes?: Record<string, string>
  theme?: {
    color?: string
  }
  modal?: {
    ondismiss?: () => void
  }
}

type RazorpayInstance = {
  open: () => void
  on: (event: "payment.failed", handler: (response: RazorpayPaymentFailureResponse) => void) => void
}

interface Window {
  Razorpay?: new (options: RazorpayCheckoutOptions) => RazorpayInstance
}
