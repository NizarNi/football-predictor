(function(){
  const $ = (sel)=>document.querySelector(sel);
  const fmt = (v)=> (v===null||v===undefined||Number.isNaN(v)) ? '—' : (typeof v==='number'? v.toFixed(2) : v);

  function renderStandings(data){
    const box = $("#standingsArea");
    if(!data || !data.table || !data.table.rows){ box.innerHTML = `<div class="text-muted">No standings</div>`; return; }
    const rows = data.table.rows;
    let html = `<div class="table-responsive"><table class="table table-sm align-middle"><thead>
      <tr><th>#</th><th>Team</th><th class="text-end">P</th><th class="text-end">W</th><th class="text-end">D</th><th class="text-end">L</th><th class="text-end">Pts</th></tr>
    </thead><tbody>`;
    for(const r of rows){
      html += `<tr>
        <td>${r.pos ?? r.position ?? ''}</td>
        <td>${r.team ?? r.name ?? ''}</td>
        <td class="text-end">${r.played ?? r.p ?? ''}</td>
        <td class="text-end">${r.w ?? ''}</td>
        <td class="text-end">${r.d ?? ''}</td>
        <td class="text-end">${r.l ?? ''}</td>
        <td class="text-end"><strong>${r.pts ?? r.points ?? ''}</strong></td>
      </tr>`;
    }
    html += `</tbody></table></div><div class="small text-muted">Source: ${data.table.source||'unknown'}</div>`;
    box.innerHTML = html;
  }

  function renderLive(data){
    const box = $("#liveArea");
    const evs = (data && data.events) || [];
    if(!evs.length){ box.innerHTML = `<div class="text-muted">No live events</div>`; return; }
    let html = `<div class="list-group">`;
    for(const e of evs){
      const status = e.status || '';
      const clock = e.clock || '';
      html += `<div class="list-group-item d-flex justify-content-between align-items-center">
        <div><span class="badge bg-danger me-2">LIVE</span>${e.home} vs ${e.away}</div>
        <div><strong>${e.score||''}</strong> <span class="text-muted">${clock} ${status}</span></div>
      </div>`;
    }
    html += `</div>`;
    box.innerHTML = html;
  }

  function renderSnapshot(data){
    const box = $("#snapshotArea");
    const snap = (data && data.snapshot) || {};
    const teams = Object.keys(snap).sort();
    if(!teams.length){ box.innerHTML = `<div class="text-muted">No snapshot</div>`; return; }
    let html = `<div class="table-responsive"><table class="table table-sm align-middle"><thead>
      <tr><th>Team</th><th class="text-end">xG/g</th><th class="text-end">xGA/g</th><th class="text-end">xGOT/g</th><th class="text-end">xGOT A/g</th>
      <th class="text-end">BigCh F</th><th class="text-end">BigCh A</th><th class="text-end">SOT</th><th class="text-end">Shots</th><th class="text-end">Poss%</th><th class="text-end">Pass%</th></tr>
    </thead><tbody>`;
    for(const t of teams){
      const s = snap[t] || {};
      html += `<tr>
        <td>${t}</td>
        <td class="text-end">${fmt(s.xg_for_per_game)}</td>
        <td class="text-end">${fmt(s.xg_against_per_game)}</td>
        <td class="text-end">${fmt(s.xgot_for_per_game)}</td>
        <td class="text-end">${fmt(s.xgot_against_per_game)}</td>
        <td class="text-end">${fmt(s.big_chances_for)}</td>
        <td class="text-end">${fmt(s.big_chances_against)}</td>
        <td class="text-end">${fmt(s.shots_on_target_per_game)}</td>
        <td class="text-end">${fmt(s.shots_total_per_game)}</td>
        <td class="text-end">${fmt(s.possession_pct)}</td>
        <td class="text-end">${fmt(s.accurate_pass_pct)}</td>
      </tr>`;
    }
    html += `</tbody></table></div>`;
    box.innerHTML = html;
  }

  function renderTeam(data){
    const box = $("#teamArea");
    const r = (data && data.rolling) || null;
    if(!r){ box.innerHTML = `<div class="text-muted">No team data</div>`; return; }
    let html = `<div class="row"><div class="col-12 col-lg-6">
      <div class="table-responsive"><table class="table table-sm align-middle"><tbody>
        <tr><td class="text-muted">xG / g</td><td class="text-end"><strong>${fmt(r.xg_for_per_game)}</strong></td></tr>
        <tr><td class="text-muted">xGA / g</td><td class="text-end"><strong>${fmt(r.xg_against_per_game)}</strong></td></tr>
        <tr><td class="text-muted">xGOT / g</td><td class="text-end">${fmt(r.xgot_for_per_game)}</td></tr>
        <tr><td class="text-muted">xGOT A / g</td><td class="text-end">${fmt(r.xgot_against_per_game)}</td></tr>
        <tr><td class="text-muted">Big chances (F/A)</td><td class="text-end">${fmt(r.big_chances_for)} / ${fmt(r.big_chances_against)}</td></tr>
        <tr><td class="text-muted">SOT / Shots</td><td class="text-end">${fmt(r.shots_on_target_per_game)} / ${fmt(r.shots_total_per_game)}</td></tr>
        <tr><td class="text-muted">Possession %</td><td class="text-end">${fmt(r.possession_pct)}</td></tr>
        <tr><td class="text-muted">Accurate pass %</td><td class="text-end">${fmt(r.accurate_pass_pct)}</td></tr>
      </tbody></table></div>
    </div><div class="col-12 col-lg-6">`;

    const shots = r.shots || [];
    if(shots.length){
      html += `<div class="small text-muted mb-2">Recent shots</div><div class="list-group">`;
      for(const s of shots.slice(0, 12)){
        html += `<div class="list-group-item d-flex justify-content-between">
          <div><i class="fas fa-dot-circle me-1"></i> ${s.minute ?? '—'}' ${s.player ? '· '+s.player : ''}</div>
          <div>${fmt(s.xg)} ${s.on_target ? '<span class="badge bg-secondary ms-2">On Target</span>' : ''}</div>
        </div>`;
      }
      html += `</div>`;
    } else {
      html += `<div class="text-muted">No shot list available</div>`;
    }

    html += `</div></div>`;
    box.innerHTML = html;
  }

  document.addEventListener("DOMContentLoaded", ()=>{
    $("#btnLoadStandings").addEventListener("click", async ()=>{
      const comp = $("#competitionSelect").value;
      $("#standingsArea").innerHTML = `<div class="text-muted"><span class="spinner-border spinner-border-sm me-1"></span>Loading…</div>`;
      const r = await fetch(`/explore/api/fotmob/standings?competition=${encodeURIComponent(comp)}`);
      const j = await r.json();
      renderStandings(j);
    });

    $("#btnLoadLive").addEventListener("click", async ()=>{
      const league = $("#liveLeagueSelect").value;
      $("#liveArea").innerHTML = `<div class="text-muted"><span class="spinner-border spinner-border-sm me-1"></span>Loading…</div>`;
      const r = await fetch(`/explore/api/fotmob/live?competition=${encodeURIComponent(league)}`);
      const j = await r.json();
      renderLive(j);
    });

    $("#btnLoadSnapshot").addEventListener("click", async ()=>{
      const league = $("#xgLeagueSelect").value;
      $("#snapshotArea").innerHTML = `<div class="text-muted"><span class="spinner-border spinner-border-sm me-1"></span>Loading…</div>`;
      const r = await fetch(`/explore/api/fotmob/league_snapshot?league=${encodeURIComponent(league)}`);
      const j = await r.json();
      renderSnapshot(j);
    });

    $("#btnLoadTeam").addEventListener("click", async ()=>{
      const team = $("#teamInput").value.trim();
      const league = $("#teamLeagueSelect").value;
      if(!team){ $("#teamArea").innerHTML = `<div class="text-danger">Enter a team name</div>`; return;}
      $("#teamArea").innerHTML = `<div class="text-muted"><span class="spinner-border spinner-border-sm me-1"></span>Loading…</div>`;
      const r = await fetch(`/explore/api/fotmob/team?league=${encodeURIComponent(league)}&team=${encodeURIComponent(team)}`);
      const j = await r.json();
      renderTeam(j);
    });

    $("#btnLoadStandings").click();
    $("#btnLoadSnapshot").click();
  });
})();
