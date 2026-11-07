/* Module « Facturation » branché sur l'API : factures, devis, avances, avoirs, règlements, relances,
   balance âgée, exports comptables et impression (cahier des charges, point 9). */
const FC={tab:'fact',q:'',st:'ouvertes',du:'',au:'',L:[],DV:[],RL:[],R:null,S:null};
const fcSoc=()=>{if(!FC.S)api('/societe').then(s=>FC.S=s).catch(()=>{})};
const MODES=['Virement','Chèque','Espèces','Mobile money','Carte','Compensation'];
const FST=['Impayée','Partielle','En retard','Payée','Soldée'];
const canF=()=>W.fact.includes(role),canDv=()=>W.devis.includes(role);
const mo=(v,d)=>(+v).toLocaleString('fr-FR',{minimumFractionDigits:d==='GNF'?0:2,maximumFractionDigits:d==='GNF'?0:2})+' '+d;
const dvBadge=x=>`<span class="b ${{Brouillon:'',Envoyé:'in',Accepté:'ok',Refusé:'ba',Facturé:'ok'}[x.statut]}">${esc(x.statut)}</span>`+(x.expire?' <span class="b wa">Expiré</span>':'');
const fcAfter=()=>view==='fact'&&!sel?loadFact():dsRefresh();

function vFactApi(){return`<div id="fcv"><h1>Facturation</h1><p class="mut">Chargement…</p></div>`}

async function loadFact(){try{const p=new URLSearchParams();if(FC.du)p.set('du',FC.du);if(FC.au)p.set('au',FC.au);
fcSoc();[FC.R,FC.L,FC.DV,FC.RL]=await Promise.all([api('/factures/resume'),api('/factures?'+p),api('/devis'),api('/factures-relances')])}
catch(e){$('#fcv').innerHTML=`<h1>Facturation</h1><p class="note">${esc(e.message)}</p>`;return}paintFact()}

function paintFact(){if(view!=='fact'||sel||!$('#fcv'))return;const R=FC.R,b=R.devise_base,B=R.balance_agee,mx=Math.max(1,...Object.values(B));
const T=[['fact','Factures'],['devis',`Devis (${R.devis_en_attente})`],['rel',`Relances (${FC.RL.length})`],['exp','Exports comptables']];
$('#fcv').innerHTML=`<h1>Facturation</h1><div class="kp"><div><b>${nf(R.facture_mois)}</b><span>Facturé ce mois (${b})</span></div><div><b>${nf(R.encaisse_mois)}</b><span>Encaissé ce mois (${b})</span></div>
<div><b>${nf(R.creances)}</b><span>Créances clients (${b})</span></div><div class="${R.en_retard?'w':''}"><b>${R.en_retard}</b><span>Factures en retard</span></div>
<div class="${R.a_relancer?'w':''}"><b>${R.a_relancer}</b><span>À relancer</span></div><div><b>${nf(R.devis_montant)}</b><span>Devis en attente (${b})</span></div></div>
<div class="card bars"><h3>Balance âgée des créances (${b})</h3>${[['non_echu','Non échu'],['1_30','1 à 30 jours'],['31_60','31 à 60 jours'],['61_90','61 à 90 jours'],['plus_90','Plus de 90 jours']].map(([k,l])=>`<div><span>${l}</span><i style="width:${B[k]/mx*100}%"></i><span>${nf(B[k])}</span></div>`).join('')}
${R.avances_non_imputees?`<p class="mut">Avances reçues non encore imputées : ${nf(R.avances_non_imputees)} ${b}</p>`:''}</div>
<div class="tabs">${T.map(t=>`<button class="${t[0]===FC.tab?'on':''}" onclick="FC.tab='${t[0]}';paintFact()">${t[1]}</button>`).join('')}</div><div id="fct">${({fact:fcList,devis:dvList,rel:rlList,exp:exList})[FC.tab]()}</div>`}

/* ---------- Factures ---------- */
const fcRows=()=>{const q=FC.q.toLowerCase();return FC.L.filter(f=>(FC.st==='ouvertes'?f.solde>0:!FC.st||f.statut===FC.st)&&`${f.num} ${f.client_nom} ${f.dossier_num}`.toLowerCase().includes(q)).map(f=>`<tr>
<td><button class="lk" onclick="fcView(${f.id})">${esc(f.num)}</button></td><td>${dfr(f.date_emission)}</td><td>${esc(f.client_nom)}</td><td class="mono">${esc(f.dossier_num)}</td>
<td>${mo(f.total,f.devise)}</td><td>${mo(f.solde,f.devise)}</td><td>${dfr(f.echeance)}${f.jours_retard?`<br><span class="b ba">${f.jours_retard} j de retard</span>`:''}</td><td>${badge(f.statut)}</td><td>${f.relances||''}</td></tr>`).join('')||'<tr><td colspan="9" class="mut">Aucune facture pour ces critères.</td></tr>'};
function fcList(){return`<div class="bar"><input placeholder="N° de facture, client, dossier" value="${esc(FC.q)}" oninput="FC.q=this.value;$('#fcl').innerHTML=fcRows()" size="28">
<select onchange="FC.st=this.value;$('#fcl').innerHTML=fcRows()"><option value="">Toutes</option><option value="ouvertes" ${FC.st==='ouvertes'?'selected':''}>Non soldées</option>${FST.map(s=>`<option ${s===FC.st?'selected':''}>${s}</option>`).join('')}</select>
<label class="mut">Émises du <input type="date" value="${FC.du}" onchange="FC.du=this.value;loadFact()"></label><label class="mut">au <input type="date" value="${FC.au}" onchange="FC.au=this.value;loadFact()"></label></div>
<div class="card tbl"><table><tr><th>Facture</th><th>Date</th><th>Client</th><th>Dossier</th><th>Total</th><th>Solde</th><th>Échéance</th><th>Statut</th><th>Relances</th></tr><tbody id="fcl">${fcRows()}</tbody></table></div>
<p class="mut">Une facture se génère depuis l’onglet « Facturation et marge » du dossier, ou à partir d’un devis accepté.</p>`}

async function fcView(id){let f;try{f=await api('/factures/'+id)}catch(e){return fail('Facture',e)}const w=canF(),open=f.solde>0;
info(`${esc(f.num)} ${badge(f.statut)}`,`<p class="mut">${esc(f.client_nom)}, dossier ${esc(f.dossier_num)}. Émise le ${dfr(f.date_emission)}, échéance ${dfr(f.echeance)}${f.jours_retard?`, <b>${f.jours_retard} jours de retard</b>`:''}.</p>
${fcDetail(f)}<div class="bar" style="margin-top:14px">${w&&open?`<button class="pri" type="button" onclick="fcPay(${f.id},${f.solde},'${f.devise}')">Règlement</button><button class="ghost" type="button" onclick="fcAvoir(${f.id},${f.solde},'${f.devise}')">Avoir</button><button class="ghost" type="button" onclick="fcRelance(${f.id})">Relancer</button>`:''}
<button class="ghost" type="button" onclick="fcPrint(${f.id})">Imprimer / PDF</button></div>`)}

const fcDetail=f=>`<div class="tbl"><table>${f.lignes.map(l=>`<tr><td>${esc(l.libelle)}</td><td>${mo(l.montant,f.devise)}</td></tr>`).join('')}<tr><th>Total</th><th>${mo(f.total,f.devise)}</th></tr>
${f.paiements.map(p=>`<tr><td class="mut">Règlement du ${dfr(p.date)} · ${esc(p.mode)}${p.reference?' · '+esc(p.reference):''}</td><td class="mut">− ${mo(p.montant,f.devise)}</td></tr>`).join('')}
${f.avoirs.map(a=>`<tr><td class="mut">Avoir ${esc(a.num)} du ${dfr(a.date)} · ${esc(a.motif)}</td><td class="mut">− ${mo(a.montant,f.devise)}</td></tr>`).join('')}
<tr><th>Reste dû</th><th>${mo(f.solde,f.devise)}</th></tr></table></div>`;

const fcPay=(id,solde,dev)=>ask('Enregistrer un règlement',[{n:'montant',l:`Montant (${dev})`,t:'number',v:solde,r:1},{n:'mode',l:'Mode',o:MODES},{n:'reference',l:'Référence (n° de chèque, virement…)'},{n:'date',l:'Date',t:'date',v:today()}],
async f=>{try{await api(`/factures/${id}/paiements`,{method:'POST',json:{...f,montant:+f.montant,date:f.date||null}});fcAfter()}catch(e){fail('Règlement refusé',e)}});
const fcAvoir=(id,solde,dev)=>ask('Établir un avoir',[{n:'montant',l:`Montant (${dev}, ${mo(solde,dev)} au plus)`,t:'number',r:1},{n:'motif',l:'Motif (remise, erreur de facturation…)',r:1}],
async f=>{try{await api(`/factures/${id}/avoirs`,{method:'POST',json:{montant:+f.montant,motif:f.motif}});fcAfter()}catch(e){fail('Avoir refusé',e)}});
async function fcRelance(id){try{const r=await api(`/factures/${id}/relance`,{method:'POST'});fcLettre(r.niveau,r.lettre);if(view==='fact')loadFact()}catch(e){fail('Relance impossible',e)}}
const fcLettre=(titre,txt)=>info(esc(titre),`<p class="mut">Texte à envoyer au client (l’envoi automatique par e-mail ou SMS nécessite une passerelle, pas encore branchée).</p><textarea readonly rows="12">${esc(txt)}</textarea>`);

/* ---------- Impression (facture, devis) ---------- */
function fcDoc(titre,num,x,lignes,extra){const S=FC.S||{nom:'Alliance Transit',slogan:'Transit, douane, logistique',ville:'Conakry',pays:'Guinée'},w=window.open('','_blank');
const coord=[S.adresse,[S.ville,S.pays].filter(Boolean).join(', ')].filter(Boolean).map(esc).join('<br>'),ident=[S.telephone,S.email].filter(Boolean).map(esc).join(' · '),fisc=[S.nif&&'NIF '+S.nif,S.rc&&'RCCM '+S.rc].filter(Boolean).map(esc).join(' · ');if(!w)return fail('Impression',new Error('Autorisez les fenêtres surgissantes pour imprimer'));
w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${esc(titre)} ${esc(num)}</title><style>body{font:13px/1.5 system-ui,sans-serif;color:#111;margin:40px}h1{font-size:22px;margin:0}
.h{display:flex;justify-content:space-between;border-bottom:2px solid #A8832F;padding-bottom:14px;margin-bottom:22px}table{width:100%;border-collapse:collapse;margin:18px 0}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}td:last-child,th:last-child{text-align:right}
.m{color:#666}.t th{font-size:15px}@media print{body{margin:16mm}}</style></head><body><div class="h"><div><h1>${esc(S.nom)}</h1><div class="m">${esc(S.slogan||'')}</div><div class="m">${coord}</div><div class="m">${ident}</div><div class="m">${fisc}</div></div>
<div style="text-align:right"><h1>${esc(titre)}</h1><div>${esc(num)}</div><div class="m">${extra.dates}</div></div></div><p><b>${esc(x.client_nom)}</b><br><span class="m">Dossier ${esc(x.dossier_num)}</span></p>
<table><tr><th>Désignation</th><th>Montant (${esc(x.devise)})</th></tr>${lignes}</table>${extra.pied||''}
${S.banque||S.compte?`<p class="m">Règlement par virement : ${esc(S.banque||'')} ${S.compte?'· '+esc(S.compte):''}</p>`:''}${S.pied_facture?`<p class="m" style="border-top:1px solid #ddd;padding-top:10px">${esc(S.pied_facture)}</p>`:''}<script>onload=()=>print()<\/script></body></html>`);w.document.close()}
async function fcPrint(id){const f=await api('/factures/'+id);fcDoc('Facture',f.num,f,f.lignes.map(l=>`<tr><td>${esc(l.libelle)}</td><td>${mo(l.montant,f.devise)}</td></tr>`).join('')+`<tr class="t"><th>Total</th><th>${mo(f.total,f.devise)}</th></tr>`
+f.paiements.map(p=>`<tr><td class="m">Règlement du ${dfr(p.date)} (${esc(p.mode)})</td><td class="m">− ${mo(p.montant,f.devise)}</td></tr>`).join('')+f.avoirs.map(a=>`<tr><td class="m">Avoir ${esc(a.num)} : ${esc(a.motif)}</td><td class="m">− ${mo(a.montant,f.devise)}</td></tr>`).join('')
+`<tr class="t"><th>Reste à payer</th><th>${mo(f.solde,f.devise)}</th></tr>`,{dates:`Émise le ${dfr(f.date_emission)}<br>Échéance ${dfr(f.echeance)}`})}
function dvPrint(id){const x=FC.DV.find(d=>d.id===id)||DS.dv?.find(d=>d.id===id);fcDoc('Devis',x.num,x,x.lignes.map(l=>`<tr><td>${esc(l.libelle)}</td><td>${mo(l.montant,x.devise)}</td></tr>`).join('')+`<tr class="t"><th>Total</th><th>${mo(x.total,x.devise)}</th></tr>`,
{dates:`Établi le ${dfr(x.date_emission)}<br>Valable jusqu’au ${dfr(x.validite)}`,pied:x.conditions?`<p class="m">${esc(x.conditions)}</p>`:''})}

/* ---------- Devis ---------- */
const dvActions=x=>{const a=[];if(canDv()){if(x.statut==='Brouillon')a.push(`<button class="ghost sm" onclick="dvSt(${x.id},'Envoyé')">Envoyé</button>`);
if(['Brouillon','Envoyé'].includes(x.statut)&&!x.expire)a.push(`<button class="pri sm" onclick="dvSt(${x.id},'Accepté')">Accepté</button>`);
if(['Brouillon','Envoyé'].includes(x.statut))a.push(`<button class="dg sm" onclick="dvSt(${x.id},'Refusé')">Refusé</button>`)}
if(canF()&&x.statut==='Accepté')a.push(`<button class="pri sm" onclick="dvFacturer(${x.id})">Facturer</button>`);a.push(`<button class="ghost sm" onclick="dvPrint(${x.id})">Imprimer</button>`);return a.join(' ')};
const dvRows=L=>L.map(x=>`<tr><td class="mono">${esc(x.num)}</td><td>${dfr(x.date_emission)}</td><td>${esc(x.client_nom)}</td><td class="mono">${esc(x.dossier_num)}</td><td>${mo(x.total,x.devise)}</td><td>${dfr(x.validite)}</td><td>${dvBadge(x)}</td><td class="act">${dvActions(x)}</td></tr>`).join('')||'<tr><td colspan="8" class="mut">Aucun devis.</td></tr>';
function dvList(){return`${canDv()?'<div class="bar"><button class="pri" onclick="dvNew()">Nouveau devis</button></div>':''}<div class="card tbl"><table><tr><th>Devis</th><th>Date</th><th>Client</th><th>Dossier</th><th>Montant</th><th>Valable jusqu’au</th><th>Statut</th><th></th></tr>${dvRows(FC.DV)}</table></div>`}
async function dvSt(id,s){try{await api(`/devis/${id}/statut`,{method:'POST',json:{statut:s}});fcAfter()}catch(e){fail('Statut du devis',e)}}
const dvFacturer=id=>ask('Facturer le devis',[{n:'deb',l:'Ajouter les droits et taxes avancés (débours)',o:[['non','Non'],['oui','Oui']]}],async f=>{try{const r=await api(`/devis/${id}/facturer`,{method:'POST',json:{refacturer_debours:f.deb==='oui'}});await fcAfter();if(view==='fact')fcView(r.id)}catch(e){fail('Facturation impossible',e)}});
async function dvNew(did){if(!did){const D=(await api('/dossiers')).filter(d=>!d.facture_statut);if(!D.length)return info('Aucun dossier à chiffrer','<p>Tous les dossiers sont déjà facturés, ou aucun dossier n’existe encore.</p>');
return ask('Nouveau devis',[{n:'d',l:'Dossier',o:D.map(d=>[String(d.id),`${d.num} · ${d.client_nom}`])}],f=>dvNew(+f.d))}
const n=(k,l)=>({n:k,l:`${l} (${base()})`,t:'number'});
ask('Lignes du devis',[n('tr','Honoraires de transit'),n('dd','Dédouanement'),n('tp','Transport'),n('ma','Manutention'),n('mg','Magasinage'),n('dv','Frais divers'),
{n:'validite_jours',l:'Validité (jours)',t:'number',v:30},{n:'conditions',l:'Conditions (paiement, exclusions…)',v:'Droits et taxes de douane non compris, refacturés au réel sur justificatif.'}],async f=>{
const L={tr:'Honoraires de transit',dd:'Dédouanement',tp:'Transport',ma:'Manutention',mg:'Magasinage',dv:'Frais divers'},lignes=Object.entries(L).filter(([k])=>+f[k]>0).map(([k,l])=>({libelle:l,montant:+f[k]}));
try{await api(`/dossiers/${did}/devis`,{method:'POST',json:{lignes,validite_jours:+f.validite_jours||30,conditions:f.conditions}});if(view==='fact'){FC.tab='devis';loadFact()}else dsRefresh()}catch(e){fail('Devis non créé',e)}})}

/* ---------- Relances ---------- */
function rlList(){return`${canF()&&FC.RL.length?`<div class="bar"><button class="pri" onclick="rlTout()">${FC.RL.length>1?`Relancer les ${FC.RL.length} factures dues`:'Relancer la facture due'}</button></div>`:''}
<div class="card tbl"><table><tr><th>Facture</th><th>Client</th><th>Reste dû</th><th>Retard</th><th>Relances faites</th><th>Prochaine étape</th><th></th></tr>
${FC.RL.map((r,i)=>`<tr><td class="mono">${esc(r.num)}</td><td>${esc(r.client)}</td><td>${mo(r.solde,r.devise)}</td><td><span class="b ba">${r.jours_retard} j</span></td><td>${r.relances}${r.derniere_relance?` <span class="mut">(dernière le ${dfr(r.derniere_relance)})</span>`:''}</td>
<td>${esc(r.niveau)}</td><td class="act"><button class="ghost sm" onclick="fcLettre(FC.RL[${i}].niveau,FC.RL[${i}].lettre)">Lettre</button>${canF()?` <button class="pri sm" onclick="fcRelance(${r.facture_id})">Relancer</button>`:''}</td></tr>`).join('')||'<tr><td colspan="7" class="mut">Aucune facture à relancer.</td></tr>'}</table></div>
<p class="mut">Règle : première relance dès le lendemain de l’échéance, puis tous les 15 jours (rappel amiable, deuxième relance, mise en demeure). Chaque relance est tracée dans le journal du dossier.</p>`}
async function rlTout(){try{const r=await api('/factures-relances',{method:'POST'});info(`${r.length} relance(s) enregistrée(s)`,r.map(x=>`<h3>${esc(x.num)} · ${esc(x.client)}</h3><textarea readonly rows="8">${esc(x.lettre)}</textarea>`).join(''));loadFact()}catch(e){fail('Relances',e)}}

/* ---------- Exports ---------- */
function exList(){return`<div class="card"><h3>Exports comptables</h3><div class="bar"><label class="mut">Du <input type="date" id="exdu" value="${FC.du}"></label><label class="mut">au <input type="date" id="exau" value="${FC.au}"></label></div>
<div class="bar"><button class="pri" onclick="exDl('export.csv','factures.csv')">Factures (CSV)</button><button class="pri" onclick="exDl('export-ventes.csv','journal-ventes.csv')">Journal des ventes (CSV)</button><button class="pri" onclick="exDl('export-reglements.csv','reglements.csv')">Règlements (CSV)</button></div>
<p class="mut">Fichiers séparés par des points-virgules, décimales à la virgule, s’ouvrent directement dans Excel. Le journal des ventes donne une ligne par prestation (et par avoir) avec sa contre-valeur en ${base()}.</p></div>`}
async function exDl(path,nom){const p=new URLSearchParams(),du=$('#exdu').value,au=$('#exau').value;if(du)p.set('du',du);if(au)p.set('au',au);
try{const r=await fetch(`/api/factures/${path}?${p}`,{headers:{Authorization:'Bearer '+getTok()}});if(!r.ok)throw new Error('Export impossible ('+r.status+')');
const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=nom;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}catch(e){fail('Export',e)}}
