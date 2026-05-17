import { z } from 'zod';

export const LoginSchema = z.object({
  username: z.string().min(1).max(64),
  password: z.string().min(1).max(128),
});

export const CreateUserSchema = z.object({
  username: z
    .string()
    .min(3)
    .max(64)
    .regex(/^[a-zA-Z0-9_-]+$/, {
      message: 'username may only contain letters, digits, underscore, and hyphen',
    }),
  password: z.string().min(8).max(128),
  is_admin: z.boolean().default(false),
});

export type LoginData = z.infer<typeof LoginSchema>;
export type CreateUserData = z.infer<typeof CreateUserSchema>;
