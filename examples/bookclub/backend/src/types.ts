import type { Request } from 'express';

export interface JwtUser {
  id: string;
  email: string;
  name: string;
}

export interface AuthenticatedRequest extends Request {
  user?: JwtUser;
}

