import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { usePostHog } from 'posthog-js/react';
import { api } from './api.js';

const AuthCtx = createContext(null);
const GARAGE_KEY = 'torqued.garage';

export function AuthProvider({ children }) {
  const posthog = usePostHog();
  const [user, setUser] = useState(undefined); // undefined = loading
  const [garages, setGarages] = useState(null); // null = loading
  const [dbSwitcher, setDbSwitcher] = useState(false); // dev-only DB picker available?

  const refreshGarages = useCallback(() => {
    return api.getGarages().then(setGarages).catch(() => setGarages([]));
  }, []);

  useEffect(() => {
    api.getMe().then(setUser).catch(() => setUser(null));
    api.getConfig().then(c => setDbSwitcher(!!c.db_switcher)).catch(() => setDbSwitcher(false));
  }, []);

  useEffect(() => {
    if (user) refreshGarages();
    else if (user === null) setGarages(null);
  }, [user, refreshGarages]);

  // Tie the PostHog person to our user across login, logout, and session restore.
  useEffect(() => {
    if (user === undefined) return; // still loading — do nothing yet
    if (user) posthog?.identify(String(user.id), {
      username: user.username, is_admin: !!user.is_admin,
    });
    else posthog?.reset(); // logged out
  }, [user, posthog]);

  const [currentGarageId, setCurrentGarageId] = useState(() => {
    const saved = localStorage.getItem(GARAGE_KEY);
    return saved ? Number(saved) : null;
  });

  const selectGarage = (id) => {
    setCurrentGarageId(id);
    localStorage.setItem(GARAGE_KEY, String(id));
  };

  const currentGarage =
    garages?.find(g => g.id === currentGarageId) ?? garages?.[0] ?? null;

  // Effective role in a garage: site admins are owners everywhere.
  const roleFor = (garageId) => {
    if (!user) return null;
    if (user.is_admin) return 'owner';
    return user.memberships?.find(m => m.garage_id === garageId)?.role ?? null;
  };

  const login = async (username, password, database) => {
    const u = await api.login(username, password, database);
    setUser(u);
  };

  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{
      user, login, logout, dbSwitcher,
      garages, currentGarage, selectGarage, refreshGarages, roleFor,
    }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
