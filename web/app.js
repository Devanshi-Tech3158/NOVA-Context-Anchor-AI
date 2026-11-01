/**
 * NOVA Context Anchor Web UI Client
 * Connects to live FastAPI backend or provides client-side Context Anchor simulation.
 */

// State
let memories = [];
let auditRecords = [];
let apiBaseUrl = window.location.origin.includes('github.io') ? '' : window.location.origin;

// Sample Conversations
const SAMPLES = {
  postgres: [
    {
      id: "m1",
      session_id: "session-nova-01",
      role: "user",
      text: "Let's review our tech stack decisions for the new project.",
      timestamp: new Date().toISOString()
    },
    {
      id: "m2",
      session_id: "session-nova-01",
      role: "assistant",
      text: "Sure! What database should we use?",
      timestamp: new Date().toISOString()
    },
    {
      id: "m3",
      session_id: "session-nova-01",
      role: "user",
      text: "We decided to use PostgreSQL for database storage because of ACID compliance.",
      timestamp: new Date().toISOString()
    },
    {
      id: "m4",
      session_id: "session-nova-01",
      role: "user",
      text: "Also, our backend service will listen on port 5432.",
      timestamp: new Date().toISOString()
    }
  ],
  reversal: [
    {
      id: "m5",
      session_id: "session-nova-01",
      role: "user",
      text: "Update on database: PostgreSQL has too much operational overhead for our lightweight agent.",
      timestamp: new Date().toISOString()
    },
    {
      id: "m6",
      session_id: "session-nova-01",
      role: "user",
      text: "We chose SQLite for database storage instead to simplify deployment.",
      timestamp: new Date().toISOString()
    }
  ]
};

// Initialize
window.addEventListener('DOMContentLoaded', () => {
  const savedUrl = localStorage.getItem('nova_api_url');
  if (savedUrl) {
    apiBaseUrl = savedUrl;
  }
  document.getElementById('apiBaseUrl').value = apiBaseUrl;

  document.getElementById('btnSaveHost').addEventListener('click', () => {
    apiBaseUrl = document.getElementById('apiBaseUrl').value.trim().replace(/\/$/, '');
    localStorage.setItem('nova_api_url', apiBaseUrl);
    checkHealth();
  });

  document.getElementById('btnHealth').addEventListener('click', checkHealth);

  loadSampleIngest('postgres');
  checkHealth();
});

function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('tab-active'));
  
  const target = document.getElementById(tabId);
  if (target) target.classList.remove('hidden');

  const btnId = 'nav-' + tabId.replace('tab-', '');
  const btn = document.getElementById(btnId);
  if (btn) btn.classList.add('tab-active');
}

function loadSampleIngest(key) {
  const sample = SAMPLES[key] || SAMPLES.postgres;
  document.getElementById('ingestMessagesJson').value = JSON.stringify(sample, null, 2);
}

function setAsk(q) {
  document.getElementById('askQuestion').value = q;
}

function setVerify(q, a, expected) {
  document.getElementById('verifyQuestion').value = q;
  document.getElementById('verifyAnswer').value = a;
}

async function checkHealth() {
  const statusLabel = document.getElementById('backendStatusLabel');
  statusLabel.textContent = 'Checking...';

  try {
    const res = await fetch(`${apiBaseUrl}/healthz`, { method: 'GET' });
    if (res.ok) {
      const data = await res.json();
      if (data.status === 'ok') {
        statusLabel.textContent = 'API Connected (Live)';
        statusLabel.className = 'text-emerald-400 font-semibold';
        return true;
      }
    }
  } catch {
    // API not running on this host
  }

  statusLabel.textContent = 'Client Simulation Mode';
  statusLabel.className = 'text-teal-300 font-semibold';
  return false;
}

// INGEST
async function triggerIngest() {
  const sessionId = document.getElementById('ingestSessionId').value.trim();
  const rawJson = document.getElementById('ingestMessagesJson').value.trim();
  const spinner = document.getElementById('ingestSpinner');
  const badge = document.getElementById('ingestBadge');

  let messages = [];
  try {
    messages = JSON.parse(rawJson);
  } catch (err) {
    alert('Invalid JSON in messages field: ' + err.message);
    return;
  }

  spinner.classList.remove('hidden');
  badge.textContent = 'Ingesting...';

  try {
    let report = null;
    const isLive = await checkHealth();

    if (isLive) {
      const res = await fetch(`${apiBaseUrl}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, messages: messages })
      });
      if (res.ok) {
        report = await res.json();
      }
    }

    if (!report) {
      // Local simulation
      report = simulateIngest(sessionId, messages);
    }

    document.getElementById('metricAdded').textContent = report.added;
    document.getElementById('metricSuperseded').textContent = report.superseded;
    document.getElementById('metricDropped').textContent = report.dropped;
    badge.textContent = 'Completed';
    badge.className = 'text-xs px-2 py-0.5 rounded font-mono bg-emerald-950 text-emerald-400 border border-emerald-500/30';

    renderMemoryList();
  } catch (err) {
    alert('Ingest error: ' + err.message);
    badge.textContent = 'Failed';
  } finally {
    spinner.classList.add('hidden');
  }
}

function simulateIngest(sessionId, messages) {
  let added = 0;
  let superseded = 0;

  for (const msg of messages) {
    const text = msg.text || '';
    // Decision regex
    const match = text.match(/(?:decided to use|using|switch(?:ed)? to|chose|choose)\s+([A-Za-z0-9_ -]+?)\s+(?:for|as)\s+([A-Za-z0-9_ -]+)/i);
    if (match) {
      const val = match[1].trim();
      const subj = match[2].trim().toLowerCase().replace(/ /g, '_');
      
      // Check existing current memories on same subject
      const existingIdx = memories.findIndex(m => m.subject === subj && m.status === 'current');
      let supersedesId = null;
      if (existingIdx >= 0) {
        memories[existingIdx].status = 'superseded';
        supersedesId = memories[existingIdx].id;
        superseded++;
      }

      const mem = {
        id: `mem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
        session_id: sessionId,
        type: 'decision',
        subject: subj,
        value: val,
        reason: 'Conversation turn agreement',
        source_msg_id: msg.id,
        source_quote: text,
        confidence: 0.95,
        status: 'current',
        supersedes_id: supersedesId,
        timestamp: new Date().toISOString()
      };
      memories.unshift(mem);
      added++;
    } else if (text.length > 10) {
      // Generic fact
      const mem = {
        id: `mem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
        session_id: sessionId,
        type: 'fact',
        subject: 'discussion_point',
        value: text,
        reason: 'Extracted fact',
        source_msg_id: msg.id,
        source_quote: text,
        confidence: 0.85,
        status: 'current',
        supersedes_id: null,
        timestamp: new Date().toISOString()
      };
      memories.unshift(mem);
      added++;
    }
  }

  return { added, superseded, dropped: 0 };
}

function renderMemoryList() {
  const container = document.getElementById('memoryList');
  if (memories.length === 0) {
    container.innerHTML = '<p class="text-xs text-slate-500 italic p-4 text-center">No memories in session.</p>';
    return;
  }

  container.innerHTML = memories.map(m => {
    const isCurrent = m.status === 'current';
    return `
      <div class="p-3 rounded-xl border ${isCurrent ? 'bg-slate-900/90 border-slate-700' : 'bg-slate-950/60 border-slate-800 opacity-60'} text-xs space-y-1 font-mono">
        <div class="flex items-center justify-between">
          <span class="font-bold ${isCurrent ? 'text-teal-300' : 'text-slate-400'}">${m.subject} : ${m.value}</span>
          <span class="px-2 py-0.5 rounded text-tiny uppercase font-bold ${isCurrent ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30' : 'bg-amber-950 text-amber-400 border border-amber-500/30'}">
            ${m.status}
          </span>
        </div>
        <p class="text-slate-400 italic font-sans text-tiny">"${m.source_quote}"</p>
        <div class="flex items-center justify-between text-slate-500 text-tiny pt-1">
          <span>id: ${m.id}</span>
          ${m.supersedes_id ? `<span class="text-amber-400">supersedes: ${m.supersedes_id}</span>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

// ASK
async function triggerAsk() {
  const q = document.getElementById('askQuestion').value.trim();
  const draft = document.getElementById('askDraftAnswer').value.trim() || null;

  if (!q) return;

  const finalBox = document.getElementById('finalAnswerBox');
  const badge = document.getElementById('decisionActionBadge');
  const verdictsList = document.getElementById('verdictsList');

  finalBox.innerHTML = '<span class="text-teal-400 animate-pulse">Reasoning from Context Anchor memories...</span>';

  try {
    let decision = null;
    const isLive = await checkHealth();

    if (isLive) {
      const res = await fetch(`${apiBaseUrl}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, draft_answer: draft })
      });
      if (res.ok) {
        decision = await res.json();
      }
    }

    if (!decision) {
      decision = simulateAsk(q, draft);
    }

    // Render decision
    badge.textContent = decision.action.toUpperCase();
    badge.className = `text-xs px-2.5 py-1 rounded-full font-bold font-mono ${
      decision.action === 'answer' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' :
      decision.action === 'qualify' ? 'bg-amber-950 text-amber-400 border border-amber-500/40' :
      decision.action === 'abstain' ? 'bg-slate-800 text-slate-400 border border-slate-700' :
      'bg-rose-950 text-rose-400 border border-rose-500/40'
    }`;

    finalBox.textContent = decision.final_answer || 'No definitive answer could be verified.';

    verdictsList.innerHTML = decision.verdicts.map((v, i) => `
      <div class="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
        <div class="flex items-center justify-between mb-1">
          <span class="font-bold text-white">Claim ${i + 1}: ${v.claim}</span>
          <span class="px-2 py-0.5 rounded text-tiny font-bold uppercase ${
            v.label === 'supported' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30' :
            v.label === 'contradicted' ? 'bg-rose-950 text-rose-400 border border-rose-500/30' :
            v.label === 'outdated' ? 'bg-amber-950 text-amber-400 border border-amber-500/30' :
            'bg-slate-800 text-slate-400'
          }">${v.label}</span>
        </div>
        <p class="text-slate-400 text-tiny">${v.rationale}</p>
        ${v.memory_ids && v.memory_ids.length > 0 ? `<p class="text-slate-500 text-tiny font-mono mt-1">Citations: ${v.memory_ids.join(', ')}</p>` : ''}
      </div>
    `).join('');

    // Record audit
    auditRecords.unshift({
      id: `audit_${Date.now().toString(36)}`,
      timestamp: new Date().toISOString(),
      question: q,
      answer: decision.final_answer,
      action: decision.action,
      verdict_count: decision.verdicts.length
    });
    renderAuditTable();
  } catch (err) {
    finalBox.textContent = 'Query error: ' + err.message;
  }
}

function simulateAsk(question, draftAnswer) {
  const currentMemories = memories.filter(m => m.status === 'current');
  const qLower = question.toLowerCase();

  // Find relevant memory
  const found = currentMemories.find(m => 
    qLower.includes(m.subject) || 
    m.subject.includes('database') && qLower.includes('db') ||
    qLower.includes(m.value.toLowerCase())
  );

  if (!found) {
    return {
      action: 'abstain',
      final_answer: 'I do not have verified memory evidence to answer this question.',
      verdicts: [
        {
          claim: question,
          label: 'unsupported',
          memory_ids: [],
          rationale: 'Absence of evidence in stored memories.'
        }
      ]
    };
  }

  const ans = `The team decided to use ${found.value} for ${found.subject.replace(/_/g, ' ')}.`;
  return {
    action: 'answer',
    final_answer: ans,
    verdicts: [
      {
        claim: ans,
        label: 'supported',
        memory_ids: [found.id],
        rationale: `Grounded in memory ${found.id} from session ${found.session_id}`
      }
    ]
  };
}

// VERIFY
async function triggerVerify() {
  const q = document.getElementById('verifyQuestion').value.trim();
  const a = document.getElementById('verifyAnswer').value.trim();

  if (!q || !a) return;

  const outcomeBox = document.getElementById('verifyOutcomeBox');
  const badge = document.getElementById('verifyActionBadge');
  const claimsList = document.getElementById('verifyClaimsList');

  outcomeBox.innerHTML = '<span class="text-teal-400 animate-pulse">Running claim splitter and judge...</span>';

  try {
    let decision = null;
    const isLive = await checkHealth();

    if (isLive) {
      const res = await fetch(`${apiBaseUrl}/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, answer: a })
      });
      if (res.ok) {
        decision = await res.json();
      }
    }

    if (!decision) {
      decision = simulateVerify(q, a);
    }

    badge.textContent = decision.action.toUpperCase();
    badge.className = `text-xs px-2.5 py-1 rounded-full font-bold font-mono ${
      decision.action === 'answer' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' :
      decision.action === 'correct' ? 'bg-amber-950 text-amber-400 border border-amber-500/40' :
      decision.action === 'flag_conflict' ? 'bg-rose-950 text-rose-400 border border-rose-500/40' :
      'bg-slate-800 text-slate-400'
    }`;

    outcomeBox.textContent = `Action: ${decision.action.toUpperCase()} — ${decision.final_answer || a}`;

    claimsList.innerHTML = decision.verdicts.map((v, i) => `
      <div class="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs">
        <div class="flex items-center justify-between mb-1">
          <span class="font-bold text-white">Claim ${i + 1}: ${v.claim}</span>
          <span class="px-2 py-0.5 rounded text-tiny font-bold uppercase ${
            v.label === 'supported' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30' :
            v.label === 'contradicted' ? 'bg-rose-950 text-rose-400 border border-rose-500/30' :
            v.label === 'outdated' ? 'bg-amber-950 text-amber-400 border border-amber-500/30' :
            'bg-slate-800 text-slate-400'
          }">${v.label}</span>
        </div>
        <p class="text-slate-400 text-tiny">${v.rationale}</p>
        ${v.memory_ids && v.memory_ids.length > 0 ? `<p class="text-slate-500 text-tiny font-mono mt-1">Evidence ID: ${v.memory_ids.join(', ')}</p>` : ''}
      </div>
    `).join('');

    // Record audit
    auditRecords.unshift({
      id: `audit_${Date.now().toString(36)}`,
      timestamp: new Date().toISOString(),
      question: q,
      answer: a,
      action: decision.action,
      verdict_count: decision.verdicts.length
    });
    renderAuditTable();
  } catch (err) {
    outcomeBox.textContent = 'Verification error: ' + err.message;
  }
}

function simulateVerify(question, answer) {
  const currentMemories = memories.filter(m => m.status === 'current');
  const supersededMemories = memories.filter(m => m.status === 'superseded');

  // Split into claims
  const claims = answer.split(/[.!?]\s+/).filter(c => c.trim().length > 0);
  const verdicts = [];

  for (const claim of claims) {
    const claimLower = claim.toLowerCase();
    
    // Check contradicted
    const currentContradiction = currentMemories.find(m => 
      claimLower.includes('mongo') && m.value.toLowerCase().includes('sql') ||
      claimLower.includes('mysql') && m.value.toLowerCase().includes('sql')
    );

    // Check supported
    const supported = currentMemories.find(m => claimLower.includes(m.value.toLowerCase()));

    // Check outdated
    const outdated = supersededMemories.find(m => claimLower.includes(m.value.toLowerCase()));

    if (supported) {
      verdicts.push({
        claim,
        label: 'supported',
        memory_ids: [supported.id],
        rationale: `Directly supported by active memory ${supported.id}`
      });
    } else if (outdated) {
      verdicts.push({
        claim,
        label: 'outdated',
        memory_ids: [outdated.id],
        rationale: `Outdated decision: superseded by memory ${outdated.supersedes_id || 'successor'}`
      });
    } else if (currentContradiction) {
      verdicts.push({
        claim,
        label: 'contradicted',
        memory_ids: [currentContradiction.id],
        rationale: `Contradicts current memory ${currentContradiction.id} stating ${currentContradiction.value}`
      });
    } else {
      verdicts.push({
        claim,
        label: 'unsupported',
        memory_ids: [],
        rationale: 'No stored evidence in memories. Absence of evidence is not contradicted.'
      });
    }
  }

  const hasContradicted = verdicts.some(v => v.label === 'contradicted');
  const hasOutdated = verdicts.some(v => v.label === 'outdated');
  const hasSupported = verdicts.some(v => v.label === 'supported');

  let action = 'answer';
  let finalAns = answer;

  if (hasContradicted) {
    action = 'flag_conflict';
    finalAns = 'Contradiction detected against verified team memories.';
  } else if (hasOutdated) {
    action = 'correct';
    finalAns = 'Answer updated to reflect current successor memories.';
  } else if (!hasSupported) {
    action = 'abstain';
    finalAns = 'Cannot verify answer due to lack of evidence.';
  }

  return {
    action,
    final_answer: finalAns,
    verdicts
  };
}

// AUDIT TRAIL
function refreshAuditTrail() {
  renderAuditTable();
}

function renderAuditTable() {
  const tbody = document.getElementById('auditTableBody');
  if (auditRecords.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="p-6 text-center text-slate-500 italic">No audit records generated yet. Run an Ask or Verify query first.</td></tr>';
    return;
  }

  tbody.innerHTML = auditRecords.map(r => `
    <tr class="hover:bg-slate-900/50">
      <td class="p-3 text-teal-300">${r.id}</td>
      <td class="p-3 text-slate-400">${r.timestamp.split('T')[1].slice(0, 8)}</td>
      <td class="p-3 text-white max-w-[200px] truncate" title="${r.question}">${r.question}</td>
      <td class="p-3">
        <span class="px-2 py-0.5 rounded text-tiny uppercase font-bold ${
          r.action === 'answer' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/30' :
          r.action === 'correct' ? 'bg-amber-950 text-amber-400 border border-amber-500/30' :
          r.action === 'abstain' ? 'bg-slate-800 text-slate-400' :
          'bg-rose-950 text-rose-400 border border-rose-500/30'
        }">${r.action}</span>
      </td>
      <td class="p-3 text-slate-300">${r.verdict_count}</td>
      <td class="p-3 text-right">
        <button onclick="alert('Audit Record: ' + JSON.stringify(auditRecords.find(a => a.id === '${r.id}'), null, 2))" class="text-teal-400 hover:text-teal-300 font-bold">
          View →
        </button>
      </td>
    </tr>
  `).join('');
}
