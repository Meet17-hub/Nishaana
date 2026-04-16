export const PAID_PLAN_CODES = ["monthly", "half_yearly", "yearly"] as const
export type PaidPlanCode = (typeof PAID_PLAN_CODES)[number]
export type PlanCode = PaidPlanCode | "trial"

export type SubscriptionSnapshot = {
  subscription_end?: string | null
}

const PLAN_DURATIONS_MS: Record<PaidPlanCode, number> = {
  monthly: 24 * 60 * 60 * 1000,
  half_yearly: 180 * 24 * 60 * 60 * 1000,
  yearly: 365 * 24 * 60 * 60 * 1000,
}

export function isPaidPlanCode(value: string | null | undefined): value is PaidPlanCode {
  return value === "monthly" || value === "half_yearly" || value === "yearly"
}

export function getPlanDurationMs(planCode: PlanCode): number {
  if (planCode === "trial") {
    return 24 * 60 * 60 * 1000
  }

  return PLAN_DURATIONS_MS[planCode]
}

export function hasActiveSubscription(user: SubscriptionSnapshot | null | undefined): boolean {
  const expiry = user?.subscription_end
  if (!expiry) {
    return false
  }

  const expiryDate = new Date(expiry)
  if (Number.isNaN(expiryDate.getTime())) {
    return false
  }

  return expiryDate.getTime() > Date.now()
}
