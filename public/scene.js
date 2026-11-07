/* Illustration animée du port au crépuscule : porte-conteneurs, grues, avion, camion.
   Dessin original en SVG (aucune image externe). Animations en CSS (classes sc-*), coupées si l'utilisateur
   demande moins de mouvement. sceneSVG('full') pour la connexion, sceneSVG('band') pour le bandeau. */
function sceneSVG(mode){
const id='s'+Math.random().toString(36).slice(2,7),C=['#A3342B','#2A5A8C','#2C6B53','#D2AE5C','#C9C2B2','#7A4E8C','#B8612E'];
// Pile de conteneurs du navire : colonnes x rangées, couleurs tirées d'une suite fixe (pas de hasard d'un rendu à l'autre)
let cont='';for(let col=0;col<11;col++){const h=col===0||col===10?2:col%3===1?4:3;for(let r=0;r<h;r++){const c=C[(col*3+r*5)%C.length];
cont+=`<rect x="${392+col*38}" y="${592-r*17}" width="36" height="15" rx="1" fill="${c}"/><path d="M${398+col*38} ${594-r*17}v11M${404+col*38} ${594-r*17}v11M${410+col*38} ${594-r*17}v11M${416+col*38} ${594-r*17}v11M${422+col*38} ${594-r*17}v11" stroke="#0006" stroke-width="1"/>`}}
// Conteneurs empilés sur le quai
let quai='';[[1060,0],[1060,1],[1100,0],[1140,0],[1140,1],[1140,2],[1180,0],[1180,1]].forEach(([x,r],i)=>{quai+=`<rect x="${x}" y="${735-r*17}" width="38" height="15" rx="1" fill="${C[(i*2+1)%C.length]}" opacity=".92"/>`});
const etoiles=[[120,90],[260,150],[410,70],[560,130],[720,60],[880,120],[1010,80],[1180,140],[1320,70],[1460,110],[340,210],[960,200],[1250,220]]
  .map(([x,y],i)=>`<circle class="sc-star" style="animation-delay:${(i*0.7)%4}s" cx="${x}" cy="${y}" r="${i%3?1.2:1.8}" fill="#fff"/>`).join('');
const vague=y=>`M0 ${y} q50 -8 100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0 t100 0`;
const band=mode==='band';
return`<svg class="scene-svg" viewBox="${band?'0 455 1600 320':'0 0 1600 900'}" preserveAspectRatio="${band?'xMidYMid':'xMidYMax'} slice" aria-hidden="true" focusable="false">
<defs><linearGradient id="${id}ciel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#081426"/><stop offset=".45" stop-color="#14294A"/><stop offset=".75" stop-color="#5B4A63"/><stop offset="1" stop-color="#D08A4E"/></linearGradient>
<linearGradient id="${id}mer" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3E3F5C"/><stop offset=".3" stop-color="#1B2C49"/><stop offset="1" stop-color="#0A1628"/></linearGradient>
<radialGradient id="${id}sol" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#FFD9A0"/><stop offset=".35" stop-color="#F0A85A" stop-opacity=".8"/><stop offset="1" stop-color="#F0A85A" stop-opacity="0"/></radialGradient>
<linearGradient id="${id}trainee" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>
<rect width="1600" height="900" fill="url(#${id}ciel)"/>${etoiles}
<circle cx="1030" cy="600" r="210" fill="url(#${id}sol)"/><circle cx="1030" cy="600" r="46" fill="#FFD9A0" opacity=".95"/>
<!-- Avion et traînée -->
<g transform="translate(0 ${band?265:0})"><g class="sc-avion"><rect x="80" y="-2" width="420" height="3" fill="url(#${id}trainee)"/><g fill="#E9EEF5"><path d="M0 0 C10 -6 50 -7 76 -4 L84 0 L76 4 C50 7 10 6 0 0Z"/>
<path d="M30 -3 L50 -30 L59 -30 L48 -3Z"/><path d="M30 3 L50 30 L59 30 L48 3Z" opacity=".75"/><path d="M70 -3 L66 -15 L72 -15 L80 -3Z"/></g><circle cx="12" cy="0" r="1.6" fill="#FF5A4E" class="sc-feu"/></g></g>
<!-- Ville et colline lointaines -->
<path d="M0 600 L0 560 L60 560 L60 540 L90 540 L90 565 L150 565 L150 548 L170 548 L170 530 L190 530 L190 560 L260 560 L260 575 L1600 575 L1600 600Z" fill="#20223D" opacity=".85"/>
<path d="M1240 600 L1240 545 L1280 545 L1280 520 L1300 520 L1300 545 L1340 545 L1340 560 L1420 560 L1420 535 L1450 535 L1450 560 L1600 560 L1600 600Z" fill="#20223D" opacity=".85"/>
<!-- Mer et vagues -->
<rect y="600" width="1600" height="170" fill="url(#${id}mer)"/><rect x="980" y="602" width="100" height="160" fill="#FFD9A0" opacity=".12"/>
<g class="sc-vagues"><path d="${vague(640)}" stroke="#ffffff22" stroke-width="2" fill="none"/><path d="${vague(690)}" stroke="#ffffff16" stroke-width="2" fill="none" transform="translate(-50 0)"/><path d="${vague(740)}" stroke="#ffffff12" stroke-width="2" fill="none"/></g>
<!-- Porte-conteneurs -->
<g class="sc-navire"><path d="M330 622 L860 622 L835 672 L362 672 Z" fill="#0E1F36"/><path d="M335 632 L855 632 L851 640 L339 640Z" fill="#A3342B"/>
<rect x="800" y="540" width="44" height="82" fill="#E9E4D8"/><rect x="796" y="532" width="52" height="10" fill="#C9C2B2"/><rect x="826" y="512" width="8" height="22" fill="#A3342B"/>
<g fill="#5BB0E6" class="sc-hublots"><rect x="806" y="552" width="32" height="5"/><rect x="806" y="568" width="32" height="5"/><rect x="806" y="584" width="32" height="5"/></g>${cont}
<text x="380" y="660" font-family="IBM Plex Mono,monospace" font-size="12" fill="#E9E4D8" opacity=".75" letter-spacing="2">ALLIANCE</text></g>
<g class="sc-sillage"><path d="M860 664 q40 6 90 2 M856 670 q50 10 110 6" stroke="#ffffff30" stroke-width="2" fill="none"/></g>
<!-- Quai, grues et conteneurs à terre -->
<rect y="762" width="1600" height="138" fill="#0B1424"/><rect y="762" width="1600" height="6" fill="#2A3550"/>
<g stroke="#D2AE5C" stroke-width="7" fill="none" stroke-linejoin="round"><path d="M930 762 L955 470 M1005 762 L980 470 M940 650 L995 650 M935 560 L1000 560"/><path d="M880 470 L1120 470 L1120 488 L880 488Z" fill="#D2AE5C"/><path d="M955 470 L968 420 L980 470"/></g>
<g class="sc-chariot"><rect x="900" y="488" width="26" height="12" fill="#A3342B"/><line class="sc-cable" x1="913" y1="500" x2="913" y2="575" stroke="#D2AE5C" stroke-width="2"/><rect class="sc-crochet" x="895" y="575" width="36" height="15" fill="#2A5A8C"/></g>
<g stroke="#8E7440" stroke-width="5" fill="none"><path d="M1215 762 L1232 560 M1265 762 L1248 560 M1222 680 L1258 680"/><path d="M1180 560 L1340 560 L1340 572 L1180 572Z" fill="#8E7440"/></g>
${quai}
<!-- Route et camion -->
<rect y="800" width="1600" height="44" fill="#141E31"/><path d="M0 822 H1600" stroke="#D2AE5C" stroke-width="2" stroke-dasharray="26 22" opacity=".5"/>
<g class="sc-camion"><rect x="0" y="790" width="150" height="26" rx="1" fill="#2C6B53"/><path d="M6 793v20M14 793v20M22 793v20M30 793v20M38 793v20M46 793v20" stroke="#0005"/><rect x="0" y="816" width="150" height="5" fill="#2A3550"/>
<path d="M154 821 L154 792 Q154 784 162 784 L186 784 L198 800 L198 821Z" fill="#E9E4D8"/><path d="M174 788 L184 788 L192 800 L174 800Z" fill="#5BB0E6"/><rect x="196" y="812" width="5" height="4" fill="#FFD9A0" class="sc-phare"/>
<g fill="#0B1424" stroke="#6A7280" stroke-width="2"><circle class="sc-roue" cx="24" cy="826" r="7"/><circle class="sc-roue" cx="42" cy="826" r="7"/><circle class="sc-roue" cx="128" cy="826" r="7"/><circle class="sc-roue" cx="180" cy="826" r="7"/></g></g>
<rect y="844" width="1600" height="56" fill="#0B1424"/></svg>`}
