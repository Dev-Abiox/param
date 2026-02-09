import React, { useState } from 'react';
import { Activity, Lock, User, FlaskConical, ArrowLeft, Mail, CheckCircle } from 'lucide-react';

interface LoginProps {
  onLogin: (u: string, p: string) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

const Login: React.FC<LoginProps> = ({ onLogin, isLoading, error }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [view, setView] = useState<'login' | 'forgot_password'>('login');
  const [resetStatus, setResetStatus] = useState<'idle' | 'loading' | 'success'>('idle');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLogin(username, password);
  };

  const handleResetSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setResetStatus('loading');
    // Simulate API call
    setTimeout(() => {
      setResetStatus('success');
    }, 1500);
  };

  const toggleView = () => {
    setView(view === 'login' ? 'forgot_password' : 'login');
    setResetStatus('idle');
  };

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <div className="h-16 w-16 bg-teal-600 rounded-xl flex items-center justify-center shadow-lg transform rotate-3">
            <FlaskConical className="h-10 w-10 text-white" />
          </div>
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900 tracking-tight">
          Clinomic Labs
        </h2>
        <p className="mt-2 text-center text-sm text-slate-600">
          Pathology LIS & Screening System
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200">
          
          {view === 'login' ? (
            <form className="space-y-6" onSubmit={handleSubmit}>
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                  Lab ID / Username
                </label>
                <div className="mt-1 relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                    placeholder="lab"
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <button 
                    type="button" 
                    className="text-xs font-medium text-teal-600 hover:text-teal-500 focus:outline-none"
                    onClick={toggleView}
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative rounded-md shadow-sm">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-slate-400" />
                  </div>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                    placeholder="admin"
                  />
                </div>
              </div>

              {error && (
                <div className="text-red-600 text-sm bg-red-50 p-2 rounded border border-red-100 text-center">
                  {error}
                </div>
              )}

              <div>
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-700 hover:bg-teal-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? 'Connecting...' : 'Sign in'}
                </button>
              </div>
            </form>
          ) : (
            <div className="space-y-6">
              <div className="text-center">
                <h3 className="text-lg font-medium text-slate-900">Account Recovery</h3>
                <p className="mt-1 text-sm text-slate-500">
                  Enter your Lab ID or registered email address. We'll send you instructions to reset your password.
                </p>
              </div>

              {resetStatus === 'success' ? (
                <div className="rounded-md bg-green-50 p-4">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <CheckCircle className="h-5 w-5 text-green-400" aria-hidden="true" />
                    </div>
                    <div className="ml-3">
                      <h3 className="text-sm font-medium text-green-800">Recovery email sent</h3>
                      <div className="mt-2 text-sm text-green-700">
                        <p>If an account exists for <b>{username}</b>, you will receive an email shortly.</p>
                      </div>
                      <div className="mt-4">
                        <div className="-mx-2 -my-1.5 flex">
                          <button
                            type="button"
                            onClick={toggleView}
                            className="bg-green-50 px-2 py-1.5 rounded-md text-sm font-medium text-green-800 hover:bg-green-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-600"
                          >
                            Return to Sign In
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleResetSubmit} className="space-y-4">
                  <div>
                    <label htmlFor="recovery-email" className="block text-sm font-medium text-slate-700">
                      Lab ID / Email Address
                    </label>
                    <div className="mt-1 relative rounded-md shadow-sm">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Mail className="h-5 w-5 text-slate-400" />
                      </div>
                      <input
                        id="recovery-email"
                        name="recovery-email"
                        type="text"
                        required
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="focus:ring-teal-500 focus:border-teal-500 block w-full pl-10 sm:text-sm border-slate-300 rounded-md py-2 border bg-white text-black"
                        placeholder="lab@clinomic.com"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={resetStatus === 'loading'}
                    className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-teal-600 hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 disabled:opacity-50"
                  >
                    {resetStatus === 'loading' ? 'Sending...' : 'Send Recovery Link'}
                  </button>
                </form>
              )}

              {resetStatus !== 'success' && (
                <div className="flex items-center justify-center">
                  <button
                    type="button"
                    onClick={toggleView}
                    className="flex items-center text-sm font-medium text-slate-600 hover:text-teal-600"
                  >
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Sign In
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-300" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-slate-500">
                  Demo Credentials
                </span>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-center text-slate-500">
               <div className="bg-slate-50 p-2 rounded border border-slate-200">
                 <span className="font-bold block">Pathology Lab</span>
                 user: lab / pass: lab
               </div>
               <div className="bg-slate-50 p-2 rounded border border-slate-200">
                 <span className="font-bold block">Admin</span>
                 user: admin / pass: admin
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;