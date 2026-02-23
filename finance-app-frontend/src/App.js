import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';

// Import Pages
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import AddExpense from './pages/AddExpense';
import Documents from './pages/Documents'; // Receipt list
import ReceiptDetail from './pages/ReceiptDetail';
import Reports from './pages/Reports';
import Planning from './pages/Planning';
import Expenses from './pages/Expenses';
import Incomes from './pages/Incomes';
import Insights from './pages/Insights';
import AIChat from './pages/AIChat';

// Global Styles
import './App.css';
import ErrorBoundary from './components/ErrorBoundary';

// Protected Route Component
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background-light dark:bg-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <ErrorBoundary>
            <Routes>
              {/* Public Routes */}
              <Route path="/login" element={<Login />} />

              {/* Protected Routes */}
              <Route path="/" element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              } />

              <Route path="/add-expense" element={
                <ProtectedRoute>
                  <AddExpense />
                </ProtectedRoute>
              } />

              <Route path="/receipts" element={
                <ProtectedRoute>
                  <Documents />
                </ProtectedRoute>
              } />

              <Route path="/receipts/:id" element={
                <ProtectedRoute>
                  <ReceiptDetail />
                </ProtectedRoute>
              } />

              <Route path="/reports" element={
                <ProtectedRoute>
                  <Reports />
                </ProtectedRoute>
              } />

              <Route path="/budget" element={
                <ProtectedRoute>
                  <Planning />
                </ProtectedRoute>
              } />

              <Route path="/expenses" element={
                <ProtectedRoute>
                  <Expenses />
                </ProtectedRoute>
              } />

              <Route path="/incomes" element={
                <ProtectedRoute>
                  <Incomes />
                </ProtectedRoute>
              } />

              <Route path="/insights" element={
                <ProtectedRoute>
                  <Insights />
                </ProtectedRoute>
              } />

              <Route path="/chat" element={
                <ProtectedRoute>
                  <AIChat />
                </ProtectedRoute>
              } />

              {/* Catch-all Route */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ErrorBoundary>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
