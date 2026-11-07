/* Portail client : accueil (dossiers en cours, prochaines étapes, pièces à fournir, livraisons, sommes à payer,
   notifications) et « Mes factures » (consultation et impression). Données de /api/portail, limitées au client connecté. */
const PT={A:null,F:[],nl:0};
const isCli=()=>role==='Client';

function vPortail(){return`<div id="ptv"><p class="mut">Chargement…</p></div>`}
async function loadPortail(){try{PT.A=await api('/portail/accueil');PT.nl=PT.A.non_lues}catch(e){$('#ptv').innerHTML=`<p class="note">${esc(e.message)}</p>`;return}paintPortail();ptBadge()}
function ptBadge(){const b=[...document.querySelectorAll('#nav button')].find(x=>x.textContent.includes('Accueil'));if(!b)return;b.querySelector('.nb')?.remove();
if(PT.nl)b.insertAdjacentHTML('beforeend',`<span class="nb" aria-label="${PT.nl} notification(s) non lue(s)">${PT.nl}</span>`)}

function paintPortail(){if(view!=='portail'||!$('#ptv'))return;const A=PT.A,h=new Date().getHours(),apayer=A.a_payer.reduce((s,f)=>s+f.solde,0),dev=A.a_payer[0]?.devise||'';
$('#ptv').innerHTML=`<div class="hero"><div class="scene">${(PT.svg=PT.svg||sceneSVG('band'))}</div><div class="hero-tx"><small>${new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'})}</small>
<h1>${h<5||h>=18?'Bonsoir':'Bonjour'}, ${esc(ME.nom.split(' ')[0])}</h1><p>Suivez vos opérations avec Alliance Transit en temps réel.</p></div></div>
<div class="kp"><div><b>${A.dossiers.length}</b><span>Dossiers en cours</span></div><div><b>${A.livraisons.length}</b><span>Transports prévus ou en cours</span></div>
<div class="${A.a_payer.some(f=>f.jours_retard)?'w':''}"><b>${A.a_payer.length}</b><span>Facture(s) à régler</span>${apayer?`<small class="mut">${mo(apayer,dev)}${A.a_payer.length>1&&new Set(A.a_payer.map(f=>f.devise)).size>1?' (plusieurs devises)':''}</small>`:''}</div>
<div class="${PT.nl?'w':''}"><b>${PT.nl}</b><span>Nouvelle(s) notification(s)</span></div></div>
<div class="duo"><div><h3 class="sec">Vos dossiers en cours</h3>${A.dossiers.map(d=>`<div class="card pt-dos"><div class="bar" style="margin:0"><button class="lk" onclick="ptOuvrir(${d.id})">${esc(d.num)}</button>${badge(d.statut)}<span class="mut" style="margin-left:auto">${esc(d.type)}${d.ref?' · '+esc(d.ref):''}</span></div>
<p style="margin:6px 0">${esc(d.designation)}</p><div class="prog" role="progressbar" aria-valuenow="${d.etapes_faites}" aria-valuemax="${d.etapes}" aria-label="Avancement"><i style="width:${d.etapes?d.etapes_faites/d.etapes*100:0}%"></i></div>
<p class="mut" style="margin:6px 0 0">${d.etapes_faites}/${d.etapes} étapes${d.prochaine_etape?` · prochaine : <b>${esc(d.prochaine_etape.libelle)}</b>${d.prochaine_etape.prevue?` (prévue le ${dfr(d.prochaine_etape.prevue)})`:''}`:''}</p>
${d.douane||d.transit?`<p style="margin:6px 0 0">${d.douane?`Douane ${badge(d.douane)} `:''}${d.transit?`Transit ${trBadge({statut:d.transit,en_retard:false,scelle_casse:false})}`:''}</p>`:''}
${d.pieces_manquantes.length?`<div class="note">Pièces à nous transmettre : ${d.pieces_manquantes.map(esc).join(', ')}. <button class="lk" onclick="ptOuvrir(${d.id},'docs')">Déposer</button></div>`:''}</div>`).join('')||'<div class="card"><p class="mut">Aucun dossier en cours.</p></div>'}
${A.termines?`<p class="mut">${A.termines} dossier(s) terminé(s) : retrouvez-les dans « Dossiers ».</p>`:''}</div>
<div><h3 class="sec">Notifications</h3><div class="card">${PT.nl?`<div class="bar" style="margin:0 0 6px"><button class="ghost sm" onclick="ptLu()">Tout marquer comme lu</button></div>`:''}
${A.notifications.map(n=>`<div class="al"><span class="b ${{ok:'ok',info:'in',alerte:'ba'}[n.niveau]}">${n.nouveau?'Nouveau':{ok:'Fait',info:'Info',alerte:'Attention'}[n.niveau]}</span> <span><button class="lk" style="font-weight:500" onclick="ptOuvrir(${n.dossier_id})">${esc(n.texte)}</button><br><span class="mut">${hfr(n.ts)}</span></span></div>`).join('')||'<p class="mut">Aucune notification pour le moment.</p>'}</div>
<h3 class="sec">Transports</h3><div class="card">${A.livraisons.map(m=>`<div class="al">${mBadge({statut:m.statut,en_retard:false})} <span>${dfr(m.date_prevue)} · ${esc(m.type)} · ${esc(m.origine)} → ${esc(m.destination)}<br><span class="mut">Dossier ${esc(m.dossier_num)}</span></span></div>`).join('')||'<p class="mut">Aucun transport prévu.</p>'}</div>
<h3 class="sec">À régler</h3><div class="card">${A.a_payer.map(f=>`<div class="al">${f.jours_retard?`<span class="b ba">${f.jours_retard} j de retard</span>`:'<span class="b wa">À échéance</span>'} <span><button class="lk" onclick="ptFacture(${f.id})">${esc(f.num)}</button> · ${mo(f.solde,f.devise)}<br><span class="mut">Échéance ${dfr(f.echeance)} · dossier ${esc(f.dossier_num)}</span></span></div>`).join('')||'<p class="mut">Aucune facture en attente. Merci !</p>'}</div></div></div>`}

async function ptOuvrir(did,onglet){go('dossiers');DS.sel=did;DS.tab=onglet||'res';await dsLoad()}
async function ptLu(){try{await api('/portail/notifications/vues',{method:'POST'});await loadPortail()}catch(e){fail('Notifications',e)}}

/* ---------- Mes factures ---------- */
function vMesFact(){return`<div id="mfv"><h1>Mes factures</h1><p class="mut">Chargement…</p></div>`}
async function loadMesFact(){try{PT.F=await api('/portail/factures')}catch(e){$('#mfv').innerHTML=`<h1>Mes factures</h1><p class="note">${esc(e.message)}</p>`;return}fcSoc();
const ouv=PT.F.filter(f=>f.solde>0),parDev={};ouv.forEach(f=>parDev[f.devise]=(parDev[f.devise]||0)+f.solde);
$('#mfv').innerHTML=`<h1>Mes factures</h1><div class="kp"><div><b>${PT.F.length}</b><span>Factures</span></div><div class="${ouv.some(f=>f.jours_retard)?'w':''}"><b>${ouv.length}</b><span>À régler</span>${Object.keys(parDev).length?`<small class="mut">${Object.entries(parDev).map(([d,v])=>mo(v,d)).join(' · ')}</small>`:''}</div></div>
<div class="card tbl"><table><tr><th>Facture</th><th>Émise le</th><th>Dossier</th><th>Montant</th><th>Reste à payer</th><th>Échéance</th><th>Statut</th><th></th></tr>
${PT.F.map(f=>`<tr><td><button class="lk" onclick="ptFacture(${f.id})">${esc(f.num)}</button></td><td>${dfr(f.date_emission)}</td><td class="mono">${esc(f.dossier_num)}</td><td>${mo(f.total,f.devise)}</td><td>${mo(f.solde,f.devise)}</td>
<td>${dfr(f.echeance)}${f.jours_retard?`<br><span class="b ba">${f.jours_retard} j de retard</span>`:''}</td><td>${badge(f.statut)}</td><td><button class="ghost sm" onclick="ptPrint(${f.id})">PDF</button></td></tr>`).join('')||'<tr><td colspan="8" class="mut">Aucune facture.</td></tr>'}</table></div>
<p class="mut">Pour régler une facture ou poser une question, contactez notre service comptabilité. Les montants sont dans la devise de facturation convenue.</p>`}
async function ptFacture(id){let f;try{f=await api('/portail/factures/'+id)}catch(e){return fail('Facture',e)}
info(`${esc(f.num)} ${badge(f.statut)}`,`<p class="mut">Dossier ${esc(f.dossier_num)}. Émise le ${dfr(f.date_emission)}, échéance ${dfr(f.echeance)}${f.jours_retard?`, <b>${f.jours_retard} jours de retard</b>`:''}.</p>${fcDetail(f)}
<div class="bar" style="margin-top:14px"><button class="pri" type="button" onclick="ptPrint(${f.id})">Télécharger en PDF</button></div>`)}
async function ptPrint(id){const win=window.open('','_blank');fcSoc();const f=await api('/portail/factures/'+id);if(!FC.S)FC.S=await api('/societe').catch(()=>null);
fcDoc('Facture',f.num,f,f.lignes.map(l=>`<tr><td>${esc(l.libelle)}</td><td>${mo(l.montant,f.devise)}</td></tr>`).join('')+`<tr class="t"><th>Total</th><th>${mo(f.total,f.devise)}</th></tr>`
+f.paiements.map(p=>`<tr><td class="m">Règlement du ${dfr(p.date)}</td><td class="m">− ${mo(p.montant,f.devise)}</td></tr>`).join('')+f.avoirs.map(a=>`<tr><td class="m">Avoir ${esc(a.num)} : ${esc(a.motif)}</td><td class="m">− ${mo(a.montant,f.devise)}</td></tr>`).join('')
+`<tr class="t"><th>Reste à payer</th><th>${mo(f.solde,f.devise)}</th></tr>`,{dates:`Émise le ${dfr(f.date_emission)}<br>Échéance ${dfr(f.echeance)}`},win)}
