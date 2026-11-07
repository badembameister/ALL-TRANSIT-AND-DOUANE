/* Tableau de bord branché sur l'API (/api/pilotage) : indicateurs du point 13 du cahier des charges,
   tendance sur 12 mois, classements, rentabilité et alertes consolidées cliquables. */
const TB={per:'12m',du:'',au:'',R:null,mod:'',tab:false};
const MOIS=['janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
const compact=v=>{const a=Math.abs(v);return a>=1e9?(v/1e9).toLocaleString('fr-FR',{maximumFractionDigits:1})+' Md':a>=1e6?(v/1e6).toLocaleString('fr-FR',{maximumFractionDigits:1})+' M':a>=1e4?(v/1e3).toLocaleString('fr-FR',{maximumFractionDigits:0})+' k':nf(v)};
const moisLib=m=>{const[y,mm]=m.split('-');return MOIS[+mm-1]+' '+y.slice(2)};
function tbPeriode(){const t=new Date(),iso=d=>d.toISOString().slice(0,10),first=(y,m)=>new Date(Date.UTC(y,m,1));
const y=t.getFullYear(),m=t.getMonth();if(TB.per==='mois')return[iso(first(y,m)),today()];if(TB.per==='3m')return[iso(first(y,m-2)),today()];
if(TB.per==='an')return[iso(first(y,0)),today()];if(TB.per==='perso')return[TB.du,TB.au];return[iso(first(y,m-11)),today()]}

function vDashApi(){return`<div id="tbv"><h1>Tableau de bord</h1><p class="mut">Chargement…</p></div>`}
async function loadDash(){const[du,au]=tbPeriode(),p=new URLSearchParams();if(du)p.set('du',du);if(au)p.set('au',au);
try{TB.R=await api('/pilotage?'+p)}catch(e){$('#tbv').innerHTML=`<h1>Tableau de bord</h1><p class="note">${esc(e.message)}</p>`;return}paintDash()}

const tile=(v,l,warn,sub)=>`<div class="${warn?'w':''}"><b>${v}</b><span>${l}</span>${sub?`<small class="mut">${sub}</small>`:''}</div>`;
const dash=v=>v==null?'—':v;
function paintDash(){if(view!=='dashboard'||sel||!$('#tbv'))return;const R=TB.R,A=R.activite,D=R.douane,T=R.transit,O=R.operations,F=R.finance,b=R.devise_base,S=A.par_statut;
const P=[['mois','Ce mois'],['3m','3 derniers mois'],['12m','12 derniers mois'],['an','Cette année'],['perso','Période…']];
const urg=R.alertes.filter(a=>a.niveau==='ba').length,h=new Date().getHours(),salut=h<5||h>=18?'Bonsoir':'Bonjour';TB.svg=TB.svg||sceneSVG('band');
$('#tbv').innerHTML=`<div class="hero"><div class="scene">${TB.svg}</div><div class="hero-tx"><small>${new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</small>
<h1>${salut}${ME?', '+esc(ME.nom.split(' ')[0]):''}</h1><p><b>${S['Ouvert']+S['En cours']}</b> dossier(s) en cours · <b>${T.en_cours}</b> transit(s) en route · <b>${O.conteneurs_au_port}</b> conteneur(s) au port${urg?` · <b>${urg}</b> alerte(s) urgente(s)`:''}</p></div></div><div class="bar">${P.map(([k,l])=>`<button class="${k===TB.per?'pri':'ghost'} sm" onclick="TB.per='${k}';${k==='perso'?'paintDash()':'loadDash()'}">${l}</button>`).join('')}
${TB.per==='perso'?`<label class="mut">Du <input type="date" value="${TB.du}" onchange="TB.du=this.value;loadDash()"></label><label class="mut">au <input type="date" value="${TB.au}" onchange="TB.au=this.value;loadDash()"></label>`:''}
<span class="mut">Période : ${dfr(R.periode.du)} – ${dfr(R.periode.au)}</span></div>
<h3 class="sec">Activité</h3><div class="kp">${tile(S['Ouvert']+S['En cours'],'Dossiers ouverts')}${tile(S['Bloqué'],'Dossiers bloqués',S['Bloqué'])}${tile(S['Livré'],'Livrés')}${tile(S['Clôturé'],'Clôturés')}
${tile(A.ouverts_periode,'Ouverts sur la période')}${tile(A.taux_complets==null?'—':A.taux_complets+' %','Dossiers actifs complets',A.taux_complets!=null&&A.taux_complets<80,A.pieces_manquantes?`${A.pieces_manquantes} pièce(s) manquante(s)`:'')}</div>
<h3 class="sec">Douane, transit et opérations</h3><div class="kp">${tile(D.delai_moyen_jours==null?'—':jours(D.delai_moyen_jours),'Délai moyen de dédouanement','',`${D.bae} bon(s) à enlever`)}
${tile(D.taux_premier_depot==null?'—':D.taux_premier_depot+' %','Acceptées au premier dépôt',D.taux_premier_depot!=null&&D.taux_premier_depot<80,`${D.transmises} transmise(s)`)}${tile(D.rejets+D.controles,'Incidents douaniers',D.rejets,`${D.rejets} rejet(s), ${D.controles} contrôle(s)`)}
${tile(T.en_cours,'Transits en cours','',`${T.apures_periode} apuré(s) sur la période`)}${tile(T.non_apures_retard,'Transits non apurés en retard',T.non_apures_retard)}${tile(O.missions_en_retard,'Missions en retard',O.missions_en_retard,`${O.missions_livrees} livrée(s), ${T.incidents+O.incidents} incident(s)`)}</div>
<h3 class="sec">Finance (${esc(b)})</h3><div class="kp">${tile(compact(F.ca),'Chiffre d’affaires facturé','',`${F.factures} facture(s)`)}${tile(compact(F.ca_hors_debours),'Hors débours refacturés')}
${tile(compact(F.creances),'Créances clients')}${tile(compact(F.montant_retard),'Dont en retard',F.en_retard,`${F.en_retard} facture(s)`)}${tile(compact(R.rentabilite.marge),'Marge sur dossiers facturés',R.rentabilite.marge<0,R.rentabilite.produits?`${pct(Math.round(R.rentabilite.marge/R.rentabilite.produits*1000)/10)} des produits`:'')}</div>
<div class="card"><div class="bar" style="margin:0 0 6px"><h3 style="margin:0">Chiffre d’affaires facturé par mois (${esc(b)})</h3><button class="ghost sm" style="margin-left:auto" onclick="TB.tab=!TB.tab;paintDash()">${TB.tab?'Voir le graphique':'Voir le tableau'}</button></div>
<p class="mut" style="margin:0 0 8px">12 derniers mois, quelle que soit la période choisie.</p>${TB.tab?tbTable(R.tendance):tbColumns(R.tendance)}</div>
<div class="duo"><div class="card"><h3>Chiffre d’affaires par client</h3>${tbBars(F.par_client)}</div><div class="card"><h3>Par type de prestation</h3>${tbBars(F.par_prestation)}</div></div>
<div class="duo"><div class="card tbl"><h3>Rentabilité par client</h3>${tbRent(R.rentabilite.par_client)}</div><div class="card tbl"><h3>Rentabilité par transporteur</h3>${tbRent(R.rentabilite.par_transporteur)}</div></div>
<div class="duo"><div class="card tbl"><h3>Dossiers les plus rentables</h3>${tbDos(R.rentabilite.meilleurs)}</div><div class="card tbl"><h3>Dossiers à marge faible (moins de 10 %)</h3>${tbDos(R.rentabilite.moins_bons)}</div></div>
${F.par_agent.length?`<div class="card"><h3>Chiffre d’affaires par personne ayant émis les factures</h3>${tbBars(F.par_agent)}</div>`:''}
<div class="card" id="tbal">${tbAlertes()}</div>`;tbHover();tbCompte()}
/* Les chiffres des indicateurs défilent jusqu'à leur valeur (sauf si l'utilisateur limite les animations) */
function tbCompte(){if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;document.querySelectorAll('#tbv .kp b').forEach(el=>{const m=el.textContent.match(/^([\d\s\u202f\u00a0]+(?:,\d+)?)(.*)$/);if(!m)return;
const cible=parseFloat(m[1].replace(/[\s\u202f\u00a0]/g,'').replace(',','.')),dec=(m[1].split(',')[1]||'').length,suf=m[2],t0=performance.now();if(!cible)return;
const pas=t=>{const k=Math.min(1,(t-t0)/700),v=cible*(1-Math.pow(1-k,3));el.textContent=v.toLocaleString('fr-FR',{minimumFractionDigits:dec,maximumFractionDigits:dec})+suf;if(k<1)requestAnimationFrame(pas)};requestAnimationFrame(pas)})}

/* Colonnes : une seule série, une seule couleur, info-bulle au survol, étiquette sur le maximum et le dernier mois */
function tbColumns(L){const W=760,H=240,pl=56,pr=10,pt=22,pb=28,max=Math.max(...L.map(x=>x.ca),0);
const step=max<=0?1:Math.pow(10,Math.floor(Math.log10(max))),nice=[1,2,2.5,5,10].map(k=>k*step).find(v=>v*4>=max)||step*10,top=nice*4||1;
const bw=(W-pl-pr)/L.length,bar=Math.min(24,bw*.6),y=v=>pt+(H-pt-pb)*(1-v/top),imax=L.reduce((m,x,i)=>x.ca>L[m].ca?i:m,0);
let g='';for(let i=0;i<=4;i++){const v=top*i/4;g+=`<line x1="${pl}" x2="${W-pr}" y1="${y(v)}" y2="${y(v)}" class="gl"/><text x="${pl-8}" y="${y(v)+4}" text-anchor="end" class="ax">${compact(v)}</text>`}
const cols=L.map((x,i)=>{const cx=pl+bw*i+bw/2,h=H-pb-y(x.ca),lab=(i===imax||i===L.length-1)&&x.ca>0;
return`<g class="col" data-i="${i}"><rect class="hit" x="${pl+bw*i}" y="${pt}" width="${bw}" height="${H-pt-pb}"/>${x.ca>0?`<path class="mk" d="M${cx-bar/2},${H-pb} v${-(h-Math.min(4,h))} q0,${-Math.min(4,h)} ${Math.min(4,h)},${-Math.min(4,h)} h${bar-2*Math.min(4,h)} q${Math.min(4,h)},0 ${Math.min(4,h)},${Math.min(4,h)} v${h-Math.min(4,h)} z"/>`:''}
${lab?`<text x="${cx}" y="${y(x.ca)-6}" text-anchor="middle" class="vl">${compact(x.ca)}</text>`:''}<text x="${cx}" y="${H-pb+16}" text-anchor="middle" class="ax">${moisLib(x.mois)}</text></g>`}).join('');
return`<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Chiffre d’affaires facturé par mois sur 12 mois">${g}<line x1="${pl}" x2="${W-pr}" y1="${H-pb}" y2="${H-pb}" class="bl"/>${cols}</svg><div class="tip" id="tbtip" hidden></div></div>`}
function tbHover(){const svg=document.querySelector('#tbv .chart svg'),tip=$('#tbtip');if(!svg||!tip)return;const L=TB.R.tendance,b=TB.R.devise_base;
svg.querySelectorAll('.col').forEach(g=>{g.onmouseenter=g.onfocus=e=>{const x=L[+g.dataset.i],r=svg.getBoundingClientRect(),hr=g.querySelector('.hit').getBoundingClientRect();
svg.querySelectorAll('.col').forEach(o=>o.classList.toggle('dim',o!==g));tip.innerHTML=`<b>${moisLib(x.mois)}</b><br>${nf(x.ca)} ${esc(b)}<br><span class="mut">${x.dossiers} dossier(s) ouvert(s)</span>`;
tip.hidden=false;const left=hr.left-r.left+hr.width/2;tip.style.left=Math.min(Math.max(left,70),r.width-70)+'px'};g.onmouseleave=()=>{tip.hidden=true;svg.querySelectorAll('.col').forEach(o=>o.classList.remove('dim'))}})}
const tbTable=L=>`<div class="tbl"><table><tr><th>Mois</th><th>Chiffre d’affaires</th><th>Dossiers ouverts</th></tr>${L.map(x=>`<tr><td>${moisLib(x.mois)}</td><td>${nf(x.ca)}</td><td>${x.dossiers}</td></tr>`).join('')}</table></div>`;

/* Barres horizontales : valeur au bout, une seule couleur */
const tbBars=L=>{if(!L.length)return'<p class="mut">Aucune facture sur la période.</p>';const mx=Math.max(...L.map(x=>x.montant),1);
return`<div class="hb">${L.map(x=>`<div title="${esc(x.nom)} : ${nf(x.montant)}"><span>${esc(x.nom)}</span><i><b style="width:${Math.max(.5,x.montant/mx*100)}%"></b></i><span>${compact(x.montant)}</span></div>`).join('')}</div>`};
const tbRent=L=>L.length?`<table><tr><th></th><th>Produits</th><th>Marge</th><th>Taux</th></tr>${L.map(x=>`<tr><td>${esc(x.nom)}<br><span class="mut">${x.dossiers} dossier(s)</span></td><td>${compact(x.produits)}</td><td>${compact(x.marge)}</td><td>${x.taux==null?'—':`<span class="b ${x.taux<10?'ba':x.taux<25?'wa':'ok'}">${pct(x.taux)}</span>`}</td></tr>`).join('')}</table>`:'<p class="mut">Aucun dossier facturé sur la période.</p>';
const tbDos=L=>L.length?`<table><tr><th>Dossier</th><th>Produits</th><th>Coûts</th><th>Marge</th></tr>${L.map(x=>`<tr><td><button class="lk" onclick="tbGo({vue:'dossier',id:${x.dossier_id},onglet:'fact'})">${esc(x.num)}</button><br><span class="mut">${esc(x.client)}</span></td><td>${compact(x.produits)}</td><td>${compact(x.couts)}</td><td>${compact(x.marge)}${x.taux!=null?` <span class="mut">(${pct(x.taux)})</span>`:''}</td></tr>`).join('')}</table>`:'<p class="mut">Aucun.</p>';

/* Alertes consolidées, filtrables par module, chacune ouvre l'objet concerné */
function tbAlertes(){const L=TB.R.alertes,mods=[...new Set(L.map(a=>a.module))],V=L.filter(a=>!TB.mod||a.module===TB.mod);
return`<div class="bar" style="margin-bottom:6px"><h3 style="margin:0">Alertes (${L.length})</h3>${mods.length>1?`<button class="${!TB.mod?'pri':'ghost'} sm" onclick="TB.mod='';$('#tbal').innerHTML=tbAlertes()">Toutes</button>${mods.map(m=>`<button class="${m===TB.mod?'pri':'ghost'} sm" onclick="TB.mod='${m}';$('#tbal').innerHTML=tbAlertes()">${m} (${L.filter(a=>a.module===m).length})</button>`).join('')}`:''}</div>
${V.map((a,i)=>`<div class="al"><span class="b ${a.niveau}">${a.niveau==='ba'?'Urgent':'À suivre'}</span> <span class="mut">${esc(a.module)}</span> ${a.lien?`<button class="lk" onclick='tbGo(${JSON.stringify(a.lien)})'>${esc(a.texte)}</button>`:esc(a.texte)}</div>`).join('')||'<p class="mut">Aucune alerte.</p>'}`}
async function tbGo(l){if(l.vue==='dossier'){go('dossiers');DS.sel=l.id;DS.tab=l.onglet||'res';await dsLoad()}else if(l.vue==='transit'){go('transit');await loadTransit();trOpen(l.id)}
else if(l.vue==='facture'){go('fact');fcView(l.id)}else if(l.vue==='client'){go('clients');cpOpen(l.id)}else go(l.vue)}
