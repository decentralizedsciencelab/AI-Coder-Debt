import { useCallback, useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import BookCover from '../components/BookCover';
import { ArrowIcon, BookIcon, MessageIcon, UsersIcon, VoteIcon } from '../components/Icons';
import type { Club, User } from '../types';
import DiscussionsPanel from '../components/DiscussionsPanel';
import VotingPanel from '../components/VotingPanel';

type Tab = 'overview' | 'vote' | 'discussion' | 'members';
interface Member extends User { role: 'owner' | 'moderator' | 'member'; joinedAt: string }

export default function ClubPage() {
  const { clubId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (['overview', 'vote', 'discussion', 'members'].includes(params.get('tab') ?? '') ? params.get('tab') : 'overview') as Tab;
  const [club, setClub] = useState<Club | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadClub = useCallback(async () => {
    try {
      const result = await api<{ club: Club }>(`/clubs/${clubId}`); setClub(result.club);
      if (result.club.isMember) api<{ members: Member[] }>(`/clubs/${clubId}/members`).then((data) => setMembers(data.members));
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load club'); }
    finally { setLoading(false); }
  }, [clubId]);

  useEffect(() => { void loadClub(); }, [loadClub]);

  async function join() {
    await api(`/clubs/${clubId}/join`, { method: 'POST' });
    await loadClub();
  }

  if (loading) return <div className="page-container empty-state">Opening the club room…</div>;
  if (!club) return <div className="page-container empty-state"><h2>{error || 'Club not found'}</h2><Link to="/" className="text-link">Return to clubs</Link></div>;

  const initials = club.name.split(' ').map((part) => part[0]).slice(0, 2).join('');
  return (
    <div className="club-page">
      <div className="club-hero">
        <div className="page-container">
          <Link to="/" className="back-link">‹ All clubs</Link>
          <div className="club-identity"><div className="club-monogram">{initials}</div><div><div className="club-meta"><span>{club.isPublic ? 'OPEN CLUB' : 'PRIVATE CLUB'}</span><span>·</span><span><UsersIcon size={14}/> {club.memberCount} MEMBERS</span></div><h1>{club.name}</h1><p>{club.description}</p><small>Hosted by {club.ownerName}</small></div>{!club.isMember && <button className="button light" onClick={join}>Join this club <ArrowIcon/></button>}</div>
        </div>
      </div>
      <div className="club-tabs-wrap"><nav className="club-tabs page-container">
        <TabButton active={tab === 'overview'} onClick={() => setParams({ tab: 'overview' })} icon={<BookIcon/>}>Overview</TabButton>
        <TabButton active={tab === 'vote'} onClick={() => setParams({ tab: 'vote' })} icon={<VoteIcon/>}>Next read</TabButton>
        <TabButton active={tab === 'discussion'} onClick={() => setParams({ tab: 'discussion' })} icon={<MessageIcon/>}>Discussions</TabButton>
        <TabButton active={tab === 'members'} onClick={() => setParams({ tab: 'members' })} icon={<UsersIcon/>}>Members</TabButton>
      </nav></div>
      <div className="page-container club-content">
        {!club.isMember ? <JoinPrompt club={club} onJoin={join}/> : <>
          {tab === 'overview' && <Overview club={club} members={members} setTab={(next) => setParams({ tab: next })}/>} 
          {tab === 'vote' && <VotingPanel club={club}/>} 
          {tab === 'discussion' && <DiscussionsPanel club={club}/>} 
          {tab === 'members' && <Members members={members}/>} 
        </>}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return <button className={active ? 'active' : ''} onClick={onClick}>{icon}{children}</button>;
}

function JoinPrompt({ club, onJoin }: { club: Club; onJoin: () => void }) {
  return <div className="join-prompt"><div className="join-illustration"><BookIcon size={42}/></div><h2>Pull up a chair</h2><p>Join {club.name} to vote on books and take part in chapter discussions.</p><button className="button primary" onClick={onJoin}>Join {club.name}</button></div>;
}

function Overview({ club, members, setTab }: { club: Club; members: Member[]; setTab: (tab: Tab) => void }) {
  return <div className="overview-grid"><section className="content-card reading-card"><div className="card-label">CURRENTLY READING</div>{club.currentBook ? <div className="featured-book"><BookCover book={club.currentBook} size="large"/><div><h2>{club.currentBook.title}</h2><h3>{club.currentBook.author}</h3><p>{club.currentBook.description}</p><button className="button primary" onClick={() => setTab('discussion')}><MessageIcon/> Join the discussion</button></div></div> : <div className="empty-inline"><h2>No current read yet</h2><p>Vote together and choose the club's first book.</p><button className="button primary" onClick={() => setTab('vote')}>See the ballot</button></div>}</section><aside className="overview-side"><section className="content-card"><div className="aside-heading"><h3>Reading circle</h3><button onClick={() => setTab('members')}>View all</button></div><div className="member-stack">{members.slice(0, 5).map((member, index) => <div className="member-row" key={member.id}><span className={`avatar shade-${index % 4}`}>{initials(member.name)}</span><div><b>{member.name}</b><small>{member.role === 'owner' ? 'Club host' : member.role}</small></div></div>)}</div></section><section className="content-card prompt-card"><span>THIS WEEK'S PROMPT</span><blockquote>“Which character's choices surprised you most—and why?”</blockquote><button onClick={() => setTab('discussion')}>Share your take <ArrowIcon size={16}/></button></section></aside></div>;
}

function Members({ members }: { members: Member[] }) {
  return <section><div className="panel-heading"><div><p className="eyebrow">THE READING CIRCLE</p><h2>{members.length} thoughtful readers</h2></div></div><div className="members-grid">{members.map((member, index) => <article className="content-card member-card" key={member.id}><span className={`avatar large shade-${index % 4}`}>{initials(member.name)}</span><div><h3>{member.name}</h3><p>{member.email}</p><span className="status-pill member">{member.role}</span></div></article>)}</div></section>;
}

function initials(name: string) { return name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase(); }

