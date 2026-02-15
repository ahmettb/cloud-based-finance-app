import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../services/api';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Check if user is logged in
        const checkAuth = async () => {
            try {
                const currentUser = api.getCurrentUser();
                if (currentUser) {
                    setUser(currentUser);
                } else {
                    // Try to refresh or verify token
                    // api.fetchWithAuth('/auth/me'); // Optional: force refresh
                }
            } catch (error) {
                console.error('Auth check failed:', error);
            } finally {
                setLoading(false);
            }
        };
        checkAuth();
    }, []);

    const login = async (email, password) => {
        try {
            const data = await api.login(email, password);
            setUser(api.getCurrentUser()); // Update state from local storage
            return data;
        } catch (error) {
            throw error;
        }
    };

    const logout = () => {
        api.logout();
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
