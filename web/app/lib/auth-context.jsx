"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { apiFetch, ApiError } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/auth/me")
      .then(setUser)
      .catch((e) => { if (!(e instanceof ApiError && e.status === 401)) console.error(e); })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const u = await apiFetch("/auth/login", { method: "POST", body: { email, password } });
    setUser(u);
    return u;
  };
  const signup = async (email, password) => {
    const u = await apiFetch("/auth/signup", { method: "POST", body: { email, password } });
    setUser(u);
    return u;
  };
  const logout = async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
