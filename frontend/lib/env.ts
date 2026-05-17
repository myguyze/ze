import { z } from "zod"

const schema = z.object({
  NEXT_PUBLIC_ZE_API_KEY: z.string().min(1),
  NEXT_PUBLIC_ZE_WS_URL: z.string().url(),
  NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS: z.coerce.number().default(900),
})

export const env = schema.parse({
  NEXT_PUBLIC_ZE_API_KEY: process.env.NEXT_PUBLIC_ZE_API_KEY,
  NEXT_PUBLIC_ZE_WS_URL: process.env.NEXT_PUBLIC_ZE_WS_URL,
  NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS: process.env.NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS,
})
