import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from './api.js';

const AuthCtx = createContext(null);
const GARAGE_KEY = 'torqued.garage';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading
  const [garages, setGarages] = useState(null); // null = loading

  const refreshGarages = useCallback(() => {
    return api.getGarages().then(setGarages).catch(() => setGarages([]));
  }, []);

  useEffect(() => {
    api.getMe().then(setUser).catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (user) refreshGarages();
    else if (user === null) setGarages(null);
  }, [user, refreshGarages]);

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

  const login = async (username, password) => {
    const u = await api.login(username, password);
    setUser(u);
  };

  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{
      user, login, logout,
      garages, currentGarage, selectGarage, refreshGarages, roleFor,
    }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
