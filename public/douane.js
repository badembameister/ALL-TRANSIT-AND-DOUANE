/* Module « Douane » branché sur l'API : liste des déclarations, délais de dédouanement, quittances.
   Le détail d'une déclaration s'ouvre dans l'onglet Douane du dossier. */
const DN={st:'',q:'',L:[],R:null};
const DN_ST=[['en_attente','En attente de réponse'],['Brouillon','Brouillon'],['Transmise','Transmise'],['Acceptée','Acceptée'],['Contrôle','Contrôle'],['Bon à enlever','Bon à enlever'],['Rejetée','Rejetée']];
const dnBadge=x=>`<span class="b ${{Brouillon:'',Transmise:'in',Acceptée:'in',Contrôle:'wa','Bon à enlever':'ok',Rejetée:'ba'}[x.statut]}">${esc(x.statut)}</span>`
  +(x.attente_jours>3?` <span class="b ba">${x.attente_jours} j d’attente</span>`:'');
const jours=v=>v==null?'—':(+v).toLocaleString('fr-FR',{maximumFractionDigits:1})+' j';

function vDouaneApi(){return`<div id="dnv"><h1>Douane</h1><p class="mut">Chargement…</p></div>`}

async function loadDouane(){try{[DN.L,DN.R]=await Promise.all([api('/declarations'),api('/declarations/resume')])}
catch(e){$('#dnv').innerHTML=`<h1>Douane</h1><p class="note">${esc(e.message)}</p>`;return}paintDouane()}

const dnRows=()=>{const q=DN.q.toLowerCase();return DN.L.filter(x=>(DN.st==='en_attente'?['Transmise','Acceptée','Contrôle'].includes(x.statut):!DN.st||x.statut===DN.st)
&&`${x.ref} ${x.ref_douane} ${x.dossier_num} ${x.client_nom} ${x.quittance_ref}`.toLowerCase().includes(q)).map(x=>`<tr>
<td><button class="lk" onclick="dnOpen(${x.dossier_id})">${esc(x.ref)}</button>${x.ref_douane?`<br><span class="mut mono">${esc(x.ref_douane)}</span>`:''}</td>
<td class="mono">${esc(x.dossier_num)}<br><span class="mut" style="font-family:inherit">${esc(x.client_nom)}</span></td><td>${esc(x.type_operation)}<br><span class="mut">${esc(x.regime)}</span></td>
<td>${x.montant_liquide!=null?nf(x.montant_liquide):'<span class="mut">non figée</span>'}</td><td>${x.transmise_le?hfr(x.transmise_le):'—'}</td><td>${dnBadge(x)}</td>
<td>${x.quittance_ref?`${esc(x.quittance_ref)}<br><span class="mut">${dfr(x.quittance_date)}</span>`:['Acceptée','Contrôle'].includes(x.statut)&&x.montant_liquide>0?'<span class="b wa">À payer</span>':'—'}</td>
<td>${x.bae_le?`${dfr(x.bae_le)}<br><span class="mut">en ${jours(x.delai_jours)}</span>`:'—'}</td></tr>`).join('')||'<tr><td colspan="8" class="mut">Aucune déclaration pour ces critères.</td></tr>'};

function paintDouane(){if(view!=='douane'||sel||!$('#dnv'))return;const R=DN.R,b=R.devise_base;
$('#dnv').innerHTML=`<h1>Douane</h1><div class="kp"><div><b>${R.brouillons}</b><span>Brouillons</span></div><div><b>${R.transmises}</b><span>Transmises, sans réponse</span></div>
<div class="${R.quittances_a_payer?'w':''}"><b>${R.quittances_a_payer}</b><span>Quittances à payer</span></div><div><b>${R.controles}</b><span>En contrôle</span></div>
<div><b>${R.bae_30j}</b><span>Bons à enlever (30 j)</span></div><div><b>${jours(R.delai_moyen_jours)}</b><span>Délai moyen de dédouanement</span></div>
<div class="${R.attente_plus_3j?'w':''}"><b>${R.attente_plus_3j}</b><span>En attente depuis plus de 3 j</span></div><div class="${R.rejetees?'w':''}"><b>${R.rejetees}</b><span>Rejetées</span></div></div>
<div class="bar"><input placeholder="Réf. déclaration ou douane, dossier, client, quittance" value="${esc(DN.q)}" oninput="DN.q=this.value;$('#dnl').innerHTML=dnRows()" size="38">
<select onchange="DN.st=this.value;$('#dnl').innerHTML=dnRows()"><option value="">Tous les statuts</option>${DN_ST.map(([v,l])=>`<option value="${v}" ${v===DN.st?'selected':''}>${l}</option>`).join('')}</select>
${W.douane.includes(role)?'<button class="pri" onclick="dnNew()">Nouvelle déclaration</button>':''}</div>
<div class="card tbl"><table><tr><th>Déclaration</th><th>Dossier</th><th>Opération</th><th>Liquidation (${b})</th><th>Transmise le</th><th>Statut</th><th>Quittance</th><th>Bon à enlever</th></tr><tbody id="dnl">${dnRows()}</tbody></table></div>
<p class="mut">Délai de dédouanement : de la transmission au bon à enlever (moyenne sur 90 jours). La liquidation est figée à la transmission. Cliquez sur une déclaration pour la traiter dans son dossier.</p>`}

async function dnOpen(did){go('dossiers');DS.sel=did;DS.tab='douane';await dsLoad()}
async function dnNew(){let D;try{D=(await api('/dossiers')).filter(d=>!d.declaration_statut&&!['Livré','Clôturé'].includes(d.statut))}catch(e){return fail('Dossiers',e)}
if(!D.length)return info('Aucun dossier disponible','<p>Tous les dossiers ouverts ont déjà une déclaration. Créez d’abord un dossier dans le menu Dossiers.</p>');
ask('Nouvelle déclaration en douane',[{n:'d',l:'Dossier',o:D.map(d=>[String(d.id),`${d.num} · ${d.client_nom} · ${d.designation.slice(0,30)}`])}],async f=>{
try{await api(`/dossiers/${f.d}/declaration`,{method:'POST'});dnOpen(+f.d)}catch(e){fail('Déclaration non créée',e)}})}
