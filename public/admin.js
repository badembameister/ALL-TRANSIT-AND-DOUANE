/* Module « Administration » branché sur l'API : société, devises et taux, taxes, codes SH (avec import),
   régimes douaniers, journal d'audit, état du système et export des données. */
const AD={tab:'soc',P:null,S:null,sys:null,J:[],shq:'',jf:{q:'',entite:'',utilisateur:'',du:'',au:''}};
const AD_TABS=[['soc','Société'],['dev','Devises et taux'],['tax','Taxes et TVA'],['sh','Codes SH'],['reg','Régimes'],['jr','Journal d’audit'],['sys','Système']];
const ENTITES=['dossier','document','declaration','transit','facture','client','mission','conteneur','vehicule','chauffeur','utilisateur','parametres'];

function vAdminApi(){return`<div id="adv"><h1>Administration</h1><p class="mut">Chargement…</p></div>`}
async function loadAdmin(){try{[AD.P,AD.S]=await Promise.all([api('/params'),api('/societe')])}catch(e){$('#adv').innerHTML=`<h1>Administration</h1><p class="note">${esc(e.message)}</p>`;return}paintAdmin();adTabLoad()}
function paintAdmin(){if(view!=='admin'||sel||!$('#adv'))return;$('#adv').innerHTML=`<h1>Administration</h1><div class="tabs">${AD_TABS.map(t=>`<button class="${t[0]===AD.tab?'on':''}" onclick="AD.tab='${t[0]}';paintAdmin();adTabLoad()">${t[1]}</button>`).join('')}</div>
<div id="adt">${({soc:adSoc,dev:adDev,tax:adTax,sh:adSh,reg:adReg,jr:()=>'<p class="mut">Chargement…</p>',sys:()=>'<p class="mut">Chargement…</p>'})[AD.tab]()}</div>`}
function adTabLoad(){if(AD.tab==='jr')adJournal();if(AD.tab==='sys')adSys()}
const adPaint=h=>{if($('#adt'))$('#adt').innerHTML=h};
const adOk=m=>info('Enregistré',`<p>${esc(m)}</p>`);

/* Enregistre une copie modifiée des paramètres ; en cas de refus, recharge l'état serveur */
async function adSave(P,msg){try{AD.P=await api('/params',{method:'PUT',json:P});paintAdmin();if(msg)adOk(msg)}catch(e){fail('Paramètres refusés',e);AD.P=await api('/params');paintAdmin()}}
const clone=()=>JSON.parse(JSON.stringify(AD.P));

/* ---------- Société ---------- */
function adSoc(){const S=AD.S,f=(n,l,t)=>`<label>${l}<input name="${n}" type="${t||'text'}" value="${esc(S[n]||'')}"${n==='nom'?' required':''}></label>`;
return`<div class="card"><h3>Informations de la société</h3><p class="mut">Utilisées en en-tête et en pied des factures et devis imprimés, et pour signer les lettres de relance.</p>
<form id="adsoc" class="frm" onsubmit="return adSocSave(event)">${f('nom','Raison sociale')}${f('slogan','Activité / slogan')}${f('adresse','Adresse')}${f('ville','Ville')}${f('pays','Pays')}
${f('telephone','Téléphone','tel')}${f('email','E-mail','email')}${f('nif','NIF')}${f('rc','RCCM')}${f('banque','Banque')}${f('compte','Compte bancaire (RIB / IBAN)')}
${f('signature','Signature des relances')}<label class="wide">Mentions en pied de facture<input name="pied_facture" value="${esc(S.pied_facture||'')}"></label>
<div class="row wide"><button class="pri">Enregistrer</button></div></form></div>`}
async function adSocSave(e){e.preventDefault();try{AD.S=await api('/societe',{method:'PUT',json:Object.fromEntries(new FormData(e.target))});FC.S=AD.S;adOk('Informations de la société enregistrées.')}catch(err){fail('Enregistrement refusé',err)}return false}

/* ---------- Devises et taux ---------- */
function adDev(){const P=AD.P,b=P.base;return`<div class="card tbl"><h3>Devises et taux de change</h3><p class="mut">Devise de base : <b>${esc(b)}</b>. Taux = valeur d’une unité de la devise en ${esc(b)}. ${P.rates_maj?`Dernière mise à jour des taux : ${dfr(P.rates_maj)}.`:''}</p>
<form id="adrates" onsubmit="return adRatesSave(event)"><table><tr><th>Devise</th><th>Taux (en ${esc(b)})</th><th>Exemple</th><th></th></tr>
${Object.entries(P.rates).map(([k,v])=>`<tr><td class="mono">${esc(k)}${k===b?' <span class="b ok">Base</span>':''}</td><td>${k===b?'1':`<input name="${esc(k)}" type="number" step="any" min="0" value="${v}" required style="max-width:160px">`}</td>
<td class="mut">${k===b?'—':`100 ${esc(k)} = ${nf(100*v)} ${esc(b)}`}</td><td>${k===b?'':`<button type="button" class="dg sm" onclick="adRateDel(${jsq(k)})">Retirer</button>`}</td></tr>`).join('')}</table>
<div class="bar" style="margin-top:12px"><button class="pri">Enregistrer les taux</button><button type="button" class="ghost" onclick="adRateAdd()">Ajouter une devise</button></div></form>
<p class="mut">Les factures déjà émises gardent leurs montants ; les nouveaux taux s’appliquent aux prochains calculs. Les déclarations transmises gardent leur liquidation figée. Chaque changement est tracé dans le journal.</p></div>`}
function adRatesSave(e){e.preventDefault();const P=clone();for(const[k,v]of new FormData(e.target))P.rates[k]=+v;adSave(P,'Taux de change enregistrés.');return false}
const adRateAdd=()=>ask('Nouvelle devise',[{n:'c',l:'Code ISO (3 lettres, ex. XOF)',r:1},{n:'t',l:`Taux (valeur d’une unité en ${AD.P.base})`,t:'number',r:1}],f=>{const P=clone();P.rates[f.c.trim().toUpperCase()]=+f.t;adSave(P)});
const adRateDel=k=>{if(!confirm(`Retirer la devise ${k} ? Les clients facturés dans cette devise garderaient un taux de 1 pour les calculs.`))return;const P=clone();delete P.rates[k];adSave(P)};

/* ---------- Taxes et TVA ---------- */
function adTax(){const P=AD.P;return`<div class="card"><h3>TVA et droit par défaut</h3><form class="bar" onsubmit="return adTvaSave(event)"><label class="mut">TVA (%) <input name="tva" type="number" step="any" min="0" max="100" value="${P.tva}" style="width:90px"></label>
<label class="mut">Droit de douane par défaut (%) <input name="dd0" type="number" step="any" min="0" max="100" value="${P.dd0}" style="width:90px"></label><button class="pri">Enregistrer</button></form>
<p class="mut">Le droit par défaut s’applique quand le code SH d’un dossier n’est pas dans le tarif.</p></div>
<div class="card tbl"><div class="bar"><h3 style="margin:0">Autres taxes</h3><button class="pri sm" onclick="adTaxForm()">Ajouter</button></div><table><tr><th>Taxe</th><th>Taux</th><th>Base</th><th>À l’export</th><th></th></tr>
${P.taxes.map((t,i)=>`<tr><td>${esc(t.n)}</td><td>${pct(t.t)}</td><td>${t.base==='cifdd'?'CIF + droits de douane':'Valeur CIF'}</td><td>${t.exp?'Oui':'Non'}</td><td class="act"><button class="ghost sm" onclick="adTaxForm(${i})">Modifier</button> <button class="dg sm" onclick="adTaxDel(${i})">Retirer</button></td></tr>`).join('')||'<tr><td colspan="5" class="mut">Aucune taxe.</td></tr>'}</table>
<p class="mut">Ordre de calcul : droit de douane, autres taxes, accise, puis TVA sur l’ensemble. Taux marqués « à valider » : à caler sur une quittance SYDONIA réelle.</p></div>`}
function adTvaSave(e){e.preventDefault();const P=clone(),f=Object.fromEntries(new FormData(e.target));P.tva=+f.tva;P.dd0=+f.dd0;adSave(P,'TVA et droit par défaut enregistrés.');return false}
const adTaxForm=i=>{const t=i!=null?AD.P.taxes[i]:{base:'cif',exp:false};ask(i!=null?'Modifier la taxe':'Nouvelle taxe',[{n:'n',l:'Nom',v:t.n||'',r:1},{n:'t',l:'Taux (%)',t:'number',v:t.t??'',r:1},
{n:'base',l:'Base de calcul',o:[['cif','Valeur CIF'],['cifdd','CIF + droits de douane']],v:t.base},{n:'exp',l:'S’applique à l’export',o:[['false','Non'],['true','Oui']],v:String(!!t.exp)}],f=>{const P=clone(),x={n:f.n,t:+f.t,base:f.base,exp:f.exp==='true'};
if(i!=null)P.taxes[i]=x;else P.taxes.push(x);adSave(P)})};
const adTaxDel=i=>{if(!confirm('Retirer cette taxe ?'))return;const P=clone();P.taxes.splice(i,1);adSave(P)};

/* ---------- Codes SH ---------- */
const shRows=()=>{const q=AD.shq.toLowerCase();return AD.P.sh.map((x,i)=>[x,i]).filter(([x])=>(x.c+' '+x.l).toLowerCase().includes(q)).slice(0,300).map(([x,i])=>`<tr><td class="mono">${esc(x.c)}</td><td>${esc(x.l)}</td><td>${pct(x.dd)}</td><td>${x.ac?pct(x.ac):'—'}</td>
<td class="act"><button class="ghost sm" onclick="adShForm(${i})">Modifier</button> <button class="dg sm" onclick="adShDel(${i})">Retirer</button></td></tr>`).join('')||'<tr><td colspan="5" class="mut">Aucun code.</td></tr>'};
function adSh(){return`<div class="card tbl"><div class="bar"><h3 style="margin:0">Tarif des codes SH (${AD.P.sh.length})</h3><input placeholder="Code ou libellé" value="${esc(AD.shq)}" oninput="AD.shq=this.value;$('#shl').innerHTML=shRows()"><button class="pri sm" onclick="adShForm()">Ajouter</button></div>
<table><tr><th>Code (début)</th><th>Libellé</th><th>Droit de douane</th><th>Accise</th><th></th></tr><tbody id="shl">${shRows()}</tbody></table>
<p class="mut">Un dossier prend le taux du code le plus proche qui commence son code SH (ex. 1006 couvre 100630). Affichage limité à 300 lignes : utilisez la recherche.</p></div>
<div class="card"><h3>Importer un tarif</h3><p class="mut">Collez des lignes « code;libellé;droit %;accise % » (export Excel en CSV, séparateur point-virgule, virgule ou tabulation ; en-tête facultatif). Rien n’est importé si une ligne est invalide.</p>
<textarea id="shcsv" rows="6" placeholder="1006.30;Riz semi-blanchi ou blanchi;10;0&#10;2523.29;Ciment Portland;20;0"></textarea>
<div class="bar" style="margin-top:10px"><select id="shmode"><option value="fusion">Ajouter et mettre à jour</option><option value="remplacer">Remplacer tout le tarif</option></select><button class="pri" onclick="adShImport()">Importer</button></div></div>`}
const adShForm=i=>{const x=i!=null?AD.P.sh[i]:{};ask(i!=null?`Code ${x.c}`:'Nouveau code SH',[{n:'c',l:'Code SH (2 à 10 chiffres)',v:x.c||'',r:1},{n:'l',l:'Libellé',v:x.l||'',r:1},{n:'dd',l:'Droit de douane (%)',t:'number',v:x.dd??'',r:1},{n:'ac',l:'Accise (%)',t:'number',v:x.ac??0}],
f=>{const P=clone(),y={c:f.c,l:f.l,dd:+f.dd,ac:+f.ac||0};if(i!=null)P.sh[i]=y;else P.sh.push(y);adSave(P)})};
const adShDel=i=>{if(!confirm(`Retirer le code ${AD.P.sh[i].c} ?`))return;const P=clone();P.sh.splice(i,1);adSave(P)};
async function adShImport(){const csv=$('#shcsv').value,mode=$('#shmode').value;if(mode==='remplacer'&&!confirm('Remplacer tout le tarif par ces lignes ?'))return;
try{const r=await api('/params/sh/import',{method:'POST',json:{csv,mode}});AD.P=await api('/params');paintAdmin();adOk(`${r.importes} ligne(s) importée(s) : ${r.nouveaux} nouveau(x) code(s), ${r.mis_a_jour} mis à jour. Tarif : ${r.total} codes.`)}
catch(e){fail('Import refusé',e)}}

/* ---------- Régimes ---------- */
function adReg(){return`<div class="card"><h3>Régimes douaniers</h3>${AD.P.reg.map((r,i)=>`<div class="al">${esc(r)} <button class="dg sm" style="margin-left:auto" onclick="adRegDel(${i})">Retirer</button></div>`).join('')}
<form class="bar" style="margin-top:12px" onsubmit="return adRegAdd(event)"><input name="r" placeholder="Nouveau régime" required><button class="pri">Ajouter</button></form>
<p class="mut">Les incoterms (EXW, FOB, CIF, DAP…) suivent la liste officielle de la CCI et ne se paramètrent pas.</p></div>`}
function adRegAdd(e){e.preventDefault();const P=clone();P.reg.push(new FormData(e.target).get('r'));adSave(P);return false}
const adRegDel=i=>{if(!confirm('Retirer ce régime ? Les dossiers existants gardent leur régime.'))return;const P=clone();P.reg.splice(i,1);adSave(P)};

/* ---------- Journal d'audit ---------- */
const jParams=()=>{const p=new URLSearchParams();Object.entries(AD.jf).forEach(([k,v])=>{if(v)p.set(k,v)});return p};
async function adJournal(){try{AD.J=await api('/audit?limit=500&'+jParams())}catch(e){return adPaint(`<p class="note">${esc(e.message)}</p>`)}const F=AD.jf;
adPaint(`<div class="bar"><input placeholder="Action ou détail" value="${esc(F.q)}" onchange="AD.jf.q=this.value;adJournal()"><select onchange="AD.jf.entite=this.value;adJournal()"><option value="">Tous les objets</option>${ENTITES.map(x=>`<option ${x===F.entite?'selected':''}>${x}</option>`).join('')}</select>
<input placeholder="Utilisateur" value="${esc(F.utilisateur)}" onchange="AD.jf.utilisateur=this.value;adJournal()"><label class="mut">Du <input type="date" value="${F.du}" onchange="AD.jf.du=this.value;adJournal()"></label><label class="mut">au <input type="date" value="${F.au}" onchange="AD.jf.au=this.value;adJournal()"></label>
<button class="ghost" onclick="adJournalCsv()">Exporter (CSV)</button></div><div class="card tbl"><table><tr><th>Date</th><th>Utilisateur</th><th>Objet</th><th>Action</th><th>Détail</th></tr>
${AD.J.map(j=>`<tr><td>${hfr(j.ts)}</td><td>${esc(j.utilisateur)}</td><td>${esc(j.entite)}${j.entite_id?` <span class="mut">#${j.entite_id}</span>`:''}</td><td>${esc(j.action)}</td><td>${esc(j.detail)}</td></tr>`).join('')||'<tr><td colspan="5" class="mut">Aucune entrée.</td></tr>'}</table></div>
<p class="mut">500 dernières entrées affichées ; l’export CSV en contient jusqu’à 5 000.</p>`)}
async function adDl(url,nom){try{const r=await fetch('/api'+url,{headers:{Authorization:'Bearer '+getTok()}});if(!r.ok)throw new Error('Téléchargement impossible ('+r.status+')');
const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download=nom;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)}catch(e){fail('Téléchargement',e)}}
const adJournalCsv=()=>adDl('/audit/export.csv?'+jParams(),'journal-audit.csv');

/* ---------- Système ---------- */
async function adSys(){try{AD.sys=await api('/admin/systeme')}catch(e){return adPaint(`<p class="note">${esc(e.message)}</p>`)}const s=AD.sys;
adPaint(`<div class="card"><h3>Intégrations</h3>${s.integrations.map(i=>`<div class="al"><span class="b ${i.etat==='connecté'||i.etat==='prêt'?'ok':i.etat==='simulé'?'wa':''}">${esc(i.etat)}</span> <b>${esc(i.nom)}</b> <span class="mut">${esc(i.detail)}</span></div>`).join('')}</div>
<div class="card"><h3>Données</h3><div class="g"><div><span>Base de données</span>${esc(s.base_de_donnees)}</div><div><span>Hébergement</span>${esc(s.hebergement)}</div><div><span>Taux mis à jour le</span>${dfr(s.taux_maj)}</div></div>
<div class="tbl" style="margin-top:12px"><table><tr><th>Table</th><th>Lignes</th></tr>${Object.entries(s.volumes).filter(([,n])=>n).map(([t,n])=>`<tr><td class="mono">${esc(t)}</td><td>${nf(n)}</td></tr>`).join('')}</table></div></div>
<div class="card"><h3>Sauvegarde et archivage</h3><p>${esc(s.sauvegardes)}</p><div class="bar"><button class="pri" onclick="adDl('/admin/export.json','alliance-export.json')">Exporter les données (JSON)</button></div>
<p class="mut">L’export contient toutes les données métier, sans les fichiers joints ni les mots de passe. Il est tracé dans le journal.</p></div>`)}
