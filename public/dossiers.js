/* Module « Dossiers » branché sur l'API : liste et recherche, création et modification, fiche complète
   (étapes prévues/réelles, documents, douane, transit, opérations, facturation et marge, journal). */
const DS={sel:null,tab:'res',q:'',st:'',ty:'',L:[],CL:[],P:null,d:null,docs:[],jal:[]};
const DOC_LIB={facture:'Facture commerciale',packing:'Packing list',bl:'Connaissement / LTA',cmr:'Lettre de voiture CMR',origine:'Certificat d’origine',dum:'DUM / déclaration',quittance:'Quittance de paiement',pod:'Preuve de livraison',photo:'Photo de chargement / déchargement',autre:'Autre document'};
const INCOTERMS=['','EXW','FCA','FAS','FOB','CFR','CIF','CPT','CIP','DAP','DPU','DDP'];
const COUT_CAT=['Transport','Manutention','Magasinage','Frais portuaires','Droits et taxes','Honoraires agent','Frais bancaires','Autre'];
const reqDocs=t=>t==='Export'?['facture','packing']:(/^Transit/.test(t)||t==='T1/T2')?['facture','packing','cmr']:['facture','packing','bl'];
const isStaff=()=>role!=='Client',canFact=()=>['Administrateur','Comptable','Direction','Responsable transit','Commercial'].includes(role);
const dsBadge=s=>s?badge(s):'<span class="mut">—</span>';
const base=()=>DS.P?DS.P.base:(typeof FC!=='undefined'&&FC.R?FC.R.devise_base:'GNF');
const pct=v=>(+v).toLocaleString('fr-FR',{maximumFractionDigits:2})+' %';
const dsUrl=p=>`/dossiers/${DS.sel}${p||''}`;

function vDossiersApi(){return`<div id="dsv"><h1>Dossiers</h1><p class="mut">Chargement…</p></div>`}

async function loadDossiers(){try{const p=new URLSearchParams();if(DS.q)p.set('q',DS.q);if(DS.st)p.set('statut',DS.st);if(DS.ty)p.set('type',DS.ty);
[DS.L,DS.CL,DS.P]=await Promise.all([api('/dossiers?'+p),isStaff()?api('/clients').catch(()=>[]):[],isStaff()?api('/params').catch(()=>null):null])}
catch(e){$('#dsv').innerHTML=`<h1>Dossiers</h1><p class="note">${esc(e.message)}</p>`;return}
if(DS.sel)return dsLoad();paintDossiers()}

function paintDossiers(){if(view!=='dossiers'||sel||!$('#dsv'))return;$('#dsv').innerHTML=DS.sel&&DS.d?dsDetail():dsList()}

/* ---------- Liste ---------- */
function dsList(){const rows=DS.L.map(d=>`<tr><td><button class="lk" onclick="dsOpen(${d.id})">${esc(d.num)}</button><br><span class="mut">${esc(d.ref||'')}</span></td>
<td>${esc(d.type)}</td><td>${esc(d.client_nom)}</td><td>${esc(d.designation)}<br><span class="mut mono">SH ${esc(d.code_sh)}</span></td>
<td><span class="b ${d.completude===100?'ok':'wa'}">${d.completude} %</span></td><td>${dsBadge(d.declaration_statut)}</td><td>${dsBadge(d.transit_statut)}</td>
${isStaff()?`<td>${dsBadge(d.facture_statut)}</td>`:''}<td>${badge(d.statut)}</td><td>${dfr(d.created_at)}</td></tr>`).join('')
||`<tr><td colspan="10" class="mut">${DS.q||DS.st||DS.ty?'Aucun dossier pour ces critères.':'Aucun dossier enregistré.'}</td></tr>`;
return`<h1>Dossiers</h1><div class="bar"><input id="dsq" placeholder="N°, client, référence, code SH, conteneur, réf. douane" value="${esc(DS.q)}" size="38" onkeydown="if(event.key==='Enter'){DS.q=this.value;loadDossiers()}">
<button class="ghost" onclick="DS.q=$('#dsq').value;loadDossiers()">Rechercher</button>
<select onchange="DS.st=this.value;loadDossiers()"><option value="">Tous les statuts</option>${DSTAT.map(s=>`<option ${s===DS.st?'selected':''}>${s}</option>`).join('')}</select>
<select onchange="DS.ty=this.value;loadDossiers()"><option value="">Tous les types</option>${TYPES.map(s=>`<option ${s===DS.ty?'selected':''}>${s}</option>`).join('')}</select>
${W.dossier.includes(role)?'<button class="pri" onclick="dsForm()">Nouveau dossier</button>':''}</div>
<div class="card tbl"><table><tr><th>Dossier</th><th>Type</th><th>Client</th><th>Marchandises</th><th>Documents</th><th>Douane</th><th>Transit</th>${isStaff()?'<th>Facture</th>':''}<th>Statut</th><th>Ouvert le</th></tr>${rows}</table></div>`}

/* ---------- Création / modification ---------- */
function dsForm(id){const d=id?DS.d:{type:'Import',regime:(DS.P?.reg||[])[0],devise:'USD',incoterm:'',colis:0,poids:0,valeur:0,fret:0,assurance:0},v=x=>x==null?'':x;
ask(id?`Modifier ${d.num}`:'Nouveau dossier',[{n:'type',l:'Type d’opération',o:TYPES,v:d.type},{n:'regime',l:'Régime douanier',o:DS.P?.reg||['Mise à la consommation'],v:d.regime},
{n:'client_id',l:'Client',o:[...(id?[]:[['','Nouveau client…']]),...DS.CL.map(c=>[String(c.id),c.nom])],v:id?String(d.client_id):(DS.CL[0]?String(DS.CL[0].id):'')},
...(id?[]:[{n:'cnom',l:'Nouveau client : raison sociale'},{n:'cnif',l:'Nouveau client : NIF / RC'}]),
{n:'ref',l:'Référence client',v:v(d.ref)},{n:'incoterm',l:'Incoterm',o:INCOTERMS.map(x=>[x,x||'—']),v:d.incoterm||''},
{n:'fournisseur',l:'Fournisseur / expéditeur',v:v(d.fournisseur)},{n:'destinataire',l:'Destinataire',v:v(d.destinataire)},
{n:'transporteur',l:'Transporteur',v:v(d.transporteur)},{n:'agent_douanier',l:'Agent / commissionnaire en douane',v:v(d.agent_douanier)},
{n:'lieu_livraison',l:'Lieu de livraison',v:v(d.lieu_livraison)},{n:'origine',l:'Pays d’origine',v:v(d.origine)},
{n:'designation',l:'Désignation des marchandises',v:v(d.designation),r:1},{n:'code_sh',l:'Code SH',v:v(d.code_sh),r:1},
{n:'colis',l:'Nombre de colis',t:'number',v:+d.colis},{n:'poids',l:'Poids brut (kg)',t:'number',v:+d.poids},
{n:'valeur',l:'Valeur des marchandises',t:'number',v:+d.valeur},{n:'devise',l:'Devise',o:Object.keys(DS.P?.rates||{GNF:1,USD:1,EUR:1}),v:d.devise},
{n:'fret',l:`Fret (${base()})`,t:'number',v:+d.fret},{n:'assurance',l:`Assurance (${base()})`,t:'number',v:+d.assurance}],async f=>{
try{let cid=+f.client_id;if(!cid){if(!f.cnom?.trim()||!f.cnif?.trim())throw new Error('Choisissez un client ou renseignez la raison sociale et le NIF du nouveau client');
cid=(await api('/clients',{method:'POST',json:{nom:f.cnom,nif:f.cnif}})).id}
const body={type:f.type,regime:f.regime,client_id:cid,ref:f.ref,incoterm:f.incoterm,fournisseur:f.fournisseur,destinataire:f.destinataire,transporteur:f.transporteur,agent_douanier:f.agent_douanier,
lieu_livraison:f.lieu_livraison,origine:f.origine,designation:f.designation,code_sh:f.code_sh,colis:+f.colis||0,poids:+f.poids||0,valeur:+f.valeur||0,devise:f.devise,fret:+f.fret||0,assurance:+f.assurance||0};
const n=await api(id?'/dossiers/'+id:'/dossiers',{method:id?'PUT':'POST',json:body});DS.sel=n.id;DS.tab='res';await loadDossiers()}catch(e){fail('Dossier non enregistré',e)}})}

/* ---------- Fiche ---------- */
const dsOpen=id=>{DS.sel=id;DS.tab='res';dsLoad()};
async function dsLoad(){try{[DS.d,DS.docs,DS.jal]=await Promise.all([api(dsUrl()),api(dsUrl('/documents')),api(dsUrl('/jalons'))])}catch(e){fail('Dossier indisponible',e);DS.sel=null;return paintDossiers()}paintDossiers();scrollTo(0,0);dsTabLoad()}
const dsTab=t=>{DS.tab=t;paintDossiers();dsTabLoad()};

function dsDetail(){const d=DS.d,w=W.dossier.includes(role);
const T=[['res','Résumé'],['docs',`Documents (${d.completude} %)`],['douane','Douane'],['transit','Transit'],['ops','Opérations'],...(isStaff()?[['fact','Facturation et marge'],['jr','Journal']]:[])];
return`<div class="bar"><button class="ghost" onclick="DS.sel=null;DS.d=null;loadDossiers()">Retour</button>${w?`<button class="ghost" onclick="dsForm(${d.id})">Modifier</button>
<select onchange="dsStatut(this.value)" aria-label="Statut du dossier">${DSTAT.map(s=>`<option ${s===d.statut?'selected':''}>${s}</option>`).join('')}</select>`:''}</div>
<h1>${esc(d.num)} ${badge(d.statut)}</h1><p class="mut">${esc(d.type)}, ${esc(d.client_nom)}${d.ref?`, réf. ${esc(d.ref)}`:''}</p>
<div class="tabs">${T.map(t=>`<button class="${t[0]===DS.tab?'on':''}" onclick="dsTab('${t[0]}')">${t[1]}</button>`).join('')}</div><div id="dst">${DS.tab==='res'?dsRes():'<p class="mut">Chargement…</p>'}</div>`}

async function dsStatut(s){try{DS.d=await api(dsUrl('/statut'),{method:'PATCH',json:{statut:s}});DS.jal=await api(dsUrl('/jalons'));paintDossiers()}catch(e){fail('Statut non modifié',e)}}

function dsTabLoad(){const f={docs:dsDocs,douane:dsDouane,transit:dsTransit,ops:dsOps,fact:dsFact,jr:dsJournal}[DS.tab];if(f)f().catch(e=>{if($('#dst'))$('#dst').innerHTML=`<p class="note">${esc(e.message)}</p>`})}
const dsPaint=h=>{if($('#dst'))$('#dst').innerHTML=h};

/* Résumé et étapes */
function dsRes(){const d=DS.d,g=(l,v)=>`<div><span>${l}</span>${v===''||v==null?'—':v}</div>`,canJ=[...W.dossier,'Agent opérationnel','Déclarant en douane'].includes(role);
return`<div class="card"><div class="g">${g('Régime',esc(d.regime))}${g('Incoterm',esc(d.incoterm))}${g('Fournisseur',esc(d.fournisseur))}${g('Destinataire',esc(d.destinataire))}
${g('Transporteur',esc(d.transporteur))}${g('Agent en douane',esc(d.agent_douanier))}${g('Lieu de livraison',esc(d.lieu_livraison))}${g('Origine',esc(d.origine))}
${g('Marchandises',esc(d.designation))}${g('Code SH',`<span class="mono">${esc(d.code_sh)}</span>`)}${g('Colis / poids',`${nf(d.colis)} colis, ${nf(d.poids)} kg`)}
${g('Valeur',`${(+d.valeur).toLocaleString('fr-FR')} ${esc(d.devise)}`)}${g('Fret + assurance',`${nf(+d.fret + +d.assurance)} ${base()}`)}${g('Ouvert le',dfr(d.created_at))}</div></div>
<div class="card tbl"><h3>Étapes opérationnelles</h3><table><tr><th>Étape</th><th>Prévue</th><th>Réelle</th><th>Écart</th><th></th></tr>${DS.jal.map(j=>`<tr><td>${esc(j.libelle)}</td><td>${dfr(j.prevue)}</td>
<td>${j.reelle?dfr(j.reelle)+(j.automatique?' <span class="mut" title="Date issue des événements enregistrés">auto</span>':''):'—'}</td>
<td>${j.ecart_jours!=null?`<span class="b ${j.ecart_jours>0?'ba':'ok'}">${j.ecart_jours>0?'+':''}${j.ecart_jours} j</span>`:j.retard?'<span class="b ba">En retard</span>':''}</td>
<td>${canJ?`<button class="ghost sm" onclick="dsJalon('${j.cle}')">Dates</button>`:''}</td></tr>`).join('')}</table>
<p class="mut">Les dates réelles marquées « auto » viennent des événements enregistrés (conteneurs, douane, transit, missions, facture) et priment sur la saisie.</p></div>`}

const dsJalon=k=>{const j=DS.jal.find(x=>x.cle===k);ask(j.libelle,[{n:'prevue',l:'Date prévue',t:'date',v:j.prevue||''},...(j.automatique?[]:[{n:'reelle',l:'Date réelle',t:'date',v:j.reelle||''}])],async f=>{
try{DS.jal=await api(dsUrl('/jalons/'+k),{method:'PUT',json:{prevue:f.prevue||null,reelle:f.reelle||null}});paintDossiers()}catch(e){fail('Étape non enregistrée',e)}})};

/* Documents */
async function dsDocs(){const d=DS.d,req=reqDocs(d.type),have=new Set(DS.docs.map(x=>x.type)),w=W.docs.includes(role);
dsPaint(`<div class="card"><h3>Pièces obligatoires (${d.completude} %)</h3>${req.map(k=>`<div class="al">${have.has(k)?badge('Conforme'):'<span class="b ba">Manquant</span>'} ${DOC_LIB[k]}</div>`).join('')}</div>
${w?`<div class="card"><h3>Déposer un document</h3><form id="dsup" class="bar" onsubmit="return dsUpload(event)"><select name="type">${Object.entries(DOC_LIB).map(([k,l])=>`<option value="${k}" ${req.includes(k)&&!have.has(k)?'selected':''}>${l}</option>`).join('')}</select>
<input type="file" name="fichier" required accept=".pdf,.png,.jpg,.jpeg,.xlsx,.docx"><button class="pri">Téléverser</button></form><p class="mut">PDF, images, Excel ou Word, 4 Mo maximum. Un nouveau dépôt du même type crée une nouvelle version.</p></div>`:''}
<div class="card tbl"><table><tr><th>Type</th><th>Version</th><th>Fichier</th><th>Déposé par</th><th>Date</th><th></th></tr>${[...DS.docs].reverse().map(x=>`<tr><td>${esc(DOC_LIB[x.type]||x.type)}</td><td>v${x.version}</td><td>${esc(x.nom_fichier)}</td><td>${esc(x.depose_par)}</td><td>${hfr(x.created_at)}</td>
<td><button class="ghost sm" onclick="dsDownload(${x.id},'${esc(x.nom_fichier).replace(/'/g,"\\'")}')">Télécharger</button></td></tr>`).join('')||'<tr><td colspan="6" class="mut">Aucun document.</td></tr>'}</table></div>`)}

async function dsUpload(e){e.preventDefault();const f=new FormData(e.target),b=e.target.querySelector('button');b.disabled=true;
try{await api(dsUrl('/documents'),{method:'POST',body:f});[DS.d,DS.docs]=await Promise.all([api(dsUrl()),api(dsUrl('/documents'))]);paintDossiers();dsTabLoad()}catch(err){fail('Dépôt refusé',err);b.disabled=false}return false}
async function dsDownload(id,nom){try{const r=await fetch('/api/documents/'+id+'/download',{headers:{Authorization:'Bearer '+getTok()}});if(!r.ok)throw new Error('Téléchargement impossible ('+r.status+')');
const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=nom;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}catch(e){fail('Téléchargement',e)}}

/* Douane */
async function dsDouane(){const w=W.douane.includes(role);let x=null;try{x=await api(dsUrl('/declaration'))}catch(e){}
if(!x)return dsPaint(`<div class="card"><p>Aucune déclaration en douane pour ce dossier.</p>${w?'<button class="pri" onclick="dsDecl(\'\')">Générer le projet de déclaration</button>':''}</div>`);
const k=await api(dsUrl('/declaration/calcul')),L=k.liquidation,ok=k.controles.every(c=>c.conforme),s=x.statut,mt=v=>nf(v)+' '+L.devise_base,A=[];
if(w){if(s==='Brouillon')A.push(`<button class="pri" ${ok?'':'disabled title="Contrôles non satisfaits"'} onclick="dsDecl('/transmettre')">Transmettre à la douane</button>`);
if(s==='Transmise')A.push(...['Acceptée','Contrôle','Rejetée'].map(r=>`<button class="${r==='Rejetée'?'dg':'ghost'}" onclick="dsRep('${r}')">Réponse : ${r}</button>`));
if(['Acceptée','Contrôle'].includes(s))A.push(`<button class="pri" onclick="dsRep('Bon à enlever')">Réponse : Bon à enlever</button>`);
if(s==='Rejetée')A.push(`<button class="ghost" onclick="dsDecl('/rouvrir')">Rouvrir pour correction</button>`)}
if([...W.douane,'Comptable'].includes(role)&&['Acceptée','Contrôle'].includes(s)&&!x.quittance_ref)A.push(`<button class="${x.montant_liquide>0?'pri':'ghost'}" onclick="dsQuit(${x.montant_liquide||0})">Enregistrer la quittance</button>`);
const g=(l,v)=>`<div><span>${l}</span>${v||'—'}</div>`,info2=`<div class="g" style="margin:12px 0">${g('Référence douane',esc(x.ref_douane))}${g('Créée le',hfr(x.created_at))}${g('Transmise le',hfr(x.transmise_le))}
${g('Liquidation figée',x.montant_liquide!=null?mt(x.montant_liquide):'')}${g('Quittance',x.quittance_ref?`${esc(x.quittance_ref)} · ${mt(x.quittance_montant)} · ${dfr(x.quittance_date)}`:'')}
${g('Bon à enlever',x.bae_le?`${hfr(x.bae_le)} (en ${jours(x.delai_jours)})`:x.attente_jours!=null?`en attente depuis ${x.attente_jours} j`:'')}</div>`;
dsPaint(`<div class="card"><h3>Déclaration ${esc(x.ref)} ${badge(s)}</h3>${info2}${A.length?`<div class="bar">${A.join('')}</div>`:''}
${s!=='Brouillon'&&x.montant_liquide!=null&&Math.round(x.montant_liquide)!==Math.round(L.total)?`<p class="note">Liquidation figée à la transmission : ${mt(x.montant_liquide)} (le calcul actuel donne ${mt(L.total)}, paramètres modifiés depuis).</p>`:''}
<div class="tbl"><table><tr><th>Élément</th><th>Taux</th><th>Montant</th></tr><tr><td>Valeur CIF (valeur + fret + assurance)</td><td></td><td>${mt(L.valeur_cif)}</td></tr>
<tr><td>Droit de douane${L.code_sh_connu?'':' <span class="mut">(taux par défaut, code SH non paramétré)</span>'}</td><td>${pct(L.droit_douane.taux)}</td><td>${mt(L.droit_douane.montant)}</td></tr>
${L.autres_taxes.map(t=>`<tr><td>${esc(t.nom)}</td><td>${pct(t.taux)}</td><td>${mt(t.montant)}</td></tr>`).join('')}${+L.accise.montant?`<tr><td>Accise</td><td>${pct(L.accise.taux)}</td><td>${mt(L.accise.montant)}</td></tr>`:''}
<tr><td>TVA</td><td>${pct(L.tva.taux)}</td><td>${mt(L.tva.montant)}</td></tr><tr><th>Total droits et taxes</th><th></th><th>${mt(L.total)}</th></tr></table></div></div>
<div class="card"><h3>Contrôles de cohérence</h3>${k.controles.map(c=>`<div class="al">${c.conforme?badge('Conforme'):'<span class="b ba">Bloquant</span>'} ${esc(c.controle)}</div>`).join('')}</div>
<div class="card"><h3>Messages douaniers</h3>${[...x.messages].reverse().map(m=>`<div class="al"><span class="b ${{envoi:'in','réception':'ok',interne:''}[m.sens]||''}">${esc(m.sens)}</span> <span class="mut">${hfr(m.created_at)}</span> ${esc(m.texte)}</div>`).join('')||'<p class="mut">Aucun message.</p>'}</div>`)}
async function dsDecl(p){try{await api(dsUrl('/declaration'+p),{method:'POST'});await dsRefresh()}catch(e){fail('Action impossible',e)}}
const dsRep=s=>ask(`Réponse de la douane : ${s}`,[...(s==='Acceptée'?[{n:'ref_douane',l:'Référence d’enregistrement douanier'}]:[]),{n:'texte',l:s==='Rejetée'?'Motif du rejet':'Texte du message (facultatif)',r:s==='Rejetée'}],
async f=>{try{await api(dsUrl('/declaration/messages'),{method:'POST',json:{statut:s,texte:f.texte,ref_douane:f.ref_douane||''}});await dsRefresh()}catch(e){fail('Réponse non enregistrée',e)}});
const dsQuit=m=>ask('Quittance des droits et taxes',[{n:'ref',l:'N° de quittance',r:1},{n:'montant',l:`Montant payé (${base()})`,t:'number',v:Math.round(m),r:1},{n:'date',l:'Date de paiement',t:'date',v:today()}],
async f=>{try{await api(dsUrl('/declaration/quittance'),{method:'POST',json:{ref:f.ref,montant:+f.montant,date:f.date||null}});await dsRefresh()}catch(e){fail('Quittance refusée',e)}});
async function dsRefresh(){[DS.d,DS.jal]=await Promise.all([api(dsUrl()),api(dsUrl('/jalons'))]);paintDossiers();dsTabLoad()}

/* Transit */
async function dsTransit(){let t=null;try{t=await api(dsUrl('/transit'))}catch(e){}
if(!t)return dsPaint(`<div class="card"><p>Aucune déclaration de transit pour ce dossier.</p>${W.transit.includes(role)?`<button class="pri" onclick="dsGoTransit(null)">Créer la déclaration de transit</button>`:''}</div>`);
dsPaint(`<div class="card"><h3>${esc(t.num||'Transit')} ${trBadge(t)}</h3><p>${route(t)}</p><div class="g"><div><span>Véhicule</span>${esc(t.vehicule||'—')}</div><div><span>Scellés</span>${esc(t.scelle||'—')}</div>
<div><span>Départ</span>${dfr(t.depart)}</div><div><span>Échéance</span>${dfr(t.echeance)}</div><div><span>Apurement</span>${dfr(t.apurement)}</div><div><span>Réf. douane</span>${esc(t.ref_douane||'—')}</div></div>
${ACCESS[role].includes('transit')?`<div class="bar" style="margin-top:12px"><button class="pri" onclick="dsGoTransit(${t.id})">Ouvrir dans le module Transit</button></div>`:''}</div>`)}
async function dsGoTransit(tid){const did=DS.sel;go('transit');await loadTransit();if(tid)trOpen(tid);else trForm(null,did)}

/* Opérations */
async function dsOps(){const[K,M]=await Promise.all([api(dsUrl('/conteneurs')),api(dsUrl('/missions'))]);
dsPaint(`<div class="card tbl"><h3>Conteneurs</h3><table><tr><th>Conteneur</th><th>Compagnie</th><th>Arrivée</th><th>Sortie</th><th>Retour vide</th><th>Statut</th><th>Magasinage</th></tr>
${K.map(k=>`<tr><td class="mono">${esc(k.numero)} <span class="mut">${esc(k.type)}</span></td><td>${esc(k.compagnie||'—')}</td><td>${dfr(k.arrivee)}</td><td>${dfr(k.sortie)}</td><td>${dfr(k.retour)}</td><td>${kBadge(k)}</td><td>${k.jours_magasinage?`<span class="b wa">${k.jours_magasinage} j</span>`:'0 j'}</td></tr>`).join('')||'<tr><td colspan="7" class="mut">Aucun conteneur rattaché.</td></tr>'}</table></div>
<div class="card tbl"><h3>Missions de transport</h3><table><tr><th>Mission</th><th>Date</th><th>Type</th><th>Trajet</th><th>Véhicule / chauffeur</th><th>Statut</th></tr>
${M.map(m=>`<tr><td class="mono">${esc(m.num)}</td><td>${dfr(m.date_prevue)}</td><td>${esc(m.type)}</td><td>${esc(m.origine)} → ${esc(m.destination)}</td><td>${esc(m.vehicule_immat||'—')}<br><span class="mut">${esc(m.chauffeur_nom||'')}</span></td><td>${mBadge(m)}</td></tr>`).join('')||'<tr><td colspan="6" class="mut">Aucune mission.</td></tr>'}</table>
${ACCESS[role].includes('ops')?'<div class="bar" style="margin-top:12px"><button class="ghost" onclick="go(\'ops\')">Ouvrir le module Opérations</button></div>':''}</div>`)}

/* Facturation, coûts et marge */
async function dsFact(){let f=null,dv=[],av=[];const wf=W.fact.includes(role),wc=[...W.dossier,...W.fact].includes(role);
if(canFact()){[f,dv,av]=await Promise.all([api(dsUrl('/facture')).catch(()=>null),api(dsUrl('/devis')).catch(()=>[]),api(dsUrl('/avances')).catch(()=>[])])}
DS.dv=dv;const C=await api(dsUrl('/couts')),b=C.devise_base,mb=v=>nf(v)+' '+b,dev=f?f.devise:(dv[0]?.devise||'');
const fac=!canFact()?'':!f?`<div class="card"><p>Aucune facture pour ce dossier.</p><div class="bar">${wf?'<button class="pri" onclick="dsInvoice()">Générer la facture</button>':''}${W.devis.includes(role)?`<button class="ghost" onclick="dvNew(${DS.sel})">Établir un devis</button>`:''}${wf?'<button class="ghost" onclick="dsAvance()">Enregistrer une avance</button>':''}</div></div>`
:`<div class="card"><h3>${esc(f.num)} ${badge(f.statut)}</h3><p class="mut">Émise le ${dfr(f.date_emission)}, échéance ${dfr(f.echeance)}${f.jours_retard?`, <b>${f.jours_retard} jours de retard</b>`:''}${f.relances?`, ${f.relances} relance(s)`:''}</p>${fcDetail(f)}
<div class="bar" style="margin-top:12px">${wf&&f.solde>0?`<button class="pri" onclick="fcPay(${f.id},${f.solde},'${f.devise}')">Enregistrer un règlement</button><button class="ghost" onclick="fcAvoir(${f.id},${f.solde},'${f.devise}')">Établir un avoir</button><button class="ghost" onclick="fcRelance(${f.id})">Relancer</button>`:''}<button class="ghost" onclick="fcPrint(${f.id})">Imprimer / PDF</button></div></div>`;
const devis=!canFact()||!dv.length?'':`<div class="card tbl"><h3>Devis</h3><table><tr><th>Devis</th><th>Date</th><th>Montant</th><th>Valable jusqu’au</th><th>Statut</th><th></th></tr>${dv.map(x=>`<tr><td class="mono">${esc(x.num)}</td><td>${dfr(x.date_emission)}</td><td>${mo(x.total,x.devise)}</td><td>${dfr(x.validite)}</td><td>${dvBadge(x)}</td><td class="act">${dvActions(x)}</td></tr>`).join('')}</table>${!f&&W.devis.includes(role)?`<div class="bar" style="margin-top:10px"><button class="ghost" onclick="dvNew(${DS.sel})">Nouveau devis</button></div>`:''}</div>`;
const avances=!av.length?'':`<div class="card"><h3>Avances reçues</h3>${av.map(a=>`<div class="al"><span class="b ${a.facture_id?'ok':'wa'}">${a.facture_id?'Imputée':'En attente de facture'}</span> ${dfr(a.date)} · ${mo(a.montant,a.devise)} · ${esc(a.mode)}${a.reference?' · '+esc(a.reference):''}</div>`).join('')}${!f&&wf?'<div class="bar" style="margin-top:10px"><button class="ghost" onclick="dsAvance()">Nouvelle avance</button></div>':''}</div>`;
dsPaint(`${fac}${devis}${avances}<div class="kp"><div><b>${nf(C.facture)}</b><span>Facturé (${b})</span></div><div><b>${nf(C.total_couts)}</b><span>Coûts engagés (${b})</span></div>
<div class="${C.marge<0?'w':''}"><b>${nf(C.marge)}</b><span>Marge${C.taux_marge!=null?` (${pct(C.taux_marge)})`:''}</span></div></div>
<div class="card tbl"><div class="bar"><h3 style="margin:0">Coûts du dossier</h3>${wc?'<button class="pri" onclick="dsCout()">Ajouter un coût</button>':''}</div><table><tr><th>Date</th><th>Catégorie</th><th>Libellé</th><th>Fournisseur</th><th>Montant</th><th>En ${b}</th><th></th></tr>
${C.couts.map(c=>`<tr><td>${dfr(c.date)}</td><td>${esc(c.categorie)}</td><td>${esc(c.libelle)}</td><td>${esc(c.fournisseur||'—')}</td><td>${(+c.montant).toLocaleString('fr-FR')} ${c.devise}</td><td>${mb(c.montant_base)}</td>
<td>${wc?`<button class="dg sm" onclick="dsCoutDel(${c.id})">Supprimer</button>`:''}</td></tr>`).join('')||'<tr><td colspan="7" class="mut">Aucun coût saisi.</td></tr>'}</table>
${C.dont_debours?`<p class="mut">Le montant facturé inclut ${mb(C.dont_debours)} de droits et taxes refacturés (débours). Saisissez leur paiement en coût « Droits et taxes » pour une marge juste.</p>`:''}</div>`)}

function dsInvoice(){const n=(k,l)=>({n:k,l:`${l} (${base()})`,t:'number',v:''});
ask(`Facture du dossier ${DS.d.num}`,[n('tr','Honoraires de transit'),n('dd','Dédouanement'),n('tp','Transport'),n('ma','Manutention'),n('mg','Magasinage'),n('dv','Frais divers'),
{n:'deb',l:'Refacturer les droits et taxes avancés (débours)',o:[['non','Non'],['oui','Oui']]}],async f=>{const L={tr:'Honoraires de transit',dd:'Dédouanement',tp:'Transport',ma:'Manutention',mg:'Magasinage',dv:'Frais divers'};
const lignes=Object.entries(L).filter(([k])=>+f[k]>0).map(([k,l])=>({libelle:l,montant:+f[k]}));
try{await api(dsUrl('/facture'),{method:'POST',json:{lignes,refacturer_debours:f.deb==='oui'}});await dsRefresh()}catch(e){fail('Facture non générée',e)}})}
const dsAvance=()=>ask('Avance reçue du client',[{n:'montant',l:'Montant (devise du client)',t:'number',r:1},{n:'mode',l:'Mode',o:MODES},{n:'reference',l:'Référence'},{n:'date',l:'Date',t:'date',v:today()}],
async f=>{try{await api(dsUrl('/avances'),{method:'POST',json:{...f,montant:+f.montant,date:f.date||null}});dsTabLoad()}catch(e){fail('Avance refusée',e)}});
const dsCout=()=>ask('Nouveau coût',[{n:'categorie',l:'Catégorie',o:COUT_CAT},{n:'libelle',l:'Libellé',r:1},{n:'fournisseur',l:'Fournisseur'},{n:'montant',l:'Montant',t:'number',r:1},
{n:'devise',l:'Devise',o:Object.keys(DS.P?.rates||{GNF:1}),v:base()},{n:'date',l:'Date',t:'date',v:today()}],async f=>{try{await api(dsUrl('/couts'),{method:'POST',json:{...f,montant:+f.montant,date:f.date||null}});dsTabLoad()}catch(e){fail('Coût non enregistré',e)}});
const dsCoutDel=async id=>{if(!confirm('Supprimer ce coût ?'))return;try{await api(dsUrl('/couts/'+id),{method:'DELETE'});dsTabLoad()}catch(e){fail('Suppression impossible',e)}};

/* Journal */
async function dsJournal(){const J=await api(dsUrl('/journal'));
dsPaint(`<div class="card tbl"><table><tr><th>Date</th><th>Utilisateur</th><th>Objet</th><th>Action</th><th>Détail</th></tr>${J.map(j=>`<tr><td>${hfr(j.ts)}</td><td>${esc(j.utilisateur)}</td><td>${esc(j.entite)}</td><td>${esc(j.action)}</td><td>${esc(j.detail)}</td></tr>`).join('')||'<tr><td colspan="5" class="mut">Journal vide.</td></tr>'}</table></div>`)}
