import { useState, type FormEvent } from 'react';
import { useAuth } from '../AuthContext';

export default function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('maya@bookclub.local');
  const [password, setPassword] = useState('password123');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setSubmitting(true);
    try {
      if (mode === 'login') await login(email, password);
      else await register(name, email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not continue');
    } finally { setSubmitting(false); }
  }

  return (
    <main className="auth-page">
      <section className="auth-story">
        <div className="brand light"><span className="brand-mark">B</span><span>BookClub</span></div>
        <div className="story-copy"><p className="eyebrow">YOUR NEXT GREAT CONVERSATION</p><h1>Books are better<br/><em>when shared.</em></h1><p>Create a reading circle, choose your next story together, and keep every thoughtful conversation in one place.</p></div>
        <div className="quote-card"><p>“Reading is an exercise in empathy; an exercise in walking in someone else's shoes for a while.”</p><span>— Malorie Blackman</span></div>
      </section>
      <section className="auth-panel">
        <div className="auth-box">
          <p className="eyebrow">WELCOME {mode === 'login' ? 'BACK' : 'IN'}</p>
          <h2>{mode === 'login' ? 'Continue your story' : 'Start your reading life'}</h2>
          <p className="muted">{mode === 'login' ? 'Sign in to your clubs and conversations.' : 'Create your free BookClub account.'}</p>
          <form onSubmit={submit} className="form-stack">
            {mode === 'register' && <label>Your name<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Avid Reader" required minLength={2}/></label>}
            <label>Email address<input autoFocus={mode === 'login'} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required/></label>
            <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}/></label>
            {error && <div className="form-error">{error}</div>}
            <button className="button primary full" disabled={submitting}>{submitting ? 'One moment…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
          </form>
          {mode === 'login' && <div className="demo-note"><b>Demo account</b><span>maya@bookclub.local · password123</span></div>}
          <p className="auth-switch">{mode === 'login' ? 'New to BookClub?' : 'Already a member?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p>
        </div>
      </section>
    </main>
  );
}

