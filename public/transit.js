/* Module « Transit » branché sur l'API : déclarations, bureaux de passage, scellés, garantie,
   suivi jusqu'à l'apurement, incidents, alertes et échanges avec la douane. */
const TR={sel:null,st:'',q:'',al:false,L:[],R:null,D:[],CL:[],V:[],C:[]};
const TR_ST=['En préparation','Déposée','Acceptée','En circulation','Contrôlée','Arrivée à destination','Apurée','Rejetée'];
const TR_INC=['Retard','Contrôle','Scellé cassé','Anomalie','Régularisation'];
const canT=()=>W.transit.includes(role);
const trBadge=t=>`<span class="b ${{'En préparation':'','Déposée':'in','Acceptée':'in','En circulation':'wa','Contrôlée':'wa','Arrivée à destination':'in','Apurée':'ok','Rejetée':'ba'}[t.statut]}">${esc(t.statut)}</span>`
  +(t.en_retard?' <span class="b ba">Délai dépassé</span>':'')+(t.scelle_casse?' <span class="b ba">Scellé cassé</span>':'');
const trUrl=t=>`/dossiers/${t.dossier_id}/transit`;
const route=t=>[t.bureau_depart,...t.passages.map(p=>p.bureau),t.bureau_destination].map(esc).join(' → ');
const nf=n=>(+n).toLocaleString('fr-FR',{maximumFractionDigits:0});

function vTransit(){return`<div id="trv"><h1>Transit</h1><p class="mut">Chargement…</p></div>`}

async function loadTransit(){try{[TR.L,TR.R,TR.D,TR.V,TR.C]=await Promise.all([api('/transits'),api('/transits/resume'),api('/dossiers'),api('/vehicules').catch(()=>[]),api('/chauffeurs').catch(()=>[])])}
catch(e){$('#trv').innerHTML=`<h1>Transit</h1><p class="note">${esc(e.message)}</p>`;return}paintTransit()}

function paintTransit(){if(view!=='transit'||sel||!$('#trv'))return;$('#trv').innerHTML=TR.sel?trDetail(TR.L.find(t=>t.id===TR.sel)):trList();scrollTo(0,0)}
const trOpen=id=>{TR.sel=id;paintTransit()};

/* ---------- Liste ---------- */
const trRows=()=>{const q=TR.q.toLowerCase();return TR.L.filter(t=>(TR.st==='ouverts'?['En circulation','Contrôlée','Arrivée à destination'].includes(t.statut):!TR.st||t.statut===TR.st)&&(!TR.al||t.en_retard||t.scelle_casse)
&&(t.num+t.dossier_num+t.client_nom+t.ref_douane+t.vehicule+t.scelle+route(t)).toLowerCase().includes(q)).map(t=>`<tr>
<td><button class="lk" onclick="trOpen(${t.id})">${esc(t.num||'TR-'+t.id)}</button>${t.ref_douane?`<br><span class="mut mono">${esc(t.ref_douane)}</span>`:''}</td>
<td>${esc(t.dossier_num)}<br><span class="mut">${esc(t.client_nom)}</span></td><td>${route(t)}</td>
<td>${esc(t.vehicule||'—')}${t.scelle?`<br><span class="mut">Scellés : ${esc(t.scelle)}</span>`:''}</td>
<td>${t.depart?dfr(t.depart):'—'}${t.echeance?`<br><span class="mut">Échéance ${dfr(t.echeance)}</span>`:''}</td><td>${trBadge(t)}</td></tr>`).join('')||'<tr><td colspan="6" class="mut">Aucune déclaration de transit pour ces critères.</td></tr>'};

function trList(){const R=TR.R;return`<h1>Transit</h1><div class="kp"><div><b>${R.en_cours}</b><span>En circulation</span></div><div class="${R.en_retard?'w':''}"><b>${R.en_retard}</b><span>Délai dépassé</span></div>
<div><b>${R.en_preparation}</b><span>Avant départ</span></div><div class="${R.rejetes?'w':''}"><b>${R.rejetes}</b><span>Rejetés</span></div><div><b>${R.apures_30j}</b><span>Apurés sur 30 jours</span></div></div>
<div class="bar"><input placeholder="Rechercher : n°, dossier, client, bureau, scellé" value="${esc(TR.q)}" oninput="TR.q=this.value;$('#trl').innerHTML=trRows()" size="34">
<select onchange="TR.st=this.value;$('#trl').innerHTML=trRows()"><option value="">Tous les statuts</option><option value="ouverts" ${TR.st==='ouverts'?'selected':''}>En cours (non apurés)</option>${TR_ST.map(s=>`<option ${s===TR.st?'selected':''}>${s}</option>`).join('')}</select>
<label class="mut"><input type="checkbox" ${TR.al?'checked':''} onchange="TR.al=this.checked;$('#trl').innerHTML=trRows()"> Alertes seulement</label>
${canT()?'<button class="pri" onclick="trForm()">Nouvelle déclaration</button>':''}</div>
<div class="card tbl"><table><tr><th>Déclaration</th><th>Dossier</th><th>Itinéraire</th><th>Véhicule / scellés</th><th>Départ</th><th>Statut</th></tr><tbody id="trl">${trRows()}</tbody></table></div>`}

/* ---------- Détail ---------- */
function trDetail(t){const w=canT(),s=t.statut,i=TR_ST.indexOf(s),rej=s==='Rejetée',A=[];
const btn=(lib,fn,cls='pri')=>A.push(`<button class="${cls}" onclick="${fn}">${lib}</button>`);
if(w){if(['En préparation','Rejetée'].includes(s))btn('Modifier',`trForm(${t.id})`,'ghost');
if(s==='En préparation')btn('Déposer auprès de la douane',`trGo(${t.id},'Déposée')`);
if(rej)btn('Reprendre la préparation',`trGo(${t.id},'En préparation')`);
if(s==='Déposée')btn('Enregistrer l’acceptation',`trAccept(${t.id})`);
if(s==='Acceptée')btn('Mettre en circulation',`trGo(${t.id},'En circulation')`);
if(['Déposée','Acceptée'].includes(s))btn('Enregistrer un rejet',`trReject(${t.id})`,'dg');
if(s==='En circulation')btn('Contrôle en route',`trCtrl(${t.id})`,'ghost');
if(['En circulation','Contrôlée'].includes(s))btn('Arrivée à destination',`trGo(${t.id},'Arrivée à destination')`);
if(s==='Arrivée à destination')btn('Apurer le transit',`trGo(${t.id},'Apurée')`);
if(s!=='Apurée'){btn('Incident',`trInc(${t.id})`,'ghost')}btn('Consigner un échange',`trMsg(${t.id})`,'ghost')}
const g=(l,v)=>`<div><span>${l}</span>${v||'—'}</div>`;
return`<div class="bar"><button class="ghost" onclick="TR.sel=null;paintTransit()">Retour</button></div><h1>${esc(t.num||'TR-'+t.id)} ${trBadge(t)}</h1><p class="mut">Dossier ${esc(t.dossier_num)}, ${esc(t.client_nom)}${t.ref_douane?`, réf. douane <span class="mono">${esc(t.ref_douane)}</span>`:''}</p>
<div class="card"><div class="trk">${TR_ST.slice(0,7).map((x,j)=>`<div class="st ${rej?(j<2?'d':''):j<i?'d':j===i?'c':''}"><i></i>${x}</div>`).join('')}</div>${rej?'<p><span class="b ba">Rejetée par la douane</span> Corrigez puis reprenez la préparation.</p>':''}
${A.length?`<div class="bar" style="margin:6px 0 0">${A.join('')}</div>`:''}</div>
<div class="card"><h3>Déclaration</h3><div class="g">${g('Expéditeur',esc(t.expediteur))}${g('Destinataire',esc(t.destinataire))}${g('Transporteur',esc(t.transporteur))}${g('Marchandises',esc(t.marchandises))}
${g('Véhicule',esc(t.vehicule))}${g('Chauffeur',esc(t.chauffeur_nom))}${g('Scellés',esc(t.scelle))}${g('Garantie',esc(t.garantie)+(+t.garantie_montant?` (${nf(t.garantie_montant)} ${B()})`:''))}
${g('Départ',dfr(t.depart))}${g('Délai',t.delai_jours+' jours'+(t.echeance?`, échéance ${dfr(t.echeance)}`:''))}${g('Arrivée',dfr(t.arrivee))}${g('Apurement',dfr(t.apurement))}</div>${t.itineraire?`<p class="note">${esc(t.itineraire)}</p>`:''}</div>
<div class="card"><h3>Bureaux</h3><div class="al"><span class="b ok">Départ</span> ${esc(t.bureau_depart)} <span class="mut">${t.depart?'le '+dfr(t.depart):''}</span></div>
${t.passages.map(p=>`<div class="al"><span class="b ${p.date?'ok':''}">Passage</span> ${esc(p.bureau)} <span class="mut">${p.date?'constaté le '+dfr(p.date):'non constaté'}</span>${w&&!p.date&&['En circulation','Contrôlée','Arrivée à destination'].includes(s)?` <button class="ghost sm" onclick="trPass(${t.id},'${esc(p.bureau).replace(/'/g,"\\'")}')">Constater le passage</button>`:''}</div>`).join('')}
<div class="al"><span class="b ${t.arrivee?'ok':''}">Destination</span> ${esc(t.bureau_destination)} <span class="mut">${t.arrivee?'arrivée le '+dfr(t.arrivee):''}</span></div></div>
<div class="card"><h3>Incidents</h3>${t.incidents.map(x=>`<div class="al">${badge(x.type)} ${dfr(x.date)} ${esc(x.note)}</div>`).join('')||'<p class="mut">Aucun incident.</p>'}</div>
<div class="card"><h3>Échanges avec la douane</h3>${[...t.messages].reverse().map(m=>`<div class="al"><span class="b ${{envoi:'in','réception':'ok',interne:''}[m.sens]}">${{envoi:'Envoi','réception':'Réception',interne:'Interne'}[m.sens]}</span> <span class="mut">${hfr(m.ts)}</span> ${esc(m.texte)}</div>`).join('')||'<p class="mut">Aucun échange.</p>'}</div>`}

/* ---------- Actions ---------- */
async function trPost(id,path,json,title){const t=TR.L.find(x=>x.id===id);try{const n=await api(trUrl(t)+path,{method:'POST',json});TR.L=TR.L.map(x=>x.id===id?n:x);TR.R=await api('/transits/resume');paintTransit()}catch(e){fail(title,e)}}
const trGo=(id,to,extra={})=>trPost(id,'/transition',{to,...extra},'Changement de statut impossible');
const trAccept=id=>ask('Acceptation par la douane',[{n:'ref_douane',l:'Référence douanière attribuée (facultatif)'}],f=>trGo(id,'Acceptée',f));
const trReject=id=>ask('Rejet par la douane',[{n:'motif',l:'Motif du rejet',r:1}],f=>trGo(id,'Rejetée',f));
const trCtrl=id=>ask('Contrôle en route',[{n:'motif',l:'Lieu ou nature du contrôle'}],f=>trGo(id,'Contrôlée',f));
const trPass=(id,bureau)=>trPost(id,'/passages',{bureau},'Passage non enregistré');
const trInc=id=>ask('Incident de transit',[{n:'type',l:'Type',o:TR_INC},{n:'note',l:'Détail'}],f=>trPost(id,'/incidents',f,'Incident non enregistré'));
const trMsg=id=>ask('Échange avec la douane',[{n:'sens',l:'Sens',o:[['réception','Reçu de la douane'],['envoi','Envoyé à la douane'],['interne','Note interne']]},{n:'texte',l:'Contenu',r:1}],f=>trPost(id,'/messages',f,'Échange non enregistré'));

function trForm(id,dossierId){const t=id?TR.L.find(x=>x.id===id):{delai_jours:7,passages:[]},s=v=>v==null?'':String(v);
const libres=TR.D.filter(d=>!TR.L.some(x=>x.dossier_id===d.id));
if(!id&&!libres.length){info('Aucun dossier disponible',`<p>Une déclaration de transit se rattache à un dossier enregistré. Aucun dossier sans transit n’existe encore.</p>${W.dossier.includes(role)?'<div class="row"><button class="pri" type="button" onclick="dlg.close();trDossier()">Créer un dossier</button></div>':''}`);return}
const F=[...(id?[]:[{n:'dossier',l:'Dossier',o:libres.map(d=>[String(d.id),`${d.num} · ${d.designation.slice(0,40)}`]),v:s(dossierId)}]),
{n:'bureau_depart',l:'Bureau de départ',v:t.bureau_depart||'',r:1},{n:'bureau_destination',l:'Bureau de destination',v:t.bureau_destination||'',r:1},
{n:'bureaux_passage',l:'Bureaux de passage (séparés par des virgules)',v:t.passages.map(p=>p.bureau).join(', ')},{n:'itineraire',l:'Itinéraire / observations',v:t.itineraire||''},
{n:'expediteur',l:'Expéditeur (vide = fournisseur du dossier)',v:t.expediteur||''},{n:'destinataire',l:'Destinataire (vide = dossier)',v:t.destinataire||''},
{n:'transporteur',l:'Transporteur',v:t.transporteur||''},{n:'marchandises',l:'Marchandises (vide = repris du dossier)',v:t.marchandises||''},
{n:'vehicule_id',l:'Véhicule du parc',o:opt(TR.V.filter(v=>v.actif||v.id===t.vehicule_id),v=>v.immatriculation+' · '+v.type,'Hors parc / à préciser'),v:s(t.vehicule_id)},
{n:'vehicule',l:'Immatriculation (si hors parc)',v:t.vehicule_id?'':t.vehicule||''},{n:'chauffeur_id',l:'Chauffeur',o:opt(TR.C.filter(c=>c.actif||c.id===t.chauffeur_id),c=>c.nom,'Non précisé'),v:s(t.chauffeur_id)},
{n:'scelle',l:'Numéros de scellés',v:t.scelle||''},{n:'garantie',l:'Garantie (type, référence)',v:t.garantie||''},
{n:'garantie_montant',l:`Montant de la garantie (${B()})`,t:'number',v:+t.garantie_montant||''},{n:'delai_jours',l:'Délai de route (jours)',t:'number',v:t.delai_jours,r:1}];
ask(id?`Modifier ${t.num}`:'Nouvelle déclaration de transit',F,async f=>{const did=id?t.dossier_id:+f.dossier;delete f.dossier;
const body={...f,bureaux_passage:f.bureaux_passage.split(',').map(x=>x.trim()).filter(Boolean),vehicule_id:f.vehicule_id?+f.vehicule_id:null,chauffeur_id:f.chauffeur_id?+f.chauffeur_id:null,garantie_montant:+f.garantie_montant||0,delai_jours:+f.delai_jours||7};
try{const n=await api(`/dossiers/${did}/transit`,{method:id?'PUT':'POST',json:body});await loadTransit();trOpen(n.id)}catch(e){fail('Déclaration non enregistrée',e)}})}

/* Création rapide d'un dossier (et du client si besoin) pour y rattacher un transit */
async function trDossier(){try{TR.CL=await api('/clients')}catch(e){TR.CL=[]}
ask('Nouveau dossier',[{n:'client_id',l:'Client',o:[['','Nouveau client…'],...TR.CL.map(c=>[String(c.id),c.nom])],v:TR.CL[0]?String(TR.CL[0].id):''},
{n:'cnom',l:'Nouveau client : raison sociale'},{n:'cnif',l:'Nouveau client : NIF / RC'},{n:'type',l:'Type d’opération',o:TYPES,v:'Transit international'},
{n:'designation',l:'Désignation des marchandises',r:1},{n:'code_sh',l:'Code SH',r:1},{n:'colis',l:'Nombre de colis',t:'number',v:0},{n:'poids',l:'Poids brut (kg)',t:'number',v:0},
{n:'valeur',l:'Valeur',t:'number',v:0},{n:'devise',l:'Devise',o:['GNF','USD','EUR','XOF'],v:'USD'},{n:'fournisseur',l:'Fournisseur / expéditeur'},{n:'destinataire',l:'Destinataire'},
{n:'transporteur',l:'Transporteur'},{n:'ref',l:'Référence client'}],async f=>{try{let cid=+f.client_id;
if(!cid){if(!f.cnom.trim()||!f.cnif.trim())throw new Error('Choisissez un client ou renseignez la raison sociale et le NIF du nouveau client');cid=(await api('/clients',{method:'POST',json:{nom:f.cnom,nif:f.cnif}})).id}
const d=await api('/dossiers',{method:'POST',json:{type:f.type,client_id:cid,designation:f.designation,code_sh:f.code_sh,colis:+f.colis||0,poids:+f.poids||0,valeur:+f.valeur||0,devise:f.devise,fournisseur:f.fournisseur,destinataire:f.destinataire,transporteur:f.transporteur,ref:f.ref}});
TR.D=await api('/dossiers');trForm(null,d.id)}catch(e){fail('Dossier non créé',e)}})}
