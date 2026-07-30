import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { useState } from 'react';
import { ToastProvider } from './components/Toast.jsx';
import BuildInfo from './components/BuildInfo.jsx';
import { AuthProvider, useAuth } from './AuthContext.jsx';
import { ThemeProvider, useTheme } from './ThemeContext.jsx';
import { DisplayPrefsProvider } from './DisplayPrefsContext.jsx';
import LoginPage from './components/LoginPage.jsx';
import Dashboard from './components/Dashboard.jsx';
import VehicleList from './components/VehicleList.jsx';
import TyrePressures from './components/TyrePressures.jsx';
import VehicleDetail from './components/VehicleDetail.jsx';
import VehicleForm from './components/VehicleForm.jsx';
import ServiceList from './components/ServiceList.jsx';
import ServiceDetail from './components/ServiceDetail.jsx';
import ServiceForm from './components/ServiceForm.jsx';
import CodeLookup from './components/CodeLookup.jsx';
import AdminPage from './components/AdminPage.jsx';
import DvsaVehiclesPage from './components/DvsaVehiclesPage.jsx';
import SettingsPage from './components/SettingsPage.jsx';
import { FormMode, ROLE_LABELS } from './constants.js';

const THEME_ICON = { light: '☀', dark: '☾', system: '◐' };
const THEME_LABEL = { light: 'Light', dark: 'Dark', system: 'System' };

// One-tap theme rotation, shared by the sidebar and the mobile More menu.
function ThemeCycleButton() {
  const { mode, cycle } = useTheme();
  return (
    <button
      type="button"
      className="sidebar-nav-btn"
      onClick={cycle}
      aria-label={`Theme: ${THEME_LABEL[mode]}. Click to change.`}
    >
      {THEME_ICON[mode]} Theme: {THEME_LABEL[mode]}
    </button>
  );
}

function GarageSwitcher() {
  const { garages, currentGarage, selectGarage } = useAuth();
  if (!garages || garages.length === 0) return null;
  if (garages.length === 1) {
    return <div className="garage-switcher-single">{garages[0].name}</div>;
  }
  return (
    <select
      className="garage-switcher"
      value={currentGarage?.id ?? ''}
      onChange={e => selectGarage(Number(e.target.value))}
      aria-label="Switch garage"
    >
      {garages.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
    </select>
  );
}

function UserBadges() {
  const { user, currentGarage } = useAuth();
  return (
    <>
      {user?.is_admin && <span className="user-badge user-badge-admin">Site admin</span>}
      {!user?.is_admin && currentGarage && (
        <span className={`user-badge ${currentGarage.role === 'readonly' ? 'user-badge-readonly' : 'user-badge-normal'}`}>
          {ROLE_LABELS[currentGarage.role]}
        </span>
      )}
    </>
  );
}

function Nav() {
  const { user, logout } = useAuth();

  return (
    <nav className="sidebar">
      <img src="/wrench-icon.svg" className="sidebar-logo" alt="Wrench icon" />
      <div className="sidebar-title">Torqued</div>
      <div className="sidebar-tagline">All torque, no friction</div>
      <div className="sidebar-garage">
        <GarageSwitcher />
      </div>
      <NavLink to="/" end>Dashboard</NavLink>
      <hr className="sidebar-divider" />
      <NavLink to="/vehicles">Vehicles</NavLink>
      <NavLink to="/tyres">Tyre pressures</NavLink>
      <NavLink to="/services">Service log</NavLink>
      <NavLink to="/codes">Fault codes</NavLink>
      {user?.is_admin && <NavLink to="/dvsa-vehicles">DVSA Records</NavLink>}
      <div className="mt-auto">
        <div className="sidebar-user">
          <div className="sidebar-user-row">
            <div className="meta">{user?.username}</div>
            <UserBadges />
          </div>
        </div>
        {user?.is_admin && <NavLink to="/admin" className="sidebar-nav-btn">Admin</NavLink>}
        <NavLink to="/settings" className="sidebar-nav-btn">Settings</NavLink>
        <ThemeCycleButton />
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
            <div className="sidebar-garage">
              <GarageSwitcher />
            </div>
            <NavLink to="/tyres" className="sidebar-nav-btn" onClick={closeMore}>Tyre pressures</NavLink>
            <NavLink to="/codes" className="sidebar-nav-btn" onClick={closeMore}>Fault codes</NavLink>
            {user?.is_admin && (
              <NavLink to="/dvsa-vehicles" className="sidebar-nav-btn" onClick={closeMore}>DVSA Records</NavLink>
            )}
            <div className="sidebar-user">
              <div className="sidebar-user-row">
                <div className="text-sm fw-600">{user?.username}</div>
                <UserBadges />
              </div>
            </div>
            {user?.is_admin && (
              <NavLink to="/admin" className="sidebar-nav-btn" onClick={closeMore}>Admin</NavLink>
            )}
            <NavLink to="/settings" className="sidebar-nav-btn" onClick={closeMore}>Settings</NavLink>
            <ThemeCycleButton />
            <button className="sidebar-nav-btn text-danger" onClick={logout}>Sign out</button>
            <BuildInfo className="sidebar-version" />
          </div>
        </>
      )}
      <nav className="bottom-nav">
        <NavLink to="/" end className="bottom-nav-item" onClick={closeMore}>Dashboard</NavLink>
        <NavLink to="/vehicles" className="bottom-nav-item" onClick={closeMore}>Vehicles</NavLink>
        <NavLink to="/services" className="bottom-nav-item" onClick={closeMore}>Services</NavLink>
        <button className={`bottom-nav-item${moreOpen ? ' active' : ''}`} onClick={() => setMoreOpen(v => !v)}>
          More
        </button>
      </nav>
    </>
  );
}

function NoGarage() {
  const { user, logout } = useAuth();
  return (
    <div className="page-center">
      <div className="auth-card card card-body" style={{ textAlign: 'center' }}>
        <h1 className="page-title mb-3">No garage yet</h1>
        {user?.is_admin ? (
          <p className="text-muted">Create your first garage in the <NavLink to="/admin">admin panel</NavLink>.</p>
        ) : (
          <p className="text-muted">
            You&apos;re signed in as <strong>{user?.username}</strong>, but you&apos;re not a member of any
            garage yet. Ask an admin to add you.
          </p>
        )}
        <div className="mt-4">
          <button className="btn btn-secondary" onClick={logout}>Sign out</button>
        </div>
      </div>
    </div>
  );
}

function AppShell() {
  const { user, garages } = useAuth();

  if (user === undefined || (user && garages === null)) {
    return (
      <div className="page-center">
        <p className="text-muted">Loading…</p>
      </div>
    );
  }

  if (user === null) return <LoginPage />;

  if (garages.length === 0 && !user.is_admin) {
    return <NoGarage />;
  }

  return (
    <div className="layout">
      <Nav />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/vehicles" element={<VehicleList />} />
          <Route path="/tyres" element={<TyrePressures />} />
          <Route path="/vehicles/new" element={<VehicleForm mode={FormMode.CREATE} />} />
          <Route path="/vehicles/:id" element={<VehicleDetail />} />
          <Route path="/vehicles/:id/edit" element={<VehicleForm mode={FormMode.EDIT} />} />
          <Route path="/vehicles/:vehicleId/services/new" element={<ServiceForm mode={FormMode.CREATE} />} />
          <Route path="/services" element={<ServiceList />} />
          <Route path="/services/:id" element={<ServiceDetail />} />
          <Route path="/services/:id/edit" element={<ServiceForm mode={FormMode.EDIT} />} />
          <Route path="/codes" element={<CodeLookup />} />
          {user.is_admin && <Route path="/admin" element={<AdminPage />} />}
          {user.is_admin && <Route path="/dvsa-vehicles" element={<DvsaVehiclesPage />} />}
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
      <BottomNav />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ThemeProvider>
        <DisplayPrefsProvider>
          <AuthProvider>
            <ToastProvider>
              <AppShell />
            </ToastProvider>
          </AuthProvider>
        </DisplayPrefsProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
