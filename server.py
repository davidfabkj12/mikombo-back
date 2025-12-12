from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import bcrypt
import jwt
import shutil
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]


# Create the main app
app = FastAPI(title="Mikombo Park API")
app = FastAPI(title="Park Mikombo API")
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer(auto_error=False)

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# Upload directories
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
(UPLOADS_DIR / "produits").mkdir(exist_ok=True)
(UPLOADS_DIR / "animaux").mkdir(exist_ok=True)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# Enums
class UserRole(str, Enum):
    CLIENT = "client"
    ADMIN = "admin"

class ReservationStatus(str, Enum):
    EN_ATTENTE = "en_attente"
    CONFIRMEE = "confirmee"
    ANNULEE = "annulee"
    TERMINEE = "terminee"

class CommandeStatus(str, Enum):
    EN_ATTENTE = "en_attente"
    CONFIRMEE = "confirmee"
    EN_PREPARATION = "en_preparation"
    PRETE = "prete"
    LIVREE = "livree"
    RETIREE = "retiree"
    ANNULEE = "annulee"

class CultureStatus(str, Enum):
    EN_PREPARATION = "en_preparation"
    EN_PRODUCTION = "en_production"
    HORS_SAISON = "hors_saison"

# Models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    nom: str
    prenom: str
    telephone: str
    role: UserRole = UserRole.CLIENT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nom: str
    prenom: str
    telephone: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Produit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nom: str
    categorie: str
    description: str
    prix: float
    unite: str
    stock: float
    saison: bool = False
    photos: List[str] = []
    visible: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProduitCreate(BaseModel):
    nom: str
    categorie: str
    description: str
    prix: float
    unite: str
    stock: float
    saison: bool = False
    visible: bool = True

class Animal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    espece: str
    nom: str
    enclos: str
    etat_sante: str = "Bonne santé"
    photo: str = ""
    description: str = ""
    visible: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AnimalCreate(BaseModel):
    espece: str
    nom: str
    enclos: str
    etat_sante: str = "Bonne santé"
    description: str = ""
    visible: bool = True

class Culture(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type_culture: str
    surface: float
    periode_production: str
    statut: CultureStatus = CultureStatus.EN_PRODUCTION
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CultureCreate(BaseModel):
    type_culture: str
    surface: float
    periode_production: str
    statut: CultureStatus = CultureStatus.EN_PRODUCTION

class Reservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    user_email: str
    user_telephone: str
    date_visite: str
    heure_visite: str
    type_visite: str
    nb_adultes: int
    nb_enfants: int
    prix_total: float
    statut: ReservationStatus = ReservationStatus.EN_ATTENTE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReservationCreate(BaseModel):
    date_visite: str
    heure_visite: str
    type_visite: str
    nb_adultes: int
    nb_enfants: int

class CommandeItem(BaseModel):
    produit_id: str
    nom: str
    prix: float
    quantite: float
    unite: str

class Commande(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    user_email: str
    user_telephone: str
    items: List[CommandeItem]
    mode_retrait: str
    adresse_livraison: Optional[str] = ""
    statut: CommandeStatus = CommandeStatus.EN_ATTENTE
    total: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CommandeCreate(BaseModel):
    items: List[CommandeItem]
    mode_retrait: str
    adresse_livraison: Optional[str] = ""

class ContactMessage(BaseModel):
    nom: str
    email: EmailStr
    telephone: str
    message: str

# Email Service
class EmailService:
    def __init__(self):
        self.brevo_api_key = os.environ.get('BREVO_API_KEY', '')
        if self.brevo_api_key:
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key['api-key'] = self.brevo_api_key
            self.api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        else:
            self.api_instance = None
    
    def send_reservation_confirmation(self, reservation: Reservation):
        if not self.api_instance:
            logging.warning("Brevo API key not configured. Email not sent.")
            return
        
        try:
            sender = {"name": "Mikombo Park", "email": os.environ.get('SENDER_EMAIL', 'noreply@mikombopark.com')}
            to = [{"email": reservation.user_email, "name": reservation.user_name}]
            
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4e8d8;">
                        <h1 style="color: #6b5742; text-align: center;">Réservation Confirmée</h1>
                        <div style="background-color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                            <p>Bonjour {reservation.user_name},</p>
                            <p>Votre réservation au <strong>Mikombo Park</strong> a été confirmée !</p>
                            <h3 style="color: #8b9a7e;">Détails de votre réservation :</h3>
                            <ul>
                                <li><strong>Numéro :</strong> {reservation.id}</li>
                                <li><strong>Date :</strong> {reservation.date_visite}</li>
                                <li><strong>Heure :</strong> {reservation.heure_visite}</li>
                                <li><strong>Type de visite :</strong> {reservation.type_visite}</li>
                                <li><strong>Nombre d'adultes :</strong> {reservation.nb_adultes}</li>
                                <li><strong>Nombre d'enfants :</strong> {reservation.nb_enfants}</li>
                                <li><strong>Prix total :</strong> {reservation.prix_total} USD</li>
                            </ul>
                            <p style="color: #c17856;">Veuillez arriver au moins 15 minutes avant l'heure de votre visite.</p>
                            <p>À bientôt au Mikombo Park !</p>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=to,
                sender=sender,
                subject=f"Confirmation de réservation - Mikombo Park",
                html_content=html_content
            )
            
            self.api_instance.send_transac_email(send_smtp_email)
            logging.info(f"Reservation confirmation email sent to {reservation.user_email}")
        except ApiException as e:
            logging.error(f"Error sending email: {e}")
    
    def send_commande_confirmation(self, commande: Commande):
        if not self.api_instance:
            logging.warning("Brevo API key not configured. Email not sent.")
            return
        
        try:
            sender = {"name": "Mikombo Park", "email": os.environ.get('SENDER_EMAIL', 'noreply@mikombopark.com')}
            to = [{"email": commande.user_email, "name": commande.user_name}]
            
            items_html = "".join([f"<li>{item.nom} - {item.quantite} {item.unite} x {item.prix} USD = {item.prix * item.quantite} USD</li>" for item in commande.items])
            
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f4e8d8;">
                        <h1 style="color: #6b5742; text-align: center;">Commande Confirmée</h1>
                        <div style="background-color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                            <p>Bonjour {commande.user_name},</p>
                            <p>Merci pour votre commande de produits bio du <strong>Mikombo Park</strong> !</p>
                            <h3 style="color: #8b9a7e;">Détails de votre commande :</h3>
                            <p><strong>Numéro :</strong> {commande.id}</p>
                            <ul>{items_html}</ul>
                            <p style="font-size: 18px; font-weight: bold;"><strong>Total :</strong> {commande.total} USD</p>
                            <p><strong>Mode de retrait :</strong> {commande.mode_retrait}</p>
                            {f'<p><strong>Adresse de livraison :</strong> {commande.adresse_livraison}</p>' if commande.adresse_livraison else ''}
                            <p style="color: #c17856;">Nous vous contacterons dès que votre commande sera prête.</p>
                        </div>
                    </div>
                </body>
            </html>
            """
            
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=to,
                sender=sender,
                subject=f"Confirmation de commande - Mikombo Park",
                html_content=html_content
            )
            
            self.api_instance.send_transac_email(send_smtp_email)
            logging.info(f"Order confirmation email sent to {commande.user_email}")
        except ApiException as e:
            logging.error(f"Error sending email: {e}")

email_service = EmailService()

# Helper functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Non authentifié")
    
    token = credentials.credentials
    payload = verify_token(token)
    
    user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
    
    return User(**user)

async def get_admin_user(user: User = Depends(get_current_user)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Accès refusé")
    return user

# Auth Routes
@api_router.post("/auth/register")
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    
    user = User(
        email=user_data.email,
        nom=user_data.nom,
        prenom=user_data.prenom,
        telephone=user_data.telephone,
        role=UserRole.CLIENT
    )
    
    doc = user.model_dump()
    doc['password_hash'] = hash_password(user_data.password)
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.users.insert_one(doc)
    
    token = create_token(user.id, user.role)
    return {"user": user, "token": token}

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user_doc = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    if not verify_password(credentials.password, user_doc['password_hash']):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    user = User(**{k: v for k, v in user_doc.items() if k != 'password_hash'})
    token = create_token(user.id, user.role)
    return {"user": user, "token": token}

@api_router.get("/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    return user

# Public Routes
@api_router.get("/produits", response_model=List[Produit])
async def get_produits(categorie: Optional[str] = None):
    query = {"visible": True}
    if categorie:
        query["categorie"] = categorie
    
    produits = await db.produits.find(query, {"_id": 0}).to_list(1000)
    for p in produits:
        if isinstance(p.get('created_at'), str):
            p['created_at'] = datetime.fromisoformat(p['created_at'])
    return produits

@api_router.get("/produits/{produit_id}", response_model=Produit)
async def get_produit(produit_id: str):
    produit = await db.produits.find_one({"id": produit_id}, {"_id": 0})
    if not produit:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    if isinstance(produit.get('created_at'), str):
        produit['created_at'] = datetime.fromisoformat(produit['created_at'])
    return Produit(**produit)

@api_router.get("/animaux", response_model=List[Animal])
async def get_animaux():
    animaux = await db.animaux.find({"visible": True}, {"_id": 0}).to_list(1000)
    for a in animaux:
        if isinstance(a.get('created_at'), str):
            a['created_at'] = datetime.fromisoformat(a['created_at'])
    return animaux

@api_router.post("/contact")
async def contact(message: ContactMessage):
    doc = message.model_dump()
    doc['created_at'] = datetime.now(timezone.utc).isoformat()
    await db.messages.insert_one(doc)
    return {"success": True, "message": "Message envoyé avec succès"}

# Client Routes
@api_router.post("/reservations", response_model=Reservation)
async def create_reservation(reservation_data: ReservationCreate, background_tasks: BackgroundTasks, user: User = Depends(get_current_user)):
        # Calculate prix
    prix_adulte = 10.0
    prix_enfant = 5.0
    prix_total = (reservation_data.nb_adultes * prix_adulte) + (reservation_data.nb_enfants * prix_enfant)
    
    reservation = Reservation(
        user_id=user.id,
        user_name=f"{user.prenom} {user.nom}",
        user_email=user.email,
        user_telephone=user.telephone,
        date_visite=reservation_data.date_visite,
        heure_visite=reservation_data.heure_visite,
        type_visite=reservation_data.type_visite,
        nb_adultes=reservation_data.nb_adultes,
        nb_enfants=reservation_data.nb_enfants,
        prix_total=prix_total,
        statut=ReservationStatus.CONFIRMEE
    )
    
    doc = reservation.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.reservations.insert_one(doc)
    
    # Send email in background
    background_tasks.add_task(email_service.send_reservation_confirmation, reservation)
    
    return reservation

@api_router.get("/reservations/mes-reservations", response_model=List[Reservation])
async def get_my_reservations(user: User = Depends(get_current_user)):
    reservations = await db.reservations.find({"user_id": user.id}, {"_id": 0}).to_list(1000)
    for r in reservations:
        if isinstance(r.get('created_at'), str):
            r['created_at'] = datetime.fromisoformat(r['created_at'])
    return reservations

@api_router.post("/commandes", response_model=Commande)
async def create_commande(commande_data: CommandeCreate, background_tasks: BackgroundTasks, user: User = Depends(get_current_user)):
    # Calculate total
    total = sum(item.prix * item.quantite for item in commande_data.items)
    
    commande = Commande(
        user_id=user.id,
        user_name=f"{user.prenom} {user.nom}",
        user_email=user.email,
        user_telephone=user.telephone,
        items=commande_data.items,
        mode_retrait=commande_data.mode_retrait,
        adresse_livraison=commande_data.adresse_livraison,
        statut=CommandeStatus.CONFIRMEE,
        total=total
    )
    
    doc = commande.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.commandes.insert_one(doc)
    
    # Send email in background
    background_tasks.add_task(email_service.send_commande_confirmation, commande)
    
    return commande

@api_router.get("/commandes/mes-commandes", response_model=List[Commande])
async def get_my_commandes(user: User = Depends(get_current_user)):
    commandes = await db.commandes.find({"user_id": user.id}, {"_id": 0}).to_list(1000)
    for c in commandes:
        if isinstance(c.get('created_at'), str):
            c['created_at'] = datetime.fromisoformat(c['created_at'])
        if isinstance(c.get('updated_at'), str):
            c['updated_at'] = datetime.fromisoformat(c['updated_at'])
    return commandes

# Admin Routes - Produits
@api_router.get("/admin/produits", response_model=List[Produit])
async def admin_get_produits(authorization: str = None):
    produits = await db.produits.find({}, {"_id": 0}).to_list(1000)
    for p in produits:
        if isinstance(p.get('created_at'), str):
            p['created_at'] = datetime.fromisoformat(p['created_at'])
    return produits

@api_router.post("/admin/produits", response_model=Produit)
async def admin_create_produit(produit_data: ProduitCreate, user: User = Depends(get_admin_user)):
    produit = Produit(**produit_data.model_dump())
    doc = produit.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.produits.insert_one(doc)
    return produit

@api_router.put("/admin/produits/{produit_id}", response_model=Produit)
async def admin_update_produit(produit_id: str, produit_data: ProduitCreate, user: User = Depends(get_admin_user)):
    existing = await db.produits.find_one({"id": produit_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    
    updated_data = produit_data.model_dump()
    await db.produits.update_one({"id": produit_id}, {"$set": updated_data})
    
    updated_produit = await db.produits.find_one({"id": produit_id}, {"_id": 0})
    if isinstance(updated_produit.get('created_at'), str):
        updated_produit['created_at'] = datetime.fromisoformat(updated_produit['created_at'])
    return Produit(**updated_produit)

@api_router.delete("/admin/produits/{produit_id}")
async def admin_delete_produit(produit_id: str, user: User = Depends(get_admin_user)):
    result = await db.produits.delete_one({"id": produit_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    return {"success": True}

@api_router.post("/admin/produits/{produit_id}/upload-photo")
async def upload_produit_photo(produit_id: str, file: UploadFile = File(...), user: User = Depends(get_admin_user)):
    produit = await db.produits.find_one({"id": produit_id}, {"_id": 0})
    if not produit:
        raise HTTPException(status_code=404, detail="Produit non trouvé")
    
    file_ext = file.filename.split('.')[-1]
    file_name = f"{uuid.uuid4()}.{file_ext}"
    file_path = UPLOADS_DIR / "produits" / file_name
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    photo_url = f"/uploads/produits/{file_name}"
    photos = produit.get('photos', [])
    photos.append(photo_url)
    
    await db.produits.update_one({"id": produit_id}, {"$set": {"photos": photos}})
    
    return {"photo_url": photo_url}

# Admin Routes - Animaux
@api_router.get("/admin/animaux", response_model=List[Animal])
async def admin_get_animaux(authorization: str = None):
    animaux = await db.animaux.find({}, {"_id": 0}).to_list(1000)
    for a in animaux:
        if isinstance(a.get('created_at'), str):
            a['created_at'] = datetime.fromisoformat(a['created_at'])
    return animaux

@api_router.post("/admin/animaux", response_model=Animal)
async def admin_create_animal(animal_data: AnimalCreate, user: User = Depends(get_admin_user)):
    animal = Animal(**animal_data.model_dump())
    doc = animal.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.animaux.insert_one(doc)
    return animal

@api_router.put("/admin/animaux/{animal_id}", response_model=Animal)
async def admin_update_animal(animal_id: str, animal_data: AnimalCreate, user: User = Depends(get_admin_user)):
    existing = await db.animaux.find_one({"id": animal_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Animal non trouvé")
    
    updated_data = animal_data.model_dump()
    await db.animaux.update_one({"id": animal_id}, {"$set": updated_data})
    
    updated_animal = await db.animaux.find_one({"id": animal_id}, {"_id": 0})
    if isinstance(updated_animal.get('created_at'), str):
        updated_animal['created_at'] = datetime.fromisoformat(updated_animal['created_at'])
    return Animal(**updated_animal)

@api_router.delete("/admin/animaux/{animal_id}")
async def admin_delete_animal(animal_id: str, user: User = Depends(get_admin_user)):
    result = await db.animaux.delete_one({"id": animal_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Animal non trouvé")
    return {"success": True}

@api_router.post("/admin/animaux/{animal_id}/upload-photo")
async def upload_animal_photo(animal_id: str, file: UploadFile = File(...), user: User = Depends(get_admin_user)):
    animal = await db.animaux.find_one({"id": animal_id}, {"_id": 0})
    if not animal:
        raise HTTPException(status_code=404, detail="Animal non trouvé")
    
    file_ext = file.filename.split('.')[-1]
    file_name = f"{uuid.uuid4()}.{file_ext}"
    file_path = UPLOADS_DIR / "animaux" / file_name
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    photo_url = f"/uploads/animaux/{file_name}"
    await db.animaux.update_one({"id": animal_id}, {"$set": {"photo": photo_url}})
    
    return {"photo_url": photo_url}

# Admin Routes - Cultures
@api_router.get("/admin/cultures", response_model=List[Culture])
async def admin_get_cultures(authorization: str = None):
    cultures = await db.cultures.find({}, {"_id": 0}).to_list(1000)
    for c in cultures:
        if isinstance(c.get('created_at'), str):
            c['created_at'] = datetime.fromisoformat(c['created_at'])
    return cultures

@api_router.post("/admin/cultures", response_model=Culture)
async def admin_create_culture(culture_data: CultureCreate, user: User = Depends(get_admin_user)):
    culture = Culture(**culture_data.model_dump())
    doc = culture.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.cultures.insert_one(doc)
    return culture

@api_router.put("/admin/cultures/{culture_id}", response_model=Culture)
async def admin_update_culture(culture_id: str, culture_data: CultureCreate, user: User = Depends(get_admin_user)):
    existing = await db.cultures.find_one({"id": culture_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Culture non trouvée")
    
    updated_data = culture_data.model_dump()
    await db.cultures.update_one({"id": culture_id}, {"$set": updated_data})
    
    updated_culture = await db.cultures.find_one({"id": culture_id}, {"_id": 0})
    if isinstance(updated_culture.get('created_at'), str):
        updated_culture['created_at'] = datetime.fromisoformat(updated_culture['created_at'])
    return Culture(**updated_culture)

@api_router.delete("/admin/cultures/{culture_id}")
async def admin_delete_culture(culture_id: str, user: User = Depends(get_admin_user)):
    result = await db.cultures.delete_one({"id": culture_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Culture non trouvée")
    return {"success": True}

# Admin Routes - Reservations
@api_router.get("/admin/reservations", response_model=List[Reservation])
async def admin_get_reservations(authorization: str = None):
    reservations = await db.reservations.find({}, {"_id": 0}).to_list(1000)
    for r in reservations:
        if isinstance(r.get('created_at'), str):
            r['created_at'] = datetime.fromisoformat(r['created_at'])
    return reservations

@api_router.put("/admin/reservations/{reservation_id}/statut")
async def admin_update_reservation_status(reservation_id: str, statut: ReservationStatus, user: User = Depends(get_admin_user)):
    result = await db.reservations.update_one({"id": reservation_id}, {"$set": {"statut": statut}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Réservation non trouvée")
    return {"success": True}

# Admin Routes - Commandes
@api_router.get("/admin/commandes", response_model=List[Commande])
async def admin_get_commandes(authorization: str = None):
    commandes = await db.commandes.find({}, {"_id": 0}).to_list(1000)
    for c in commandes:
        if isinstance(c.get('created_at'), str):
            c['created_at'] = datetime.fromisoformat(c['created_at'])
        if isinstance(c.get('updated_at'), str):
            c['updated_at'] = datetime.fromisoformat(c['updated_at'])
    return commandes

@api_router.put("/admin/commandes/{commande_id}/statut")
async def admin_update_commande_status(commande_id: str, statut: CommandeStatus, user: User = Depends(get_admin_user)):
    updated_at = datetime.now(timezone.utc).isoformat()
    result = await db.commandes.update_one({"id": commande_id}, {"$set": {"statut": statut, "updated_at": updated_at}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commande non trouvée")
    return {"success": True}

# Admin Dashboard Stats
@api_router.get("/admin/stats")
async def admin_get_stats(authorization: str = None):
    total_produits = await db.produits.count_documents({})
    total_animaux = await db.animaux.count_documents({})
    total_cultures = await db.cultures.count_documents({})
    total_reservations = await db.reservations.count_documents({})
    total_commandes = await db.commandes.count_documents({})
    
    reservations_today = await db.reservations.count_documents({
        "date_visite": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    })
    
    return {
        "total_produits": total_produits,
        "total_animaux": total_animaux,
        "total_cultures": total_cultures,
        "total_reservations": total_reservations,
        "total_commandes": total_commandes,
        "reservations_today": reservations_today
    }

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()