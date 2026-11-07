# Alliance Transit

Gestion du transit, du transport et de la douane (Guinée). Interface web (`public/`) et API FastAPI (`app/`, servie sous `/api`).

## Déployer sur Vercel
1. Poussez ce dossier sur GitHub, GitLab ou Bitbucket.
2. Sur vercel.com : **Add New > Project**, importez le dépôt. Aucun réglage de build n'est nécessaire.
3. Créez une base PostgreSQL : onglet **Storage** du projet, puis Neon (Marketplace). Copiez l'URL de connexion (de préférence l'URL « pooled ») dans la variable `DATABASE_URL`.
4. Ajoutez les variables d'environnement (voir `.env.example`) : `DATABASE_URL`, `SECRET_KEY` (`openssl rand -hex 32`), `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
5. Déployez. Au premier appel, les tables et le compte administrateur sont créés automatiquement.
6. Vérifiez : `https://<votre-projet>.vercel.app/api/health` puis `/api/docs`.

En ligne de commande : `npm i -g vercel && vercel --prod`.

L'API refuse de démarrer sur Vercel si `SECRET_KEY` ou `ADMIN_PASSWORD` manque.

## Comptes et utilisateurs
- **Compte administrateur** : il est créé automatiquement au premier appel de l'API, à partir de `ADMIN_EMAIL` et `ADMIN_PASSWORD`. Connectez-vous avec ces identifiants sur la page d'accueil.
- **Créer ou réinitialiser un administrateur à la main** (par exemple si le mot de passe est perdu), depuis votre ordinateur, avec l'URL de la base :

      DATABASE_URL="postgresql://..." python -m scripts.create_admin admin@exemple.com 'MotDePasse2026!'

- **Gestion des utilisateurs** : l'administrateur ouvre l'onglet « Utilisateurs » pour créer un compte, changer son rôle, le désactiver ou réinitialiser son mot de passe. Chaque utilisateur change son propre mot de passe avec « Mon mot de passe ».
- Règles : mot de passe de 10 caractères minimum avec lettres et chiffres, e-mail unique (sans distinction de casse), un utilisateur « Client » est rattaché à un client, un administrateur ne peut pas se désactiver lui-même. Toutes les actions sont tracées dans le journal d'audit.
- Les rôles : Administrateur, Responsable transit, Déclarant en douane, Agent opérationnel, Comptable, Commercial, Client, Direction.

## Limites de l'hébergement Vercel à connaître
- Les fonctions n'ont pas de disque persistant : les documents sont stockés dans PostgreSQL. Taille limitée à 4 Mo par fichier (plafond de Vercel : 4,5 Mo par requête). Pour des scans plus lourds, passer à un stockage objet (Vercel Blob, S3).
- Démarrage à froid : le premier appel après une période d'inactivité est plus lent.
- Durée maximale d'un appel : 30 s (réglable dans `vercel.json` selon le plan).
- Données de santé de l'application, sauvegardes et conservation de 10 ans : à assurer côté fournisseur PostgreSQL (sauvegardes automatiques, exports réguliers).
- Souveraineté des données : choisissez la région de la base selon vos exigences (point 17 du cahier des charges).

## Interface
`public/index.html` exige une connexion à l'API (comptes et rôles réels). Les écrans Dossiers, Transit, Douane, Opérations, Facturation et Utilisateurs sont branchés sur l'API. Le tableau de bord, Clients et Administration utilisent encore des données de démonstration stockées dans le navigateur.

## Module Douane
Menu « Douane » (personnel), traitement dans l'onglet Douane de chaque dossier (déclarant en douane et responsable transit ; quittance aussi pour le comptable).
- **Liste des déclarations** avec recherche (référence de déclaration ou douanière, dossier, client, quittance) et filtres par statut, dont « en attente de réponse ».
- **Indicateurs** : brouillons, transmises sans réponse, quittances à payer, contrôles, bons à enlever sur 30 jours, délai moyen de dédouanement (transmission → bon à enlever, sur 90 jours), attentes de plus de 3 jours, rejets.
- **Cycle** : projet généré depuis le dossier, contrôles de cohérence, transmission (liquidation figée à ce moment), acceptation avec référence douanière, contrôle, rejet motivé puis réouverture, bon à enlever.
- **Quittance** des droits et taxes (numéro, montant, date) : obligatoire avant le bon à enlever quand des droits sont dus ; elle est archivée sur la déclaration et inscrite automatiquement dans les coûts du dossier (catégorie « Droits et taxes »), avec signalement d'un écart avec la liquidation.

## Module Facturation
Menu « Facturation » (comptable, direction, commercial ; écriture des factures pour le comptable, des devis aussi pour le commercial et le responsable transit), et onglet « Facturation et marge » de chaque dossier.
- **Devis** depuis un dossier, en devise du client, avec validité et conditions : brouillon, envoyé, accepté ou refusé, puis facturé (avec ou sans débours). Un devis expiré ne peut plus être accepté.
- **Factures** multi-devises (taux paramétrables), refacturation des droits et taxes avancés, **avances** reçues avant facture et imputées automatiquement, **avoirs** numérotés `AV-AAAA-NNNN`, **règlements** partiels avec mode (virement, chèque, espèces, mobile money…) et référence. Statuts : impayée, partielle, en retard, payée, soldée (par avoir).
- **Relances** : liste des factures dues (dès le lendemain de l'échéance, puis tous les 15 jours), relance unitaire ou groupée, lettre générée selon le niveau (rappel amiable, deuxième relance, mise en demeure). L'envoi par e-mail ou SMS attend une passerelle.
- **Pilotage** : facturé et encaissé du mois, créances, retards, devis en attente, balance âgée (non échu, 1-30, 31-60, 61-90, plus de 90 jours).
- **Exports comptables** CSV compatibles Excel (factures, journal des ventes avec contre-valeur en devise de base, règlements), filtrables par période. Impression des factures et devis (PDF via le navigateur).

## Module Dossiers
Menu « Dossiers », branché sur l'API ; un client ne voit que ses propres dossiers.
- **Liste et recherche** par numéro, client (nom ou code), référence, désignation, code SH, numéro de conteneur, référence de déclaration ou de transit ; filtres par statut et par type.
- **Création et modification** (responsable transit) avec création du client à la volée, incoterm, agent en douane, lieu de livraison. Un dossier clôturé n'est plus modifiable ; un dossier facturé ne change plus de client.
- **Fiche** en onglets : résumé et étapes opérationnelles (dates prévues et réelles, écarts, retards ; les dates réelles se remplissent seules à partir des conteneurs, de la douane, du transit, des missions et de la facture), documents (pièces obligatoires, dépôt versionné, téléchargement), douane (liquidation, contrôles, transmission, réponses, messages), transit, opérations (conteneurs et missions), facturation avec coûts engagés et marge, journal (y compris missions et conteneurs).

## Module Transit
Menu « Transit », branché sur l'API (lecture pour tout le personnel, écriture pour le responsable transit et l'agent opérationnel).
- **Déclaration** rattachée à un dossier (création rapide du dossier et du client depuis l'écran si besoin) : bureaux de départ, de passage et de destination, itinéraire, expéditeur, destinataire, transporteur et marchandises (repris du dossier par défaut), véhicule et chauffeur du parc, scellés, garantie et montant, délai de route. Numéro automatique `TR-AAAA-NNNN`.
- **Suivi** : en préparation, déposée (transmise via la passerelle douanière, simulée pour l'instant), acceptée (référence douanière), en circulation, contrôlée, arrivée à destination, apurée, ou rejetée (motif obligatoire, puis correction et nouveau dépôt).
- **Contrôles** : pas de mise en circulation sans véhicule, scellé et garantie ; pas d'apurement tant qu'un bureau de passage n'est pas constaté (régularisation possible après l'arrivée) ; modification seulement en préparation ou après rejet.
- **Alertes** : délai de route dépassé, scellé cassé. **Historique** des échanges avec la douane (envois, réceptions, notes internes) et des incidents.
- La table `transits` existante reçoit ses nouvelles colonnes automatiquement au démarrage (`app/db.py`, `sync_columns`) ; les déclarations déjà enregistrées restent lisibles.

## Module Opérations (transport et suivi opérationnel)
Menu « Opérations », ouvert à l'administrateur, au responsable transit, à l'agent opérationnel (lecture et écriture) et à la direction (lecture). Entièrement branché sur l'API.
- **Planning des missions** : enlèvement, livraison, transfert, retour vide. Affectation d'un véhicule et d'un chauffeur, refus des doubles affectations le même jour, démarrage, incidents, annulation motivée, dernière position GPS (géolocalisation du téléphone ou saisie manuelle ; `POST /api/missions/{id}/position` est prêt pour un boîtier GPS).
- **Preuve de livraison** : nom du réceptionnaire, observations, signature tactile et photo facultative rangée dans les documents du dossier (type « Preuve de livraison »).
- **Conteneurs** : numéro contrôlé selon la norme ISO 6346, compagnie, navire, BL, ETA, arrivée, sortie, restitution du vide. Calcul des jours de magasinage et de détention au-delà des franchises. La sortie est enregistrée au démarrage d'un enlèvement, la restitution à la livraison d'un retour vide.
- **Parc** : véhicules et chauffeurs, avec alertes à 30 jours sur l'assurance, la visite technique et le permis.
- **Synthèse** : `GET /api/operations/resume` (missions du jour, en cours, en retard, conteneurs, véhicules disponibles, alertes).

Les nouvelles tables sont créées automatiquement au premier appel ; aucune table existante n'est modifiée.

## Développement local
    python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
    uvicorn app.main:app --reload     # SQLite par défaut, documentation sur /docs
    pytest

Avec Docker : `DB_PASSWORD=... SECRET_KEY=... ADMIN_PASSWORD=... docker compose up -d --build`

## État par rapport au cahier des charges
Fait : clients et utilisateurs (8 rôles), dossiers, documents, transit, douane (liquidation, contrôles, messages), facturation multi-devises, tableau de bord, audit, paramétrage des taxes.
À faire : liaison réelle avec SYDONIA World (`app/gateway.py`, simulée), interface branchée sur l'API et portail client, application mobile chauffeur dédiée (l'écran Opérations fonctionne déjà sur téléphone), boîtiers GPS et SMS/WhatsApp, migrations Alembic.

Taux de change, redevance statistique et prélèvement CEDEAO sont des valeurs d'exemple (`app/customs.py`, modifiables par `PUT /api/params`) : à caler sur une quittance SYDONIA réelle.
