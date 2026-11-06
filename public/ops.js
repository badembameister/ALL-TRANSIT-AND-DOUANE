/* Module « Opérations » : transport et suivi opérationnel (missions, conteneurs, parc).
   Branché sur l'API (/api/missions, /api/conteneurs, /api/vehicules, /api/chauffeurs, /api/operations/resume). */
const OPS={tab:'plan',q:'',st:'',du:'',au:'',M:[],K:[],V:[],C:[],D:[],R:null};
const MTYPES=['Enlèvement','Livraison','Transfert','Retour vide'],MSTAT=['Planifiée','En cours','Livrée','Annulée'];
const KTYPES=['20','40','40HC','45HC','20RF','40RF','Autre'],VTYPES=['Camion','Tracteur','Remorque','Semi-remorque','Fourgon'];
const INC=['Retard','Panne','Accident','Contrôle routier','Marchandise endommagée','Refus de livraison','Autre'];
const canOps=()=>W.ops.includes(role);
const dfr=s=>s?String(s).slice(0,10).split('-').reverse().join('/'):'—';
const hfr=s=>s?new Date(s.endsWith('Z')?s:s+'Z').toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short'}):'—';
const mBadge=m=>`<span class="b ${{Planifiée:'in','En cours':'wa',Livrée:'ok',Annulée:''}[m.statut]}">${esc(m.statut)}</span>`+(m.en_retard?' '+badge('En retard'):'');
const kBadge=k=>`<span class="b ${{Attendu:'in','Au port':'wa',Sorti:'in',Restitué:'ok'}[k.statut]}">${esc(k.statut)}</span>`;
const fail=(t,e)=>info(t,`<p>${esc(e.message)}</p>`);

function vOps(){const T=[['plan','Planning des missions'],['cont','Conteneurs'],['parc','Véhicules et chauffeurs']];
return`<h1>Opérations</h1><div id="okp"></div><div class="tabs">${T.map(t=>`<button class="${t[0]===OPS.tab?'on':''}" onclick="OPS.tab='${t[0]}';render()">${t[1]}</button>`).join('')}</div><div id="ops"><p class="mut">Chargement…</p></div>`}

async function loadOps(){try{const p=new URLSearchParams();if(OPS.du)p.set('du',OPS.du);if(OPS.au)p.set('au',OPS.au);if(OPS.st)p.set('statut',OPS.st);
[OPS.R,OPS.M,OPS.K,OPS.V,OPS.C,OPS.D]=await Promise.all([api('/operations/resume'),api('/missions?'+p),api('/conteneurs'),api('/vehicules'),api('/chauffeurs'),api('/dossiers').catch(()=>[])])}
catch(e){$('#ops').innerHTML=`<p class="note">${esc(e.message)}</p>`;return}paintOps()}

function paintOps(){if(view!=='ops'||sel||!$('#ops'))return;const R=OPS.R;
$('#okp').innerHTML=`<div class="kp"><div><b>${R.missions_du_jour}</b><span>Missions du jour</span></div><div><b>${R.missions_en_cours}</b><span>En cours</span></div><div class="${R.missions_en_retard?'w':''}"><b>${R.missions_en_retard}</b><span>Missions en retard</span></div><div><b>${R.conteneurs_au_port}</b><span>Conteneurs au port</span></div><div class="${R.conteneurs_a_restituer?'w':''}"><b>${R.conteneurs_a_restituer}</b><span>Vides à restituer</span></div><div><b>${R.vehicules_disponibles}/${R.vehicules_actifs}</b><span>Véhicules disponibles</span></div></div>
${R.alertes.length?`<div class="card"><h3>Alertes opérationnelles</h3>${R.alertes.map(a=>`<div class="al"><span class="b ${a.niveau}">${a.niveau==='ba'?'Urgent':'À suivre'}</span> ${esc(a.texte)}</div>`).join('')}</div>`:''}`;
$('#ops').innerHTML=({plan:opsPlan,cont:opsCont,parc:opsParc})[OPS.tab]()}

/* ---------- Planning ---------- */
const mRows=()=>{const q=OPS.q.toLowerCase();return OPS.M.filter(m=>(m.num+m.origine+m.destination+m.dossier_num+m.conteneur_num+m.vehicule_immat+m.chauffeur_nom).toLowerCase().includes(q)).map(m=>{const w=canOps(),a=[];
if(w&&m.statut==='Planifiée')a.push(`<button class="pri sm" onclick="mStart(${m.id})">Démarrer</button>`,`<button class="ghost sm" onclick="mForm(${m.id})">Modifier</button>`);
if(w&&m.statut==='En cours')a.push(`<button class="pri sm" onclick="mDeliver(${m.id})">Livrer</button>`,`<button class="ghost sm" onclick="mPos(${m.id})">Position</button>`);
if(w&&['Planifiée','En cours'].includes(m.statut))a.push(`<button class="ghost sm" onclick="mInc(${m.id})">Incident</button>`,`<button class="dg sm" onclick="mCancel(${m.id})">Annuler</button>`);
return`<tr><td><button class="lk" onclick="mView(${m.id})">${esc(m.num)}</button></td><td>${dfr(m.date_prevue)}</td><td>${esc(m.type)}</td><td>${esc(m.origine)} → ${esc(m.destination)}</td><td>${esc(m.dossier_num||'—')}${m.conteneur_num?`<br><span class="mut mono">${esc(m.conteneur_num)}</span>`:''}</td><td>${esc(m.vehicule_immat||'—')}<br><span class="mut">${esc(m.chauffeur_nom||'Non affecté')}</span></td><td>${mBadge(m)}${m.incidents.length?` <span class="mut">${m.incidents.length} incident(s)</span>`:''}</td><td class="act">${a.join(' ')}</td></tr>`}).join('')||'<tr><td colspan="8" class="mut">Aucune mission pour ces critères.</td></tr>'};

function opsPlan(){return`<div class="bar"><input placeholder="Rechercher : n°, lieu, dossier, conteneur, véhicule" value="${esc(OPS.q)}" oninput="OPS.q=this.value;$('#ml').innerHTML=mRows()" size="34">
<label class="mut">Du <input type="date" value="${OPS.du}" onchange="OPS.du=this.value;loadOps()"></label><label class="mut">au <input type="date" value="${OPS.au}" onchange="OPS.au=this.value;loadOps()"></label>
<select onchange="OPS.st=this.value;loadOps()"><option value="">Tous les statuts</option>${MSTAT.map(s=>`<option ${s===OPS.st?'selected':''}>${s}</option>`).join('')}</select>
<button class="ghost" onclick="OPS.du=OPS.au=today();loadOps()">Aujourd’hui</button>${canOps()?'<button class="pri" onclick="mForm()">Nouvelle mission</button>':''}</div>
<div class="card tbl"><table><tr><th>Mission</th><th>Date</th><th>Type</th><th>Trajet</th><th>Dossier / conteneur</th><th>Véhicule / chauffeur</th><th>Statut</th><th></th></tr><tbody id="ml">${mRows()}</tbody></table></div>`}

const opt=(L,f,none)=>[...(none?[['',none]]:[]),...L.map(x=>[String(x.id),f(x)])];
function mForm(id){const m=id?OPS.M.find(x=>x.id===id):{type:'Livraison',date_prevue:today()},s=v=>v==null?'':String(v);
ask(id?`Modifier ${m.num}`:'Nouvelle mission',[{n:'type',l:'Type de mission',o:MTYPES,v:m.type},{n:'date_prevue',l:'Date prévue',t:'date',v:m.date_prevue,r:1},
{n:'origine',l:'Lieu d’enlèvement',v:m.origine||'',r:1},{n:'destination',l:'Lieu de livraison',v:m.destination||'',r:1},
{n:'dossier_id',l:'Dossier',o:opt(OPS.D,d=>d.num+' · '+d.designation.slice(0,30),'Aucun'),v:s(m.dossier_id)},
{n:'conteneur_id',l:'Conteneur',o:opt(OPS.K.filter(k=>k.statut!=='Restitué'||k.id===m.conteneur_id),k=>k.numero+' · '+k.statut,'Aucun'),v:s(m.conteneur_id)},
{n:'vehicule_id',l:'Véhicule',o:opt(OPS.V.filter(v=>v.actif||v.id===m.vehicule_id),v=>v.immatriculation+' · '+v.type,'Non affecté'),v:s(m.vehicule_id)},
{n:'chauffeur_id',l:'Chauffeur',o:opt(OPS.C.filter(c=>c.actif||c.id===m.chauffeur_id),c=>c.nom,'Non affecté'),v:s(m.chauffeur_id)},
{n:'instructions',l:'Instructions au chauffeur',v:m.instructions||''}],async f=>{
const body={...f};['dossier_id','conteneur_id','vehicule_id','chauffeur_id'].forEach(k=>body[k]=f[k]?+f[k]:null);
try{await api(id?'/missions/'+id:'/missions',{method:id?'PUT':'POST',json:body});loadOps()}catch(e){fail('Mission non enregistrée',e)}})}

async function mStart(id){try{await api(`/missions/${id}/statut`,{method:'POST',json:{to:'En cours'}});loadOps()}catch(e){fail('Démarrage impossible',e)}}
const mCancel=id=>ask('Annuler la mission',[{n:'motif',l:'Motif de l’annulation',r:1}],async f=>{try{await api(`/missions/${id}/statut`,{method:'POST',json:{to:'Annulée',motif:f.motif}});loadOps()}catch(e){fail('Annulation impossible',e)}});
const mInc=id=>ask('Incident de mission',[{n:'type',l:'Type',o:INC},{n:'note',l:'Détail'}],async f=>{try{await api(`/missions/${id}/incidents`,{method:'POST',json:f});loadOps()}catch(e){fail('Incident non enregistré',e)}});
function mPos(id){const send=async(lat,lng)=>{try{await api(`/missions/${id}/position`,{method:'POST',json:{lat:+lat,lng:+lng}});loadOps()}catch(e){fail('Position refusée',e)}};
const manual=()=>ask('Position du véhicule',[{n:'lat',l:'Latitude',t:'number',r:1},{n:'lng',l:'Longitude',t:'number',r:1}],f=>send(f.lat,f.lng));
if(navigator.geolocation)navigator.geolocation.getCurrentPosition(p=>send(p.coords.latitude,p.coords.longitude),manual,{timeout:8000});else manual()}

async function mView(id){const m=OPS.M.find(x=>x.id===id);let sig='';
if(m.signee){try{const r=await fetch(`/api/missions/${id}/signature`,{headers:{Authorization:'Bearer '+getTok()}});if(r.ok)sig=URL.createObjectURL(await r.blob())}catch(e){}}
const pos=m.position?`<a href="https://www.openstreetmap.org/?mlat=${m.position.lat}&mlon=${m.position.lng}#map=13/${m.position.lat}/${m.position.lng}" target="_blank" rel="noopener">${m.position.lat.toFixed(5)}, ${m.position.lng.toFixed(5)}</a> <span class="mut">(${hfr(m.position.ts)})</span>`:'—';
info(`${esc(m.num)} ${mBadge(m)}`,`<div class="g"><div><span>Type</span>${esc(m.type)}</div><div><span>Date prévue</span>${dfr(m.date_prevue)}</div><div><span>Départ</span>${esc(m.origine)}</div><div><span>Arrivée</span>${esc(m.destination)}</div>
<div><span>Dossier</span>${esc(m.dossier_num||'—')}</div><div><span>Conteneur</span>${esc(m.conteneur_num||'—')}</div><div><span>Véhicule</span>${esc(m.vehicule_immat||'—')}</div><div><span>Chauffeur</span>${esc(m.chauffeur_nom||'—')}</div>
<div><span>Démarrée</span>${hfr(m.debut)}</div><div><span>Livrée</span>${hfr(m.fin)}</div><div><span>Dernière position</span>${pos}</div></div>
${m.instructions?`<p class="note">${esc(m.instructions)}</p>`:''}
${m.statut==='Livrée'?`<h3 style="margin-top:16px">Preuve de livraison</h3><p>Reçu par <b>${esc(m.receptionnaire)}</b>${m.note_livraison?` : ${esc(m.note_livraison)}`:''}</p>${sig?`<img src="${sig}" alt="Signature du réceptionnaire" class="sigimg">`:'<p class="mut">Pas de signature.</p>'}`:''}
<h3 style="margin-top:16px">Incidents</h3>${m.incidents.map(x=>`<div class="al">${badge(x.type)} ${dfr(x.date)} ${esc(x.note)}</div>`).join('')||'<p class="mut">Aucun incident.</p>'}`)}

/* Livraison : réceptionnaire, signature tactile, photo facultative rangée dans les documents du dossier */
function mDeliver(id){const m=OPS.M.find(x=>x.id===id);
dlg.innerHTML=`<form id="lv"><h3>Livraison ${esc(m.num)}</h3><label>Reçu par<input name="receptionnaire" required minlength="2"></label><label>Observations<input name="note"></label>
<div style="grid-column:1/-1"><span class="mut lbl">Signature du réceptionnaire</span><canvas id="sig" width="560" height="170" class="sig"></canvas><button type="button" class="ghost sm" id="sigc">Effacer</button></div>
${m.dossier_id?`<label style="grid-column:1/-1">Photo de déchargement (facultatif)<input type="file" name="photo" accept="image/*" capture="environment"></label>`:''}
<p id="lverr" class="lerr" style="grid-column:1/-1"></p><div class="row"><button type="button" class="ghost" onclick="dlg.close()">Annuler</button><button class="pri">Confirmer la livraison</button></div></form>`;
const cv=$('#sig'),cx=cv.getContext('2d');let drawing=false,inked=false;cx.lineWidth=2.4;cx.lineCap='round';cx.strokeStyle='#0E1F36';
const pt=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left)*cv.width/r.width,(e.clientY-r.top)*cv.height/r.height]};
cv.onpointerdown=e=>{drawing=true;cv.setPointerCapture(e.pointerId);cx.beginPath();cx.moveTo(...pt(e))};
cv.onpointermove=e=>{if(!drawing)return;cx.lineTo(...pt(e));cx.stroke();inked=true};cv.onpointerup=cv.onpointercancel=()=>drawing=false;
$('#sigc').onclick=()=>{cx.clearRect(0,0,cv.width,cv.height);inked=false};
$('#lv').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),b=e.target.querySelector('button.pri');b.disabled=true;
try{const photo=f.get('photo');if(photo&&photo.size){const fd=new FormData();fd.append('type','pod');fd.append('fichier',photo);await api(`/dossiers/${m.dossier_id}/documents`,{method:'POST',body:fd})}
await api(`/missions/${id}/livrer`,{method:'POST',json:{receptionnaire:f.get('receptionnaire'),note:f.get('note')||'',signature:inked?cv.toDataURL('image/png'):''}});dlg.close();loadOps()}
catch(err){$('#lverr').textContent=err.message;b.disabled=false}};dlg.showModal()}

/* ---------- Conteneurs ---------- */
function opsCont(){const L=OPS.K.filter(k=>(k.numero+k.bl+k.compagnie+k.dossier_num).toLowerCase().includes(OPS.q.toLowerCase()));
return`<div class="bar"><input placeholder="Rechercher : n° conteneur, BL, compagnie, dossier" value="${esc(OPS.q)}" onchange="OPS.q=this.value;paintOps()" size="34">${canOps()?'<button class="pri" onclick="kForm()">Nouveau conteneur</button>':''}</div>
<div class="card tbl"><table><tr><th>Conteneur</th><th>Dossier</th><th>Compagnie / navire</th><th>ETA</th><th>Arrivée</th><th>Sortie</th><th>Retour vide</th><th>Statut</th><th>Magasinage</th><th>Détention</th><th></th></tr>
${L.map(k=>`<tr><td class="mono">${esc(k.numero)}<br><span class="mut">${esc(k.type)}</span></td><td>${esc(k.dossier_num||'—')}</td><td>${esc(k.compagnie||'—')}<br><span class="mut">${esc(k.navire)}</span></td><td>${dfr(k.eta)}</td><td>${dfr(k.arrivee)}</td><td>${dfr(k.sortie)}</td><td>${dfr(k.retour)}</td><td>${kBadge(k)}</td>
<td>${k.jours_magasinage?`<span class="b wa">${k.jours_magasinage} j</span>`:'<span class="mut">0 j</span>'}</td><td>${k.jours_detention?`<span class="b ba">${k.jours_detention} j</span>`:'<span class="mut">0 j</span>'}</td>
<td>${canOps()?`<button class="ghost sm" onclick="kForm(${k.id})">Modifier</button>`:''}</td></tr>`).join('')||'<tr><td colspan="11" class="mut">Aucun conteneur enregistré.</td></tr>'}</table></div>
<p class="mut">Magasinage : jours au port au-delà de la franchise. Détention : jours sans restitution du vide au-delà de la franchise de retour. La sortie est enregistrée au démarrage d’une mission d’enlèvement, le retour à la livraison d’une mission « Retour vide ».</p>`}

function kForm(id){const k=id?OPS.K.find(x=>x.id===id):{type:'40HC',franchise_port:10,franchise_retour:14};
ask(id?`Conteneur ${k.numero}`:'Nouveau conteneur',[{n:'numero',l:'Numéro (ISO 6346)',v:k.numero||'',r:1},{n:'type',l:'Type',o:KTYPES,v:k.type},
{n:'dossier_id',l:'Dossier',o:opt(OPS.D,d=>d.num,'Aucun'),v:k.dossier_id?String(k.dossier_id):''},{n:'compagnie',l:'Compagnie maritime',v:k.compagnie||''},{n:'navire',l:'Navire / voyage',v:k.navire||''},
{n:'bl',l:'N° de BL',v:k.bl||''},{n:'plomb',l:'N° de plomb',v:k.plomb||''},{n:'eta',l:'Arrivée prévue (ETA)',t:'date',v:k.eta||''},{n:'arrivee',l:'Débarqué le',t:'date',v:k.arrivee||''},
{n:'sortie',l:'Sorti du port le',t:'date',v:k.sortie||''},{n:'retour',l:'Vide restitué le',t:'date',v:k.retour||''},
{n:'franchise_port',l:'Franchise port (jours)',t:'number',v:k.franchise_port},{n:'franchise_retour',l:'Franchise retour (jours)',t:'number',v:k.franchise_retour}],async f=>{
const body={...f,dossier_id:f.dossier_id?+f.dossier_id:null,franchise_port:+f.franchise_port||0,franchise_retour:+f.franchise_retour||0};['eta','arrivee','sortie','retour'].forEach(x=>body[x]=f[x]||null);
try{await api(id?'/conteneurs/'+id:'/conteneurs',{method:id?'PUT':'POST',json:body});loadOps()}catch(e){fail('Conteneur non enregistré',e)}})}

/* ---------- Parc ---------- */
const soon=d=>{if(!d)return'<span class="mut">—</span>';const x=d<today()?'ba':d<=addDays(today(),30)?'wa':'';return x?`<span class="b ${x}">${dfr(d)}</span>`:dfr(d)};
const actif=a=>`<span class="b ${a?'ok':'ba'}">${a?'Actif':'Inactif'}</span>`;
function opsParc(){const w=canOps();return`<div class="card tbl"><div class="bar"><h3 style="margin:0">Véhicules</h3>${w?'<button class="pri" onclick="vForm()">Nouveau véhicule</button>':''}</div><table><tr><th>Immatriculation</th><th>Type</th><th>Capacité</th><th>Transporteur</th><th>Assurance</th><th>Visite technique</th><th>Statut</th><th></th></tr>
${OPS.V.map(v=>`<tr><td class="mono">${esc(v.immatriculation)}</td><td>${esc(v.type)}${v.marque?`<br><span class="mut">${esc(v.marque)}</span>`:''}</td><td>${+v.capacite_t?(+v.capacite_t)+' t':'—'}</td><td>${esc(v.transporteur||'Parc propre')}</td><td>${soon(v.assurance_expire)}</td><td>${soon(v.visite_expire)}</td><td>${actif(v.actif)}</td><td>${w?`<button class="ghost sm" onclick="vForm(${v.id})">Modifier</button>`:''}</td></tr>`).join('')||'<tr><td colspan="8" class="mut">Aucun véhicule.</td></tr>'}</table></div>
<div class="card tbl"><div class="bar"><h3 style="margin:0">Chauffeurs</h3>${w?'<button class="pri" onclick="cForm()">Nouveau chauffeur</button>':''}</div><table><tr><th>Nom</th><th>Téléphone</th><th>Permis</th><th>Expiration</th><th>Transporteur</th><th>Statut</th><th></th></tr>
${OPS.C.map(c=>`<tr><td>${esc(c.nom)}</td><td>${c.telephone?`<a href="tel:${esc(c.telephone.replace(/\s/g,''))}">${esc(c.telephone)}</a>`:'—'}</td><td>${esc(c.permis||'—')}</td><td>${soon(c.permis_expire)}</td><td>${esc(c.transporteur||'Interne')}</td><td>${actif(c.actif)}</td><td>${w?`<button class="ghost sm" onclick="cForm(${c.id})">Modifier</button>`:''}</td></tr>`).join('')||'<tr><td colspan="7" class="mut">Aucun chauffeur.</td></tr>'}</table></div>`}

function vForm(id){const v=id?OPS.V.find(x=>x.id===id):{type:'Camion',actif:true};
ask(id?`Véhicule ${v.immatriculation}`:'Nouveau véhicule',[{n:'immatriculation',l:'Immatriculation',v:v.immatriculation||'',r:1},{n:'type',l:'Type',o:VTYPES,v:v.type},{n:'marque',l:'Marque / modèle',v:v.marque||''},
{n:'capacite_t',l:'Capacité (tonnes)',t:'number',v:v.capacite_t?+v.capacite_t:''},{n:'transporteur',l:'Transporteur (vide = parc propre)',v:v.transporteur||''},
{n:'assurance_expire',l:'Assurance valable jusqu’au',t:'date',v:v.assurance_expire||''},{n:'visite_expire',l:'Visite technique jusqu’au',t:'date',v:v.visite_expire||''},{n:'actif',l:'Statut',o:[['true','Actif'],['false','Inactif']],v:String(v.actif)}],async f=>{
const body={...f,capacite_t:+f.capacite_t||0,actif:f.actif==='true',assurance_expire:f.assurance_expire||null,visite_expire:f.visite_expire||null};
try{await api(id?'/vehicules/'+id:'/vehicules',{method:id?'PUT':'POST',json:body});loadOps()}catch(e){fail('Véhicule non enregistré',e)}})}

function cForm(id){const c=id?OPS.C.find(x=>x.id===id):{actif:true};
ask(id?`Chauffeur ${c.nom}`:'Nouveau chauffeur',[{n:'nom',l:'Nom complet',v:c.nom||'',r:1},{n:'telephone',l:'Téléphone',t:'tel',v:c.telephone||''},{n:'permis',l:'N° de permis',v:c.permis||''},
{n:'permis_expire',l:'Permis valable jusqu’au',t:'date',v:c.permis_expire||''},{n:'transporteur',l:'Transporteur (vide = interne)',v:c.transporteur||''},{n:'actif',l:'Statut',o:[['true','Actif'],['false','Inactif']],v:String(c.actif)}],async f=>{
try{await api(id?'/chauffeurs/'+id:'/chauffeurs',{method:id?'PUT':'POST',json:{...f,actif:f.actif==='true',permis_expire:f.permis_expire||null}});loadOps()}catch(e){fail('Chauffeur non enregistré',e)}})}
