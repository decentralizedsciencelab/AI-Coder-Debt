import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, json } from '../api';
import type { Book, Club, ThreadSummary } from '../types';
import { ArrowIcon, MessageIcon, PlusIcon } from './Icons';
import Modal from './Modal';

export default function DiscussionsPanel({ club }: { club: Club }) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [chapter, setChapter] = useState<number | 'all'>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => api<{ threads: ThreadSummary[] }>(`/clubs/${club.id}/threads`).then((data) => setThreads(data.threads)).finally(() => setLoading(false)), [club.id]);
  useEffect(() => { void load(); }, [load]);
  const chapters = useMemo(() => [...new Set(threads.map((thread) => thread.chapterNumber))].sort((a, b) => a - b), [threads]);
  const shown = chapter === 'all' ? threads : threads.filter((thread) => thread.chapterNumber === chapter);

  return <section><div className="panel-heading"><div><p className="eyebrow">READ BETWEEN THE LINES</p><h2>Chapter discussions</h2><p>Spoilers stay contained, ideas get room to grow.</p></div>{club.currentBook && <button className="button primary" onClick={() => setShowCreate(true)}><PlusIcon/> Start a thread</button>}</div>
    <div className="discussion-toolbar"><div className="chapter-filters"><button className={chapter === 'all' ? 'active' : ''} onClick={() => setChapter('all')}>All chapters</button>{chapters.map((number) => <button className={chapter === number ? 'active' : ''} onClick={() => setChapter(number)} key={number}>Ch. {number}</button>)}</div><span>{shown.length} {shown.length === 1 ? 'thread' : 'threads'}</span></div>
    {loading ? <div className="empty-state">Loading conversations…</div> : shown.length ? <div className="thread-list">{shown.map((thread) => <Link className="thread-row" to={`/threads/${thread.id}`} key={thread.id}><div className="chapter-badge"><span>CHAPTER</span><b>{thread.chapterNumber}</b></div><div className="thread-copy"><span>{thread.book.title}</span><h3>{thread.title}</h3><p>Started by {thread.createdBy} · {relativeTime(thread.lastActivityAt ?? thread.createdAt)}</p></div><div className="thread-count"><MessageIcon/><b>{thread.postCount}</b><span>replies</span></div><ArrowIcon/></Link>)}</div> : <div className="content-card empty-state"><MessageIcon size={38}/><h3>No threads here yet</h3><p>Start with a question you can't stop thinking about.</p>{club.currentBook && <button className="button secondary" onClick={() => setShowCreate(true)}>Start the conversation</button>}</div>}
    {showCreate && club.currentBook && <CreateThreadModal club={club} defaultBook={club.currentBook} onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); void load(); }}/>} 
  </section>;
}

function CreateThreadModal({ club, defaultBook, onClose, onSaved }: { club: Club; defaultBook: Book; onClose: () => void; onSaved: () => void }) {
  const [chapterNumber, setChapterNumber] = useState(1); const [title, setTitle] = useState(''); const [body, setBody] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) { event.preventDefault(); setSaving(true); try { await api(`/clubs/${club.id}/threads`, { method: 'POST', ...json({ bookId: defaultBook.id, chapterNumber, title, body }) }); onSaved(); } catch (err) { setError(err instanceof Error ? err.message : 'Could not start thread'); setSaving(false); } }
  return <Modal title="Start a chapter thread" onClose={onClose}><form className="form-stack" onSubmit={submit}><div className="selected-book"><span>DISCUSSING</span><b>{defaultBook.title}</b><small>{defaultBook.author}</small></div><label>Chapter<input type="number" min={1} max={10000} value={chapterNumber} onChange={(e) => setChapterNumber(Number(e.target.value))} required/></label><label>Question or topic<input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What stayed with you?" required minLength={3}/></label><label>Your opening thought<textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} placeholder="Give the group somewhere interesting to begin…" required/></label>{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving}>{saving ? 'Posting…' : 'Start thread'}</button></div></form></Modal>;
}

function relativeTime(value: string) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  if (Math.abs(seconds) < 3600) return formatter.format(Math.round(seconds / 60), 'minute');
  if (Math.abs(seconds) < 86400) return formatter.format(Math.round(seconds / 3600), 'hour');
  return formatter.format(Math.round(seconds / 86400), 'day');
}

