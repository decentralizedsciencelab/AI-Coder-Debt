import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, json } from '../api';
import BookCover from '../components/BookCover';
import { MessageIcon } from '../components/Icons';
import type { ThreadDetail } from '../types';

export default function ThreadPage() {
  const { threadId = '' } = useParams();
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [posting, setPosting] = useState(false);

  const load = useCallback(() => api<{ thread: ThreadDetail }>(`/threads/${threadId}`).then((result) => setThread(result.thread)).catch((err) => setError(err instanceof Error ? err.message : 'Could not load thread')), [threadId]);
  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setPosting(true); setError('');
    try { await api(`/threads/${threadId}/posts`, { method: 'POST', ...json({ body }) }); setBody(''); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not post reply'); }
    finally { setPosting(false); }
  }

  if (!thread) return <div className="page-container empty-state">{error || 'Opening the conversation…'}</div>;
  return <div className="thread-page"><div className="thread-hero"><div className="page-container"><Link to={`/clubs/${thread.clubId}?tab=discussion`} className="back-link">‹ Back to discussions</Link><div className="thread-title-row"><div><p className="eyebrow">CHAPTER {thread.chapterNumber} · {thread.book.title.toUpperCase()}</p><h1>{thread.title}</h1><p>Started by {thread.createdBy} · {formatDate(thread.createdAt)}</p></div><BookCover book={thread.book} size="medium"/></div></div></div><div className="page-container conversation"><div className="conversation-heading"><div><MessageIcon/><h2>{thread.posts.length} {thread.posts.length === 1 ? 'thought' : 'thoughts'}</h2></div><span>Be curious. Be kind. Mind the chapter.</span></div><div className="posts">{thread.posts.map((post, index) => <article className="post" key={post.id}><div className="post-rail"><span className={`avatar shade-${index % 4}`}>{initials(post.author.name)}</span><span/></div><div className="post-body"><div><b>{post.author.name}</b><time>{formatDate(post.createdAt)}</time></div><p>{post.body}</p></div></article>)}</div><form className="reply-box" onSubmit={submit}><label htmlFor="reply">Add to the conversation</label><textarea id="reply" rows={5} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Share what you're thinking…" required/><div className="reply-actions"><span>Thoughtful replies make better reading.</span><button className="button primary" disabled={posting}>{posting ? 'Posting…' : 'Post reply'}</button></div>{error && <div className="form-error">{error}</div>}</form></div></div>;
}

function initials(name: string) { return name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase(); }
function formatDate(value: string) { return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value)); }

