import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './AuthContext';
import Layout from './components/Layout';
import AuthPage from './pages/AuthPage';
import ClubPage from './pages/ClubPage';
import DiscoverPage from './pages/DiscoverPage';
import ThreadPage from './pages/ThreadPage';

function LoadingScreen() {
  return <div className="loading-screen"><span className="brand-mark">B</span><span>Opening your books…</span></div>;
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Routes><Route path="*" element={<AuthPage />} /></Routes>;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DiscoverPage />} />
        <Route path="clubs/:clubId" element={<ClubPage />} />
        <Route path="threads/:threadId" element={<ThreadPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

