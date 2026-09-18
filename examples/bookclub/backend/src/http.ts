import type { NextFunction, Request, RequestHandler, Response } from 'express';
import { ZodError } from 'zod';

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export const asyncHandler = (handler: RequestHandler): RequestHandler =>
  (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(handler(req, res, next)).catch(next);
  };

export function errorHandler(error: unknown, _req: Request, res: Response, _next: NextFunction) {
  if (error instanceof ZodError) {
    return res.status(400).json({ error: 'Invalid request', details: error.flatten() });
  }
  if (error instanceof HttpError) {
    return res.status(error.status).json({ error: error.message });
  }
  const pgError = error as { code?: string; constraint?: string };
  if (pgError.code === '23505') {
    return res.status(409).json({ error: 'That record already exists' });
  }
  if (pgError.code === '23503') {
    return res.status(400).json({ error: 'A referenced record does not exist' });
  }
  console.error(error);
  return res.status(500).json({ error: 'Internal server error' });
}

