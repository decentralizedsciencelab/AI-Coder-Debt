import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, json } from '../api';
import BookCover from '../components/BookCover';
import { ArrowIcon, PlusIcon, SearchIcon, UsersIcon } from '../components/Icons';
import Modal from '../components/Modal';
import type { Club } from '../types';

export default function DiscoverPage() {
  const navigate = useNavigate();
  const [clubs, setClubs] = useState<Club[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      api<{ clubs: Club[] }>(`/clubs${search ? `?search=${encodeURIComponent(search)}` : ''}`)
        .then((result) => setClubs(result.clubs)).finally(() => setLoading(false));
    }, 180);
    return () => clearTimeout(timer);
  }, [search]);

  const myClubs = clubs.filter((club) => club.isMember);
  const otherClubs = clubs.filter((club) => !club.isMember);

  return (
    <div className="page-container discover-page">
      <section className="page-intro">
        <div><p className="eyebrow">FIND YOUR PEOPLE</p><h1>Stories worth <em>sharing.</em></h1><p>Join a circle of curious readers—or start one of your own.</p></div>
        <button className="button primary" onClick={() => setShowCreate(true)}><PlusIcon /> Start a club</button>
      </section>
      <div className="search-box"><SearchIcon/><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by club name or interest…" /></div>
      {loading ? <div className="empty-state">Finding your next conversation…</div> : <>
        {myClubs.length > 0 && <ClubSection title="Your clubs" subtitle="Pick up where you left off" clubs={myClubs} />}
        {otherClubs.length > 0 && <ClubSection title={myClubs.length ? 'Discover more' : 'Explore clubs'} subtitle="Open circles looking for another perspective" clubs={otherClubs} />}
        {!clubs.length && <div className="empty-state"><h3>No clubs found</h3><p>Try a broader search, or start a new circle.</p></div>}
      </>}
      {showCreate && <CreateClubModal onClose={() => setShowCreate(false)} onCreated={(id) => navigate(`/clubs/${id}`)} />}
    </div>
  );
}

function ClubSection({ title, subtitle, clubs }: { title: string; subtitle: string; clubs: Club[] }) {
  return <section className="club-section"><div className="section-heading"><div><h2>{title}</h2><p>{subtitle}</p></div><span>{clubs.length} {clubs.length === 1 ? 'club' : 'clubs'}</span></div><div className="club-grid">{clubs.map((club) => <ClubCard key={club.id} club={club}/>)}</div></section>;
}

function ClubCard({ club }: { club: Club }) {
  return (
    <Link to={`/clubs/${club.id}`} className="club-card">
      <div className="club-card-accent" />
      <div className="club-card-body">
        <div className="club-card-top"><span className={`status-pill ${club.isMember ? 'member' : ''}`}>{club.isMember ? 'Your club' : 'Open club'}</span><ArrowIcon/></div>
        <h3>{club.name}</h3><p>{club.description}</p>
        {club.currentBook ? <div className="currently-reading"><BookCover book={club.currentBook} size="small"/><div><span>NOW READING</span><b>{club.currentBook.title}</b><small>{club.currentBook.author}</small></div></div> : <div className="currently-reading no-book">Choosing their first read</div>}
      </div>
      <div className="club-card-footer"><span><UsersIcon size={16}/> {club.memberCount} members</span><span>Hosted by {club.ownerName}</span></div>
    </Link>
  );
}

function CreateClubModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [isPublic, setIsPublic] = useState(true); const [error, setError] = useState(''); const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('');
    try { const { club } = await api<{ club: Club }>('/clubs', { method: 'POST', ...json({ name, description, isPublic }) }); onCreated(club.id); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not create club'); setSaving(false); }
  }
  return <Modal title="Start a new club" onClose={onClose}><form className="form-stack" onSubmit={submit}><label>Club name<input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="The Sunday Shelf" required minLength={3}/></label><label>What will you read?<textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Tell future members what makes this circle special…" rows={4}/></label><label className="checkbox-label"><input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)}/><span><b>Open to everyone</b><small>Anyone can discover and join this club.</small></span></label>{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving}>{saving ? 'Creating…' : 'Create club'}</button></div></form></Modal>;
}

