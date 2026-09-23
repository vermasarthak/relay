import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';

interface TenantInfo {
  tenant_id: string;
  name: string;
  role: string;
}

interface ResolutionData {
  ticket: any;
  evidence: any[];
  proposals: any[];
  active_proposal: any;
  receipts: any[];
  audit_events: any[];
}

const App: React.FC = () => {
  const [token, setToken] = useState<string>(localStorage.getItem('relay_token') || '');
  const [user, setUser] = useState<any>(null);
  const [activeTenant, setActiveTenant] = useState<string>('ten_acme_corp');
  const [view, setView] = useState<'inbox' | 'detail' | 'eval'>('inbox');
  const [tickets, setTickets] = useState<any[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [resolution, setResolution] = useState<ResolutionData | null>(null);
  const [evalResults, setEvalResults] = useState<any>(null);
  const [editMode, setEditMode] = useState<boolean>(false);
  const [editArgs, setEditArgs] = useState<string>('{}');
  const [editExplanation, setEditExplanation] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string>('');

  const [csrfToken, setCsrfToken] = useState<string>(localStorage.getItem('relay_csrf_token') || '');

  // Login state
  const [loginEmail, setLoginEmail] = useState('alice@acme.com');
  const [loginPassword, setLoginPassword] = useState('admin123456');

  useEffect(() => {
    if (token) {
      fetchTickets();
      fetchEval();
    }
  }, [token, activeTenant]);

  useEffect(() => {
    if (selectedTicketId && token) {
      fetchResolution(selectedTicketId);
    }
  }, [selectedTicketId]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('http://localhost:8000/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword })
      });
      if (!res.ok) throw new Error('Invalid credentials');
      const data = await res.json();
      setToken(data.access_token);
      setCsrfToken(data.csrf_token || '');
      setUser(data.user);
      localStorage.setItem('relay_token', data.access_token);
      if (data.csrf_token) {
        localStorage.setItem('relay_csrf_token', data.csrf_token);
      }
      setErrorMsg('');
    } catch (err: any) {
      setErrorMsg(err.message || 'Login failed');
    }
  };

  const fetchTickets = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/tickets', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'x-tenant-id': activeTenant
        }
      });
      if (res.ok) {
        const data = await res.json();
        setTickets(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchResolution = async (ticketId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/tickets/${ticketId}/resolution`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'x-tenant-id': activeTenant
        }
      });
      if (res.ok) {
        const data = await res.json();
        setResolution(data);
        if (data.active_proposal) {
          setEditArgs(JSON.stringify(data.active_proposal.action_arguments, null, 2));
          setEditExplanation(data.active_proposal.explanation);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchEval = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/eval/results', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'x-tenant-id': activeTenant
        }
      });
      if (res.ok) {
        const data = await res.json();
        setEvalResults(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDecision = async (approved: boolean) => {
    if (!resolution || !resolution.active_proposal) return;
    try {
      const res = await fetch(
        `http://localhost:8000/api/v1/tickets/${resolution.ticket.id}/proposals/${resolution.active_proposal.id}/decide`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            'x-tenant-id': activeTenant,
            'x-csrf-token': csrfToken
          },
          body: JSON.stringify({ is_approved: approved, reviewer_notes: 'Reviewed via UI console.' })
        }
      );
      if (res.ok) {
        fetchResolution(resolution.ticket.id);
        fetchTickets();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSaveEdit = async () => {
    if (!resolution || !resolution.active_proposal) return;
    try {
      const parsed = JSON.parse(editArgs);
      const res = await fetch(
        `http://localhost:8000/api/v1/tickets/${resolution.ticket.id}/proposals/${resolution.active_proposal.id}/edit`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            'x-tenant-id': activeTenant,
            'x-csrf-token': csrfToken
          },
          body: JSON.stringify({
            action_type: resolution.active_proposal.action_type,
            action_arguments: parsed,
            explanation: editExplanation
          })
        }
      );
      if (res.ok) {
        setEditMode(false);
        fetchResolution(resolution.ticket.id);
      }
    } catch (e) {
      alert('Invalid JSON in action arguments');
    }
  };

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
        <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-8 shadow-2xl">
          <div className="flex items-center space-x-3 mb-6">
            <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-xl text-white">R</div>
            <div>
              <h1 className="text-xl font-bold text-slate-100">Relay Support Engine</h1>
              <p className="text-xs text-slate-400">Production AI Resolution & Durable Workflows</p>
            </div>
          </div>
          {errorMsg && <div className="mb-4 p-3 bg-rose-950 border border-rose-800 text-rose-300 text-sm rounded">{errorMsg}</div>}
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Email Address</label>
              <input 
                type="email" 
                value={loginEmail} 
                onChange={e => setLoginEmail(e.target.value)} 
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase text-slate-400 mb-1">Password</label>
              <input 
                type="password" 
                value={loginPassword} 
                onChange={e => setLoginPassword(e.target.value)} 
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <button type="submit" className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded text-sm transition">
              Sign In to Workspace
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-2">
            <span className="w-8 h-8 bg-indigo-600 rounded flex items-center justify-center font-bold text-white">R</span>
            <span className="font-bold text-slate-100 tracking-tight">RELAY</span>
          </div>
          <nav className="flex space-x-1 text-sm">
            <button 
              onClick={() => { setView('inbox'); setSelectedTicketId(null); }}
              className={`px-3 py-1.5 rounded-md ${view === 'inbox' ? 'bg-slate-800 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Ticket Inbox
            </button>
            <button 
              onClick={() => setView('eval')}
              className={`px-3 py-1.5 rounded-md ${view === 'eval' ? 'bg-slate-800 text-white font-medium' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Evaluation Benchmark
            </button>
          </nav>
        </div>
        <div className="flex items-center space-x-4">
          <select 
            value={activeTenant} 
            onChange={e => setActiveTenant(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-xs text-slate-200 rounded px-2.5 py-1.5 focus:outline-none"
          >
            <option value="ten_acme_corp">Acme Cloud Services (Tenant A)</option>
            <option value="ten_globex_ai">Globex Intelligence (Tenant B)</option>
          </select>
          <button 
            onClick={() => { localStorage.removeItem('relay_token'); setToken(''); }}
            className="text-xs text-slate-400 hover:text-rose-400 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 flex overflow-hidden">
        {view === 'eval' ? (
          <div className="flex-1 p-8 overflow-y-auto">
            <div className="max-w-5xl mx-auto space-y-6">
              <div>
                <h2 className="text-2xl font-bold text-slate-100">Evaluation Benchmark Results</h2>
                <p className="text-sm text-slate-400">100 Synthetic Held-out & Dev Cases across 5 Policy & Adversarial Families</p>
              </div>

              {evalResults && (
                <div className="grid grid-cols-2 gap-6">
                  {/* Baseline Card */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="font-semibold text-rose-400 text-sm">System A: Unconstrained Baseline</h3>
                      <span className="text-xs bg-rose-950 text-rose-400 px-2 py-0.5 rounded border border-rose-800">Single Prompt</span>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-slate-950 p-4 rounded border border-slate-800">
                        <div className="text-xs text-slate-500">Overall Accuracy</div>
                        <div className="text-2xl font-bold text-slate-200">{evalResults.systems.baseline_unconstrained.overall_accuracy * 100}%</div>
                      </div>
                      <div className="bg-slate-950 p-4 rounded border border-slate-800">
                        <div className="text-xs text-slate-500">Unsafe Proposal Rate</div>
                        <div className="text-2xl font-bold text-rose-500">{evalResults.systems.baseline_unconstrained.unsafe_proposal_rate * 100}%</div>
                      </div>
                    </div>
                  </div>

                  {/* Relay Card */}
                  <div className="bg-slate-900 border border-indigo-900/60 rounded-xl p-6 shadow-lg shadow-indigo-950/20">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="font-semibold text-emerald-400 text-sm">System B: Relay Grounded Pipeline</h3>
                      <span className="text-xs bg-emerald-950 text-emerald-400 px-2 py-0.5 rounded border border-emerald-800">Retrieved & Validated</span>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-slate-950 p-4 rounded border border-slate-800">
                        <div className="text-xs text-slate-500">Overall Accuracy</div>
                        <div className="text-2xl font-bold text-emerald-400">{evalResults.systems.relay_structured_pipeline.overall_accuracy * 100}%</div>
                      </div>
                      <div className="bg-slate-950 p-4 rounded border border-slate-800">
                        <div className="text-xs text-slate-500">Unsafe Proposal Rate</div>
                        <div className="text-2xl font-bold text-emerald-400">{evalResults.systems.relay_structured_pipeline.unsafe_proposal_rate * 100}%</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Left Ticket List */}
            <div className="w-80 border-r border-slate-800 bg-slate-900/50 flex flex-col">
              <div className="p-4 border-b border-slate-800 flex justify-between items-center">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Incoming Queue</span>
                <span className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded">{tickets.length}</span>
              </div>
              <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
                {tickets.map(t => (
                  <button
                    key={t.id}
                    onClick={() => { setSelectedTicketId(t.id); setView('detail'); }}
                    className={`w-full text-left p-4 hover:bg-slate-800/60 transition ${selectedTicketId === t.id ? 'bg-slate-800/90 border-l-2 border-indigo-500' : ''}`}
                  >
                    <div className="flex justify-between items-start mb-1">
                      <span className="text-xs font-mono text-indigo-400">{t.external_ticket_id}</span>
                      <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">{t.status}</span>
                    </div>
                    <div className="text-sm font-medium text-slate-200 truncate">{t.subject}</div>
                    <div className="text-xs text-slate-500 mt-1">{t.customer_name} ({t.customer_email})</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Right Resolution Console */}
            <div className="flex-1 flex flex-col overflow-y-auto bg-slate-950">
              {resolution ? (
                <div className="p-8 max-w-5xl mx-auto w-full space-y-6">
                  {/* Ticket Header */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="text-xs font-mono text-indigo-400">{resolution.ticket.external_ticket_id}</div>
                        <h2 className="text-xl font-bold text-slate-100 mt-1">{resolution.ticket.subject}</h2>
                        <div className="text-xs text-slate-400 mt-1">From: {resolution.ticket.customer_name} &lt;{resolution.ticket.customer_email}&gt;</div>
                      </div>
                      <span className="px-3 py-1 text-xs font-semibold rounded-full bg-slate-800 text-indigo-300 border border-slate-700">
                        Status: {resolution.ticket.status}
                      </span>
                    </div>
                    <div className="mt-4 p-4 bg-slate-950 rounded-lg border border-slate-800/80 text-sm text-slate-300 whitespace-pre-wrap">
                      {resolution.ticket.body}
                    </div>
                  </div>

                  {/* Evidence Items */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">Grounded Evidence Excerpts</h3>
                    <div className="grid grid-cols-2 gap-4">
                      {resolution.evidence.map(e => (
                        <div key={e.id} className="bg-slate-950 border border-slate-800 p-4 rounded-lg">
                          <div className="flex justify-between text-xs font-semibold text-indigo-400 mb-1">
                            <span>{e.source_title}</span>
                            <span className="text-slate-500">{e.source_type}</span>
                          </div>
                          <div className="text-xs text-slate-300 mt-2">{e.excerpt}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Active Proposal & Approval Console */}
                  {resolution.active_proposal && (
                    <div className="bg-slate-900 border border-indigo-900/50 rounded-xl p-6 shadow-xl">
                      <div className="flex justify-between items-center mb-4">
                        <div>
                          <h3 className="text-sm font-bold text-indigo-400 uppercase tracking-wider">Proposed Resolution Action</h3>
                          <span className="text-xs text-slate-500">Proposal Version {resolution.active_proposal.version} ({resolution.active_proposal.status})</span>
                        </div>
                        <button
                          onClick={() => setEditMode(!editMode)}
                          className="text-xs text-slate-400 hover:text-indigo-400 underline"
                        >
                          {editMode ? 'Cancel Edit' : 'Edit Arguments'}
                        </button>
                      </div>

                      {editMode ? (
                        <div className="space-y-4">
                          <div>
                            <label className="block text-xs font-semibold text-slate-400 mb-1">Action Arguments (JSON)</label>
                            <textarea
                              rows={4}
                              value={editArgs}
                              onChange={e => setEditArgs(e.target.value)}
                              className="w-full bg-slate-950 font-mono text-xs border border-slate-700 rounded p-2 text-slate-100"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-semibold text-slate-400 mb-1">Reviewer Explanation</label>
                            <input
                              type="text"
                              value={editExplanation}
                              onChange={e => setEditExplanation(e.target.value)}
                              className="w-full bg-slate-950 text-xs border border-slate-700 rounded p-2 text-slate-100"
                            />
                          </div>
                          <button
                            onClick={handleSaveEdit}
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold rounded text-white"
                          >
                            Save & Create New Proposal Version
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4 bg-slate-950 p-4 rounded border border-slate-800">
                            <div>
                              <div className="text-xs text-slate-500">Action Type</div>
                              <div className="font-mono text-sm font-bold text-slate-200">{resolution.active_proposal.action_type}</div>
                            </div>
                            <div>
                              <div className="text-xs text-slate-500">Parameters</div>
                              <pre className="font-mono text-xs text-slate-300">{JSON.stringify(resolution.active_proposal.action_arguments, null, 2)}</pre>
                            </div>
                          </div>

                          <div className="text-xs text-slate-400">
                            <span className="font-semibold text-slate-300">Model Explanation:</span> {resolution.active_proposal.explanation}
                          </div>

                          {/* Approval Controls */}
                          {resolution.ticket.status === 'awaiting_review' && (
                            <div className="flex space-x-3 pt-4 border-t border-slate-800">
                              <button
                                onClick={() => handleDecision(true)}
                                className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg shadow-lg transition"
                              >
                                Approve & Execute Sandbox Action
                              </button>
                              <button
                                onClick={() => handleDecision(false)}
                                className="px-6 py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs rounded-lg transition"
                              >
                                Reject Proposal
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Sandbox Execution Receipts */}
                  {resolution.receipts.length > 0 && (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                      <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">Durable Action Receipts</h3>
                      <div className="space-y-3">
                        {resolution.receipts.map(r => (
                          <div key={r.id} className="bg-slate-950 border border-slate-800 p-4 rounded-lg flex justify-between items-center">
                            <div>
                              <div className="font-mono text-xs text-emerald-400">{r.provider_transaction_id || 'IDEMP: ' + r.idempotency_key}</div>
                              <div className="text-xs text-slate-400 mt-1">Provider: {r.provider} | Status: {r.status}</div>
                            </div>
                            <span className={`px-2 py-1 text-xs font-semibold rounded ${r.verified ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400'}`}>
                              {r.verified ? 'Verified on Ledger' : 'Unverified'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
                  Select a ticket from the queue to inspect evidence and proposals.
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);
root.render(<App />);
