import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { BookIcon } from './Icons';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const initials = user?.name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase();

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/" className="brand"><span className="brand-mark">B</span><span>BookClub</span></NavLink>
        <nav className="main-nav"><NavLink to="/" end><BookIcon size={17} /> Discover clubs</NavLink></nav>
        <div className="account-menu">
          <span className="avatar">{initials}</span>
          <div><b>{user?.name}</b><button onClick={() => { logout(); navigate('/'); }}>Sign out</button></div>
        </div>
      </header>
      <main><Outlet /></main>
      <footer className="site-footer"><span><span className="brand-mark mini">B</span> Made for readers, by readers.</span><span>Read together. Think deeper.</span></footer>
    </div>
  );
}

