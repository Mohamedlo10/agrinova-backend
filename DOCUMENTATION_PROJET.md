# Agrinova — Documentation technique du projet

> Document d'analyse de l'existant destiné à préparer la partie technique d'une soutenance.
> Les diagrammes ne sont pas tracés ici : ils sont **décrits en détail** pour qu'une autre
> personne puisse les réaliser (sous PlantUML, Mermaid, draw.io, StarUML, Looping, etc.).

---

## 1. Description générale du projet

**Agrinova** est une **marketplace agricole** (place de marché en ligne) conçue pour le
contexte sénégalais. La plateforme met en relation directe deux types d'utilisateurs :

- les **producteurs** (agriculteurs) qui publient et vendent leurs récoltes ;
- les **acheteurs** (consommateurs, commerçants) qui parcourent, commandent et notent les produits.

L'objectif est de **désintermédier** la vente de produits agricoles : un agriculteur publie
ses produits (légumes, fruits, céréales, légumineuses), fixe un prix en FCFA, et un acheteur
passe commande directement, avec livraison et paiement mobile (Wave, Orange Money…).

La plateforme intègre des dimensions **sociales** (fil d'actualité, likes, commentaires,
messagerie privée) et une **assistance par intelligence artificielle** : un chatbot
(**AgrinovaBot**) qui répond aux questions agronomiques, analyse les statistiques de
l'utilisateur connecté et effectue des recherches en temps réel dans le catalogue.

### Architecture globale

L'application suit une architecture **client / serveur découplée** (API REST) :

- **Frontend** : application web **React** (SPA) — réalisée séparément.
- **Backend** : API REST en **Python / FastAPI** (le présent dépôt).
- **Base de données** : **PostgreSQL**.
- **IA** : service externe **Groq** (modèle LLaMA 3.3 70B) via appel API.
- **Stockage des images** : système de fichiers du serveur (dossier `static/images`).

```
┌──────────────┐     HTTP/JSON      ┌────────────────────┐      SQL       ┌──────────────┐
│   Frontend   │  ───────────────►  │   Backend FastAPI  │  ───────────►  │  PostgreSQL  │
│   (React)    │  ◄───────────────  │   (API REST /api)  │  ◄───────────  │              │
└──────────────┘   JWT Bearer       └─────────┬──────────┘                └──────────────┘
                                              │ HTTPS
                                              ▼
                                       ┌────────────┐
                                       │  Groq API  │  (LLaMA 3.3 70B — AgrinovaBot)
                                       └────────────┘
```

---

## 2. Outils et technologies utilisés

### Backend (ce dépôt)

| Domaine | Outil / Techno | Version | Rôle |
|---|---|---|---|
| Langage | **Python** | 3.12 | Langage du backend |
| Framework web | **FastAPI** | 0.135.3 | API REST, validation, docs auto (Swagger) |
| Serveur ASGI | **Uvicorn** | 0.44.0 | Serveur d'exécution de l'API |
| ORM | **SQLAlchemy** | 2.0.49 | Mapping objet-relationnel, requêtes |
| Validation / Schémas | **Pydantic** | 2.12.5 | Validation des entrées/sorties (DTO) |
| Base de données | **PostgreSQL** | 16 | Stockage relationnel |
| Driver BD | **psycopg2-binary** | 2.9.11 | Connexion Python ↔ PostgreSQL |
| Authentification | **python-jose** | 3.5.0 | Génération/validation des tokens **JWT** |
| Hachage mot de passe | **passlib + bcrypt** | 1.7.4 / 4.0.1 | Stockage sécurisé des mots de passe |
| IA / LLM | **groq** (SDK) | ≥0.9.0 | Client de l'API Groq (chatbot) |
| Traitement images | **Pillow (PIL)** | 10.4.0 | Redimensionnement/compression des uploads |
| Upload fichiers | **python-multipart** | 0.0.24 | Gestion des fichiers `multipart/form-data` |
| Config | **python-dotenv** | 1.2.2 | Chargement des variables d'environnement |
| CORS | **Starlette CORSMiddleware** | — | Autorisation des appels cross-origin |

### Frontend
- **React** (application SPA), consommant l'API REST en JSON et stockant le token JWT côté client.

### IA
- **Groq** — fournisseur d'inférence LLM.
- Modèle : **`llama-3.3-70b-versatile`**.
- Utilisation du **function calling** (tool calling) pour la recherche produits.

### Déploiement / Infrastructure
- **Docker** (image `python:3.12-slim`) + **Docker Compose** (services `db` PostgreSQL + `backend`).
- Volumes persistants : `postgres_data` (BD) et `static_images` (images uploadées).
- Healthcheck PostgreSQL, politique `restart: unless-stopped`.
- Variables d'environnement : `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`,
  `GROQ_API_KEY`, `FRONTEND_URL`, `SERVER_URL`, `ENV`.

### Organisation du code backend
```
agrinova-backend/
├── main.py              # Point d'entrée FastAPI : app, CORS, montage static, routes
├── app/
│   ├── database.py      # Connexion SQLAlchemy, engine, session, Base
│   ├── models.py        # Modèles ORM (tables)
│   ├── auth.py          # JWT, hachage, dépendances de sécurité (rôles)
│   ├── routes.py        # Tous les endpoints REST + schémas Pydantic + helpers
│   └── bot.py           # Logique du chatbot IA (Groq + tool calling + contexte)
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 3. Fonctionnalités

### 3.1 Authentification & comptes
- **Inscription** (`POST /api/auth/inscription`) avec choix du rôle (`acheteur` ou `producteur`).
- **Connexion** (`POST /api/auth/connexion`) renvoyant un **token JWT** + infos utilisateur.
- **Profil courant** (`GET /api/auth/moi`).
- **Mise à jour du profil** (`PUT /api/auth/profile`) : nom, email, téléphone, localisation, bio, photo.
- Sécurité : mots de passe hachés (bcrypt), migration transparente des anciens hash SHA256,
  contrôle d'accès par rôle (`exiger_producteur`, `exiger_acheteur`).

### 3.2 Produits (catalogue)
- **Lister/filtrer** les produits (`GET /api/produits`) : par catégorie, recherche texte, prix max, localisation.
- **Détail** d'un produit (`GET /api/produits/{id}`).
- **Créer** un produit (`POST /api/produits`) — réservé aux producteurs.
- **Modifier** (`PUT /api/produits/{id}`), **supprimer** (`DELETE /api/produits/{id}`).
- **Basculer la disponibilité** (`PUT /api/produits/{id}/disponibilite`).
- **Mes produits** (`GET /api/mes-produits`) — vue producteur.

### 3.3 Commandes
- **Passer commande** (`POST /api/commandes`) : vérifie le stock, décrémente la quantité, calcule le montant, génère un numéro.
- **Mes commandes** (`GET /api/mes-commandes`) : vue adaptée acheteur / producteur.
- **Mise à jour du statut** (`PUT /api/commandes/{id}/statut`) : `en_attente → confirmee → expediee → livree` / `annulee`.
- Paiement : champ `methode_paiement` (ex. Wave) — la commande enregistre le mode choisi.

### 3.4 Avis & réputation
- **Laisser un avis** (`POST /api/avis`) : note 1–5 + commentaire, rattaché à une commande.
- Recalcule automatiquement la **note globale** et le **nombre d'avis** du producteur.
- **Avis d'un agriculteur** (`GET /api/avis/agriculteur/{id}`).

### 3.5 Messagerie privée
- **Conversations** (`GET /api/conversations`) : liste des fils, dernier message, compteur de non-lus.
- **Envoyer un message** (`POST /api/messages`).
- **Historique d'une conversation** (`GET /api/messages/{autre_id}`) : marque les messages comme lus.

### 3.6 Réseau social / Fil d'actualité
- **Fil d'actualité** paginé (`GET /api/feed`).
- **Créer / supprimer un post** (`POST /api/posts`, `DELETE /api/posts/{id}`).
- **Like / unlike** (`POST /api/posts/{id}/like`).
- **Commentaires** (`GET` / `POST /api/posts/{id}/commentaires`).

### 3.7 Profils publics & annuaire
- **Profil public** (`GET /api/profil/{id}`) : infos, produits en vente, avis, posts.
- **Annuaire des agriculteurs** (`GET /api/agriculteurs`) : recherche, tri par note.
- **Recherche globale** (`GET /api/recherche`) : produits + agriculteurs en une requête.

### 3.8 Upload d'images
- **Upload** (`POST /api/upload/image`) : validation du type, taille max 10 Mo, conversion RGB,
  redimensionnement (max 1200 px), compression JPEG qualité 80, nom UUID, renvoie l'URL publique.

### 3.9 Chatbot IA — AgrinovaBot
- **Discuter** (`POST /api/bot/chat`), **historique** (`GET /api/bot/historique`), **réinitialiser** (`DELETE /api/bot/reset`).
- Construit un **contexte temps réel** de l'utilisateur (profil + produits + commandes + revenus + avis pour un producteur ; commandes + dépenses pour un acheteur).
- **Mémoire conversationnelle** : 20 derniers échanges stockés en base (`conversation_bot`).
- **Function calling** : l'outil `rechercher_produits` interroge le catalogue en direct (nom, catégorie, prix max, localisation).
- Répond aux questions agronomiques générales avec ses connaissances, et aux questions de stats avec les données réelles.

---

## 4. Description de la base de données (pour tracer le MCD / MLD / diagramme BD)

La base est **PostgreSQL**. Elle comprend **9 tables**. Ci-dessous, chaque table avec ses
colonnes, types et contraintes. Les types sont donnés en équivalent SQL standard.

### Table `utilisateurs`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK**, auto-incrément |
| nom | VARCHAR(100) | NOT NULL |
| email | VARCHAR(150) | UNIQUE, NOT NULL, indexé |
| telephone | VARCHAR(20) | |
| mot_de_passe | VARCHAR(255) | NOT NULL (haché bcrypt) |
| role | VARCHAR(20) | défaut `acheteur` (valeurs : `acheteur`, `producteur`) |
| localisation | VARCHAR(200) | |
| photo_profil | VARCHAR(500) | URL |
| bio | TEXT | |
| note_globale | FLOAT | défaut 0.0 |
| nombre_avis | INTEGER | défaut 0 |
| est_verifie | BOOLEAN | défaut false |
| date_inscription | DATETIME | défaut now() |

### Table `produits`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| nom | VARCHAR(200) | NOT NULL |
| description | TEXT | |
| prix | FLOAT | NOT NULL |
| unite | VARCHAR(50) | défaut `kg` |
| quantite_disponible | INTEGER | défaut 0 |
| categorie | VARCHAR(100) | (Légumes, Fruits, Céréales, Légumineuses) |
| photo | VARCHAR(500) | URL |
| localisation | VARCHAR(200) | |
| est_disponible | BOOLEAN | défaut true |
| date_publication | DATETIME | défaut now() |
| agriculteur_id | INTEGER | **FK → utilisateurs.id** |

### Table `commandes`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| quantite | INTEGER | NOT NULL |
| montant_total | FLOAT | NOT NULL |
| statut | VARCHAR(50) | défaut `en_attente` |
| adresse_livraison | TEXT | |
| methode_paiement | VARCHAR(50) | |
| date_commande | DATETIME | défaut now() |
| acheteur_id | INTEGER | **FK → utilisateurs.id** |
| agriculteur_id | INTEGER | **FK → utilisateurs.id** |
| produit_id | INTEGER | **FK → produits.id** |

### Table `avis`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| note | INTEGER | 1 à 5 |
| commentaire | TEXT | |
| date_avis | DATETIME | défaut now() |
| commande_id | INTEGER | **FK → commandes.id** (relation 1–1) |
| auteur_id | INTEGER | **FK → utilisateurs.id** |
| agriculteur_id | INTEGER | **FK → utilisateurs.id** |

### Table `messages`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| contenu | TEXT | NOT NULL |
| est_lu | BOOLEAN | défaut false |
| date_envoi | DATETIME | défaut now() |
| expediteur_id | INTEGER | **FK → utilisateurs.id** |
| destinataire_id | INTEGER | **FK → utilisateurs.id** |

### Table `conversation_bot`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| user_id | INTEGER | **FK → utilisateurs.id**, NOT NULL |
| role | VARCHAR(20) | NOT NULL (`user` ou `assistant`) |
| contenu | TEXT | NOT NULL |
| date_envoi | DATETIME | défaut now() |

### Table `posts`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| contenu | TEXT | NOT NULL |
| photo | VARCHAR(500) | URL |
| date_publication | DATETIME | défaut now() |
| auteur_id | INTEGER | **FK → utilisateurs.id**, NOT NULL |

### Table `post_likes`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| post_id | INTEGER | **FK → posts.id**, NOT NULL |
| user_id | INTEGER | **FK → utilisateurs.id**, NOT NULL |

### Table `post_commentaires`
| Colonne | Type | Contraintes |
|---|---|---|
| id | INTEGER | **PK** |
| contenu | TEXT | NOT NULL |
| date_commentaire | DATETIME | défaut now() |
| post_id | INTEGER | **FK → posts.id**, NOT NULL |
| auteur_id | INTEGER | **FK → utilisateurs.id**, NOT NULL |

### Relations à représenter sur le diagramme (cardinalités)
- **Utilisateur (1) — (N) Produit** : un producteur publie plusieurs produits (`produits.agriculteur_id`).
- **Utilisateur (1) — (N) Commande** *en tant qu'acheteur* (`commandes.acheteur_id`).
- **Utilisateur (1) — (N) Commande** *en tant que producteur/vendeur* (`commandes.agriculteur_id`).
  → Double association entre `utilisateurs` et `commandes` (deux rôles).
- **Produit (1) — (N) Commande** (`commandes.produit_id`).
- **Commande (1) — (1) Avis** (`avis.commande_id`, `uselist=False`).
- **Utilisateur (1) — (N) Avis** (auteur de l'avis et producteur évalué : deux FK).
- **Utilisateur (1) — (N) Message** (expéditeur et destinataire : deux FK, auto-relation).
- **Utilisateur (1) — (N) ConversationBot** (`conversation_bot.user_id`).
- **Utilisateur (1) — (N) Post** (`posts.auteur_id`, suppression en cascade).
- **Post (1) — (N) PostLike** (cascade) et **Utilisateur (1) — (N) PostLike**.
- **Post (1) — (N) PostCommentaire** (cascade) et **Utilisateur (1) — (N) PostCommentaire**.

> **Note pour le MCD** : `post_likes` est une table d'association (N–N) entre `utilisateurs` et
> `posts` matérialisant le « j'aime ». De même, les commandes peuvent être vues comme
> l'association centrale entre acheteur, producteur et produit.

---

## 5. Description du diagramme de classes (pour le tracer en UML)

Le diagramme de classes reflète les modèles ORM (`app/models.py`). Chaque table = une classe.
Indiquer les **attributs** (cf. section 4) et les **associations** (cf. cardinalités).

### Classes métier (entités)

**`Utilisateur`**
- Attributs : `id, nom, email, telephone, mot_de_passe, role, localisation, photo_profil, bio, note_globale, nombre_avis, est_verifie, date_inscription`.
- Associations :
  - `1 → *` `Produit` (produits publiés)
  - `1 → *` `Commande` (en tant qu'acheteur)
  - `1 → *` `Commande` (en tant qu'agriculteur)
  - `1 → *` `Post` (composition / cascade)
  - `1 → *` `Avis`, `Message`, `ConversationBot`, `PostLike`, `PostCommentaire`

**`Produit`**
- Attributs : `id, nom, description, prix, unite, quantite_disponible, categorie, photo, localisation, est_disponible, date_publication, agriculteur_id`.
- Associations : `* → 1` `Utilisateur` (agriculteur) ; `1 → *` `Commande`.

**`Commande`**
- Attributs : `id, quantite, montant_total, statut, adresse_livraison, methode_paiement, date_commande, acheteur_id, agriculteur_id, produit_id`.
- Associations : `* → 1` `Utilisateur` (acheteur), `* → 1` `Utilisateur` (agriculteur), `* → 1` `Produit`, `1 → 0..1` `Avis`.

**`Avis`**
- Attributs : `id, note, commentaire, date_avis, commande_id, auteur_id, agriculteur_id`.
- Associations : `0..1 → 1` `Commande` ; `* → 1` `Utilisateur` (auteur), `* → 1` `Utilisateur` (agriculteur évalué).

**`Message`**
- Attributs : `id, contenu, est_lu, date_envoi, expediteur_id, destinataire_id`.
- Association réflexive : `* → 1` `Utilisateur` (expéditeur) et `* → 1` `Utilisateur` (destinataire).

**`ConversationBot`**
- Attributs : `id, user_id, role, contenu, date_envoi`.
- Association : `* → 1` `Utilisateur`. (Mémoire des échanges avec AgrinovaBot.)

**`Post`**
- Attributs : `id, contenu, photo, date_publication, auteur_id`.
- Associations : `* → 1` `Utilisateur` (auteur) ; `1 → *` `PostLike` (composition) ; `1 → *` `PostCommentaire` (composition).

**`PostLike`**
- Attributs : `id, post_id, user_id`.
- Associations : `* → 1` `Post`, `* → 1` `Utilisateur`.

**`PostCommentaire`**
- Attributs : `id, contenu, date_commentaire, post_id, auteur_id`.
- Associations : `* → 1` `Post`, `* → 1` `Utilisateur`.

### Classes techniques (optionnel, pour un diagramme « architecture »)
Si la soutenance attend aussi la couche service/contrôleur, on peut représenter :
- **Couche Contrôleur** : `router` (FastAPI) regroupant les endpoints par domaine
  (Auth, Produits, Commandes, Avis, Messages, Posts, Bot).
- **Couche Sécurité** : module `auth` — opérations `hasher_mdp()`, `verifier_mdp()`,
  `creer_token()`, `get_utilisateur_actuel()`, `exiger_producteur()`, `exiger_acheteur()`.
- **Couche IA** : module `bot` — `chat_avec_groq()`, `_construire_contexte()`,
  `_executer_recherche_produits()`, `_system_prompt()`.
- **Couche Persistance** : `database` (engine, `SessionLocal`, `get_db()`) + les entités ci-dessus.
- **DTO / Schémas Pydantic** : `InscriptionSchema`, `ConnexionSchema`, `ProduitSchema`,
  `CommandeSchema`, `AvisSchema`, `MessageSchema`, `PostSchema`, `BotMessageSchema`, etc.

> Stéréotypes UML suggérés : `<<entity>>` pour les modèles, `<<controller>>` pour le router,
> `<<service>>` pour `bot`/`auth`, `<<dto>>` pour les schémas Pydantic.

---

## 6. Descriptions des diagrammes de séquence (pour les tracer en UML)

Voici plusieurs scénarios clés. Acteurs/participants à représenter sur chaque diagramme :
**Utilisateur (navigateur React)**, **API FastAPI (router)**, **Module Auth**,
**Base de données (PostgreSQL via SQLAlchemy)**, et pour le bot **API Groq**.

### 6.1 Séquence — Inscription
1. L'**Utilisateur** (React) envoie `POST /api/auth/inscription` avec `{nom, email, mot_de_passe, role, …}`.
2. L'**API** demande à la **BD** si l'email existe déjà (`SELECT … WHERE email`).
3. Si oui → réponse `400 Email déjà utilisé` (fin de l'alternative).
4. Sinon, l'**API** appelle **Auth** `hasher_mdp()` pour hacher le mot de passe (bcrypt).
5. L'**API** insère l'utilisateur en **BD** (`INSERT`), commit, refresh.
6. L'**API** appelle **Auth** `creer_token()` → génère le **JWT**.
7. L'**API** renvoie `{token, utilisateur}` à l'**Utilisateur**.

### 6.2 Séquence — Connexion (avec migration de hash)
1. `POST /api/auth/connexion` `{email, mot_de_passe}`.
2. **API** → **BD** : récupération de l'utilisateur par email.
3. **API** → **Auth** `verifier_mdp()` (teste d'abord un éventuel hash legacy SHA256, puis bcrypt).
4. Si invalide → `401 Email ou mot de passe incorrect`.
5. *Optionnel (alt)* : si le hash stocké était en SHA256, l'**API** le **re-hache en bcrypt** et met à jour la **BD**.
6. **API** → **Auth** `creer_token()` → JWT.
7. **API** renvoie `{token, utilisateur}`.

### 6.3 Séquence — Publier un produit (producteur authentifié)
1. `POST /api/produits` avec en-tête `Authorization: Bearer <JWT>` et le corps du produit.
2. **API** → **Auth** `get_utilisateur_actuel()` : décode le JWT, charge l'utilisateur depuis la **BD**.
3. **Auth** `exiger_producteur()` : vérifie `role == producteur` (sinon `403`).
4. **API** insère le `Produit` en **BD** (`INSERT`), commit, refresh.
5. **API** renvoie `{message, produit}`.

### 6.4 Séquence — Passer une commande (cœur métier)
1. L'**Acheteur** envoie `POST /api/commandes` `{produit_id, quantite, adresse_livraison, methode_paiement}` + JWT.
2. **API** → **Auth** : authentifie l'utilisateur via le JWT.
3. **API** → **BD** : `SELECT` du produit par `produit_id`.
   - alt : produit introuvable → `404`.
4. **API** vérifie le stock : `quantite_disponible >= quantite`.
   - alt : stock insuffisant → `400 Stock insuffisant`.
5. **API** calcule `montant_total = prix × quantite`.
6. **API** crée la `Commande` et **décrémente** `produit.quantite_disponible` (même transaction).
7. **API** commit en **BD**, génère un **numéro** (`AG-#####`).
8. **API** renvoie `{message, numero, commande_id, montant}`.

> Variante à montrer : **mise à jour du statut** (`PUT /api/commandes/{id}/statut`) où le producteur
> fait évoluer la commande `en_attente → confirmee → expediee → livree`.

### 6.5 Séquence — Laisser un avis (avec recalcul de la note)
1. **Acheteur** : `POST /api/avis` `{commande_id, note, commentaire}` + JWT.
2. **API** valide la note (1–5) → sinon `400`.
3. **API** → **BD** : charge la commande (sinon `404`).
4. **API** insère l'`Avis` lié à la commande et au producteur.
5. **API** → **BD** : charge le producteur, **recalcule** `note_globale` et incrémente `nombre_avis`.
6. **API** commit, renvoie `{message, nouvelle_note}`.

### 6.6 Séquence — Discuter avec AgrinovaBot (IA + function calling) ⭐
C'est le scénario le plus riche pour la soutenance. Participants :
**Utilisateur, API (router), Module Bot, BD, API Groq**.

1. **Utilisateur** : `POST /api/bot/chat` `{message}` + JWT.
2. **API** → **Auth** : authentifie l'utilisateur.
3. **API** → **Bot** `chat_avec_groq(message, user, db)`.
4. **Bot** → **BD** : `_construire_contexte()` agrège le profil + produits + commandes + revenus + avis (producteur) ou commandes + dépenses (acheteur).
5. **Bot** → **BD** : charge les **20 derniers** messages de `conversation_bot` (mémoire).
6. **Bot** construit la liste des messages (`system` + historique + message utilisateur) et **1er appel** à **Groq** `chat.completions.create(..., tools=[rechercher_produits], tool_choice="auto")`.
7. **Groq** répond :
   - **alt A — sans outil** : renvoie directement le texte de réponse.
   - **alt B — avec `tool_calls`** :
     a. **Bot** lit l'appel d'outil `rechercher_produits(args)`, **nettoie/valide** les arguments (nom, catégorie ∈ liste, prix_max numérique > 0, localisation).
     b. **Bot** → **BD** : `_executer_recherche_produits()` exécute la requête filtrée sur `produits` (disponibles, triés par prix).
     c. **Bot** ajoute le résultat de l'outil aux messages et fait un **2e appel** à **Groq** pour la réponse finale.
8. **Bot** → **BD** : sauvegarde les deux tours (`user` + `assistant`) dans `conversation_bot`, commit.
9. **Bot** renvoie le texte ; l'**API** répond `{reponse, user}` à l'**Utilisateur**.

> Gestion d'erreur à illustrer : si Groq échoue, le bot renvoie un message de repli
> (« difficulté technique momentanée »).

### 6.7 Séquence — Upload d'image
1. **Utilisateur** : `POST /api/upload/image` (multipart, fichier) + JWT.
2. **API** → **Auth** : authentifie.
3. **API** valide le `content_type` (image/*) et la taille (≤ 10 Mo).
4. **API** ouvre l'image (**Pillow**), convertit en RGB, redimensionne (≤ 1200 px), compresse en JPEG (q=80).
5. **API** écrit le fichier sous `static/images/<uuid>.jpg`.
6. **API** renvoie `{url}` (URL publique servie via `/static`).

### 6.8 Séquence — Messagerie (envoi + lecture)
1. **Utilisateur A** : `POST /api/messages` `{destinataire_id, contenu}` + JWT → **API** insère le `Message`.
2. **Utilisateur B** : `GET /api/messages/{A_id}` → **API** charge les messages échangés, **marque comme lus** ceux destinés à B, commit, renvoie l'historique.
3. `GET /api/conversations` agrège le dernier message par interlocuteur + compteur de non-lus.

---

## 7. Sécurité (points à mentionner en soutenance)

- **Authentification stateless** par **JWT** (HS256), expiration configurable (`JWT_EXPIRE_MINUTES`, défaut 7 jours / 24 h selon l'env).
- **Hachage bcrypt** des mots de passe, avec **migration douce** depuis d'anciens hash SHA256.
- **Autorisation par rôle** via dépendances FastAPI (`exiger_producteur`, `exiger_acheteur`).
- **Vérification de propriété** : un producteur ne peut modifier/supprimer que ses propres produits.
- **CORS** restreint à l'URL du frontend en production.
- **Validation des entrées** par Pydantic, validation supplémentaire des arguments d'outil IA.
- **Désactivation de la doc Swagger** (`/docs`) en production.
- Secrets via variables d'environnement (jamais en dur).

---

## 8. Synthèse des endpoints (référence rapide)

| Méthode | Endpoint | Accès | Fonction |
|---|---|---|---|
| GET | `/` | public | Health check |
| POST | `/api/auth/inscription` | public | Créer un compte |
| POST | `/api/auth/connexion` | public | Se connecter (JWT) |
| GET | `/api/auth/moi` | authentifié | Profil courant |
| PUT | `/api/auth/profile` | authentifié | Modifier son profil |
| GET | `/api/recherche` | public | Recherche globale produits+agriculteurs |
| POST | `/api/upload/image` | authentifié | Uploader une image |
| GET | `/api/produits` | public | Lister/filtrer les produits |
| GET | `/api/produits/{id}` | public | Détail produit |
| POST | `/api/produits` | producteur | Créer un produit |
| PUT | `/api/produits/{id}` | producteur | Modifier un produit |
| PUT | `/api/produits/{id}/disponibilite` | producteur | Activer/masquer |
| DELETE | `/api/produits/{id}` | producteur | Supprimer |
| GET | `/api/mes-produits` | producteur | Ses produits |
| POST | `/api/commandes` | authentifié | Passer commande |
| GET | `/api/mes-commandes` | authentifié | Ses commandes |
| PUT | `/api/commandes/{id}/statut` | authentifié | Changer le statut |
| POST | `/api/avis` | authentifié | Laisser un avis |
| GET | `/api/avis/agriculteur/{id}` | public | Avis d'un agriculteur |
| GET | `/api/conversations` | authentifié | Liste des conversations |
| POST | `/api/messages` | authentifié | Envoyer un message |
| GET | `/api/messages/{autre_id}` | authentifié | Historique d'un fil |
| GET | `/api/profil/{id}` | public | Profil public complet |
| GET | `/api/agriculteurs` | public | Annuaire des producteurs |
| GET | `/api/feed` | authentifié | Fil d'actualité |
| POST | `/api/posts` | authentifié | Créer un post |
| DELETE | `/api/posts/{id}` | authentifié | Supprimer son post |
| POST | `/api/posts/{id}/like` | authentifié | Like / unlike |
| GET | `/api/posts/{id}/commentaires` | public | Commentaires d'un post |
| POST | `/api/posts/{id}/commentaires` | authentifié | Commenter |
| POST | `/api/bot/chat` | authentifié | Discuter avec AgrinovaBot |
| GET | `/api/bot/historique` | authentifié | Historique du chat IA |
| DELETE | `/api/bot/reset` | authentifié | Réinitialiser le chat |

---

## 9. Conseils pour réaliser les diagrammes

- **Diagramme de BD (MCD/MLD)** : Looping, MySQL Workbench, draw.io ou `dbdiagram.io`.
  Partir de la section 4 (tables + FK + cardinalités).
- **Diagramme de classes UML** : StarUML, PlantUML ou draw.io.
  Partir de la section 5 (une classe par entité, attributs typés, associations avec multiplicités).
- **Diagrammes de séquence** : PlantUML (`@startuml … @enduml`) ou draw.io.
  Partir de la section 6 (un diagramme par scénario ; bien faire apparaître les `alt` / `opt`).
- Pour PlantUML/Mermaid, chaque étape numérotée = une flèche `Participant -> Autre : message`.
```
