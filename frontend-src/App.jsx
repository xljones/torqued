import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { useState } from 'react';
import { ToastProvider } from './components/Toast.jsx';
import BuildInfo from './components/BuildInfo.jsx';
import { AuthProvider, useAuth } from './AuthContext.jsx';
import LoginPage from './components/LoginPage.jsx';
import Dashboard from './components/Dashboard.jsx';
import VehicleList from './components/VehicleList.jsx';
import VehicleDetail from './components/VehicleDetail.jsx';
import VehicleForm from './components/VehicleForm.jsx';
import ServiceList from './components/ServiceList.jsx';
import ServiceDetail from './components/ServiceDetail.jsx';
import ServiceForm from './components/ServiceForm.jsx';
import { FormMode } from './constants.js';
import UserList from './components/UserList.jsx';
import AccountPage from './components/AccountPage.jsx';

function Nav() {
  const { user, logout } = useAuth();

  return (
    <nav className="sidebar">
      <img src="/wrench-icon.svg" className="sidebar-logo" alt="Wrench icon" />
      <div className="sidebar-title">Torqued</div>
      <div className="sidebar-tagline">All torque, no friction</div>
      <NavLink to="/" end>Dashboard</NavLink>
      <hr className="sidebar-divider" />
      <NavLink to="/vehicles">Garage</NavLink>
      <NavLink to="/services">Service log</NavLink>
      <div className="mt-auto">
        <div className="sidebar-user">
          <div className="sidebar-user-row">
            <div className="meta">{user?.username}</div>
            {user?.is_admin && <span className="user-badge user-badge-admin">Admin</span>}
            {user?.is_readonly && <span className="user-badge user-badge-readonly">Read-only</span>}
          </div>
        </div>
        {user?.is_admin && <NavLink to="/admin" className="sidebar-nav-btn">Admin</NavLink>}
        <NavLink to="/account" className="sidebar-nav-btn">Change password</NavLink>
        <button className="sidebar-nav-btn text-danger" onClick={logout}>Sign out</button>
        <div className="sidebar-road-wrap">
          <div className="sidebar-road" aria-hidden="true" />
          <BuildInfo className="sidebar-version" />
        </div>
      </div>
    </nav>
  );
}

function BottomNav() {
  const { user, logout } = useAuth();
  const [moreOpen, setMoreOpen] = useState(false);
  const closeMore = () => setMoreOpen(false);

  return (
    <>
      {moreOpen && (
        <>
          <div className="bottom-nav-backdrop" onClick={closeMore} />
          <div className="bottom-nav-more">
            <div className="sidebar-user">
              <div className="sidebar-user-row">
                <div className="text-sm fw-600">{user?.username}</div>
                {user?.is_admin && <span className="user-badge user-badge-admin">Admin</span>}
                {user?.is_readonly && <span className="user-badge user-badge-readonly">Read-only</span>}
              </div>
            </div>
            {user?.is_admin && (
              <NavLink to="/admin" className="sidebar-nav-btn" onClick={closeMore}>Admin</NavLink>
            )}
            <NavLink to="/account" className="sidebar-nav-btn" onClick={closeMore}>Change password</NavLink>
            <button className="sidebar-nav-btn text-danger" onClick={logout}>Sign out</button>
            <BuildInfo className="sidebar-version" />
          </div>
        </>
      )}
      <nav className="bottom-nav">
        <NavLink to="/" end className="bottom-nav-item" onClick={closeMore}>Dashboard</NavLink>
        <NavLink to="/vehicles" className="bottom-nav-item" onClick={closeMore}>Garage</NavLink>
        <NavLink to="/services" className="bottom-nav-item" onClick={closeMore}>Services</NavLink>
        <button className={`bottom-nav-item${moreOpen ? ' active' : ''}`} onClick={() => setMoreOpen(v => !v)}>
          More
        </button>
      </nav>
    </>
  );
}

function AppShell() {
  const { user } = useAuth();

  if (user === undefined) {
    return (
      <div className="page-center">
        <p className="text-muted">Loading…</p>
      </div>
    );
  }

  if (user === null) return <LoginPage />;

  return (
    <div className="layout">
      <Nav />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/vehicles" element={<VehicleList />} />
          <Route path="/vehicles/new" element={<VehicleForm mode={FormMode.CREATE} />} />
          <Route path="/vehicles/:id" element={<VehicleDetail />} />
          <Route path="/vehicles/:id/edit" element={<VehicleForm mode={FormMode.EDIT} />} />
          <Route path="/vehicles/:vehicleId/services/new" element={<ServiceForm mode={FormMode.CREATE} />} />
          <Route path="/services" element={<ServiceList />} />
          <Route path="/services/:id" element={<ServiceDetail />} />
          <Route path="/services/:id/edit" element={<ServiceForm mode={FormMode.EDIT} />} />
          {user.is_admin && <Route path="/admin" element={<UserList />} />}
          <Route path="/account" element={<AccountPage />} />
        </Routes>
      </main>
      <BottomNav />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <AppShell />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
