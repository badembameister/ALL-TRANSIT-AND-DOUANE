/* Module « Clients et partenaires » branché sur l'API : clients, fournisseurs, transporteurs, agents étrangers,
   destinataires et administrations ; fiche, contacts, documents d'agrément, historique et situation financière. */
const CP={ty:'',q:'',actifs:true,L:[],sel:null,F:null,P:null};
const PTYPES=['Client','Fournisseur','Transporteur','Agent étranger','Destinataire','Administration'];
const PT_PLUR={'':'Tous','Client':'Clients','Fournisseur':'Fournisseurs','Transporteur':'Transporteurs','Agent étranger':'Agents étrangers','Destinataire':'Destinataires','Administration':'Administrations'};
const canC=()=>W.client.includes(role),canPiece=()=>[...W.client,'Comptable'].includes(role);
const actifB=a=>`<span class="b ${a?'ok':''}">${a?'Actif':'Inactif'}</span>`;

function vClientsApi(){return`<div id="cpv"><h1>Clients et partenaires</h1><p class="mut">Chargement…</p></div>`}

async function loadClients(){try{const p=new URLSearchParams();if(CP.ty)p.set('type',CP.ty);if(CP.q)p.set('q',CP.q);if(CP.actifs)p.set('actifs','true');
[CP.L,CP.P]=await Promise.all([api('/clients?'+p),CP.P?CP.P:api('/params').catch(()=>null)])}catch(e){$('#cpv').innerHTML=`<h1>Clients et partenaires</h1><p class="note">${esc(e.message)}</p>`;return}
if(CP.sel)return cpLoad();paintClients()}

function paintClients(){if(view!=='clients'||sel||!$('#cpv'))return;$('#cpv').innerHTML=CP.sel&&CP.F?cpFiche():cpList()}

/* ---------- Liste ---------- */
function cpList(){return`<h1>Clients et partenaires</h1><div class="tabs">${Object.entries(PT_PLUR).map(([k,l])=>`<button class="${k===CP.ty?'on':''}" onclick="CP.ty='${k}';loadClients()">${l}</button>`).join('')}</div>
<div class="bar"><input id="cpq" placeholder="Nom, code, NIF, RCCM, ville, n° de dossier, conteneur, réf. douane" value="${esc(CP.q)}" size="44" onkeydown="if(event.key==='Enter'){CP.q=this.value;loadClients()}">
<button class="ghost" onclick="CP.q=$('#cpq').value;loadClients()">Rechercher</button><label class="mut"><input type="checkbox" ${CP.actifs?'checked':''} onchange="CP.actifs=this.checked;loadClients()"> Actifs seulement</label>
${canC()?'<button class="pri" onclick="cpForm()">Nouveau partenaire</button>':''}</div>
<div class="card tbl"><table><tr><th>Code</th><th>Raison sociale</th><th>Type</th><th>NIF / RCCM</th><th>Contact</th><th>Conditions</th><th>Statut</th></tr>
${CP.L.map(c=>`<tr><td class="mono">${esc(c.code)}</td><td><button class="lk" onclick="cpOpen(${c.id})">${esc(c.nom)}</button>${c.ville?`<br><span class="mut">${esc(c.ville)}${c.pays&&c.pays!=='Guinée'?', '+esc(c.pays):''}</span>`:''}</td>
<td>${esc(c.type)}</td><td>${esc(c.nif||'—')}${c.rc?`<br><span class="mut">${esc(c.rc)}</span>`:''}</td><td>${c.telephone?`<a href="tel:${esc(c.telephone.replace(/\s/g,''))}">${esc(c.telephone)}</a>`:''}${c.email?`<br><a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`:''}${!c.telephone&&!c.email?'—':''}</td>
<td>${c.type==='Client'?`${esc(c.devise)}, ${c.delai_paiement} j`:'—'}</td><td>${actifB(c.actif)}</td></tr>`).join('')||`<tr><td colspan="7" class="mut">${CP.q?'Aucun partenaire pour cette recherche.':'Aucun partenaire enregistré.'}</td></tr>`}</table></div>`}

/* ---------- Création / modification ---------- */
function cpForm(id){const c=id?CP.F.client:{type:CP.ty||'Client',devise:'GNF',delai_paiement:30,pays:'Guinée',actif:true,plafond_credit:0},v=x=>x==null?'':x;
ask(id?`Modifier ${c.code}`:'Nouveau partenaire',[{n:'type',l:'Type',o:PTYPES,v:c.type},{n:'nom',l:'Raison sociale',v:v(c.nom),r:1},{n:'nif',l:'NIF',v:v(c.nif)},{n:'rc',l:'RCCM',v:v(c.rc)},
{n:'adresse',l:'Adresse',v:v(c.adresse)},{n:'ville',l:'Ville',v:v(c.ville)},{n:'pays',l:'Pays',v:v(c.pays)},{n:'telephone',l:'Téléphone',t:'tel',v:v(c.telephone)},{n:'email',l:'E-mail',t:'email',v:v(c.email)},
...(id?[]:[{n:'contact',l:'Contact principal (nom)'}]),{n:'devise',l:'Devise de facturation',o:Object.keys(CP.P?.rates||{GNF:1,USD:1,EUR:1}),v:c.devise},{n:'delai_paiement',l:'Délai de paiement (jours)',t:'number',v:c.delai_paiement},
{n:'plafond_credit',l:`Plafond de crédit (${CP.P?.base||'GNF'}, 0 = aucun)`,t:'number',v:+c.plafond_credit||0},{n:'banque',l:'Banque',v:v(c.banque)},{n:'compte_bancaire',l:'Compte bancaire (RIB / IBAN)',v:v(c.compte_bancaire)},
{n:'notes',l:'Notes',v:v(c.notes)},{n:'actif',l:'Statut',o:[['true','Actif'],['false','Inactif']],v:String(c.actif!==false)}],async f=>{
const body={...f,delai_paiement:+f.delai_paiement||0,plafond_credit:+f.plafond_credit||0,actif:f.actif==='true'};if(id)body.contact=c.contact||'';
try{const n=await api(id?'/clients/'+id:'/clients',{method:id?'PUT':'POST',json:body});CP.sel=n.id;await loadClients()}catch(e){fail('Partenaire non enregistré',e)}})}

/* ---------- Fiche ---------- */
const cpOpen=id=>{CP.sel=id;cpLoad()};
async function cpLoad(){try{CP.F=await api(`/clients/${CP.sel}/fiche`)}catch(e){fail('Fiche indisponible',e);CP.sel=null;return paintClients()}paintClients();scrollTo(0,0)}
const cpUrl=p=>`/clients/${CP.sel}${p||''}`;

function cpFiche(){const F=CP.F,c=F.client,s=F.stats,b=F.devise_base,w=canC(),g=(l,v)=>`<div><span>${l}</span>${v||'—'}</div>`,isCli=c.type==='Client';
return`<div class="bar"><button class="ghost" onclick="CP.sel=null;CP.F=null;loadClients()">Retour</button>${w?`<button class="ghost" onclick="cpForm(${c.id})">Modifier</button>`:''}</div>
<h1>${esc(c.nom)} ${actifB(c.actif)}</h1><p class="mut"><span class="mono">${esc(c.code)}</span> · ${esc(c.type)}${c.created_at?` · créé le ${dfr(c.created_at)}`:''}</p>
${F.alertes.length?`<div class="card"><h3>Alertes</h3>${F.alertes.map(a=>`<div class="al"><span class="b ba">À traiter</span> ${esc(a)}</div>`).join('')}</div>`:''}
<div class="kp"><div><b>${s.dossiers}</b><span>Dossiers${s.dossiers_ouverts?` (${s.dossiers_ouverts} ouverts)`:''}</span></div>
${isCli?`<div><b>${nf(s.ca_12_mois)}</b><span>Facturé sur 12 mois (${b})</span></div><div class="${c.plafond_credit&&s.encours>c.plafond_credit?'w':''}"><b>${nf(s.encours)}</b><span>Encours${+c.plafond_credit?` / plafond ${nf(c.plafond_credit)}`:''}</span></div>
<div class="${s.factures_en_retard?'w':''}"><b>${s.factures_en_retard}</b><span>Factures en retard${s.montant_retard?` (${nf(s.montant_retard)})`:''}</span></div>`:''}
${c.type==='Transporteur'?`<div><b>${s.vehicules}</b><span>Véhicules dans le parc</span></div>`:''}</div>
<div class="card"><h3>Identité</h3><div class="g">${g('NIF',esc(c.nif))}${g('RCCM',esc(c.rc))}${g('Adresse',esc(c.adresse))}${g('Ville',esc(c.ville))}${g('Pays',esc(c.pays))}
${g('Téléphone',c.telephone?`<a href="tel:${esc(c.telephone.replace(/\s/g,''))}">${esc(c.telephone)}</a>`:'')}${g('E-mail',c.email?`<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`:'')}</div>
<h3 style="margin-top:16px">Conditions et banque</h3><div class="g">${g('Devise de facturation',esc(c.devise))}${g('Délai de paiement',c.delai_paiement+' jours')}${g('Plafond de crédit',+c.plafond_credit?`${nf(c.plafond_credit)} ${b}`:'Aucun')}
${g('Banque',esc(c.banque))}${g('Compte',`<span class="mono">${esc(c.compte_bancaire)}</span>`)}</div>${c.notes?`<p class="note">${esc(c.notes)}</p>`:''}</div>
<div class="card tbl"><div class="bar"><h3 style="margin:0">Contacts</h3>${w?'<button class="pri sm" onclick="cpContact()">Ajouter</button>':''}</div><table><tr><th>Nom</th><th>Fonction</th><th>Téléphone</th><th>E-mail</th><th></th></tr>
${F.contacts.map(x=>`<tr><td>${esc(x.nom)} ${x.principal?'<span class="b ok">Principal</span>':''}</td><td>${esc(x.fonction||'—')}</td><td>${x.telephone?`<a href="tel:${esc(x.telephone.replace(/\s/g,''))}">${esc(x.telephone)}</a>`:'—'}</td>
<td>${x.email?`<a href="mailto:${esc(x.email)}">${esc(x.email)}</a>`:'—'}</td><td class="act">${w?`<button class="ghost sm" onclick="cpContact(${x.id})">Modifier</button> <button class="dg sm" onclick="cpContactDel(${x.id})">Supprimer</button>`:''}</td></tr>`).join('')||'<tr><td colspan="5" class="mut">Aucun contact.</td></tr>'}</table></div>
<div class="card tbl"><h3>Documents (agrément, carte de commerçant, attestations, contrats)</h3>
${canPiece()?`<form id="cpup" class="bar" onsubmit="return cpUpload(event)"><select name="type">${F.types_pieces.map(t=>`<option>${esc(t)}</option>`).join('')}</select><label class="mut">Expire le <input type="date" name="expiration"></label>
<input type="file" name="fichier" required accept=".pdf,.png,.jpg,.jpeg,.xlsx,.docx"><button class="pri">Déposer</button></form>`:''}
<table><tr><th>Type</th><th>Fichier</th><th>Expiration</th><th>Déposé</th><th></th></tr>${F.pieces.map(p=>`<tr><td>${esc(p.type)}</td><td>${esc(p.nom_fichier)}</td>
<td>${p.expiration?(p.expire?`<span class="b ba">Expiré le ${dfr(p.expiration)}</span>`:p.expiration<=addDays(today(),30)?`<span class="b wa">${dfr(p.expiration)}</span>`:dfr(p.expiration)):'—'}</td>
<td>${dfr(p.created_at)}<br><span class="mut">${esc(p.depose_par)}</span></td><td class="act"><button class="ghost sm" onclick="cpDl(${p.id},${jsq(p.nom_fichier)})">Télécharger</button>${w?` <button class="dg sm" onclick="cpPieceDel(${p.id})">Supprimer</button>`:''}</td></tr>`).join('')||'<tr><td colspan="5" class="mut">Aucun document.</td></tr>'}</table></div>
<div class="card tbl"><h3>Historique des opérations</h3>${!isCli?`<p class="mut">Dossiers où ce partenaire figure comme fournisseur, destinataire, transporteur ou agent en douane (même raison sociale).</p>`:''}
<table><tr><th>Dossier</th><th>Type</th><th>Marchandises</th><th>Ouvert le</th>${isCli?'<th>Facture</th>':''}<th>Statut</th></tr>${F.dossiers.map(d=>`<tr><td><button class="lk" onclick="cpDossier(${d.id})">${esc(d.num)}</button></td><td>${esc(d.type)}</td><td>${esc(d.designation)}</td><td>${dfr(d.created_at)}</td>
${isCli?`<td>${d.facture_statut?badge(d.facture_statut):'—'}</td>`:''}<td>${badge(d.statut)}</td></tr>`).join('')||'<tr><td colspan="6" class="mut">Aucune opération.</td></tr>'}</table></div>`}

const cpContact=xid=>{const x=xid?CP.F.contacts.find(y=>y.id===xid):{principal:!CP.F.contacts.length};
ask(xid?'Modifier le contact':'Nouveau contact',[{n:'nom',l:'Nom',v:x.nom||'',r:1},{n:'fonction',l:'Fonction',v:x.fonction||''},{n:'telephone',l:'Téléphone',t:'tel',v:x.telephone||''},{n:'email',l:'E-mail',t:'email',v:x.email||''},
{n:'principal',l:'Contact principal',o:[['false','Non'],['true','Oui']],v:String(!!x.principal)}],async f=>{try{await api(cpUrl('/contacts'+(xid?'/'+xid:'')),{method:xid?'PUT':'POST',json:{...f,principal:f.principal==='true'}});cpLoad()}catch(e){fail('Contact non enregistré',e)}})};
const cpContactDel=async xid=>{if(!confirm('Supprimer ce contact ?'))return;try{await api(cpUrl('/contacts/'+xid),{method:'DELETE'});cpLoad()}catch(e){fail('Suppression impossible',e)}};
async function cpUpload(e){e.preventDefault();const f=new FormData(e.target),b=e.target.querySelector('button');b.disabled=true;try{await api(cpUrl('/pieces'),{method:'POST',body:f});cpLoad()}catch(err){fail('Dépôt refusé',err);b.disabled=false}return false}
const cpPieceDel=async pid=>{if(!confirm('Supprimer ce document ?'))return;try{await api(cpUrl('/pieces/'+pid),{method:'DELETE'});cpLoad()}catch(e){fail('Suppression impossible',e)}};
async function cpDl(pid,nom){try{const r=await fetch('/api'+cpUrl('/pieces/'+pid),{headers:{Authorization:'Bearer '+getTok()}});if(!r.ok)throw new Error('Téléchargement impossible ('+r.status+')');
const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=nom;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}catch(e){fail('Téléchargement',e)}}
async function cpDossier(did){go('dossiers');DS.sel=did;DS.tab='res';await dsLoad()}
