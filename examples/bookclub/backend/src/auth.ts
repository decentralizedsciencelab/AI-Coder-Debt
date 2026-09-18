import type { NextFunction, Response } from 'express';
import jwt, { type SignOptions } from 'jsonwebtoken';
import { config } from './config.js';
import type { AuthenticatedRequest, JwtUser } from './types.js';

export function signToken(user: JwtUser): string {
  return jwt.sign(user, config.jwtSecret, {
    expiresIn: config.jwtExpiresIn as SignOptions['expiresIn'],
  });
}

export function authenticate(req: AuthenticatedRequest, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace(/^Bearer\s+/i, '');
  if (!token) return res.status(401).json({ error: 'Authentication required' });

  try {
    req.user = jwt.verify(token, config.jwtSecret) as JwtUser;
    next();
  } catch {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

export function optionalAuth(req: AuthenticatedRequest, _res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace(/^Bearer\s+/i, '');
  if (token) {
    try {
      req.user = jwt.verify(token, config.jwtSecret) as JwtUser;
    } catch {
      // Public endpoints remain accessible when a stale token is supplied.
    }
  }
  next();
}

