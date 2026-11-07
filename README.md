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
`public/index.html` exige maintenant une connexion à l'API (comptes et rôles réels). Les modules dossiers, transit, douane et facturation tournent encore sur des données de démonstration stockées dans le navigateur : les brancher sur l'API est l'étape suivante.

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
