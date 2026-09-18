import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api, json } from '../api';
import type { Book, Club, VotingRound } from '../types';
import BookCover from './BookCover';
import { CalendarIcon, PlusIcon, VoteIcon } from './Icons';
import Modal from './Modal';

export default function VotingPanel({ club }: { club: Club }) {
  const [rounds, setRounds] = useState<VotingRound[]>([]);
  const [loading, setLoading] = useState(true);
  const [showProposal, setShowProposal] = useState(false);
  const [showRound, setShowRound] = useState(false);
  const [message, setMessage] = useState('');
  const activeRound = rounds.find((round) => round.status === 'open');

  const load = useCallback(() => api<{ rounds: VotingRound[] }>(`/clubs/${club.id}/rounds`).then((data) => setRounds(data.rounds)).finally(() => setLoading(false)), [club.id]);
  useEffect(() => { void load(); }, [load]);

  async function vote(roundId: string, candidateId: string) {
    setMessage('');
    try { await api(`/rounds/${roundId}/vote`, { method: 'PUT', ...json({ candidateId }) }); setMessage('Your vote is in. You can change it until the round closes.'); await load(); }
    catch (err) { setMessage(err instanceof Error ? err.message : 'Could not save vote'); }
  }

  if (loading) return <div className="empty-state">Counting the ballots…</div>;
  return <section><div className="panel-heading"><div><p className="eyebrow">CHOOSE TOGETHER</p><h2>What should we read next?</h2><p>Propose a title, make your case, and cast one vote.</p></div><div className="button-group">{activeRound && <button className="button secondary" onClick={() => setShowProposal(true)}><PlusIcon/> Propose a book</button>}{['owner','moderator'].includes(club.myRole ?? '') && !activeRound && <button className="button primary" onClick={() => setShowRound(true)}><PlusIcon/> Start a vote</button>}</div></div>
    {message && <div className="notice">{message}</div>}
    {activeRound ? <RoundCard round={activeRound} onVote={vote}/> : <div className="content-card empty-state"><VoteIcon size={36}/><h3>No open vote right now</h3><p>A club host can start the next voting round.</p></div>}
    {rounds.filter((round) => round.status === 'closed').length > 0 && <div className="past-rounds"><h3>Past selections</h3>{rounds.filter((round) => round.status === 'closed').map((round) => <RoundCard key={round.id} round={round} onVote={vote}/>)}</div>}
    {showProposal && activeRound && <ProposalModal round={activeRound} onClose={() => setShowProposal(false)} onSaved={() => { setShowProposal(false); void load(); }}/>} 
    {showRound && <CreateRoundModal clubId={club.id} onClose={() => setShowRound(false)} onSaved={() => { setShowRound(false); void load(); }}/>} 
  </section>;
}

function RoundCard({ round, onVote }: { round: VotingRound; onVote: (roundId: string, candidateId: string) => void }) {
  const totalVotes = round.candidates.reduce((sum, candidate) => sum + candidate.voteCount, 0);
  const closed = round.status === 'closed';
  return <div className={`round-card ${closed ? 'closed' : ''}`}><div className="round-heading"><div><span className={`status-pill ${closed ? '' : 'member'}`}>{closed ? 'Closed' : 'Vote open'}</span><h3>{round.title}</h3></div><span className="round-time"><CalendarIcon/>{closed ? `Closed ${formatDate(round.closedAt ?? round.closesAt)}` : `Closes ${formatDate(round.closesAt)}`}</span></div><div className="ballot-grid">{round.candidates.map((candidate) => { const selected = round.myVote === candidate.id; const winner = closed && round.winnerBookId === candidate.book.id; const percent = totalVotes ? Math.round(candidate.voteCount / totalVotes * 100) : 0; return <button disabled={closed} onClick={() => onVote(round.id, candidate.id)} className={`ballot-card ${selected ? 'selected' : ''} ${winner ? 'winner' : ''}`} key={candidate.id}><BookCover book={candidate.book} size="medium"/><div className="ballot-info">{winner && <span className="winner-label">CLUB PICK</span>}<h4>{candidate.book.title}</h4><span className="book-author">{candidate.book.author}</span><p>“{candidate.pitch || 'A title worth considering together.'}”</p><small>Proposed by {candidate.proposedBy}</small><div className="vote-progress"><span style={{ width: `${percent}%` }}/></div><div className="vote-line"><span>{candidate.voteCount} {candidate.voteCount === 1 ? 'vote' : 'votes'} · {percent}%</span>{!closed && <span className="radio">{selected ? '✓' : ''}</span>}</div></div></button>; })}</div>{!round.candidates.length && <div className="empty-inline">No books have been proposed yet.</div>}</div>;
}

function ProposalModal({ round, onClose, onSaved }: { round: VotingRound; onClose: () => void; onSaved: () => void }) {
  const [books, setBooks] = useState<Book[]>([]); const [bookId, setBookId] = useState(''); const [mode, setMode] = useState<'library' | 'new'>('library'); const [title, setTitle] = useState(''); const [author, setAuthor] = useState(''); const [coverUrl, setCoverUrl] = useState(''); const [pitch, setPitch] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false);
  useEffect(() => { api<{ books: Book[] }>('/books').then((result) => { const eligible = result.books.filter((book) => !round.candidates.some((candidate) => candidate.book.id === book.id)); setBooks(eligible); setBookId(eligible[0]?.id ?? ''); }); }, [round]);
  async function submit(e: FormEvent) { e.preventDefault(); setSaving(true); setError(''); try { let selectedBookId = bookId; if (mode === 'new') { const result = await api<{ book: Book }>('/books', { method: 'POST', ...json({ title, author, coverUrl: coverUrl || null }) }); selectedBookId = result.book.id; } await api(`/rounds/${round.id}/candidates`, { method: 'POST', ...json({ bookId: selectedBookId, pitch }) }); onSaved(); } catch (err) { setError(err instanceof Error ? err.message : 'Could not add proposal'); setSaving(false); } }
  return <Modal title="Propose the next read" onClose={onClose}><form className="form-stack" onSubmit={submit}><div className="choice-tabs"><button type="button" className={mode === 'library' ? 'active' : ''} onClick={() => setMode('library')}>From the library</button><button type="button" className={mode === 'new' ? 'active' : ''} onClick={() => setMode('new')}>Add a new book</button></div>{mode === 'library' ? <label>Choose a book<select value={bookId} onChange={(e) => setBookId(e.target.value)} required>{books.map((book) => <option value={book.id} key={book.id}>{book.title} — {book.author}</option>)}</select></label> : <><label>Book title<input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="The title" required/></label><label>Author<input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Author name" required/></label><label>Cover image URL <span className="optional">optional</span><input type="url" value={coverUrl} onChange={(e) => setCoverUrl(e.target.value)} placeholder="https://…"/></label></>}<label>Make your case<textarea rows={4} value={pitch} onChange={(e) => setPitch(e.target.value)} placeholder="Why is this a great choice for the group?" maxLength={2000}/></label>{mode === 'library' && !books.length && <div className="form-error">Every library book is on the ballot. Add a new one instead.</div>}{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving || (mode === 'library' ? !bookId : !title || !author)}>{saving ? 'Adding…' : 'Add to ballot'}</button></div></form></Modal>;
}

function CreateRoundModal({ clubId, onClose, onSaved }: { clubId: string; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState('Our next read'); const [closesAt, setClosesAt] = useState(() => { const date = new Date(Date.now() + 7 * 86400000); return date.toISOString().slice(0, 16); }); const [error, setError] = useState('');
  async function submit(e: FormEvent) { e.preventDefault(); try { await api(`/clubs/${clubId}/rounds`, { method: 'POST', ...json({ title, closesAt: new Date(closesAt).toISOString() }) }); onSaved(); } catch (err) { setError(err instanceof Error ? err.message : 'Could not start vote'); } }
  return <Modal title="Start a voting round" onClose={onClose}><form className="form-stack" onSubmit={submit}><label>Round title<input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3}/></label><label>Voting closes<input type="datetime-local" value={closesAt} onChange={(e) => setClosesAt(e.target.value)} required/></label>{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Cancel</button><button className="button primary">Open voting</button></div></form></Modal>;
}

function formatDate(value: string) { return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value)); }
