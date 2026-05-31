from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func as sqlfunc
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models import (
    Utilisateur, Produit, Commande, Avis, Message,
    ConversationBot, Post, PostLike, PostCommentaire
)
from app.auth import (
    hasher_mdp, verifier_mdp, creer_token,
    get_utilisateur_actuel, exiger_producteur
)

router = APIRouter()


# ══════════════════════════════════════════════
# SCHEMAS
# ══════════════════════════════════════════════

class InscriptionSchema(BaseModel):
    nom: str
    email: str
    mot_de_passe: str
    telephone: Optional[str] = None
    role: str = "acheteur"
    localisation: Optional[str] = None

class ConnexionSchema(BaseModel):
    email: str
    mot_de_passe: str

class ProfileUpdateSchema(BaseModel):
    nom: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    localisation: Optional[str] = None
    bio: Optional[str] = None
    photo_profil: Optional[str] = None

class ProduitSchema(BaseModel):
    nom: str
    description: Optional[str] = None
    prix: float
    unite: str = "kg"
    quantite_disponible: int
    categorie: Optional[str] = None
    photo: Optional[str] = None
    localisation: Optional[str] = None

class CommandeSchema(BaseModel):
    produit_id: int
    quantite: int
    adresse_livraison: str
    methode_paiement: str = "wave"

class AvisSchema(BaseModel):
    commande_id: int
    note: int
    commentaire: Optional[str] = None

class MessageSchema(BaseModel):
    destinataire_id: int
    contenu: str

class StatutSchema(BaseModel):
    statut: str

class BotMessageSchema(BaseModel):
    message: str

class PostSchema(BaseModel):
    contenu: str
    photo: Optional[str] = None

class CommentaireSchema(BaseModel):
    contenu: str


# ══════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════

def _produit_dict(p: Produit) -> dict:
    return {
        "id": p.id,
        "nom": p.nom,
        "description": p.description,
        "prix": p.prix,
        "unite": p.unite,
        "quantite_disponible": p.quantite_disponible,
        "categorie": p.categorie,
        "photo": p.photo,
        "localisation": p.localisation,
        "est_disponible": p.est_disponible,
        "date_publication": p.date_publication,
        "agriculteur_id": p.agriculteur_id,
        "agriculteur_nom": p.agriculteur.nom if p.agriculteur else None,
        "agriculteur_note": p.agriculteur.note_globale if p.agriculteur else None,
        "agriculteur_verifie": p.agriculteur.est_verifie if p.agriculteur else False,
        "agriculteur_localisation": p.agriculteur.localisation if p.agriculteur else None,
        "agriculteur_photo": p.agriculteur.photo_profil if p.agriculteur else None,
    }


def _user_public_dict(u: Utilisateur) -> dict:
    return {
        "id": u.id,
        "nom": u.nom,
        "role": u.role,
        "localisation": u.localisation,
        "photo_profil": u.photo_profil,
        "bio": u.bio,
        "note_globale": u.note_globale,
        "nombre_avis": u.nombre_avis,
        "est_verifie": u.est_verifie,
        "date_inscription": u.date_inscription,
    }


def _post_dict(p: Post, current_user_id: Optional[int] = None) -> dict:
    nb_likes = len(p.likes)
    liked = any(l.user_id == current_user_id for l in p.likes) if current_user_id else False
    nb_commentaires = len(p.commentaires)
    return {
        "id": p.id,
        "contenu": p.contenu,
        "photo": p.photo,
        "date_publication": p.date_publication,
        "auteur_id": p.auteur_id,
        "auteur_nom": p.auteur.nom if p.auteur else None,
        "auteur_photo": p.auteur.photo_profil if p.auteur else None,
        "auteur_role": p.auteur.role if p.auteur else None,
        "auteur_verifie": p.auteur.est_verifie if p.auteur else False,
        "nb_likes": nb_likes,
        "liked": liked,
        "nb_commentaires": nb_commentaires,
    }


# ══════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════

@router.post("/auth/inscription")
def inscription(data: InscriptionSchema, db: Session = Depends(get_db)):
    if db.query(Utilisateur).filter(Utilisateur.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    if data.role not in ["acheteur", "producteur"]:
        raise HTTPException(status_code=400, detail="Rôle invalide")

    user = Utilisateur(
        nom=data.nom,
        email=data.email,
        mot_de_passe=hasher_mdp(data.mot_de_passe),
        telephone=data.telephone,
        role=data.role,
        localisation=data.localisation,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = creer_token(user.email, user.role, user.id)
    return {
        "token": token,
        "utilisateur": {
            "id": user.id,
            "nom": user.nom,
            "email": user.email,
            "role": user.role,
            "telephone": user.telephone,
            "localisation": user.localisation,
            "photo_profil": user.photo_profil,
            "bio": user.bio,
            "note_globale": user.note_globale,
            "est_verifie": user.est_verifie,
        }
    }


@router.post("/auth/connexion")
def connexion(data: ConnexionSchema, db: Session = Depends(get_db)):
    user = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
    if not user or not verifier_mdp(data.mot_de_passe, user.mot_de_passe):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    # Re-hash with bcrypt if stored as legacy SHA256
    import hashlib
    sha_hash = hashlib.sha256(data.mot_de_passe.encode()).hexdigest()
    if user.mot_de_passe == sha_hash:
        user.mot_de_passe = hasher_mdp(data.mot_de_passe)
        db.commit()

    token = creer_token(user.email, user.role, user.id)
    return {
        "token": token,
        "utilisateur": {
            "id": user.id,
            "nom": user.nom,
            "email": user.email,
            "role": user.role,
            "telephone": user.telephone,
            "localisation": user.localisation,
            "photo_profil": user.photo_profil,
            "bio": user.bio,
            "note_globale": user.note_globale,
            "est_verifie": user.est_verifie,
        }
    }


@router.get("/auth/moi")
def mon_profil(user: Utilisateur = Depends(get_utilisateur_actuel)):
    return {
        "id": user.id,
        "nom": user.nom,
        "email": user.email,
        "role": user.role,
        "telephone": user.telephone,
        "localisation": user.localisation,
        "photo_profil": user.photo_profil,
        "bio": user.bio,
        "note_globale": user.note_globale,
        "nombre_avis": user.nombre_avis,
        "est_verifie": user.est_verifie,
    }


@router.put("/auth/profile")
def mettre_a_jour_profil(
    data: ProfileUpdateSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    if data.email and data.email != user.email:
        existing = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email déjà utilisé")

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if value is not None:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "utilisateur": {
            "id": user.id,
            "nom": user.nom,
            "email": user.email,
            "role": user.role,
            "telephone": user.telephone,
            "localisation": user.localisation,
            "photo_profil": user.photo_profil,
            "bio": user.bio,
            "note_globale": user.note_globale,
            "est_verifie": user.est_verifie,
        }
    }


# ══════════════════════════════════════════════
# RECHERCHE GLOBALE
# ══════════════════════════════════════════════

@router.get("/recherche")
def recherche_globale(q: str, db: Session = Depends(get_db)):
    """Recherche produits + agriculteurs."""
    terme = f"%{q}%"

    produits = (
        db.query(Produit)
        .filter(
            Produit.est_disponible == True,
            or_(
                Produit.nom.ilike(terme),
                Produit.description.ilike(terme),
                Produit.localisation.ilike(terme),
            )
        )
        .limit(10)
        .all()
    )

    agriculteurs = (
        db.query(Utilisateur)
        .filter(
            Utilisateur.role == "producteur",
            or_(
                Utilisateur.nom.ilike(terme),
                Utilisateur.localisation.ilike(terme),
                Utilisateur.bio.ilike(terme),
            )
        )
        .limit(8)
        .all()
    )

    return {
        "produits": [_produit_dict(p) for p in produits],
        "agriculteurs": [_user_public_dict(u) for u in agriculteurs],
    }


# ══════════════════════════════════════════════
# PRODUITS ROUTES
# ══════════════════════════════════════════════

@router.get("/produits")
def lister_produits(
    categorie: Optional[str] = None,
    recherche: Optional[str] = None,
    prix_max: Optional[float] = None,
    localisation: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Produit).filter(Produit.est_disponible == True)
    if categorie:
        query = query.filter(Produit.categorie == categorie)
    if recherche:
        query = query.filter(
            or_(
                Produit.nom.ilike(f"%{recherche}%"),
                Produit.localisation.ilike(f"%{recherche}%"),
            )
        )
    if prix_max:
        query = query.filter(Produit.prix <= prix_max)
    if localisation:
        query = query.filter(Produit.localisation.ilike(f"%{localisation}%"))

    produits = query.order_by(Produit.date_publication.desc()).all()
    return [_produit_dict(p) for p in produits]


@router.get("/produits/{produit_id}")
def detail_produit(produit_id: int, db: Session = Depends(get_db)):
    p = db.query(Produit).filter(Produit.id == produit_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return _produit_dict(p)


@router.post("/produits")
def creer_produit(
    data: ProduitSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_producteur)
):
    produit = Produit(
        nom=data.nom,
        description=data.description,
        prix=data.prix,
        unite=data.unite,
        quantite_disponible=data.quantite_disponible,
        categorie=data.categorie,
        photo=data.photo,
        localisation=data.localisation or user.localisation,
        agriculteur_id=user.id,
    )
    db.add(produit)
    db.commit()
    db.refresh(produit)
    return {
        "message": "Produit publié !",
        "produit": _produit_dict(produit)
    }


@router.put("/produits/{produit_id}")
def modifier_produit(
    produit_id: int,
    data: ProduitSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_producteur)
):
    produit = db.query(Produit).filter(
        Produit.id == produit_id,
        Produit.agriculteur_id == user.id
    ).first()
    if not produit:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(produit, key, val)
    db.commit()
    db.refresh(produit)
    return {"message": "Produit mis à jour !", "produit": _produit_dict(produit)}


@router.put("/produits/{produit_id}/disponibilite")
def toggle_disponibilite(
    produit_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_producteur)
):
    produit = db.query(Produit).filter(
        Produit.id == produit_id,
        Produit.agriculteur_id == user.id
    ).first()
    if not produit:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    produit.est_disponible = not produit.est_disponible
    db.commit()
    return {"est_disponible": produit.est_disponible}


@router.delete("/produits/{produit_id}")
def supprimer_produit(
    produit_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_producteur)
):
    produit = db.query(Produit).filter(
        Produit.id == produit_id,
        Produit.agriculteur_id == user.id
    ).first()
    if not produit:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    db.delete(produit)
    db.commit()
    return {"message": "Produit supprimé"}


@router.get("/mes-produits")
def mes_produits(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_producteur)
):
    produits = db.query(Produit).filter(Produit.agriculteur_id == user.id).order_by(Produit.date_publication.desc()).all()
    return [_produit_dict(p) for p in produits]


# ══════════════════════════════════════════════
# COMMANDES ROUTES
# ══════════════════════════════════════════════

@router.post("/commandes")
def passer_commande(
    data: CommandeSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    produit = db.query(Produit).filter(Produit.id == data.produit_id).first()
    if not produit:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    if produit.quantite_disponible < data.quantite:
        raise HTTPException(status_code=400, detail="Stock insuffisant")

    montant = produit.prix * data.quantite
    commande = Commande(
        acheteur_id=user.id,
        agriculteur_id=produit.agriculteur_id,
        produit_id=produit.id,
        quantite=data.quantite,
        montant_total=montant,
        adresse_livraison=data.adresse_livraison,
        methode_paiement=data.methode_paiement,
    )
    produit.quantite_disponible -= data.quantite
    db.add(commande)
    db.commit()
    db.refresh(commande)

    import random
    numero = f"AG-{random.randint(10000, 99999)}"
    return {
        "message": "Commande passée !",
        "numero": numero,
        "commande_id": commande.id,
        "montant": montant,
    }


@router.get("/mes-commandes")
def mes_commandes(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    if user.role == "acheteur":
        commandes = db.query(Commande).filter(Commande.acheteur_id == user.id).order_by(Commande.date_commande.desc()).all()
    else:
        commandes = db.query(Commande).filter(Commande.agriculteur_id == user.id).order_by(Commande.date_commande.desc()).all()

    result = []
    for c in commandes:
        result.append({
            "id": c.id,
            "quantite": c.quantite,
            "montant_total": c.montant_total,
            "statut": c.statut,
            "adresse_livraison": c.adresse_livraison,
            "methode_paiement": c.methode_paiement,
            "date_commande": c.date_commande,
            "produit_id": c.produit_id,
            "produit_nom": c.produit.nom if c.produit else None,
            "produit_unite": c.produit.unite if c.produit else None,
            "produit_prix": c.produit.prix if c.produit else None,
            "acheteur_id": c.acheteur_id,
            "acheteur_nom": c.acheteur.nom if c.acheteur else None,
            "agriculteur_id": c.agriculteur_id,
            "agriculteur_nom": c.agriculteur.nom if c.agriculteur else None,
        })
    return result


@router.put("/commandes/{commande_id}/statut")
def mettre_a_jour_statut(
    commande_id: int,
    data: StatutSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    statuts = ["en_attente", "confirmee", "expediee", "livree", "annulee"]
    if data.statut not in statuts:
        raise HTTPException(status_code=400, detail=f"Statut invalide. Valides: {statuts}")

    commande = db.query(Commande).filter(Commande.id == commande_id).first()
    if not commande:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    commande.statut = data.statut
    db.commit()
    return {"message": f"Statut mis à jour : {data.statut}"}


# ══════════════════════════════════════════════
# AVIS ROUTES
# ══════════════════════════════════════════════

@router.post("/avis")
def laisser_avis(
    data: AvisSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    if data.note < 1 or data.note > 5:
        raise HTTPException(status_code=400, detail="Note entre 1 et 5")

    commande = db.query(Commande).filter(Commande.id == data.commande_id).first()
    if not commande:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    avis = Avis(
        commande_id=data.commande_id,
        auteur_id=user.id,
        agriculteur_id=commande.agriculteur_id,
        note=data.note,
        commentaire=data.commentaire,
    )
    db.add(avis)

    agriculteur = db.query(Utilisateur).filter(Utilisateur.id == commande.agriculteur_id).first()
    if agriculteur:
        total = (agriculteur.note_globale * agriculteur.nombre_avis) + data.note
        agriculteur.nombre_avis += 1
        agriculteur.note_globale = round(total / agriculteur.nombre_avis, 2)

    db.commit()
    return {"message": "Avis enregistré !", "nouvelle_note": agriculteur.note_globale if agriculteur else None}


@router.get("/avis/agriculteur/{agriculteur_id}")
def avis_agriculteur(agriculteur_id: int, db: Session = Depends(get_db)):
    avis = db.query(Avis).filter(Avis.agriculteur_id == agriculteur_id).order_by(Avis.date_avis.desc()).all()
    result = []
    for a in avis:
        auteur = db.query(Utilisateur).filter(Utilisateur.id == a.auteur_id).first()
        result.append({
            "id": a.id,
            "note": a.note,
            "commentaire": a.commentaire,
            "date_avis": a.date_avis,
            "auteur_nom": auteur.nom if auteur else "Anonyme",
            "auteur_photo": auteur.photo_profil if auteur else None,
        })
    return result


# ══════════════════════════════════════════════
# MESSAGES ROUTES
# ══════════════════════════════════════════════

@router.get("/conversations")
def mes_conversations(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    tous_msgs = (
        db.query(Message)
        .filter(or_(Message.expediteur_id == user.id, Message.destinataire_id == user.id))
        .order_by(Message.date_envoi.desc())
        .all()
    )
    seen: set[int] = set()
    conversations = []
    for msg in tous_msgs:
        autre_id = msg.destinataire_id if msg.expediteur_id == user.id else msg.expediteur_id
        if autre_id in seen:
            continue
        seen.add(autre_id)
        autre = db.query(Utilisateur).filter(Utilisateur.id == autre_id).first()
        if not autre:
            continue
        non_lus = db.query(Message).filter(
            Message.expediteur_id == autre_id,
            Message.destinataire_id == user.id,
            Message.est_lu == False,
        ).count()
        conversations.append({
            "user_id": autre.id,
            "nom": autre.nom,
            "role": autre.role,
            "photo_profil": autre.photo_profil,
            "last_message": msg.contenu,
            "last_message_moi": msg.expediteur_id == user.id,
            "last_message_time": msg.date_envoi,
            "non_lus": non_lus,
        })
    return conversations


@router.post("/messages")
def envoyer_message(
    data: MessageSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    msg = Message(
        expediteur_id=user.id,
        destinataire_id=data.destinataire_id,
        contenu=data.contenu,
    )
    db.add(msg)
    db.commit()
    return {"message": "Message envoyé !"}


@router.get("/messages/{autre_id}")
def historique_messages(
    autre_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    msgs = db.query(Message).filter(
        or_(
            (Message.expediteur_id == user.id) & (Message.destinataire_id == autre_id),
            (Message.expediteur_id == autre_id) & (Message.destinataire_id == user.id),
        )
    ).order_by(Message.date_envoi).all()

    for m in msgs:
        if m.destinataire_id == user.id and not m.est_lu:
            m.est_lu = True
    db.commit()

    return [
        {
            "id": m.id,
            "contenu": m.contenu,
            "est_lu": m.est_lu,
            "date_envoi": m.date_envoi,
            "expediteur_id": m.expediteur_id,
            "destinataire_id": m.destinataire_id,
            "moi": m.expediteur_id == user.id,
        }
        for m in msgs
    ]


# ══════════════════════════════════════════════
# PROFILS PUBLICS
# ══════════════════════════════════════════════

@router.get("/profil/{user_id}")
def profil_public(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    produits = db.query(Produit).filter(
        Produit.agriculteur_id == user_id,
        Produit.est_disponible == True
    ).order_by(Produit.date_publication.desc()).all()

    avis = db.query(Avis).filter(Avis.agriculteur_id == user_id).order_by(Avis.date_avis.desc()).all()
    avis_avec_auteur = []
    for a in avis:
        auteur = db.query(Utilisateur).filter(Utilisateur.id == a.auteur_id).first()
        avis_avec_auteur.append({
            "id": a.id,
            "note": a.note,
            "commentaire": a.commentaire,
            "date_avis": a.date_avis,
            "auteur_nom": auteur.nom if auteur else "Anonyme",
            "auteur_photo": auteur.photo_profil if auteur else None,
        })

    posts = (
        db.query(Post)
        .filter(Post.auteur_id == user_id)
        .order_by(Post.date_publication.desc())
        .limit(20)
        .all()
    )

    return {
        "utilisateur": _user_public_dict(user),
        "produits": [_produit_dict(p) for p in produits],
        "avis": avis_avec_auteur,
        "posts": [_post_dict(p) for p in posts],
        "nb_produits": len(produits),
    }


@router.get("/agriculteurs")
def liste_agriculteurs(
    recherche: Optional[str] = None,
    localisation: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Utilisateur).filter(Utilisateur.role == "producteur")
    if recherche:
        terme = f"%{recherche}%"
        query = query.filter(
            or_(
                Utilisateur.nom.ilike(terme),
                Utilisateur.bio.ilike(terme),
                Utilisateur.localisation.ilike(terme),
            )
        )
    if localisation:
        query = query.filter(Utilisateur.localisation.ilike(f"%{localisation}%"))

    agriculteurs = query.order_by(Utilisateur.note_globale.desc()).all()
    result = []
    for u in agriculteurs:
        nb_produits = db.query(Produit).filter(
            Produit.agriculteur_id == u.id,
            Produit.est_disponible == True
        ).count()
        d = _user_public_dict(u)
        d["nb_produits"] = nb_produits
        result.append(d)
    return result


# ══════════════════════════════════════════════
# POSTS / FIL D'ACTUALITÉ
# ══════════════════════════════════════════════

@router.get("/feed")
def fil_actualite(
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    offset = (page - 1) * limit
    posts = (
        db.query(Post)
        .order_by(Post.date_publication.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_post_dict(p, user.id) for p in posts]


@router.post("/posts")
def creer_post(
    data: PostSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    if not data.contenu.strip():
        raise HTTPException(status_code=400, detail="Le contenu est requis")

    post = Post(
        contenu=data.contenu.strip(),
        photo=data.photo,
        auteur_id=user.id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"message": "Post publié !", "post": _post_dict(post, user.id)}


@router.delete("/posts/{post_id}")
def supprimer_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    post = db.query(Post).filter(Post.id == post_id, Post.auteur_id == user.id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post introuvable")
    db.delete(post)
    db.commit()
    return {"message": "Post supprimé"}


@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post introuvable")

    existing = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == user.id
    ).first()

    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(PostLike(post_id=post_id, user_id=user.id))
        liked = True

    db.commit()
    nb_likes = db.query(PostLike).filter(PostLike.post_id == post_id).count()
    return {"liked": liked, "nb_likes": nb_likes}


@router.get("/posts/{post_id}/commentaires")
def get_commentaires(post_id: int, db: Session = Depends(get_db)):
    commentaires = (
        db.query(PostCommentaire)
        .filter(PostCommentaire.post_id == post_id)
        .order_by(PostCommentaire.date_commentaire.asc())
        .all()
    )
    result = []
    for c in commentaires:
        auteur = db.query(Utilisateur).filter(Utilisateur.id == c.auteur_id).first()
        result.append({
            "id": c.id,
            "contenu": c.contenu,
            "date_commentaire": c.date_commentaire,
            "auteur_id": c.auteur_id,
            "auteur_nom": auteur.nom if auteur else "Anonyme",
            "auteur_photo": auteur.photo_profil if auteur else None,
        })
    return result


@router.post("/posts/{post_id}/commentaires")
def ajouter_commentaire(
    post_id: int,
    data: CommentaireSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post introuvable")

    commentaire = PostCommentaire(
        contenu=data.contenu.strip(),
        post_id=post_id,
        auteur_id=user.id,
    )
    db.add(commentaire)
    db.commit()
    db.refresh(commentaire)
    return {
        "id": commentaire.id,
        "contenu": commentaire.contenu,
        "date_commentaire": commentaire.date_commentaire,
        "auteur_id": user.id,
        "auteur_nom": user.nom,
        "auteur_photo": user.photo_profil,
    }


# ══════════════════════════════════════════════
# BOT ROUTES
# ══════════════════════════════════════════════

@router.post("/bot/chat")
def bot_chat(
    data: BotMessageSchema,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="Message vide")
    try:
        from app.bot import chat_avec_groq
        reponse = chat_avec_groq(data.message.strip(), user, db)
        return {"reponse": reponse or "Je n'ai pas pu générer de réponse.", "user": user.nom}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur AgrinovaBot: {str(e)}")


@router.get("/bot/historique")
def bot_historique(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    historique = (
        db.query(ConversationBot)
        .filter(ConversationBot.user_id == user.id)
        .order_by(ConversationBot.date_envoi.asc())
        .all()
    )
    return [
        {
            "id": h.id,
            "role": h.role,
            "contenu": h.contenu,
            "date_envoi": h.date_envoi,
        }
        for h in historique
    ]


@router.delete("/bot/reset")
def bot_reset(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(get_utilisateur_actuel)
):
    db.query(ConversationBot).filter(ConversationBot.user_id == user.id).delete()
    db.commit()
    return {"message": "Conversation réinitialisée."}
